"""Task 5 — Network quarantine button."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, STOP_RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WARNING, subtle_btn_style,
)


class QuarantinePanel(QFrame):
    quarantine_requested = Signal()
    restore_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._quarantined = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("NETWORK QUARANTINE", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Instantly isolate the VM from all network access. "
            "The VM keeps running but cannot send or receive traffic. "
            "Use this to contain a compromised VM.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Quarantine button
        self._btn_quarantine = QPushButton("QUARANTINE NOW")
        self._btn_quarantine.setFixedHeight(48)
        self._btn_quarantine.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_quarantine.setStyleSheet(
            f"QPushButton {{ background-color: {STOP_RED}; color: #ffffff;"
            f" border: none; border-radius: 8px; font-size: 14px; font-weight: 800;"
            f" font-family: {FONT_FAMILY}; }}"
            f"QPushButton:hover {{ background-color: #e74c3c; }}")
        layout.addWidget(self._btn_quarantine)

        # Restore button
        self._btn_restore = QPushButton("Restore Network")
        self._btn_restore.setStyleSheet(subtle_btn_style())
        self._btn_restore.setFixedHeight(34)
        self._btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_restore.hide()
        layout.addWidget(self._btn_restore)

        # Status banner
        self._banner = QLabel("")
        self._banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner.setWordWrap(True)
        self._banner.setFixedHeight(42)
        self._banner.hide()
        layout.addWidget(self._banner)

        # Info card
        info_card = QFrame()
        info_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        ic_lay = QVBoxLayout(info_card)
        ic_lay.setContentsMargins(14, 12, 14, 12)
        ic_lay.setSpacing(6)

        self._status_lbl = QLabel("Status: Normal (network active)")
        self._status_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        ic_lay.addWidget(self._status_lbl)

        self._detail_lbl = QLabel(
            "Quarantine removes the network device via QMP (device_del + netdev_del). "
            "Restore re-adds it. State is not persisted across app restarts.")
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        ic_lay.addWidget(self._detail_lbl)
        layout.addWidget(info_card)
        layout.addStretch()

        self._btn_quarantine.clicked.connect(self._on_quarantine)
        self._btn_restore.clicked.connect(self._on_restore)

    def set_quarantined(self, q: bool) -> None:
        self._quarantined = q
        self._update_ui()

    def _update_ui(self) -> None:
        if self._quarantined:
            self._btn_quarantine.hide()
            self._btn_restore.show()
            self._banner.show()
            self._banner.setText("QUARANTINED — ALL NETWORK ACCESS BLOCKED")
            self._banner.setStyleSheet(
                f"background-color: {STOP_RED}; color: #ffffff;"
                f" border-radius: 6px; font-size: 13px; font-weight: 800;"
                f" font-family: {FONT_FAMILY}; padding: 8px;")
            self._status_lbl.setText("Status: QUARANTINED")
            self._status_lbl.setStyleSheet(
                f"color: {STOP_RED}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
        else:
            self._btn_quarantine.show()
            self._btn_restore.hide()
            self._banner.hide()
            self._status_lbl.setText("Status: Normal (network active)")
            self._status_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")

    def _on_quarantine(self) -> None:
        if QMessageBox.warning(
                self, "Network Quarantine",
                "This will immediately cut ALL network access for this VM.\n"
                "The VM will keep running.\n\nConfirm?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.quarantine_requested.emit()

    def _on_restore(self) -> None:
        self.restore_requested.emit()
