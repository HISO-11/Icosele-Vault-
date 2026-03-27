from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
)


def _detect_pipewire() -> bool:
    try:
        out = subprocess.check_output(["ps", "aux"], text=True, timeout=3)
        return "pipewire" in out.lower()
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


class AudioPanel(QFrame):
    config_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pw_available = _detect_pipewire()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("AUDIO", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Configure audio output for the VM using the host's audio server. "
            "Audio is passed through an emulated Intel HDA sound card."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Enable toggle
        self._enable_check = QCheckBox("Enable audio output")
        self._enable_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self._enable_check)

        # Backend badge
        badge_row = QHBoxLayout()
        badge_lbl = QLabel("Backend:")
        badge_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        self._backend_badge = QLabel()
        self._backend_badge.setFixedHeight(26)
        badge_row.addWidget(badge_lbl)
        badge_row.addWidget(self._backend_badge)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        self._update_badge()

        # PulseAudio fallback banner
        if not self._pw_available:
            warn = QLabel(
                "PipeWire not detected. Falling back to PulseAudio backend. "
                "For best audio experience, consider installing PipeWire."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"background-color: #2d2010; border: 1px solid {WARNING};"
                f" border-radius: 6px; padding: 10px; color: {WARNING}; font-size: 11px;")
            layout.addWidget(warn)

        # Status card
        status_card = QFrame()
        status_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        sc_layout = QVBoxLayout(status_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(6)

        backend_name = "PipeWire" if self._pw_available else "PulseAudio"
        backend_id = "pipewire" if self._pw_available else "pa"

        self._info_label = QLabel(f"Audio server: {backend_name}")
        self._info_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        sc_layout.addWidget(self._info_label)

        self._device_label = QLabel("Device: Intel HDA (ich9-intel-hda)")
        self._device_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        sc_layout.addWidget(self._device_label)

        layout.addWidget(status_card)

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

        self._enable_check.toggled.connect(self._on_toggled)
        self._update_args()

    def set_config(self, enabled: bool) -> None:
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(enabled)
        self._enable_check.blockSignals(False)
        self._update_args()

    def _on_toggled(self, checked: bool) -> None:
        self._update_args()
        self.config_changed.emit(checked)

    def _update_badge(self) -> None:
        if self._pw_available:
            self._backend_badge.setText("  PipeWire  ")
            self._backend_badge.setStyleSheet(
                f"background-color: #1a3328; color: {ACCENT}; border: 1px solid {ACCENT};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700;"
                f" padding: 3px 10px; font-family: {FONT_FAMILY};")
        else:
            self._backend_badge.setText("  PulseAudio  ")
            self._backend_badge.setStyleSheet(
                f"background-color: #2d2010; color: {WARNING}; border: 1px solid {WARNING};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700;"
                f" padding: 3px 10px; font-family: {FONT_FAMILY};")

    def _update_args(self) -> None:
        if not self._enable_check.isChecked():
            self._args_preview.setText("(audio disabled)")
            return
        backend_id = "pipewire" if self._pw_available else "pa"
        self._args_preview.setText(
            f"-audiodev {backend_id},id=audio0 "
            f"-device ich9-intel-hda -device hda-output,audiodev=audio0")

    def get_audio_args(self) -> list[str]:
        if not self._enable_check.isChecked():
            return []
        backend_id = "pipewire" if self._pw_available else "pa"
        return [
            "-audiodev", f"{backend_id},id=audio0",
            "-device", "ich9-intel-hda",
            "-device", "hda-output,audiodev=audio0",
        ]
