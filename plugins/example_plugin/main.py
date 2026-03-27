"""Example plugin — logs VM events to a text file."""
from datetime import datetime
from pathlib import Path

_LOG = Path(__file__).parent / "events.log"


def _log(msg: str) -> None:
    with open(_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def on_vm_start(vm_id: str = "", vm_name: str = "", **kw) -> None:
    _log(f"VM started: {vm_name} ({vm_id})")


def on_vm_stop(vm_id: str = "", vm_name: str = "", **kw) -> None:
    _log(f"VM stopped: {vm_name} ({vm_id})")


def on_snapshot_created(vm_id: str = "", snapshot_name: str = "", **kw) -> None:
    _log(f"Snapshot created: {snapshot_name} for VM {vm_id}")
