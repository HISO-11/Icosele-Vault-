from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

INSTANT_BOOT_TAG = "instant-boot"


class InstantBootPanel(QFrame):
    config_changed = Signal(bool)
    reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("INSTANT BOOT", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Instant Boot saves a RAM snapshot after the first successful boot. "
            "On subsequent starts, the VM restores from this snapshot instead of "
            "cold booting, dramatically reducing startup time."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Toggle
        self._enable_check = QCheckBox("Enable Instant Boot")
        self._enable_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self._enable_check)

        info = QLabel(
            "The snapshot is saved automatically ~30 seconds after the VM starts running. "
            "Requires a qcow2 disk image to store the snapshot."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(info)

        # Snapshot status card
        status_card = QFrame()
        status_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        sc_layout = QVBoxLayout(status_card)
        sc_layout.setContentsMargins(16, 14, 16, 14)
        sc_layout.setSpacing(8)

        self._status_label = QLabel("No instant-boot snapshot found")
        self._status_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        sc_layout.addWidget(self._status_label)

        self._detail_label = QLabel("")
        self._detail_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        sc_layout.addWidget(self._detail_label)

        layout.addWidget(status_card)

        # Reset button
        btn_row = QHBoxLayout()
        self._reset_btn = QPushButton("Reset Instant Boot")
        self._reset_btn.setStyleSheet(subtle_btn_style())
        self._reset_btn.setFixedHeight(32)
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setToolTip(
            "Delete the instant-boot snapshot and force a cold boot next time")
        btn_row.addWidget(self._reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

        self._enable_check.toggled.connect(self._on_toggled)
        self._reset_btn.clicked.connect(self.reset_requested.emit)

    def set_config(self, enabled: bool) -> None:
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(enabled)
        self._enable_check.blockSignals(False)

    def set_snapshot_info(self, exists: bool, detail: str = "") -> None:
        if exists:
            self._status_label.setText("Instant-boot snapshot available")
            self._status_label.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._detail_label.setText(detail or "Snapshot will be used on next start")
        else:
            self._status_label.setText("No instant-boot snapshot found")
            self._status_label.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._detail_label.setText(
                "Snapshot will be created after first boot" if self._enable_check.isChecked()
                else "Enable Instant Boot to create a snapshot")

    def _on_toggled(self, checked: bool) -> None:
        self.config_changed.emit(checked)
        if not checked:
            self.set_snapshot_info(False)
