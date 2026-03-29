from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QSlider,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style,
)

PRESETS = {
    "unlimited": {"label": "Unlimited", "bw": 0, "latency": 0, "loss": 0.0},
    "office": {"label": "Office (100Mbps, 1ms)", "bw": 100, "latency": 1, "loss": 0.0},
    "broadband": {"label": "Home Broadband (50Mbps, 5ms, 0.1%)", "bw": 50, "latency": 5, "loss": 0.1},
    "4g": {"label": "4G Mobile (20Mbps, 30ms, 0.5%)", "bw": 20, "latency": 30, "loss": 0.5},
    "3g": {"label": "3G Mobile (2Mbps, 100ms, 2%)", "bw": 2, "latency": 100, "loss": 2.0},
    "terrible": {"label": "Terrible (0.5Mbps, 500ms, 10%)", "bw": 0, "latency": 500, "loss": 10.0},
}
PRESET_KEYS = ["unlimited", "office", "broadband", "4g", "3g", "terrible"]


class NetSimPanel(QFrame):
    config_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("NETWORK SIMULATION", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Simulate network conditions for testing. Adds latency and packet loss "
            "parameters to the QEMU netdev configuration."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Profile dropdown
        profile_row = QHBoxLayout()
        profile_lbl = QLabel("Profile")
        profile_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        profile_lbl.setFixedWidth(90)
        self._profile_combo = QComboBox()
        self._profile_combo.setStyleSheet(COMBO_STYLE)
        for key in PRESET_KEYS:
            self._profile_combo.addItem(PRESETS[key]["label"], key)
        profile_row.addWidget(profile_lbl)
        profile_row.addWidget(self._profile_combo, 1)
        layout.addLayout(profile_row)

        slider_style = (
            f"QSlider::groove:horizontal {{"
            f" background: {BORDER}; height: 6px; border-radius: 3px; }}"
            f"QSlider::handle:horizontal {{"
            f" background: {ACCENT}; width: 14px; height: 14px;"
            f" margin: -4px 0; border-radius: 7px; }}"
            f"QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}"
        )

        # Bandwidth slider
        self._bw_label = QLabel("Bandwidth: Unlimited")
        self._bw_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(self._bw_label)
        self._bw_slider = QSlider(Qt.Orientation.Horizontal)
        self._bw_slider.setRange(0, 1000)
        self._bw_slider.setValue(0)
        self._bw_slider.setStyleSheet(slider_style)
        layout.addWidget(self._bw_slider)

        # Latency slider
        self._lat_label = QLabel("Latency: 0 ms")
        self._lat_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(self._lat_label)
        self._lat_slider = QSlider(Qt.Orientation.Horizontal)
        self._lat_slider.setRange(0, 500)
        self._lat_slider.setValue(0)
        self._lat_slider.setStyleSheet(slider_style)
        layout.addWidget(self._lat_slider)

        # Packet loss slider
        self._loss_label = QLabel("Packet Loss: 0%")
        self._loss_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(self._loss_label)
        self._loss_slider = QSlider(Qt.Orientation.Horizontal)
        self._loss_slider.setRange(0, 100)
        self._loss_slider.setValue(0)
        self._loss_slider.setStyleSheet(slider_style)
        layout.addWidget(self._loss_slider)

        # Warning
        warn = QLabel("Changes take effect on next VM start.")
        warn.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 8px; color: {WARNING}; font-size: 11px;")
        layout.addWidget(warn)

        # QEMU args preview
        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self._args_preview = QLabel()
        self._args_preview.setWordWrap(True)
        self._args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self._args_preview)

        layout.addStretch()

        # Connections
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        self._bw_slider.valueChanged.connect(self._on_slider_changed)
        self._lat_slider.valueChanged.connect(self._on_slider_changed)
        self._loss_slider.valueChanged.connect(self._on_slider_changed)
        self._update_labels()
        self._update_preview()

    def set_config(self, netsim: dict) -> None:
        self._bw_slider.blockSignals(True)
        self._lat_slider.blockSignals(True)
        self._loss_slider.blockSignals(True)
        self._bw_slider.setValue(netsim.get("bandwidth_mbps", 0))
        self._lat_slider.setValue(netsim.get("latency_ms", 0))
        self._loss_slider.setValue(int(netsim.get("loss_pct", 0)))
        self._bw_slider.blockSignals(False)
        self._lat_slider.blockSignals(False)
        self._loss_slider.blockSignals(False)
        self._update_labels()
        self._update_preview()

    def get_config(self) -> dict:
        return {
            "bandwidth_mbps": self._bw_slider.value(),
            "latency_ms": self._lat_slider.value(),
            "loss_pct": self._loss_slider.value(),
        }

    def _on_profile_changed(self, idx: int) -> None:
        key = self._profile_combo.currentData()
        if key and key in PRESETS:
            p = PRESETS[key]
            self._bw_slider.setValue(p["bw"])
            self._lat_slider.setValue(p["latency"])
            self._loss_slider.setValue(int(p["loss"]))

    def _on_slider_changed(self) -> None:
        self._update_labels()
        self._update_preview()
        self.config_changed.emit(self.get_config())

    def _update_labels(self) -> None:
        bw = self._bw_slider.value()
        self._bw_label.setText(f"Bandwidth: {'Unlimited' if bw == 0 else f'{bw} Mbps'}")
        self._lat_label.setText(f"Latency: {self._lat_slider.value()} ms")
        self._loss_label.setText(f"Packet Loss: {self._loss_slider.value()}%")

    def _update_preview(self) -> None:
        bw = self._bw_slider.value()
        lat = self._lat_slider.value()
        loss = self._loss_slider.value()
        base = "-netdev user,id=net0,net=10.0.2.0/24,restrict=off"
        extras = []
        if lat > 0:
            extras.append(f"delay={lat}ms")
        if loss > 0:
            extras.append(f"loss={loss}%")
        if extras:
            base += "," + ",".join(extras)
        if bw > 0:
            base += f"\n(bandwidth shaping: {bw} Mbps — applied via tc in guest)"
        self._args_preview.setText(base)
