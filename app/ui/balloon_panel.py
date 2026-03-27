from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    save_btn_style,
)


class BalloonPanel(QFrame):
    config_changed = Signal(bool, int)
    balloon_adjust = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max_ram = 2048
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("MEMORY BALLOONING", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Memory ballooning allows dynamic adjustment of guest RAM at runtime. "
            "The virtio-balloon device can inflate (reclaim memory from guest) or "
            "deflate (return memory to guest) without restarting the VM."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Enable toggle
        self._enable_check = QCheckBox("Enable virtio-balloon device")
        self._enable_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self._enable_check)

        # Min RAM config
        min_row = QHBoxLayout()
        min_lbl = QLabel("Minimum RAM (MB)")
        min_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        min_lbl.setFixedWidth(140)
        self._min_spin = QSpinBox()
        self._min_spin.setRange(128, 131072)
        self._min_spin.setValue(512)
        self._min_spin.setSuffix(" MB")
        self._min_spin.setSingleStep(256)
        self._min_spin.setStyleSheet(INPUT_STYLE)
        self._min_spin.setFixedWidth(160)
        min_row.addWidget(min_lbl)
        min_row.addWidget(self._min_spin)
        min_row.addStretch()
        layout.addLayout(min_row)

        info = QLabel(
            "Minimum RAM prevents the balloon from reclaiming below this threshold. "
            "Maximum RAM is set in the VM's main configuration.")
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(info)

        # Runtime control section
        layout.addWidget(QLabel("RUNTIME CONTROL", styleSheet=SECTION_LABEL_STYLE))

        ctrl_card = QFrame()
        ctrl_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        cl = QVBoxLayout(ctrl_card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)

        # Current status
        status_row = QHBoxLayout()
        self._target_label = QLabel("Balloon target: --")
        self._target_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._actual_label = QLabel("Actual: --")
        self._actual_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        status_row.addWidget(self._target_label)
        status_row.addStretch()
        status_row.addWidget(self._actual_label)
        cl.addLayout(status_row)

        # Slider
        slider_row = QHBoxLayout()
        self._slider_min_lbl = QLabel("128 MB")
        self._slider_min_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        self._slider_max_lbl = QLabel("2048 MB")
        self._slider_max_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(128)
        self._slider.setMaximum(2048)
        self._slider.setValue(2048)
        self._slider.setSingleStep(64)
        self._slider.setStyleSheet(
            f"QSlider::groove:horizontal {{"
            f" background: {BORDER}; height: 6px; border-radius: 3px; }}"
            f"QSlider::handle:horizontal {{"
            f" background: {ACCENT}; width: 16px; height: 16px;"
            f" margin: -5px 0; border-radius: 8px; }}"
            f"QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}"
        )
        slider_row.addWidget(self._slider_min_lbl)
        slider_row.addWidget(self._slider, 1)
        slider_row.addWidget(self._slider_max_lbl)
        cl.addLayout(slider_row)

        self._slider_val_lbl = QLabel("Set target: 2048 MB")
        self._slider_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._slider_val_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        cl.addWidget(self._slider_val_lbl)

        layout.addWidget(ctrl_card)

        # QEMU args preview
        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self._args_preview = QLabel("-device virtio-balloon-pci")
        self._args_preview.setWordWrap(True)
        self._args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self._args_preview)

        layout.addStretch()

        # Connections
        self._enable_check.toggled.connect(self._on_config_changed)
        self._min_spin.valueChanged.connect(self._on_config_changed)
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._update_enabled_state()

    def set_config(self, enabled: bool, min_mb: int, max_mb: int) -> None:
        self._max_ram = max_mb
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(enabled)
        self._enable_check.blockSignals(False)
        self._min_spin.blockSignals(True)
        self._min_spin.setMaximum(max_mb)
        self._min_spin.setValue(min_mb if min_mb > 0 else 512)
        self._min_spin.blockSignals(False)
        self._slider.setMaximum(max_mb)
        self._slider.setMinimum(min_mb if min_mb > 0 else 128)
        self._slider.setValue(max_mb)
        self._slider_max_lbl.setText(f"{max_mb} MB")
        self._slider_min_lbl.setText(f"{self._slider.minimum()} MB")
        self._update_enabled_state()

    def set_balloon_stats(self, target_mb: int, actual_mb: int) -> None:
        self._target_label.setText(f"Balloon target: {target_mb} MB")
        self._actual_label.setText(f"Actual: {actual_mb} MB")

    def set_vm_running(self, running: bool) -> None:
        self._slider.setEnabled(running and self._enable_check.isChecked())

    def _on_config_changed(self) -> None:
        self._update_enabled_state()
        self.config_changed.emit(
            self._enable_check.isChecked(),
            self._min_spin.value(),
        )

    def _on_slider_changed(self, value: int) -> None:
        self._slider_val_lbl.setText(f"Set target: {value} MB")

    def _on_slider_released(self) -> None:
        self.balloon_adjust.emit(self._slider.value())

    def _update_enabled_state(self) -> None:
        enabled = self._enable_check.isChecked()
        self._min_spin.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        if enabled:
            self._args_preview.setText("-device virtio-balloon-pci")
        else:
            self._args_preview.setText("(ballooning disabled)")
