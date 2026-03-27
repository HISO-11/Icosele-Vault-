"""Task 2 — USB hot-plug detection via sysfs polling (stdlib only)."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

_USB_BASE = Path("/sys/bus/usb/devices")


def _read(path: Path, attr: str) -> str:
    try:
        return (path / attr).read_text().strip()
    except (OSError, ValueError):
        return ""


def _scan_usb_ids() -> dict[str, dict]:
    """Return {busnum-devnum: {vid, pid, name, bus, addr}} for all non-hub devices."""
    if not _USB_BASE.exists():
        return {}
    result = {}
    for entry in _USB_BASE.iterdir():
        if ":" in entry.name:
            continue
        vid = _read(entry, "idVendor")
        pid = _read(entry, "idProduct")
        if not vid or not pid:
            continue
        if _read(entry, "bDeviceClass") == "09":
            continue
        bn = _read(entry, "busnum")
        dn = _read(entry, "devnum")
        if not bn or not dn:
            continue
        key = f"{bn}-{dn}"
        result[key] = {
            "vendor_id": vid,
            "product_id": pid,
            "device_name": _read(entry, "product") or _read(entry, "manufacturer") or f"{vid}:{pid}",
            "bus": bn,
            "addr": dn,
        }
    return result


class USBHotplugMonitor(QObject):
    """Polls sysfs every 2 seconds; emits device_connected for new devices."""
    device_connected = Signal(dict)  # {vendor_id, product_id, device_name, bus, addr}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._known: set[str] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._first = True

    def start(self):
        self._known = set(_scan_usb_ids().keys())
        self._first = False
        self._timer.start(2000)

    def stop(self):
        self._timer.stop()

    def _poll(self):
        current = _scan_usb_ids()
        current_keys = set(current.keys())
        new_keys = current_keys - self._known
        self._known = current_keys
        if self._first:
            self._first = False
            return
        for k in new_keys:
            dev = current[k]
            log.info("USB hot-plug detected: %s (%s:%s)",
                     dev["device_name"], dev["vendor_id"], dev["product_id"])
            self.device_connected.emit(dev)
