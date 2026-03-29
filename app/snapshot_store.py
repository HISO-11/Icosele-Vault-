"""Snapshot metadata store — persists branching/tagging data alongside QEMU snapshots."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "vms"


def _snap_path(vm_id: str) -> Path:
    return DATA_DIR / f"{vm_id}_snapshots.json"


def _sync_cfg_path() -> Path:
    return DATA_DIR.parent / "sync_config.json"


# ── snapshot CRUD ──────────────────────────────────────────────────────

def load_snapshots(vm_id: str) -> list[dict]:
    p = _snap_path(vm_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_snapshots(vm_id: str, snaps: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _snap_path(vm_id).write_text(json.dumps(snaps, indent=2))


def add_snapshot(
    vm_id: str,
    name: str,
    tag: str = "",
    parent_id: str | None = None,
    branch_name: str = "main",
    ram_size_mb: float = 0,
    disk_size_mb: float = 0,
) -> dict:
    snaps = load_snapshots(vm_id)
    # Auto-assign parent to the last snapshot on the same branch if not given
    if parent_id is None:
        for s in reversed(snaps):
            if s.get("branch_name", "main") == branch_name:
                parent_id = s["id"]
                break
    entry = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "tag": tag,
        "parent_id": parent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ram_size_mb": ram_size_mb,
        "disk_size_mb": disk_size_mb,
        "branch_name": branch_name,
    }
    snaps.append(entry)
    save_snapshots(vm_id, snaps)
    return entry


def delete_snapshot(vm_id: str, snap_id: str) -> None:
    snaps = load_snapshots(vm_id)
    # Re-parent children of the deleted snap to its parent
    target = None
    for s in snaps:
        if s["id"] == snap_id:
            target = s
            break
    if target:
        parent = target.get("parent_id")
        for s in snaps:
            if s.get("parent_id") == snap_id:
                s["parent_id"] = parent
    snaps = [s for s in snaps if s["id"] != snap_id]
    save_snapshots(vm_id, snaps)


def update_snapshot(vm_id: str, snap_id: str, **fields) -> None:
    snaps = load_snapshots(vm_id)
    for s in snaps:
        if s["id"] == snap_id:
            s.update(fields)
            break
    save_snapshots(vm_id, snaps)


def get_branches(vm_id: str) -> list[str]:
    seen: set[str] = set()
    for s in load_snapshots(vm_id):
        seen.add(s.get("branch_name", "main"))
    if not seen:
        seen.add("main")
    return sorted(seen)


def get_snap_by_id(vm_id: str, snap_id: str) -> dict | None:
    for s in load_snapshots(vm_id):
        if s["id"] == snap_id:
            return s
    return None


def copy_snapshots(src_vm_id: str, dst_vm_id: str) -> None:
    snaps = load_snapshots(src_vm_id)
    save_snapshots(dst_vm_id, snaps)


# ── sync config ────────────────────────────────────────────────────────

_SYNC_DEFAULTS = {
    "mode": "local",
    "local_path": "",
    "rsync_host": "",
    "rsync_path": "",
    "rsync_user": "",
    "auto_sync": False,
    "last_sync": "",
}


def load_sync_config() -> dict:
    p = _sync_cfg_path()
    if not p.exists():
        return dict(_SYNC_DEFAULTS)
    try:
        cfg = json.loads(p.read_text())
        merged = dict(_SYNC_DEFAULTS)
        merged.update(cfg)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(_SYNC_DEFAULTS)


def save_sync_config(cfg: dict) -> None:
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    _sync_cfg_path().write_text(json.dumps(cfg, indent=2))
