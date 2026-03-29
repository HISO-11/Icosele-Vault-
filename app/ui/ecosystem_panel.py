"""Tasks 3-5 — GitHub Actions and Terraform integration panels."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, SECTION_LABEL_STYLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, save_btn_style, subtle_btn_style,
)

_GH_DIR = Path(__file__).resolve().parent.parent.parent / "github-actions"
_TF_DIR = Path(__file__).resolve().parent.parent.parent / "terraform-provider"


def _read_file(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return "(file not found)"


class _TemplateViewer(QFrame):
    def __init__(self, title: str, content: str, filename: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(QLabel(title, styleSheet=SECTION_LABEL_STYLE))
        self._box = QPlainTextEdit()
        self._box.setPlainText(content)
        self._box.setReadOnly(True)
        self._box.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {BG_CARD}; color: {ACCENT};"
            f" border: 1px solid {BORDER}; border-radius: 6px; padding: 8px;"
            f" font-size: 10px; font-family: monospace; }}")
        self._box.setMaximumHeight(300)
        lay.addWidget(self._box)
        br = QHBoxLayout()
        br.setSpacing(6)
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setStyleSheet(subtle_btn_style())
        copy_btn.setFixedHeight(26)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(lambda: self._copy(content))
        br.addWidget(copy_btn)
        dl_btn = QPushButton("Download")
        dl_btn.setStyleSheet(subtle_btn_style())
        dl_btn.setFixedHeight(26)
        dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_btn.clicked.connect(lambda: self._download(content, filename))
        br.addWidget(dl_btn)
        br.addStretch()
        lay.addLayout(br)

    def _copy(self, text: str):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(text)

    def _download(self, text: str, filename: str):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Save", filename)
        if path:
            Path(path).write_text(text)


class GitHubActionsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("GITHUB ACTIONS INTEGRATION", styleSheet=SECTION_LABEL_STYLE))
        guide = QLabel(
            "Copy these workflow templates to your repo's .github/workflows/ directory.\n"
            "Set ICOSELE_VAULT_API_KEY as a GitHub Actions secret.\n"
            "The API must be accessible from your self-hosted runner.")
        guide.setWordWrap(True)
        guide.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(guide)
        lay.addWidget(_TemplateViewer(
            "CI TEST WORKFLOW",
            _read_file(_GH_DIR / "icosele-vault-test.yml"),
            "icosele-vault-test.yml"))
        lay.addWidget(_TemplateViewer(
            "RELEASE SNAPSHOT WORKFLOW",
            _read_file(_GH_DIR / "icosele-vault-snapshot.yml"),
            "icosele-vault-snapshot.yml"))
        lay.addStretch()


class TerraformPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("TERRAFORM PROVIDER", styleSheet=SECTION_LABEL_STYLE))
        note = QLabel(
            "Full Terraform provider coming post-launch.\n"
            "Contribute at github.com/HISO-11/icosele-vault")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(note)
        lay.addWidget(_TemplateViewer(
            "EXAMPLE CONFIGURATION",
            _read_file(_TF_DIR / "main.tf.example"),
            "main.tf"))
        lay.addStretch()
