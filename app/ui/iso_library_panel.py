"""ISO Library Panel — manage downloaded ISOs in ~/Downloads."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    save_btn_style, subtle_btn_style,
)


class ISOLibraryPanel(QFrame):
    mount_iso = Signal(str)  # path to ISO to mount to running VM

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._isos: list[Path] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(QLabel("ISO LIBRARY", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel("ISOs found in ~/Downloads. Mount to a running VM or delete unused files.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        self._iso_list = QListWidget()
        self._iso_list.setMinimumHeight(150)
        self._iso_list.setStyleSheet(
            f"QListWidget {{ background: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; color: {TEXT_PRIMARY}; font-size: 12px; }}"
            f"QListWidget::item {{ padding: 6px; }}"
            f"QListWidget::item:selected {{ background: {BORDER}; }}")
        layout.addWidget(self._iso_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setStyleSheet(subtle_btn_style())
        self._btn_refresh.setFixedHeight(30)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.clicked.connect(self.refresh)
        self._btn_mount = QPushButton("Mount to VM")
        self._btn_mount.setStyleSheet(save_btn_style())
        self._btn_mount.setFixedHeight(30)
        self._btn_mount.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mount.clicked.connect(self._on_mount)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setStyleSheet(subtle_btn_style())
        self._btn_delete.setFixedHeight(30)
        self._btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addWidget(self._btn_mount)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        self._iso_list.clear()
        self._isos.clear()
        dl_dir = Path.home() / "Downloads"
        if not dl_dir.exists():
            return
        for p in sorted(dl_dir.glob("*.iso")):
            size_mb = p.stat().st_size / (1024 * 1024)
            mtime = os.path.getmtime(p)
            from datetime import datetime
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            self._isos.append(p)
            self._iso_list.addItem(QListWidgetItem(
                f"{p.name}  ({size_mb:.0f} MB)  {date_str}"))

    def _on_mount(self) -> None:
        row = self._iso_list.currentRow()
        if 0 <= row < len(self._isos):
            self.mount_iso.emit(str(self._isos[row]))

    def _on_delete(self) -> None:
        row = self._iso_list.currentRow()
        if row < 0 or row >= len(self._isos):
            return
        path = self._isos[row]
        reply = QMessageBox.question(
            self, "Delete ISO",
            f"Delete {path.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                path.unlink()
                self.refresh()
            except OSError as exc:
                QMessageBox.warning(self, "Delete Failed", str(exc))
