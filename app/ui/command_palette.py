"""Task 4 — Command palette (Ctrl+K) with fuzzy search."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_ELEVATED, BORDER, FONT_FAMILY,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)

_MOCHA_SURFACE = "#313244"
_MOCHA_TEXT = "#cdd6f4"


def _fuzzy_match(query: str, text: str) -> bool:
    q = query.lower()
    t = text.lower()
    if not q:
        return True
    qi = 0
    for c in t:
        if c == q[qi]:
            qi += 1
            if qi == len(q):
                return True
    return False


class CommandPalette(QDialog):
    action_selected = Signal(str)

    def __init__(self, actions: list[dict], parent=None) -> None:
        """actions: list of {id, label, shortcut?, category?}"""
        super().__init__(parent)
        self._actions = actions
        self._build_ui()
        self._filter("")

    def _build_ui(self) -> None:
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 380)
        self.setStyleSheet("background: transparent;")

        container = QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)

        card = QLabel()
        card.setStyleSheet(
            f"background-color: {_MOCHA_SURFACE}; border: 1px solid {BORDER};"
            f" border-radius: 12px;")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 16, 16, 12)
        card_lay.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command...")
        self._input.setStyleSheet(
            f"QLineEdit {{ background-color: {BG_DEEP}; color: {_MOCHA_TEXT};"
            f" border: 1px solid {BORDER}; border-radius: 8px;"
            f" padding: 10px 14px; font-size: 14px; font-family: {FONT_FAMILY}; }}"
            f"QLineEdit:focus {{ border-color: {ACCENT}; }}")
        self._input.textChanged.connect(self._filter)
        card_lay.addWidget(self._input)

        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; outline: none;
                          color: {_MOCHA_TEXT}; font-size: 13px; }}
            QListWidget::item {{ padding: 8px 12px; border-radius: 6px; }}
            QListWidget::item:selected {{ background-color: {BG_ELEVATED}; }}
            QListWidget::item:hover {{ background-color: {BG_CARD}; }}
        """)
        self._list.itemActivated.connect(self._on_activate)
        card_lay.addWidget(self._list, 1)

        hint = QLabel("Enter to execute  |  Esc to close  |  Up/Down to navigate")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(hint)

        container.addWidget(card)
        self._input.setFocus()

    def _filter(self, text: str) -> None:
        self._list.clear()
        for a in self._actions:
            if not _fuzzy_match(text, a["label"]):
                continue
            shortcut = a.get("shortcut", "")
            display = a["label"]
            if shortcut:
                display += f"    [{shortcut}]"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, a["id"])
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_activate(self, item: QListWidgetItem) -> None:
        aid = item.data(Qt.ItemDataRole.UserRole)
        if aid:
            self.action_selected.emit(aid)
            self.accept()

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() == Qt.Key.Key_Escape:
            self.reject()
        elif ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cur = self._list.currentItem()
            if cur:
                self._on_activate(cur)
        elif ev.key() == Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
        elif ev.key() == Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
        else:
            super().keyPressEvent(ev)
