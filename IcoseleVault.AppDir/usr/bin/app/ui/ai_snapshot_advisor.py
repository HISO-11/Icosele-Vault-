"""Task 4 — Smart auto-snapshots advisor."""
from __future__ import annotations

import json
import logging
import subprocess
import threading
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal

from app.ollama_client import check_available, query, extract_json
from app.snapshot_store import add_snapshot, load_snapshots

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a snapshot advisor for a VM named {vm_name}. Here is "
    "the session summary: duration {duration} minutes, disk growth "
    "{disk_growth_mb}MB, manual snapshots taken {manual_count}, "
    "crashes this session {crash_count}, last snapshot was "
    "{hours_since_snapshot} hours ago. Should an automatic snapshot "
    "be taken now? Respond with JSON only: "
    '{"take_snapshot": true|false, "reason": "one sentence", '
    '"suggested_tag": "short tag string"}.'
)


class _Signals(QObject):
    snapshot_taken = Signal(str, str, str)  # vm_id, tag, reason
    snapshot_suggested = Signal(str, str, str)  # vm_id, tag, reason


class SnapshotAdvisor:
    """Call evaluate_session() when a VM stops to get snapshot advice."""

    def __init__(self):
        self._sigs = _Signals()
        self.snapshot_taken = self._sigs.snapshot_taken
        self.snapshot_suggested = self._sigs.snapshot_suggested

    def evaluate_session(self, vm_id: str, vm_name: str, disk_path: str,
                         duration_min: float, disk_growth_mb: float,
                         manual_count: int, crash_count: int):
        snaps = load_snapshots(vm_id)
        hours_since = 999
        if snaps:
            try:
                last_ts = snaps[-1].get("created_at", "")
                last = datetime.fromisoformat(last_ts)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        if not check_available():
            self._fallback(vm_id, vm_name, disk_path, disk_growth_mb, hours_since)
            return

        threading.Thread(
            target=self._worker,
            args=(vm_id, vm_name, disk_path, duration_min,
                  disk_growth_mb, manual_count, crash_count, hours_since),
            daemon=True,
        ).start()

    def _fallback(self, vm_id, vm_name, disk_path, disk_growth_mb, hours_since):
        """Rule-based: snapshot if >1GB growth or >24h since last."""
        if disk_growth_mb > 1024 or hours_since > 24:
            tag = f"auto-{datetime.now().strftime('%Y%m%d-%H%M')}"
            reason = ("Disk grew >1GB" if disk_growth_mb > 1024
                      else "Over 24h since last snapshot")
            self._take_snapshot(vm_id, vm_name, disk_path, tag, reason)

    def _worker(self, vm_id, vm_name, disk_path, duration_min,
                disk_growth_mb, manual_count, crash_count, hours_since):
        try:
            system = _SYSTEM_PROMPT.replace(
                "{vm_name}", vm_name
            ).replace("{duration}", str(int(duration_min))
            ).replace("{disk_growth_mb}", str(int(disk_growth_mb))
            ).replace("{manual_count}", str(manual_count)
            ).replace("{crash_count}", str(crash_count)
            ).replace("{hours_since_snapshot}", str(int(hours_since)))
            raw = query("Should I take a snapshot?", system=system, timeout=20)
            parsed = extract_json(raw)
            if parsed and parsed.get("take_snapshot"):
                tag = parsed.get("suggested_tag", "ai-auto")
                reason = parsed.get("reason", "AI recommended")
                self._take_snapshot(vm_id, vm_name, disk_path, tag, reason)
            elif parsed:
                log.info("Snapshot advisor: no snapshot needed for %s", vm_name)
        except Exception:
            self._fallback(vm_id, vm_name, disk_path,
                           disk_growth_mb, hours_since)

    def _take_snapshot(self, vm_id, vm_name, disk_path, tag, reason):
        try:
            subprocess.run(
                ["qemu-img", "snapshot", "-c", tag, disk_path],
                check=True, capture_output=True, timeout=30)
            add_snapshot(vm_id, tag, tag=tag, branch_name="auto")
            import app.audit_log as audit
            audit.record("snapshot_create", vm_id, vm_name,
                         {"tag": tag, "reason": f"AI recommended: {reason}"})
            self._sigs.snapshot_taken.emit(vm_id, tag, reason)
        except Exception as exc:
            log.warning("Auto-snapshot failed for %s: %s", vm_name, exc)
