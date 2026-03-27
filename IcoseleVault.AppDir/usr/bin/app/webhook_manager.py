"""Task 1 — Webhook system: store, dispatch, retry, log deliveries."""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_WEBHOOKS_PATH = Path(__file__).resolve().parent.parent / "data" / "webhooks.json"
_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "webhook_log.jsonl"
_MAX_LOG = 50
_MAX_RETRIES = 3
_RETRY_DELAY = 5


def load_webhooks() -> list[dict]:
    if _WEBHOOKS_PATH.exists():
        try:
            data = json.loads(_WEBHOOKS_PATH.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_webhooks(hooks: list[dict]) -> None:
    _WEBHOOKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WEBHOOKS_PATH.write_text(json.dumps(hooks, indent=2))


def load_delivery_log() -> list[dict]:
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
    return entries[-_MAX_LOG:]


def _append_log(entry: dict) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    # Trim to last MAX_LOG entries periodically
    try:
        lines = _LOG_PATH.read_text().splitlines()
        if len(lines) > _MAX_LOG * 2:
            _LOG_PATH.write_text("\n".join(lines[-_MAX_LOG:]) + "\n")
    except OSError:
        pass


def _send(url: str, payload: dict) -> tuple[int, bool]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "IcoseleVault/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, True
    except urllib.error.HTTPError as e:
        return e.code, False
    except Exception:
        return 0, False


def dispatch(event: str, vm_id: str = "", vm_name: str = "",
             details: dict | None = None) -> None:
    """Fire webhooks for an event in a background thread."""
    hooks = load_webhooks()
    payload = {
        "event": event,
        "vm_name": vm_name,
        "vm_id": vm_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }
    for hook in hooks:
        if not hook.get("enabled", True):
            continue
        events = hook.get("events", [])
        if event not in events:
            continue
        url = hook.get("url", "")
        if not url:
            continue
        threading.Thread(
            target=_deliver, args=(url, hook.get("name", ""), event, payload),
            daemon=True).start()


def _deliver(url: str, name: str, event: str, payload: dict) -> None:
    for attempt in range(_MAX_RETRIES):
        status, ok = _send(url, payload)
        _append_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "webhook_name": name,
            "event": event,
            "url": url,
            "status_code": status,
            "success": ok,
            "attempt": attempt + 1,
        })
        if ok:
            return
        if attempt < _MAX_RETRIES - 1:
            time.sleep(_RETRY_DELAY)


def send_test(url: str, name: str = "test") -> tuple[int, bool]:
    """Synchronous test ping."""
    payload = {
        "event": "test_ping",
        "vm_name": "",
        "vm_id": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": {"message": "Test webhook from Icosele Vault"},
    }
    status, ok = _send(url, payload)
    _append_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_name": name,
        "event": "test_ping",
        "url": url,
        "status_code": status,
        "success": ok,
        "attempt": 1,
    })
    return status, ok
