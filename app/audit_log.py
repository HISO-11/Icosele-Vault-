"""Immutable append-only audit log for VM management actions."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "audit_log.jsonl"


def _user() -> str:
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USER", "unknown")


def record(action: str, vm_id: str = "", vm_name: str = "",
           details: dict | None = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "vm_id": vm_id,
        "vm_name": vm_name,
        "user": _user(),
        "details": details or {},
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_entries() -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    entries = []
    for line in _LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def export_csv(path: str) -> None:
    entries = load_entries()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Timestamp", "Action", "VM ID", "VM Name", "User", "Details"])
        for e in entries:
            w.writerow([
                e.get("timestamp", ""),
                e.get("action", ""),
                e.get("vm_id", ""),
                e.get("vm_name", ""),
                e.get("user", ""),
                json.dumps(e.get("details", {})),
            ])
