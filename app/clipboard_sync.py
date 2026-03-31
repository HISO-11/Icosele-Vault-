"""Clipboard synchronisation between host and VM via QEMU Guest Agent socket."""
from __future__ import annotations

import json
import logging
import socket

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)


class ClipboardSync:
    """Polls the host clipboard every 500ms and sends changes to the VM guest agent."""

    def __init__(self, vm_name: str) -> None:
        self.vm_name = vm_name
        self.socket_path = f"/tmp/qga_{vm_name}.sock"
        self._timer = QTimer()
        self._timer.timeout.connect(self._sync)
        self._last_clipboard = ""

    def start(self) -> None:
        self._last_clipboard = ""
        self._timer.start(500)
        log.info("Clipboard sync started for VM %s", self.vm_name)

    def stop(self) -> None:
        self._timer.stop()
        log.info("Clipboard sync stopped for VM %s", self.vm_name)

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    def _sync(self) -> None:
        try:
            clipboard = QApplication.clipboard()
            if clipboard is None:
                return
            text = clipboard.text()
            if text and text != self._last_clipboard:
                self._send_to_guest(text)
                self._last_clipboard = text
        except Exception:
            pass

    def _send_to_guest(self, text: str) -> None:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(self.socket_path)
            cmd = json.dumps({
                "execute": "guest-clipboard-set",
                "arguments": {"protocol": "text", "data": text[:4096]},
            })
            sock.sendall(cmd.encode() + b"\n")
            sock.close()
        except (OSError, socket.timeout):
            pass  # Guest agent not available — ignore silently
