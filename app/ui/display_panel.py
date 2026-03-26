from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, INPUT_STYLE,
    LABEL_STYLE, SECTION_LABEL_STYLE, TEXT_SECONDARY, save_btn_style,
)

DISPLAY_BACKENDS = ["gtk", "sdl", "vnc", "spice", "none"]
VGA_TYPES = ["virtio", "std", "qxl", "vmware", "none"]
DISPLAY_DESCRIPTIONS = {
    "gtk": "Native GTK window. Best for local use.", "sdl": "SDL2 window. Lightweight.",
    "vnc": "Remote VNC access.", "spice": "SPICE high-performance remote.", "none": "Headless.",
}
VGA_DESCRIPTIONS = {
    "virtio": "VirtIO GPU. Best performance.", "std": "Standard VGA. Broadest compat.",
    "qxl": "QXL. Optimized for SPICE.", "vmware": "VMware SVGA.", "none": "No graphics.",
}


class DisplayPanel(QFrame):
    config_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(QLabel("DISPLAY & GRAPHICS", styleSheet=SECTION_LABEL_STYLE))

        r1 = QHBoxLayout()
        l1 = QLabel("Backend")
        l1.setStyleSheet(LABEL_STYLE)
        l1.setFixedWidth(90)
        self.display_combo = QComboBox()
        self.display_combo.setStyleSheet(COMBO_STYLE)
        for b in DISPLAY_BACKENDS:
            self.display_combo.addItem(b, b)
        r1.addWidget(l1)
        r1.addWidget(self.display_combo, 1)
        layout.addLayout(r1)

        self.display_desc = QLabel(DISPLAY_DESCRIPTIONS["gtk"])
        self.display_desc.setWordWrap(True)
        self.display_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(self.display_desc)

        r2 = QHBoxLayout()
        l2 = QLabel("VGA")
        l2.setStyleSheet(LABEL_STYLE)
        l2.setFixedWidth(90)
        self.vga_combo = QComboBox()
        self.vga_combo.setStyleSheet(COMBO_STYLE)
        for v in VGA_TYPES:
            self.vga_combo.addItem(v, v)
        r2.addWidget(l2)
        r2.addWidget(self.vga_combo, 1)
        layout.addLayout(r2)

        self.vga_desc = QLabel(VGA_DESCRIPTIONS["virtio"])
        self.vga_desc.setWordWrap(True)
        self.vga_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(self.vga_desc)

        self.vnc_row = QWidget()
        self.vnc_row.setStyleSheet("background: transparent;")
        vl = QHBoxLayout(self.vnc_row)
        vl.setContentsMargins(0, 0, 0, 0)
        vll = QLabel("VNC Port")
        vll.setStyleSheet(LABEL_STYLE)
        vll.setFixedWidth(90)
        self.vnc_port = QSpinBox()
        self.vnc_port.setRange(5900, 5999)
        self.vnc_port.setValue(5900)
        self.vnc_port.setStyleSheet(INPUT_STYLE)
        vl.addWidget(vll)
        vl.addWidget(self.vnc_port, 1)
        layout.addWidget(self.vnc_row)
        self.vnc_row.hide()

        r3 = QHBoxLayout()
        l3 = QLabel("Resolution")
        l3.setStyleSheet(LABEL_STYLE)
        l3.setFixedWidth(90)
        self.resolution_input = QLineEdit()
        self.resolution_input.setPlaceholderText("e.g. 1920x1080")
        self.resolution_input.setStyleSheet(INPUT_STYLE)
        r3.addWidget(l3)
        r3.addWidget(self.resolution_input, 1)
        layout.addLayout(r3)

        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self.args_preview = QLabel()
        self.args_preview.setWordWrap(True)
        self.args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self.args_preview)

        br = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(save_btn_style())
        br.addWidget(self.btn_save)
        br.addStretch()
        layout.addLayout(br)
        layout.addStretch()

        self.display_combo.currentIndexChanged.connect(self._on_display_changed)
        self.vga_combo.currentIndexChanged.connect(self._on_vga_changed)
        self.vnc_port.valueChanged.connect(self._update_preview)
        self.resolution_input.textChanged.connect(self._update_preview)
        self.btn_save.clicked.connect(self._on_save)
        self._update_preview()

    def set_config(self, dc: dict) -> None:
        i = self.display_combo.findData(dc.get("display_backend", "gtk"))
        if i >= 0:
            self.display_combo.setCurrentIndex(i)
        j = self.vga_combo.findData(dc.get("vga_type", "virtio"))
        if j >= 0:
            self.vga_combo.setCurrentIndex(j)
        self.vnc_port.setValue(dc.get("vnc_port", 5900))
        self.resolution_input.setText(dc.get("resolution", ""))
        self._on_display_changed()

    def get_config(self) -> dict:
        return {"display_backend": self.display_combo.currentData() or "gtk",
                "vga_type": self.vga_combo.currentData() or "virtio",
                "vnc_port": self.vnc_port.value(),
                "resolution": self.resolution_input.text().strip()}

    def _on_display_changed(self, _i: int = 0) -> None:
        b = self.display_combo.currentData() or "gtk"
        self.display_desc.setText(DISPLAY_DESCRIPTIONS.get(b, ""))
        self.vnc_row.setVisible(b == "vnc")
        self._update_preview()

    def _on_vga_changed(self, _i: int = 0) -> None:
        self.vga_desc.setText(VGA_DESCRIPTIONS.get(self.vga_combo.currentData() or "virtio", ""))
        self._update_preview()

    def _update_preview(self) -> None:
        self.args_preview.setText(" ".join(self._build_args()))

    def _build_args(self) -> list[str]:
        args: list[str] = []
        b = self.display_combo.currentData() or "gtk"
        v = self.vga_combo.currentData() or "virtio"
        if b == "vnc":
            args += ["-display", f"vnc=:{self.vnc_port.value() - 5900}"]
        elif b == "spice":
            args += ["-display", "spice-app"]
        elif b == "none":
            args += ["-display", "none"]
        else:
            args += ["-display", b]
        args += ["-vga", v]
        r = self.resolution_input.text().strip()
        if r and "x" in r and v != "none":
            p = r.split("x")
            args += ["-device", f"VGA,xres={p[0]},yres={p[1]}"]
        return args

    def _on_save(self) -> None:
        self.config_changed.emit(self.get_config())

    def apply_theme(self) -> None:
        from app.ui import theme
        self.setStyleSheet(f"background-color: {theme.get('BG_PANEL')}; border: none;")
        self.display_combo.setStyleSheet(theme.COMBO_STYLE)
        self.vga_combo.setStyleSheet(theme.COMBO_STYLE)
        self.vnc_port.setStyleSheet(theme.INPUT_STYLE)
        self.resolution_input.setStyleSheet(theme.INPUT_STYLE)
        self.args_preview.setStyleSheet(
            f"color: {theme.get('ACCENT')}; font-size: 11px; font-family: monospace;"
            f" background-color: {theme.get('BG_CARD')}; border: 1px solid {theme.get('BORDER')};"
            f" border-radius: 6px; padding: 10px 12px;")
        self.btn_save.setStyleSheet(theme.save_btn_style())
