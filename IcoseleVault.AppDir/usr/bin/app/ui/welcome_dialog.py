from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout,
)

from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_ELEVATED, BG_PANEL, BORDER,
    FONT_FAMILY, TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY,
    primary_btn_style, secondary_btn_style, subtle_btn_style,
)

SETUP_FLAG = Path(__file__).resolve().parent.parent.parent / "data" / ".setup_complete"


def should_show_welcome() -> bool:
    return not SETUP_FLAG.exists()


def mark_setup_complete() -> None:
    SETUP_FLAG.parent.mkdir(parents=True, exist_ok=True)
    SETUP_FLAG.write_text("1")


class _WelcomeCard(QFrame):
    def __init__(self, title: str, desc: str, btn_text: str, primary: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            _WelcomeCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        t = QLabel(title)
        t.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(t)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(d)

        layout.addStretch()

        self.btn = QPushButton(btn_text)
        self.btn.setFixedHeight(38)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            self.btn.setStyleSheet(primary_btn_style())
        else:
            self.btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {ACCENT};
                    border: 1px solid {ACCENT};
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 12px;
                    font-weight: 600;
                    font-family: {FONT_FAMILY};
                }}
                QPushButton:hover {{
                    background-color: {BG_ELEVATED};
                }}
            """)
        layout.addWidget(self.btn)


class WelcomeDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.wants_create = False
        self.import_path: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Welcome to Icosele Vault")
        self.setFixedSize(640, 420)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(8)

        title = QLabel("Welcome to Icosele Vault")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 36px; font-weight: 900;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("The open source VM manager built for professionals")
        sub.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addSpacing(24)

        # Two cards side by side
        cards = QHBoxLayout()
        cards.setSpacing(16)

        create_card = _WelcomeCard(
            "Create your first machine",
            "Set up a new QEMU virtual machine from scratch "
            "with guided templates and configuration.",
            "Get Started", primary=True)
        create_card.btn.clicked.connect(self._on_create)

        import_card = _WelcomeCard(
            "Import existing QEMU config",
            "Already have a QEMU VM? Import an existing "
            "JSON config file to add it to Icosele Vault.",
            "Import Config", primary=False)
        import_card.btn.clicked.connect(self._on_import)

        cards.addWidget(create_card)
        cards.addWidget(import_card)
        layout.addLayout(cards, 1)

        layout.addSpacing(16)

        # Skip link
        skip = QPushButton("Skip for now")
        skip.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_MUTED};"
            f" border: none; font-size: 11px; font-family: {FONT_FAMILY}; }}"
            f" QPushButton:hover {{ color: {TEXT_SECONDARY}; }}")
        skip.setCursor(Qt.CursorShape.PointingHandCursor)
        skip.clicked.connect(self._on_skip)
        skip_row = QHBoxLayout()
        skip_row.addStretch()
        skip_row.addWidget(skip)
        skip_row.addStretch()
        layout.addLayout(skip_row)

    def _on_skip(self) -> None:
        mark_setup_complete()
        self.reject()

    def _on_create(self) -> None:
        mark_setup_complete()
        self.wants_create = True
        self.accept()

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import VM Config", str(Path.home()),
            "JSON Files (*.json);;All Files (*)")
        if path:
            mark_setup_complete()
            self.import_path = path
            self.accept()
