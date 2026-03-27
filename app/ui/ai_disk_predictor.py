"""Task 3 — Predictive disk space warnings with growth log."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.ollama_client import check_available, query, extract_json

log = logging.getLogger(__name__)

_GROWTH_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "disk_growth"

_SYSTEM_PROMPT = (
    "You are a disk space analyst. Here is the disk usage history for "
    "a VM named {vm_name}: {growth_json}. Each entry has a timestamp "
    "and size in bytes. Predict when the disk will be full given the "
    "VM's maximum disk size of {max_gb}GB. Respond with JSON only: "
    '{"days_until_full": number or null, "growth_rate_mb_per_day": '
    'number, "warning_level": "none|low|medium|high", "message": '
    '"one sentence summary"}. Set days_until_full to null if growth '
    "is too irregular to predict."
)


def record_disk_size(vm_id: str, size_bytes: int) -> None:
    _GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "size_bytes": size_bytes,
    }
    with open(_GROWTH_DIR / f"{vm_id}.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_growth_log(vm_id: str) -> list[dict]:
    p = _GROWTH_DIR / f"{vm_id}.jsonl"
    if not p.exists():
        return []
    entries = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _fallback_predict(entries: list[dict], max_bytes: int) -> dict:
    """Simple linear extrapolation without AI."""
    if len(entries) < 2:
        return {"days_until_full": None, "growth_rate_mb_per_day": 0,
                "warning_level": "none", "message": "Not enough data for prediction."}
    first = entries[0]
    last = entries[-1]
    try:
        t0 = datetime.fromisoformat(first["timestamp"])
        t1 = datetime.fromisoformat(last["timestamp"])
        days = max((t1 - t0).total_seconds() / 86400, 0.01)
        growth = last["size_bytes"] - first["size_bytes"]
        rate_per_day = growth / days
        rate_mb = rate_per_day / (1024 * 1024)
        if rate_per_day <= 0:
            return {"days_until_full": None, "growth_rate_mb_per_day": round(rate_mb, 1),
                    "warning_level": "none", "message": "Disk is not growing."}
        remaining = max_bytes - last["size_bytes"]
        if remaining <= 0:
            return {"days_until_full": 0, "growth_rate_mb_per_day": round(rate_mb, 1),
                    "warning_level": "high", "message": "Disk is full."}
        days_left = remaining / rate_per_day
        if days_left < 7:
            level = "high"
        elif days_left < 30:
            level = "medium"
        else:
            level = "low"
        return {
            "days_until_full": round(days_left, 1),
            "growth_rate_mb_per_day": round(rate_mb, 1),
            "warning_level": level,
            "message": f"At current rate, disk full in ~{int(days_left)} days.",
        }
    except (KeyError, ValueError, TypeError):
        return {"days_until_full": None, "growth_rate_mb_per_day": 0,
                "warning_level": "none", "message": "Could not parse growth data."}


class _Signals(QObject):
    prediction = Signal(str, dict)  # vm_id, result dict


class DiskPredictor:
    """Call predict() after VM start to get async disk warnings."""

    def __init__(self):
        self._sigs = _Signals()
        self.prediction = self._sigs.prediction

    def predict(self, vm_id: str, vm_name: str, disk_path: str, max_gb: float = 100):
        entries = load_growth_log(vm_id)
        if len(entries) < 3:
            result = _fallback_predict(entries, int(max_gb * 1024**3))
            self._sigs.prediction.emit(vm_id, result)
            return

        if not check_available():
            result = _fallback_predict(entries, int(max_gb * 1024**3))
            self._sigs.prediction.emit(vm_id, result)
            return

        threading.Thread(
            target=self._worker,
            args=(vm_id, vm_name, entries, max_gb),
            daemon=True,
        ).start()

    def _worker(self, vm_id, vm_name, entries, max_gb):
        try:
            system = _SYSTEM_PROMPT.replace(
                "{vm_name}", vm_name
            ).replace(
                "{growth_json}", json.dumps(entries[-30:])
            ).replace(
                "{max_gb}", str(max_gb)
            )
            raw = query("Analyze disk growth.", system=system, timeout=30)
            parsed = extract_json(raw)
            if parsed and "warning_level" in parsed:
                self._sigs.prediction.emit(vm_id, parsed)
            else:
                fb = _fallback_predict(entries, int(max_gb * 1024**3))
                self._sigs.prediction.emit(vm_id, fb)
        except Exception:
            fb = _fallback_predict(entries, int(max_gb * 1024**3))
            self._sigs.prediction.emit(vm_id, fb)
