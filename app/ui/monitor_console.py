"""QEMU Monitor Console — send raw commands to the QEMU human monitor."""
from __future__ import annotations

import socket
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    INPUT_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    primary_btn_style,
)

log = logging.getLogger(__name__)


class MonitorConsoleDialog(QDialog):
    def __init__(self, monitor_path: str, parent=None) -> None:
        super().__init__(parent)
        self._monitor_path = monitor_path
        self._sock: socket.socket | None = None
        self._build_ui()
        self._connect_socket()

    def _build_ui(self) -> None:
        self.setWindowTitle("QEMU Monitor Console")
        self.setMinimumSize(600, 400)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("QEMU Monitor Console")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(title)

        hint = QLabel("Send raw QEMU monitor commands (e.g. info version, info cpus, info balloon)")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        layout.addWidget(hint)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            f"QTextEdit {{ background-color: {BG_CARD}; color: {ACCENT};"
            f" border: 1px solid {BORDER}; border-radius: 6px;"
            f" padding: 8px; font-family: monospace; font-size: 12px; }}")
        layout.addWidget(self._output, 1)

        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Enter command...")
        self._input.setStyleSheet(INPUT_STYLE)
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input, 1)

        self._btn_send = QPushButton("Send")
        self._btn_send.setStyleSheet(primary_btn_style())
        self._btn_send.setFixedHeight(34)
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.clicked.connect(self._on_send)
        input_row.addWidget(self._btn_send)
        layout.addLayout(input_row)

    def _connect_socket(self) -> None:
        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.connect(self._monitor_path)
            self._sock.settimeout(1.0)
            # Read initial greeting
            try:
                greeting = self._sock.recv(4096).decode(errors="replace")
                self._output.append(greeting.strip())
            except socket.timeout:
                pass
        except (OSError, FileNotFoundError) as exc:
            self._output.append(f"[Error] Could not connect to monitor: {exc}")
            self._sock = None

    def _on_send(self) -> None:
        cmd = self._input.text().strip()
        if not cmd or not self._sock:
            return
        self._input.clear()
        self._output.append(f">>> {cmd}")
        try:
            self._sock.sendall((cmd + "\n").encode())
            # Read response
            response = b""
            self._sock.settimeout(1.0)
            while True:
                try:
                    chunk = self._sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                except socket.timeout:
                    break
            if response:
                self._output.append(response.decode(errors="replace").strip())
        except OSError as exc:
            self._output.append(f"[Error] {exc}")

    def closeEvent(self, event) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        super().closeEvent(event)
