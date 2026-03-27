"""Task 1 — AES-256 disk encryption panel."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
)


class EncryptionPanel(QFrame):
    config_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("DISK ENCRYPTION", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Encrypt the VM disk image using QEMU LUKS (AES-256). "
            "When enabled, a password is required every time the VM starts. "
            "The disk image is created with qemu-img in LUKS format.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        self._enable_check = QCheckBox("Enable LUKS disk encryption")
        self._enable_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}")
        layout.addWidget(self._enable_check)

        # Status card
        status_card = QFrame()
        status_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        sc_lay = QVBoxLayout(status_card)
        sc_lay.setContentsMargins(14, 12, 14, 12)
        sc_lay.setSpacing(6)

        self._status_label = QLabel("Encryption: disabled")
        self._status_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        sc_lay.addWidget(self._status_label)

        self._lock_badge = QLabel("")
        self._lock_badge.setFixedHeight(26)
        sc_lay.addWidget(self._lock_badge)

        layout.addWidget(status_card)

        # Warning
        warn = QLabel(
            "Lost passwords cannot be recovered. There is no backdoor.\n"
            "Keep your password in a secure password manager.")
        warn.setWordWrap(True)
        warn.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 10px; color: {WARNING}; font-size: 11px;")
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
        self._enable_check.toggled.connect(self._on_toggled)
        self._update_ui()

    def set_config(self, encrypted: bool) -> None:
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(encrypted)
        self._enable_check.blockSignals(False)
        self._update_ui()

    def _on_toggled(self, checked: bool) -> None:
        self._update_ui()
        self.config_changed.emit(checked)

    def _update_ui(self) -> None:
        enc = self._enable_check.isChecked()
        if enc:
            self._status_label.setText("Encryption: ENABLED (LUKS AES-256)")
            self._status_label.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._lock_badge.setText("  \U0001f512 Encrypted  ")
            self._lock_badge.setStyleSheet(
                f"background-color: #1a3328; color: {ACCENT}; border: 1px solid {ACCENT};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700;"
                f" padding: 3px 10px; font-family: {FONT_FAMILY};")
            self._args_preview.setText(
                "-object secret,id=sec0,data=<password>,format=raw\n"
                "-drive file=<disk>,format=luks,key-secret=sec0")
        else:
            self._status_label.setText("Encryption: disabled")
            self._status_label.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._lock_badge.setText("  \U0001f513 Unencrypted  ")
            self._lock_badge.setStyleSheet(
                f"background-color: #2a2a2a; color: {TEXT_MUTED}; border: 1px solid {TEXT_MUTED};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700;"
                f" padding: 3px 10px; font-family: {FONT_FAMILY};")
            self._args_preview.setText("(encryption disabled)")
