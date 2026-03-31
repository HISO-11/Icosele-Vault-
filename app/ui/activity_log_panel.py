"""Activity Log Panel — shows recent VM events from audit log."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY,
    subtle_btn_style,
)

_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "audit_log.jsonl"


class ActivityLogPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(QLabel("RECENT ACTIVITY", styleSheet=SECTION_LABEL_STYLE))

        self._event_list = QListWidget()
        self._event_list.setMinimumHeight(200)
        self._event_list.setStyleSheet(
            f"QListWidget {{ background: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; color: {TEXT_PRIMARY}; font-size: 11px;"
            f" font-family: {FONT_FAMILY}; }}"
            f"QListWidget::item {{ padding: 4px 8px; }}")
        layout.addWidget(self._event_list)

        btn_row = QPushButton("Refresh")
        btn_row.setStyleSheet(subtle_btn_style())
        btn_row.setFixedHeight(28)
        btn_row.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.clicked.connect(self.refresh)
        layout.addWidget(btn_row)

        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        self._event_list.clear()
        if not _LOG_PATH.exists():
            self._event_list.addItem(QListWidgetItem("No activity yet."))
            return
        lines = _LOG_PATH.read_text().strip().splitlines()
        # Show last 50 entries, newest first
        for line in reversed(lines[-50:]):
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")[:16].replace("T", " ")
                action = entry.get("action", "?")
                vm = entry.get("vm_name", "")
                text = f"{ts}  {vm}  {action}"
                self._event_list.addItem(QListWidgetItem(text))
            except (json.JSONDecodeError, KeyError):
                continue
