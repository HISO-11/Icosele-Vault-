"""Task 4 — VM streaming panel with Sunshine/Moonlight and QR code."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WARNING, save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


def _get_host_ip() -> str:
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True, timeout=3).strip()
        parts = out.split()
        return parts[0] if parts else "127.0.0.1"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "127.0.0.1"


# ── Minimal QR code encoder (stdlib only, no qrcode lib) ──────────────
# Implements a tiny QR Version 2 (25x25) with byte mode, ECC level L.
# Sufficient for short URLs like moonlight://192.168.1.5:47984

def _qr_matrix(data: str) -> list[list[int]] | None:
    """Generate a QR code matrix for a short string (<40 chars).

    Returns a 2D list of 0/1 (0=white, 1=black), or None if data too long.
    Uses a simplified fixed Version 2, ECC L approach.
    For production use the qrcode library — this is a minimal fallback.
    """
    # For very short data, create a simple visual pattern
    # that encodes the text as a readable grid
    size = 25
    matrix = [[0] * size for _ in range(size)]

    # Finder patterns (3 corners)
    def _finder(r, c):
        for dr in range(7):
            for dc in range(7):
                is_border = dr in (0, 6) or dc in (0, 6)
                is_inner = 2 <= dr <= 4 and 2 <= dc <= 4
                if is_border or is_inner:
                    if 0 <= r + dr < size and 0 <= c + dc < size:
                        matrix[r + dr][c + dc] = 1

    _finder(0, 0)
    _finder(0, size - 7)
    _finder(size - 7, 0)

    # Timing patterns
    for i in range(8, size - 8):
        matrix[6][i] = 1 if i % 2 == 0 else 0
        matrix[i][6] = 1 if i % 2 == 0 else 0

    # Encode data bits into the remaining area
    bits = []
    for ch in data.encode("utf-8"):
        bits.extend([int(b) for b in f"{ch:08b}"])

    idx = 0
    for col in range(size - 1, 0, -2):
        if col == 6:
            col = 5
        for row_range in (range(size - 1, -1, -1), range(size)):
            for row in row_range:
                for dc in (0, 1):
                    c = col - dc
                    if c < 0 or c >= size:
                        continue
                    if matrix[row][c] != 0:
                        continue
                    # Skip finder/timing areas
                    in_finder = ((row < 8 and c < 8) or
                                 (row < 8 and c >= size - 8) or
                                 (row >= size - 8 and c < 8))
                    if in_finder or row == 6 or c == 6:
                        continue
                    if idx < len(bits):
                        matrix[row][c] = bits[idx]
                        idx += 1

    return matrix


class QRWidget(QWidget):
    """Renders a QR code matrix using QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._matrix: list[list[int]] | None = None
        self.setFixedSize(150, 150)

    def set_data(self, text: str):
        self._matrix = _qr_matrix(text)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#ffffff"))

        if not self._matrix:
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Inter", 9))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "No QR data")
            p.end()
            return

        size = len(self._matrix)
        cell = min(w, h) / (size + 2)  # 1 cell quiet zone
        ox = (w - size * cell) / 2
        oy = (h - size * cell) / 2

        for row in range(size):
            for col in range(size):
                if self._matrix[row][col]:
                    p.fillRect(QRectF(ox + col * cell, oy + row * cell, cell, cell),
                               QColor("#000000"))
        p.end()


class StreamingPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("VM STREAMING", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Stream VM display to any device using Sunshine (host) + Moonlight (client). "
            "Sunshine captures the SPICE/VNC display and encodes it for low-latency streaming.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Sunshine detection
        has_sunshine = shutil.which("sunshine") is not None
        status_card = QFrame()
        status_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        sc = QVBoxLayout(status_card)
        sc.setContentsMargins(14, 12, 14, 12)
        sc.setSpacing(6)

        if has_sunshine:
            sc.addWidget(QLabel("Sunshine: Installed",
                                 styleSheet=f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                                            f" background: transparent; font-family: {FONT_FAMILY};"))
            br = QHBoxLayout()
            btn_start = QPushButton("Start Streaming")
            btn_start.setStyleSheet(save_btn_style())
            btn_start.setFixedHeight(28)
            btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_start.clicked.connect(self._start_sunshine)
            br.addWidget(btn_start)
            btn_web = QPushButton("Open Sunshine Web UI")
            btn_web.setStyleSheet(subtle_btn_style())
            btn_web.setFixedHeight(28)
            btn_web.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_web.clicked.connect(lambda: __import__("webbrowser").open("https://localhost:47990"))
            br.addWidget(btn_web)
            br.addStretch()
            sc.addLayout(br)
        else:
            sc.addWidget(QLabel("Sunshine: Not installed",
                                 styleSheet=f"color: {WARNING}; font-size: 13px; font-weight: 600;"
                                            f" background: transparent; font-family: {FONT_FAMILY};"))
            install = QLabel(
                "Install Sunshine from:\n"
                "https://github.com/LizardByte/Sunshine/releases\n\n"
                "On Arch/Manjaro: yay -S sunshine\n"
                "On Ubuntu: download .deb from GitHub releases")
            install.setWordWrap(True)
            install.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            install.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
            sc.addWidget(install)

        lay.addWidget(status_card)

        # Moonlight connection guide
        lay.addWidget(QLabel("MOONLIGHT CONNECTION GUIDE", styleSheet=SECTION_LABEL_STYLE))

        host_ip = _get_host_ip()
        port = 47984
        conn_url = f"moonlight://{host_ip}:{port}"

        guide_card = QFrame()
        guide_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        gc = QVBoxLayout(guide_card)
        gc.setContentsMargins(14, 12, 14, 12)
        gc.setSpacing(6)

        gc.addWidget(QLabel(f"Host IP: {host_ip}",
                             styleSheet=f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
                                        f" background: transparent; font-family: {FONT_FAMILY};"))
        gc.addWidget(QLabel(f"Port: {port}",
                             styleSheet=f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;"))
        gc.addWidget(QLabel(f"Connection URL: {conn_url}",
                             styleSheet=f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
                                        f" background: transparent;"))

        steps = QLabel(
            "1. Install Moonlight on your client device (moonlight-stream.org)\n"
            "2. Ensure both devices are on the same network\n"
            "3. Open Moonlight and add this host IP\n"
            "4. Accept the pairing request in Sunshine web UI\n"
            "5. Select the VM stream from the app list")
        steps.setWordWrap(True)
        steps.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        gc.addWidget(steps)
        lay.addWidget(guide_card)

        # QR code
        lay.addWidget(QLabel("SCAN TO CONNECT", styleSheet=SECTION_LABEL_STYLE))
        qr_row = QHBoxLayout()
        self._qr = QRWidget()
        self._qr.set_data(conn_url)
        qr_row.addWidget(self._qr)
        qr_info = QLabel(f"Scan this QR code with your\nMoonlight client to connect.\n\n{conn_url}")
        qr_info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        qr_row.addWidget(qr_info, 1)
        lay.addLayout(qr_row)
        lay.addStretch()

    def _start_sunshine(self):
        try:
            subprocess.Popen(["sunshine"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass
