"""Task 5 — Webcam passthrough panel."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, SECTION_LABEL_STYLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_V4L_BASE = Path("/sys/class/video4linux")
_USB_BASE = Path("/sys/bus/usb/devices")


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except (OSError, ValueError):
        return ""


def scan_webcams() -> list[dict]:
    if not _V4L_BASE.exists():
        return []
    cams = []
    for dev_dir in sorted(_V4L_BASE.iterdir()):
        name = _read(dev_dir / "name")
        dev_path = f"/dev/{dev_dir.name}"
        # Try to find USB bus/addr by walking up the device tree
        bus = addr = vendor_id = product_id = ""
        device_link = dev_dir / "device"
        if device_link.is_symlink():
            real = device_link.resolve()
            # Walk up looking for busnum/devnum
            for parent in [real] + list(real.parents):
                bn = _read(parent / "busnum")
                dn = _read(parent / "devnum")
                if bn and dn:
                    bus = bn
                    addr = dn
                    vendor_id = _read(parent / "idVendor")
                    product_id = _read(parent / "idProduct")
                    break
        cams.append({
            "name": name or dev_dir.name,
            "dev_path": dev_path,
            "v4l_device": dev_dir.name,
            "bus": bus,
            "addr": addr,
            "vendor_id": vendor_id,
            "product_id": product_id,
        })
    return cams


class WebcamPanel(QFrame):
    passthrough_requested = Signal(str, str, str, str)  # bus, addr, vendor_id, product_id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("WEBCAM PASSTHROUGH", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Detected V4L2 webcam devices. USB webcams can be passed through "
            "directly via USB host passthrough.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        self._cam_list = QVBoxLayout()
        self._cam_list.setSpacing(8)
        lay.addLayout(self._cam_list)

        br = QHBoxLayout()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setStyleSheet(subtle_btn_style())
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.clicked.connect(self.refresh)
        br.addWidget(self._btn_refresh)
        br.addStretch()
        lay.addLayout(br)

        # v4l2 note
        note = QLabel(
            "For webcams that don't support USB passthrough, share /dev/video0 "
            "via virtio-fs and use v4l2 inside the VM:\n"
            "  mount -t virtiofs video /mnt/video\n"
            "  ln -s /mnt/video/video0 /dev/video0")
        note.setWordWrap(True)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        lay.addWidget(note)
        lay.addStretch()
        self.refresh()

    def refresh(self):
        while self._cam_list.count():
            w = self._cam_list.takeAt(0).widget()
            if w:
                w.deleteLater()

        cams = scan_webcams()
        if not cams:
            lbl = QLabel("No webcams detected.")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
            self._cam_list.addWidget(lbl)
            return

        for cam in cams:
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(8)

            info = QVBoxLayout()
            info.setSpacing(2)
            name_lbl = QLabel(cam["name"])
            name_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            info.addWidget(name_lbl)

            detail = f"{cam['dev_path']}"
            if cam["vendor_id"] and cam["product_id"]:
                detail += f"  ({cam['vendor_id']}:{cam['product_id']})"
            if cam["bus"]:
                detail += f"  bus={cam['bus']} addr={cam['addr']}"
            det_lbl = QLabel(detail)
            det_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
            info.addWidget(det_lbl)
            cl.addLayout(info, 1)

            if cam["bus"] and cam["addr"]:
                btn = QPushButton("Pass Through")
                btn.setStyleSheet(save_btn_style())
                btn.setFixedHeight(28)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(
                    lambda checked, c=cam: self.passthrough_requested.emit(
                        c["bus"], c["addr"], c["vendor_id"], c["product_id"]))
                cl.addWidget(btn)
            else:
                lbl = QLabel("USB info unavailable")
                lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
                cl.addWidget(lbl)

            self._cam_list.addWidget(card)
