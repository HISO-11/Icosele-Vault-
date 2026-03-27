from __future__ import annotations

import logging
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY,
    primary_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


class ConsolePanel(QFrame):
    start_requested = False

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_status = "stopped"
        self._qemu_pid: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QHBoxLayout()
        header.setContentsMargins(16, 12, 16, 12)

        self._status_label = QLabel("STOPPED")
        self._status_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 700;"
            f" letter-spacing: 1.5px; background: transparent;"
            f" font-family: {FONT_FAMILY};")
        header.addWidget(self._status_label)
        header.addStretch()

        self._btn_front = QPushButton("Bring to Front")
        self._btn_front.setStyleSheet(subtle_btn_style())
        self._btn_front.setFixedHeight(28)
        self._btn_front.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_front.clicked.connect(self._bring_to_front)
        self._btn_front.hide()
        header.addWidget(self._btn_front)

        layout.addLayout(header)

        # Content area — placeholder when stopped, display info when running
        self._content = QWidget()
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content.setStyleSheet(f"background-color: {BG_PANEL};")

        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        content_layout.addStretch()

        # --- Stopped state ---
        self._stopped_widget = QWidget()
        self._stopped_widget.setStyleSheet("background: transparent;")
        stopped_layout = QVBoxLayout(self._stopped_widget)
        stopped_layout.setContentsMargins(40, 0, 40, 0)
        stopped_layout.setSpacing(0)

        self._placeholder_text = QLabel("Start the machine to view console")
        self._placeholder_text.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 14px;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._placeholder_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stopped_layout.addWidget(self._placeholder_text)

        self._btn_start = QPushButton("\u25b6 Start Machine")
        self._btn_start.setStyleSheet(primary_btn_style())
        self._btn_start.setFixedHeight(44)
        self._btn_start.setFixedWidth(180)
        self._btn_start.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_wrapper = QHBoxLayout()
        btn_wrapper.addStretch()
        btn_wrapper.addWidget(self._btn_start)
        btn_wrapper.addStretch()
        stopped_layout.addSpacing(12)
        stopped_layout.addLayout(btn_wrapper)

        content_layout.addWidget(self._stopped_widget)

        # --- Running state ---
        self._running_widget = QWidget()
        self._running_widget.setStyleSheet("background: transparent;")
        running_layout = QVBoxLayout(self._running_widget)
        running_layout.setContentsMargins(40, 0, 40, 0)
        running_layout.setSpacing(16)
        running_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._running_icon = QLabel("\U0001f5b5")
        self._running_icon.setStyleSheet(
            f"font-size: 48px; background: transparent;")
        self._running_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        running_layout.addWidget(self._running_icon)

        self._running_title = QLabel("Display running in external window")
        self._running_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._running_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        running_layout.addWidget(self._running_title)

        self._running_detail = QLabel(
            "Embedded display requires a SPICE or VNC client widget,\n"
            "which is not available in PySide6. The VM display is\n"
            "running in QEMU\u2019s native window instead.")
        self._running_detail.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._running_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._running_detail.setWordWrap(True)
        running_layout.addWidget(self._running_detail)

        running_layout.addSpacing(4)

        self._btn_open_ext = QPushButton("\u25a3  Open in External Window")
        self._btn_open_ext.setFixedHeight(44)
        self._btn_open_ext.setFixedWidth(240)
        self._btn_open_ext.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open_ext.setStyleSheet(
            f"QPushButton {{"
            f"background-color: {ACCENT}; color: {TEXT_ON_ACCENT};"
            f" border: none; border-radius: 8px;"
            f" font-size: 13px; font-weight: 700;"
            f" font-family: {FONT_FAMILY};"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: {ACCENT}; opacity: 0.85;"
            f"}}")
        self._btn_open_ext.clicked.connect(self._bring_to_front)

        ext_btn_wrapper = QHBoxLayout()
        ext_btn_wrapper.addStretch()
        ext_btn_wrapper.addWidget(self._btn_open_ext)
        ext_btn_wrapper.addStretch()
        running_layout.addLayout(ext_btn_wrapper)

        self._running_widget.hide()
        content_layout.addWidget(self._running_widget)

        content_layout.addStretch()

        layout.addWidget(self._content, 1)

    def get_start_button(self) -> QPushButton:
        return self._btn_start

    def set_status(self, status: str, qemu_pid: int | None = None) -> None:
        self._vm_status = status
        self._qemu_pid = qemu_pid

        if status == "running":
            self._status_label.setText("RUNNING")
            self._status_label.setStyleSheet(
                f"color: {ACCENT}; font-size: 11px; font-weight: 700;"
                f" letter-spacing: 1.5px; background: transparent;"
                f" font-family: {FONT_FAMILY};")
            self._stopped_widget.hide()
            self._running_title.setText("Display running in external window")
            self._running_widget.show()
            self._btn_front.show()
        elif status == "paused":
            self._status_label.setText("PAUSED")
            self._status_label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 700;"
                f" letter-spacing: 1.5px; background: transparent;"
                f" font-family: {FONT_FAMILY};")
            self._stopped_widget.hide()
            self._running_title.setText("Display paused")
            self._running_widget.show()
            self._btn_front.show()
        else:
            self._status_label.setText("STOPPED")
            self._status_label.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 700;"
                f" letter-spacing: 1.5px; background: transparent;"
                f" font-family: {FONT_FAMILY};")
            self._stopped_widget.show()
            self._running_widget.hide()
            self._btn_front.hide()

    def apply_theme(self) -> None:
        from app.ui import theme
        self.setStyleSheet(f"background-color: {theme.get('BG_PANEL')}; border: none;")
        self._placeholder_text.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 14px;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._running_title.setStyleSheet(
            f"color: {theme.get('TEXT_PRIMARY')}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._running_detail.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 12px;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._btn_start.setStyleSheet(primary_btn_style())
        self._btn_front.setStyleSheet(subtle_btn_style())

    def _bring_to_front(self) -> None:
        try:
            subprocess.run(
                ["wmctrl", "-r", "QEMU", "-e", "0,-1,-1,-1,-1"],
                timeout=3, check=False)
            subprocess.run(
                ["wmctrl", "-a", "QEMU"],
                timeout=3, check=False)
        except FileNotFoundError:
            log.warning("wmctrl not installed, cannot bring QEMU window to front")
        except Exception as exc:
            log.warning("Failed to bring QEMU to front: %s", exc)
