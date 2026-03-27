"""Task 4 — IOMMU group visualiser panel."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL, BORDER,
    FONT_FAMILY, SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, subtle_btn_style,
)

_PCI_BASE = Path("/sys/bus/pci/devices")
_IOMMU_BASE = Path("/sys/kernel/iommu_groups")

# Device class colours
_CLASS_COLORS = {
    0x03: "#cba6f7",  # GPU — purple
    0x02: "#89b4fa",  # Network — blue
    0x04: "#a6e3a1",  # Audio — green
    0x0c: "#fab387",  # USB controller — orange
}
_DEFAULT_COLOR = "#585b70"  # grey


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except (OSError, ValueError):
        return ""


def _class_name(cls_int: int) -> str:
    top = cls_int >> 8
    names = {0x01: "Storage", 0x02: "Network", 0x03: "Display",
             0x04: "Audio", 0x05: "Memory", 0x06: "Bridge",
             0x07: "Serial", 0x08: "System", 0x0c: "USB/Serial Bus",
             0x0d: "Wireless", 0x12: "Processing"}
    return names.get(top, f"Class 0x{top:02x}")


def scan_iommu_groups() -> list[dict]:
    if not _IOMMU_BASE.exists():
        return []
    groups = []
    for gdir in sorted(_IOMMU_BASE.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
        if not gdir.name.isdigit():
            continue
        devs_path = gdir / "devices"
        if not devs_path.exists():
            continue
        devices = []
        has_gpu = False
        for link in sorted(devs_path.iterdir()):
            pci = link.name
            dev_path = _PCI_BASE / pci
            vid = _read(dev_path / "vendor").replace("0x", "")
            did = _read(dev_path / "device").replace("0x", "")
            cls_str = _read(dev_path / "class")
            cls_int = int(cls_str, 16) >> 8 if cls_str else 0
            driver = ""
            drv = dev_path / "driver"
            if drv.is_symlink():
                driver = drv.resolve().name
            top_class = cls_int >> 8 if cls_int > 0xff else cls_int
            color = _CLASS_COLORS.get(top_class, _DEFAULT_COLOR)
            if top_class == 0x03:
                has_gpu = True
            devices.append({
                "pci_addr": pci, "vendor_id": vid, "device_id": did,
                "class_int": cls_int, "class_name": _class_name(cls_int),
                "driver": driver, "color": color,
            })
        groups.append({
            "id": gdir.name,
            "devices": devices,
            "has_gpu": has_gpu,
        })
    return groups


class IOMMUCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups: list[dict] = []
        self.setMinimumHeight(200)

    def set_groups(self, groups: list[dict]):
        self._groups = groups
        total_h = 0
        for g in groups:
            total_h += 50 + len(g["devices"]) * 28 + 20
        self.setMinimumHeight(max(200, total_h + 40))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.fillRect(0, 0, w, self.height(), QColor(BG_DEEP))

        if not self._groups:
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Inter", 11))
            p.drawText(QRectF(0, 0, w, 100), Qt.AlignmentFlag.AlignCenter,
                       "No IOMMU groups found. Is IOMMU enabled?")
            p.end()
            return

        y = 16
        card_w = w - 32

        for g in self._groups:
            card_h = 32 + len(g["devices"]) * 28 + 8
            # Group card
            border_col = ACCENT if g["has_gpu"] else BORDER
            p.setPen(QColor(border_col))
            p.setBrush(QColor("#1e1e2e"))
            p.drawRoundedRect(QRectF(16, y, card_w, card_h), 8, 8)

            # Group label
            p.setPen(QColor(TEXT_PRIMARY))
            p.setFont(QFont("Inter", 10, QFont.Weight.Bold))
            label = f"IOMMU Group {g['id']}"
            if g["has_gpu"]:
                label += "  (GPU)"
            p.drawText(QRectF(24, y + 6, card_w - 16, 18),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

            # Device cards
            dy = y + 30
            for dev in g["devices"]:
                dev_w = card_w - 24
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(dev["color"]))
                p.drawRoundedRect(QRectF(28, dy, 6, 20), 2, 2)

                p.setPen(QColor(TEXT_PRIMARY))
                p.setFont(QFont("Inter", 8))
                text = (f"{dev['pci_addr']}  {dev['vendor_id']}:{dev['device_id']}  "
                        f"{dev['class_name']}  drv={dev['driver'] or 'none'}")
                p.drawText(QRectF(40, dy, dev_w - 20, 20),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
                dy += 28

            y += card_h + 12

        p.end()


class IOMMUPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("IOMMU GROUPS", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "IOMMU groups define which PCI devices must be passed through together. "
            "All devices in a group share the same memory isolation boundary. "
            "Groups containing a GPU are highlighted as passthrough candidates.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Legend
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for name, color in [("GPU", "#cba6f7"), ("Network", "#89b4fa"),
                            ("Audio", "#a6e3a1"), ("USB", "#fab387"), ("Other", "#585b70")]:
            dot = QLabel(f"  {name}")
            dot.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;"
                f" border-left: 4px solid {color}; padding-left: 4px;")
            legend.addWidget(dot)
        legend.addStretch()
        lay.addLayout(legend)

        btn_row = QHBoxLayout()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setStyleSheet(subtle_btn_style())
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.clicked.connect(self.refresh)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BG_DEEP}; }}")
        self._canvas = IOMMUCanvas()
        scroll.setWidget(self._canvas)
        lay.addWidget(scroll, 1)

        self.refresh()

    def refresh(self):
        groups = scan_iommu_groups()
        self._canvas.set_groups(groups)
