"""Remote VM Management — connect to remote hosts via SSH and list QEMU VMs."""
from __future__ import annotations

import logging
import subprocess
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    LABEL_STYLE, SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, primary_btn_style, secondary_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


class _SSHSignals(QObject):
    vms_found = Signal(list)  # list of dicts
    error = Signal(str)
    status = Signal(str)
    command_result = Signal(str)


class RemoteHostDialog(QDialog):
    """Dialog for connecting to a remote host and managing QEMU VMs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None
        self._hostname = ""
        self._username = ""
        self._remote_vms: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Connect to Remote Host")
        self.setFixedSize(520, 480)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        title = QLabel("Remote VM Management")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(title)

        desc = QLabel("Connect to a remote host via SSH to manage QEMU virtual machines.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(8)
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("192.168.1.100 or hostname")
        self._host_input.setStyleSheet(INPUT_STYLE)
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("username")
        self._user_input.setStyleSheet(INPUT_STYLE)
        self._port_input = QLineEdit("22")
        self._port_input.setStyleSheet(INPUT_STYLE)
        self._port_input.setFixedWidth(80)
        for lbl, w in [("Hostname / IP", self._host_input),
                        ("Username", self._user_input),
                        ("SSH Port", self._port_input)]:
            l = QLabel(lbl)
            l.setStyleSheet(LABEL_STYLE)
            form.addRow(l, w)
        layout.addLayout(form)

        note = QLabel("Uses your SSH keys (~/.ssh). Password auth not supported for security.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-style: italic;"
                           f" background: transparent;")
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setStyleSheet(primary_btn_style())
        self._btn_connect.setFixedHeight(34)
        self._btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_connect.clicked.connect(self._on_connect)
        btn_row.addWidget(self._btn_connect)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._status)

        layout.addWidget(QLabel("REMOTE QEMU VMS", styleSheet=SECTION_LABEL_STYLE))

        self._vm_list = QListWidget()
        self._vm_list.setStyleSheet(
            f"QListWidget {{ background: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; color: {TEXT_PRIMARY}; font-size: 12px; }}"
            f"QListWidget::item {{ padding: 6px; }}"
            f"QListWidget::item:selected {{ background: {BORDER}; }}")
        self._vm_list.setMinimumHeight(100)
        layout.addWidget(self._vm_list)

        action_row = QHBoxLayout()
        self._btn_stop_remote = QPushButton("Stop Selected")
        self._btn_stop_remote.setStyleSheet(subtle_btn_style())
        self._btn_stop_remote.setFixedHeight(30)
        self._btn_stop_remote.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop_remote.clicked.connect(self._on_stop_remote)
        action_row.addWidget(self._btn_stop_remote)
        action_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(secondary_btn_style())
        close_btn.setFixedHeight(30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)

    def _on_connect(self) -> None:
        host = self._host_input.text().strip()
        user = self._user_input.text().strip()
        port = self._port_input.text().strip() or "22"
        if not host or not user:
            self._status.setText("Hostname and username are required.")
            return
        self._hostname = host
        self._username = user
        self._status.setText(f"Connecting to {user}@{host}:{port}...")
        self._btn_connect.setEnabled(False)

        self._sig = _SSHSignals()
        self._sig.vms_found.connect(self._on_vms_found)
        self._sig.error.connect(self._on_error)
        self._sig.status.connect(self._status.setText)

        self._thread = threading.Thread(
            target=self._ssh_worker, args=(host, user, port), daemon=True)
        self._thread.start()

    def _ssh_worker(self, host: str, user: str, port: str) -> None:
        try:
            self._sig.status.emit(f"Scanning QEMU processes on {host}...")
            result = subprocess.run(
                ["ssh", "-p", port, "-o", "StrictHostKeyChecking=accept-new",
                 "-o", "ConnectTimeout=10", f"{user}@{host}",
                 "ps aux | grep qemu-system | grep -v grep"],
                capture_output=True, text=True, timeout=30)
            vms = []
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) < 11:
                    continue
                pid = parts[1]
                # Extract VM name from -name arg if present
                name = f"remote-qemu-{pid}"
                for i, p in enumerate(parts):
                    if p == "-name" and i + 1 < len(parts):
                        name = parts[i + 1].split(",")[0]
                        break
                vms.append({"pid": pid, "name": name, "host": host,
                            "user": user, "port": port})
            self._sig.vms_found.emit(vms)
        except subprocess.TimeoutExpired:
            self._sig.error.emit("SSH connection timed out.")
        except FileNotFoundError:
            self._sig.error.emit("ssh command not found.")
        except Exception as exc:
            self._sig.error.emit(str(exc))

    def _on_vms_found(self, vms: list[dict]) -> None:
        self._btn_connect.setEnabled(True)
        self._remote_vms = vms
        self._vm_list.clear()
        if not vms:
            self._status.setText("Connected — no QEMU VMs found on remote host.")
            return
        self._status.setText(f"Found {len(vms)} QEMU VM(s) on {self._hostname}")
        for vm in vms:
            self._vm_list.addItem(QListWidgetItem(
                f"{vm['name']}  (PID {vm['pid']})"))

    def _on_error(self, msg: str) -> None:
        self._btn_connect.setEnabled(True)
        self._status.setText(f"Error: {msg}")

    def _on_stop_remote(self) -> None:
        row = self._vm_list.currentRow()
        if row < 0 or row >= len(self._remote_vms):
            return
        vm = self._remote_vms[row]
        reply = QMessageBox.question(
            self, "Stop Remote VM",
            f"Send SIGTERM to VM \"{vm['name']}\" (PID {vm['pid']}) on {vm['host']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            subprocess.run(
                ["ssh", "-p", vm["port"], f"{vm['user']}@{vm['host']}",
                 f"kill {vm['pid']}"],
                capture_output=True, text=True, timeout=10)
            self._status.setText(f"Sent stop signal to {vm['name']}")
            self._remote_vms.pop(row)
            self._vm_list.takeItem(row)
        except Exception as exc:
            self._status.setText(f"Error: {exc}")
