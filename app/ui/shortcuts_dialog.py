"""Task 5 — Keyboard shortcuts reference dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, FONT_FAMILY,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    secondary_btn_style,
)

SHORTCUTS = {
    "Ctrl+N": "New VM",
    "Ctrl+K": "Command palette",
    "Ctrl+1..9": "Switch to VM by position",
    "Space": "Start/Stop selected VM",
    "P": "Pause selected VM",
    "S": "Take snapshot",
    "Delete": "Delete selected VM",
    "Ctrl+Z": "Restore last snapshot",
    "Ctrl+D": "Clone selected VM",
    "Ctrl+Q": "Quarantine network",
    "Ctrl+L": "Open audit log",
    "F5": "Refresh all VM statuses",
    "F11": "Toggle fullscreen",
    "Ctrl+F": "Focus search in VM list",
    "Tab": "Cycle through panels",
    "Escape": "Close dialog",
    "Alt+H": "Toggle high contrast",
    "Alt+M": "Toggle reduced motion",
    "Ctrl+?": "This shortcuts reference",
}


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setFixedSize(420, 480)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)

        title = QLabel("Keyboard Shortcuts")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)

        for key, desc in SHORTCUTS.items():
            row = QLabel(
                f'<span style="color:{ACCENT}; font-weight:700; font-family:monospace">'
                f'{key:16s}</span>'
                f'<span style="color:{TEXT_SECONDARY}">  {desc}</span>')
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setStyleSheet(
                f"font-size: 12px; padding: 4px 0; background: transparent;"
                f" font-family: {FONT_FAMILY};")
            cl.addWidget(row)

        cl.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

        from PySide6.QtWidgets import QPushButton
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(secondary_btn_style())
        close_btn.setFixedHeight(32)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)
