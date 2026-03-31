"""Task 5 — VM replication manager with background transfers."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import app.audit_log as audit

log = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent / "data"
_REPL_CFG = _DATA / "replication.json"
_SMTP_CFG = _DATA / "smtp_config.json"

# ── Config ─────────────────────────────────────────────────────────────

def load_repl_config() -> dict:
    if _REPL_CFG.exists():
        try:
            return json.loads(_REPL_CFG.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"targets": [], "policies": {}}


def save_repl_config(cfg: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _REPL_CFG.write_text(json.dumps(cfg, indent=2))


def load_smtp_config() -> dict:
    if _SMTP_CFG.exists():
        try:
            return json.loads(_SMTP_CFG.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"host": "", "port": 587, "username": "", "password": "",
            "from_addr": "", "to_addr": "", "enabled": False}


def save_smtp_config(cfg: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _SMTP_CFG.write_text(json.dumps(cfg, indent=2))


# ── Replication ────────────────────────────────────────────────────────

class ReplicationJob:
    def __init__(self, vm_name: str, vm_id: str, disk_path: str,
                 target_path: str, target_type: str = "local"):
        self.vm_name = vm_name
        self.vm_id = vm_id
        self.disk_path = disk_path
        self.target_path = target_path
        self.target_type = target_type
        self.status = "pending"
        self.progress = ""
        self.error = ""

    def run(self) -> bool:
        self.status = "replicating"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{self.vm_name}_{ts}.qcow2"
        try:
            if self.target_type == "local":
                dest_dir = Path(self.target_path)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = str(dest_dir / fname)
                self.progress = f"Compressing to {dest}..."
                subprocess.run(
                    ["qemu-img", "convert", "-c", "-O", "qcow2",
                     self.disk_path, dest],
                    check=True, capture_output=True, timeout=1200)
            else:
                # rsync
                tmp = f"/tmp/icosele-vm-repl/{fname}"
                Path("/tmp/icosele-vm-repl").mkdir(parents=True, exist_ok=True)
                self.progress = "Compressing..."
                subprocess.run(
                    ["qemu-img", "convert", "-c", "-O", "qcow2",
                     self.disk_path, tmp],
                    check=True, capture_output=True, timeout=1200)
                self.progress = f"Syncing to {self.target_path}..."
                subprocess.run(
                    ["rsync", "-avz", tmp, self.target_path],
                    check=True, capture_output=True, timeout=600)
            self.status = "complete"
            audit.record("replication_complete", self.vm_id, self.vm_name,
                         {"target": self.target_path})
            return True
        except Exception as exc:
            self.status = "failed"
            self.error = str(exc)
            audit.record("replication_failed", self.vm_id, self.vm_name,
                         {"target": self.target_path, "error": str(exc)})
            _send_failure_email(self.vm_name, str(exc))
            return False


def _send_failure_email(vm_name: str, error: str) -> None:
    cfg = load_smtp_config()
    if not cfg.get("enabled") or not cfg.get("host"):
        return
    try:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = f"Icosele VM: Replication failed for {vm_name}"
        msg["From"] = cfg["from_addr"]
        msg["To"] = cfg["to_addr"]
        msg.set_content(f"Replication failed for VM '{vm_name}'.\nError: {error}")
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as s:
            if cfg.get("username"):
                s.starttls()
                s.login(cfg["username"], cfg["password"])
            s.send_message(msg)
    except Exception as exc:
        log.warning("Failed to send replication failure email: %s", exc)


def replicate_async(job: ReplicationJob) -> threading.Thread:
    t = threading.Thread(target=job.run, daemon=True)
    t.start()
    return t
