"""Task 1 — Live VM sharing via socket-based screen streaming."""
from __future__ import annotations

import json
import logging
import random
import socket
import struct
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal, QObject
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

import app.audit_log as audit
from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, COMBO_STYLE,
    FONT_FAMILY, INPUT_STYLE, LABEL_STYLE, SECTION_LABEL_STYLE,
    STOP_RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    primary_btn_style, save_btn_style, secondary_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


def _get_host_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# QR code minimal generator (reuse from streaming_panel pattern)
def _qr_matrix_simple(data: str) -> list[list[int]]:
    size = 25
    m = [[0] * size for _ in range(size)]
    def _finder(r, c):
        for dr in range(7):
            for dc in range(7):
                if dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4):
                    if 0 <= r + dr < size and 0 <= c + dc < size:
                        m[r + dr][c + dc] = 1
    _finder(0, 0); _finder(0, size - 7); _finder(size - 7, 0)
    bits = []
    for ch in data.encode("utf-8"):
        bits.extend([int(b) for b in f"{ch:08b}"])
    idx = 0
    for row in range(size):
        for col in range(size):
            if m[row][col] or row == 6 or col == 6:
                continue
            in_finder = ((row < 8 and col < 8) or (row < 8 and col >= size - 8) or
                         (row >= size - 8 and col < 8))
            if in_finder:
                continue
            if idx < len(bits):
                m[row][col] = bits[idx]; idx += 1
    return m


class _QRSmall(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._matrix = None
        self.setFixedSize(100, 100)

    def set_data(self, text: str):
        self._matrix = _qr_matrix_simple(text)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(0, 0, 100, 100, QColor("#ffffff"))
        if not self._matrix:
            p.end(); return
        sz = len(self._matrix)
        cell = 100.0 / (sz + 2)
        ox = (100 - sz * cell) / 2
        oy = ox
        for r in range(sz):
            for c in range(sz):
                if self._matrix[r][c]:
                    p.fillRect(QRectF(ox + c * cell, oy + r * cell, cell, cell), QColor("#000000"))
        p.end()


class ShareServer:
    """Streams screendumps to connected clients via raw sockets."""

    def __init__(self):
        self._sock: socket.socket | None = None
        self._clients: list[socket.socket] = []
        self._running = False
        self._lock = threading.Lock()
        self.port = 0
        self.code = ""
        self.permission = "view"  # view | keyboard | full

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def start(self, permission: str = "view") -> tuple[int, str]:
        self.permission = permission
        self.code = f"{random.randint(100000, 999999)}"
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", 0))
        self.port = self._sock.getsockname()[1]
        self._sock.listen(5)
        self._sock.settimeout(1.0)
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return self.port, self.code

    def stop(self):
        self._running = False
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _accept_loop(self):
        while self._running and self._sock:
            try:
                client, addr = self._sock.accept()
                # Read code from client
                try:
                    data = client.recv(64)
                    if data.decode(errors="replace").strip() == self.code:
                        # Send permission level
                        client.sendall(self.permission.encode() + b"\n")
                        with self._lock:
                            self._clients.append(client)
                        log.info("Share client connected from %s", addr)
                    else:
                        client.close()
                except Exception:
                    try:
                        client.close()
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except Exception:
                break

    def broadcast_frame(self, frame_data: bytes):
        header = struct.pack("!I", len(frame_data))
        with self._lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(header + frame_data)
                except Exception:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
                try:
                    c.close()
                except Exception:
                    pass


class VMSharePanel(QFrame):
    share_started = Signal()
    share_stopped = Signal()
    vnc_config_changed = Signal(bool, str)  # enabled, password

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = ShareServer()
        self._vm_id = ""
        self._qmp_fn = None
        self._share_timer = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("LIVE VM SHARING", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Share this VM's screen with others on the local network. "
            "Clients connect using the session code.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Permission selector
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Permission:", styleSheet=LABEL_STYLE))
        self._perm_combo = QComboBox()
        self._perm_combo.setStyleSheet(COMBO_STYLE)
        self._perm_combo.addItem("View Only", "view")
        self._perm_combo.addItem("Keyboard Only", "keyboard")
        self._perm_combo.addItem("Full Control", "full")
        self._perm_combo.setFixedWidth(160)
        pr.addWidget(self._perm_combo)
        pr.addStretch()
        lay.addLayout(pr)

        # Start/stop
        br = QHBoxLayout()
        self._btn_start = QPushButton("Start Sharing")
        self._btn_start.setStyleSheet(save_btn_style())
        self._btn_start.setFixedHeight(32)
        self._btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop = QPushButton("End Sharing")
        self._btn_stop.setStyleSheet(
            f"QPushButton {{ background-color: {STOP_RED}; color: #fff;"
            f" border: none; border-radius: 6px; padding: 8px 16px;"
            f" font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY}; }}")
        self._btn_stop.setFixedHeight(32)
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.hide()
        br.addWidget(self._btn_start)
        br.addWidget(self._btn_stop)
        br.addStretch()
        lay.addLayout(br)

        # Share info card
        self._info_card = QFrame()
        self._info_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        self._info_card.hide()
        ic = QVBoxLayout(self._info_card)
        ic.setContentsMargins(14, 12, 14, 12)
        ic.setSpacing(6)
        self._code_label = QLabel("")
        self._code_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 28px; font-weight: 900; font-family: monospace;"
            f" background: transparent; letter-spacing: 4px;")
        ic.addWidget(self._code_label)
        self._ip_label = QLabel("")
        self._ip_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        ic.addWidget(self._ip_label)
        self._clients_label = QLabel("Connected clients: 0")
        self._clients_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;")
        ic.addWidget(self._clients_label)
        lay.addWidget(self._info_card)

        # QR code
        self._qr = _QRSmall()
        self._qr.hide()
        lay.addWidget(self._qr)

        # ── VNC Sharing Section ──
        lay.addWidget(QLabel("VNC SHARING", styleSheet=SECTION_LABEL_STYLE))
        vnc_desc = QLabel(
            "Enable VNC to let colleagues connect with any VNC client. "
            "Add -vnc args before starting the VM.")
        vnc_desc.setWordWrap(True)
        vnc_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(vnc_desc)

        vnc_btn_row = QHBoxLayout()
        self._btn_vnc_enable = QPushButton("Enable VNC Sharing")
        self._btn_vnc_enable.setStyleSheet(save_btn_style())
        self._btn_vnc_enable.setFixedHeight(32)
        self._btn_vnc_enable.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_vnc_enable.clicked.connect(self._on_enable_vnc)
        self._btn_vnc_disable = QPushButton("Disable VNC")
        self._btn_vnc_disable.setStyleSheet(subtle_btn_style())
        self._btn_vnc_disable.setFixedHeight(32)
        self._btn_vnc_disable.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_vnc_disable.clicked.connect(self._on_disable_vnc)
        self._btn_vnc_disable.hide()
        vnc_btn_row.addWidget(self._btn_vnc_enable)
        vnc_btn_row.addWidget(self._btn_vnc_disable)
        vnc_btn_row.addStretch()
        lay.addLayout(vnc_btn_row)

        self._vnc_info = QFrame()
        self._vnc_info.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        self._vnc_info.hide()
        vnc_lay = QVBoxLayout(self._vnc_info)
        vnc_lay.setContentsMargins(14, 12, 14, 12)
        vnc_lay.setSpacing(4)
        self._vnc_conn_label = QLabel("")
        self._vnc_conn_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent;")
        self._vnc_conn_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vnc_lay.addWidget(self._vnc_conn_label)
        self._vnc_pass_label = QLabel("")
        self._vnc_pass_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 14px; font-weight: 700;"
            f" font-family: monospace; background: transparent;")
        self._vnc_pass_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vnc_lay.addWidget(self._vnc_pass_label)
        lay.addWidget(self._vnc_info)

        self._vnc_enabled = False
        self._vnc_password = ""

        lay.addStretch()

    def set_vm(self, vm_id: str):
        self._vm_id = vm_id

    def set_qmp_provider(self, fn):
        self._qmp_fn = fn

    def _on_start(self):
        perm = self._perm_combo.currentData() or "view"
        port, code = self._server.start(perm)
        ip = _get_host_ip()
        self._code_label.setText(code)
        self._ip_label.setText(f"Connect to {ip}:{port}")
        self._info_card.show()
        self._qr.set_data(f"icosele-vault-share://{ip}:{port}/{code}")
        self._qr.show()
        self._btn_start.hide()
        self._btn_stop.show()
        # Start frame broadcast timer
        self._share_timer = QTimer(self)
        self._share_timer.timeout.connect(self._broadcast)
        self._share_timer.start(100)
        # Update client count timer
        self._count_timer = QTimer(self)
        self._count_timer.timeout.connect(self._update_count)
        self._count_timer.start(2000)
        audit.record("share_started", self._vm_id, details={"port": port, "permission": perm})
        self.share_started.emit()

    def _on_stop(self):
        if self._share_timer:
            self._share_timer.stop()
        if hasattr(self, "_count_timer") and self._count_timer:
            self._count_timer.stop()
        self._server.stop()
        self._info_card.hide()
        self._qr.hide()
        self._btn_start.show()
        self._btn_stop.hide()
        audit.record("share_stopped", self._vm_id)
        self.share_stopped.emit()

    def _broadcast(self):
        if not self._qmp_fn or self._server.client_count == 0:
            return
        qmp = self._qmp_fn(self._vm_id)
        if not qmp or not qmp.connected:
            return
        thumb_path = f"/tmp/icosele-vault/{self._vm_id}/share_frame.ppm"
        try:
            qmp.execute("screendump", {"filename": thumb_path})
            data = Path(thumb_path).read_bytes()
            self._server.broadcast_frame(data)
        except Exception:
            pass

    def _update_count(self):
        self._clients_label.setText(f"Connected clients: {self._server.client_count}")

    def _on_enable_vnc(self):
        import secrets
        self._vnc_password = secrets.token_hex(4)
        self._vnc_enabled = True
        ip = _get_host_ip()
        self._vnc_conn_label.setText(f"Connect via VNC: {ip}:5901")
        self._vnc_pass_label.setText(f"Password: {self._vnc_password}")
        self._vnc_info.show()
        self._btn_vnc_enable.hide()
        self._btn_vnc_disable.show()
        self.vnc_config_changed.emit(True, self._vnc_password)

    def _on_disable_vnc(self):
        self._vnc_enabled = False
        self._vnc_password = ""
        self._vnc_info.hide()
        self._btn_vnc_enable.show()
        self._btn_vnc_disable.hide()
        self.vnc_config_changed.emit(False, "")

    def get_vnc_args(self) -> list[str]:
        """Return QEMU args for VNC sharing if enabled."""
        if self._vnc_enabled and self._vnc_password:
            return ["-vnc", ":1,password=on"]
        return []


class JoinShareDialog(QDialog):
    """Dialog for joining a shared VM session."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Join Shared VM")
        self.setFixedSize(380, 260)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Join a VM sharing session on the local network.",
                              styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        from PySide6.QtWidgets import QFormLayout
        form = QFormLayout(); form.setSpacing(6)
        self._ip = QLineEdit(); self._ip.setStyleSheet(INPUT_STYLE)
        self._ip.setPlaceholderText("192.168.1.x")
        self._port = QLineEdit(); self._port.setStyleSheet(INPUT_STYLE)
        self._port.setPlaceholderText("Port number")
        self._code = QLineEdit(); self._code.setStyleSheet(INPUT_STYLE)
        self._code.setPlaceholderText("6-digit code")
        for lbl, w in [("Host IP", self._ip), ("Port", self._port), ("Code", self._code)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE); form.addRow(l, w)
        lay.addLayout(form)
        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)
        lay.addStretch()
        br = QHBoxLayout()
        bc = QPushButton("Cancel"); bc.setStyleSheet(secondary_btn_style()); bc.setFixedHeight(30)
        bc.clicked.connect(self.reject)
        bj = QPushButton("Connect"); bj.setStyleSheet(primary_btn_style()); bj.setFixedHeight(30)
        bj.clicked.connect(self._on_connect)
        br.addStretch(); br.addWidget(bc); br.addSpacing(6); br.addWidget(bj)
        lay.addLayout(br)
        self.connected_socket: socket.socket | None = None
        self.permission = "view"

    def _on_connect(self):
        ip = self._ip.text().strip()
        port_s = self._port.text().strip()
        code = self._code.text().strip()
        if not ip or not port_s or not code:
            self._status.setText("Fill in all fields.")
            return
        try:
            port = int(port_s)
            sock = socket.create_connection((ip, port), timeout=5)
            sock.sendall(code.encode() + b"\n")
            resp = sock.recv(64).decode(errors="replace").strip()
            self.permission = resp
            self.connected_socket = sock
            self._status.setText(f"Connected! Permission: {resp}")
            self.accept()
        except Exception as exc:
            self._status.setText(f"Failed: {exc}")
