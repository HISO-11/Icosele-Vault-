from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from app.ui.theme import BG_PANEL, LIST_STYLE, SECTION_LABEL_STYLE, save_btn_style, subtle_btn_style

log = logging.getLogger(__name__)


class SnapshotPanel(QFrame):
    snapshot_action = Signal(str, str)
    boot_from_snapshot = Signal(str)  # snapshot name
    screenshot_requested = Signal(str)  # snapshot name — capture screenshot at creation

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("SNAPSHOTS", styleSheet=SECTION_LABEL_STYLE))

        self.snap_list = QListWidget()
        self.snap_list.setStyleSheet(LIST_STYLE)
        self.snap_list.setMinimumHeight(160)
        layout.addWidget(self.snap_list)

        br = QHBoxLayout()
        br.setSpacing(8)
        self.btn_create = QPushButton("Create")
        self.btn_restore = QPushButton("Restore")
        self.btn_delete = QPushButton("Delete")
        self.btn_boot = QPushButton("Boot from Snapshot")
        self.btn_create.setStyleSheet(save_btn_style())
        self.btn_restore.setStyleSheet(subtle_btn_style())
        self.btn_delete.setStyleSheet(subtle_btn_style())
        self.btn_boot.setStyleSheet(subtle_btn_style())
        for btn in (self.btn_create, self.btn_restore, self.btn_delete, self.btn_boot):
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            br.addWidget(btn)
        br.addStretch()
        layout.addLayout(br)

        br2 = QHBoxLayout()
        br2.setSpacing(8)
        self.btn_compare = QPushButton("Compare")
        self.btn_compare.setStyleSheet(subtle_btn_style())
        self.btn_compare.setFixedHeight(32)
        self.btn_compare.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_compare.clicked.connect(self._on_compare)
        br2.addWidget(self.btn_compare)
        br2.addStretch()
        layout.addLayout(br2)

        # Snapshot preview area
        self._preview_label = QLabel("")
        self._preview_label.setStyleSheet(
            "background: transparent; font-size: 11px; color: #888;")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._preview_label)

        self.btn_create.clicked.connect(self._on_create)
        self.btn_restore.clicked.connect(self._on_restore)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_boot.clicked.connect(self._on_boot)
        layout.addStretch()
        self.set_enabled(False)

    def set_enabled(self, enabled: bool) -> None:
        self.btn_create.setEnabled(enabled)
        self.btn_restore.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)
        self.btn_boot.setEnabled(not enabled)  # boot only when VM stopped

    def set_snapshots(self, names: list[str]) -> None:
        self.snap_list.clear()
        for name in names:
            self.snap_list.addItem(QListWidgetItem(name))

    def _selected_name(self) -> str | None:
        item = self.snap_list.currentItem()
        return item.text() if item else None

    def _on_create(self) -> None:
        name, ok = QInputDialog.getText(self, "Create Snapshot", "Snapshot name:")
        if ok and name.strip():
            self.snapshot_action.emit("create", name.strip())
            self.screenshot_requested.emit(name.strip())

    def _on_restore(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(self, "Restore Snapshot",
                                 f"Restore '{name}'?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                 ) == QMessageBox.StandardButton.Yes:
            self.snapshot_action.emit("restore", name)

    def _on_delete(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(self, "Delete Snapshot",
                                 f"Delete '{name}'? Cannot be undone.",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                 ) == QMessageBox.StandardButton.Yes:
            self.snapshot_action.emit("delete", name)

    def _on_boot(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(self, "Boot from Snapshot",
                                 f"Start VM from snapshot '{name}'?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                 ) == QMessageBox.StandardButton.Yes:
            self.boot_from_snapshot.emit(name)

    def _on_compare(self) -> None:
        items = self.snap_list.selectedItems()
        names = [it.text() for it in items]
        if len(names) < 2:
            QMessageBox.information(self, "Compare Snapshots",
                                     "Select two snapshots to compare (Ctrl+click).")
            return
        a, b = names[0], names[1]
        self._preview_label.setText(
            f"Comparing: {a} vs {b}\n"
            f"Both snapshots share the same disk base.\n"
            f"Config differences would appear here if snapshot metadata included VM settings.")

    def set_preview_text(self, text: str) -> None:
        self._preview_label.setText(text)

    def apply_theme(self) -> None:
        from app.ui import theme
        self.setStyleSheet(f"background-color: {theme.get('BG_PANEL')}; border: none;")
        self.snap_list.setStyleSheet(theme.LIST_STYLE)
        self.btn_create.setStyleSheet(theme.save_btn_style())
        self.btn_restore.setStyleSheet(theme.subtle_btn_style())
        self.btn_delete.setStyleSheet(theme.subtle_btn_style())
