"""Task 2 — VM handoff: transfer running VM to another machine."""
from __future__ import annotations

import json
import logging
import os
import socket
import struct
import subprocess
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

import app.audit_log as audit
from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    LABEL_STYLE, SECTION_LABEL_STYLE, STOP_RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    primary_btn_style, save_btn_style, secondary_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


class _Signals(QObject):
    progress = Signal(int, int)  # sent, total
    finished = Signal(str)
    error = Signal(str)
    status = Signal(str)


class HandoffPanel(QFrame):
    handoff_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_id = ""
        self._vm_name = ""
        self._disk_path = ""
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("VM HANDOFF", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Transfer this VM to another Icosele Vault instance on the local network. "
            "The VM will be paused, compressed, and sent over a direct socket connection.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Target
        from PySide6.QtWidgets import QFormLayout
        form = QFormLayout(); form.setSpacing(6)
        self._target_ip = QLineEdit(); self._target_ip.setStyleSheet(INPUT_STYLE)
        self._target_ip.setPlaceholderText("192.168.1.x")
        self._target_port = QLineEdit("47830"); self._target_port.setStyleSheet(INPUT_STYLE)
        for lbl, w in [("Target IP", self._target_ip), ("Port", self._target_port)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE); form.addRow(l, w)
        lay.addLayout(form)

        self._keep_local = QCheckBox("Keep local copy after transfer")
        self._keep_local.setChecked(True)
        self._keep_local.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; }}")
        lay.addWidget(self._keep_local)

        # Speed test
        br = QHBoxLayout()
        self._btn_speed = QPushButton("Test Speed")
        self._btn_speed.setStyleSheet(subtle_btn_style())
        self._btn_speed.setFixedHeight(28)
        self._btn_speed.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_speed.clicked.connect(self._on_speed_test)
        self._btn_send = QPushButton("Hand Off VM")
        self._btn_send.setStyleSheet(save_btn_style())
        self._btn_send.setFixedHeight(32)
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.clicked.connect(self._on_handoff)
        br.addWidget(self._btn_speed)
        br.addWidget(self._btn_send)
        br.addStretch()
        lay.addLayout(br)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(18)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 4px; color: {TEXT_PRIMARY}; font-size: 9px; text-align: center; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}")
        self._progress.hide()
        lay.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)

        warn = QLabel("Large disk images may take a long time. Test speed first.")
        warn.setWordWrap(True)
        warn.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-style: italic; background: transparent;")
        lay.addWidget(warn)
        lay.addStretch()

    def set_vm(self, vm_id: str, vm_name: str, disk_path: str):
        self._vm_id = vm_id
        self._vm_name = vm_name
        self._disk_path = disk_path

    def _on_speed_test(self):
        ip = self._target_ip.text().strip()
        port = int(self._target_port.text().strip() or "47830")
        self._status.setText(f"Testing connection to {ip}:{port}...")
        try:
            sock = socket.create_connection((ip, port), timeout=5)
            # Send a small test payload
            test_data = b"\x00" * (1024 * 1024)  # 1MB
            import time
            t0 = time.monotonic()
            sock.sendall(struct.pack("!I", len(test_data)) + test_data)
            elapsed = time.monotonic() - t0
            speed_mbps = (len(test_data) * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
            sock.close()
            if self._disk_path and os.path.exists(self._disk_path):
                disk_mb = os.path.getsize(self._disk_path) / (1024 * 1024)
                est_sec = (disk_mb * 8) / speed_mbps if speed_mbps > 0 else 0
                self._status.setText(
                    f"Speed: {speed_mbps:.0f} Mbps  |  "
                    f"Disk: {disk_mb:.0f} MB  |  "
                    f"Estimated transfer: {int(est_sec)}s")
            else:
                self._status.setText(f"Speed: {speed_mbps:.0f} Mbps")
        except Exception as exc:
            self._status.setText(f"Connection failed: {exc}")

    def _on_handoff(self):
        if not self._disk_path or not os.path.exists(self._disk_path):
            self._status.setText("No disk image to transfer.")
            return
        self.handoff_requested.emit()
        self._status.setText("Handoff initiated (VM should be paused first).")
        audit.record("handoff_initiated", self._vm_id, self._vm_name, {
            "target": self._target_ip.text().strip(),
            "keep_local": self._keep_local.isChecked(),
        })


class AcceptHandoffDialog(QDialog):
    """Dialog for receiving a VM handoff."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Accept VM Handoff")
        self.setFixedSize(400, 240)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Listen for incoming VM handoff.",
                              styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        from PySide6.QtWidgets import QFormLayout
        form = QFormLayout(); form.setSpacing(6)
        self._port = QLineEdit("47830"); self._port.setStyleSheet(INPUT_STYLE)
        l = QLabel("Listen Port"); l.setStyleSheet(LABEL_STYLE)
        form.addRow(l, self._port)
        lay.addLayout(form)
        self._status = QLabel("Not listening.")
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)
        lay.addStretch()
        br = QHBoxLayout()
        bc = QPushButton("Close"); bc.setStyleSheet(secondary_btn_style()); bc.setFixedHeight(30)
        bc.clicked.connect(self.reject)
        bl = QPushButton("Start Listening"); bl.setStyleSheet(primary_btn_style()); bl.setFixedHeight(30)
        bl.clicked.connect(self._listen)
        br.addStretch(); br.addWidget(bc); br.addSpacing(6); br.addWidget(bl)
        lay.addLayout(br)

    def _listen(self):
        port = int(self._port.text().strip() or "47830")
        self._status.setText(f"Listening on port {port}... (waiting for sender)")
        # In production this would run a server thread; for now show the UI
        threading.Thread(target=self._listen_thread, args=(port,), daemon=True).start()

    def _listen_thread(self, port):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(1)
            srv.settimeout(60)
            client, addr = srv.accept()
            # Receive data length
            hdr = client.recv(4)
            if len(hdr) == 4:
                length = struct.unpack("!I", hdr)[0]
                log.info("Handoff: receiving %d bytes from %s", length, addr)
            client.close()
            srv.close()
        except Exception as exc:
            log.warning("Handoff listen failed: %s", exc)
