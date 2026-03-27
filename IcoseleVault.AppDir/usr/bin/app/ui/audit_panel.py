"""Task 2 — Immutable audit log viewer panel."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.audit_log import export_csv, load_entries
from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL, BORDER,
    COMBO_STYLE, FONT_FAMILY, SECTION_LABEL_STYLE, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, save_btn_style, subtle_btn_style,
)


class AuditPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(QLabel("AUDIT LOG", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Immutable append-only log of all significant actions. "
            "This log cannot be cleared or modified from the UI.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Filters
        filt = QHBoxLayout()
        filt.setSpacing(8)
        filt.addWidget(QLabel("VM:", styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        self._vm_filter = QComboBox()
        self._vm_filter.setStyleSheet(COMBO_STYLE)
        self._vm_filter.setFixedWidth(160)
        self._vm_filter.addItem("All VMs", "")
        filt.addWidget(self._vm_filter)
        filt.addWidget(QLabel("Action:", styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        self._action_filter = QComboBox()
        self._action_filter.setStyleSheet(COMBO_STYLE)
        self._action_filter.setFixedWidth(160)
        self._action_filter.addItem("All Actions", "")
        filt.addWidget(self._action_filter)
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setStyleSheet(subtle_btn_style())
        self._btn_refresh.setFixedHeight(30)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        filt.addWidget(self._btn_refresh)
        self._btn_export = QPushButton("Export CSV")
        self._btn_export.setStyleSheet(subtle_btn_style())
        self._btn_export.setFixedHeight(30)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        filt.addWidget(self._btn_export)
        filt.addStretch()
        layout.addLayout(filt)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Timestamp", "Action", "VM Name", "User", "Details"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {BG_CARD}; border: 1px solid {BORDER};
                border-radius: 6px; color: {TEXT_PRIMARY}; font-size: 11px;
                gridline-color: {BORDER};
            }}
            QTableWidget::item {{ padding: 4px 8px; }}
            QTableWidget::item:selected {{ background: {BG_ELEVATED}; }}
            QHeaderView::section {{
                background: {BG_CARD}; color: {TEXT_MUTED}; border: none;
                border-bottom: 1px solid {BORDER}; padding: 6px 8px;
                font-size: 10px; font-weight: 600;
            }}
        """)
        layout.addWidget(self._table, 1)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        layout.addWidget(self._count_label)

        self._btn_refresh.clicked.connect(self.refresh)
        self._btn_export.clicked.connect(self._on_export)
        self._vm_filter.currentIndexChanged.connect(self._apply_filter)
        self._action_filter.currentIndexChanged.connect(self._apply_filter)

    def refresh(self) -> None:
        self._entries = load_entries()
        # Populate filter combos
        vms: set[str] = set()
        actions: set[str] = set()
        for e in self._entries:
            n = e.get("vm_name", "")
            if n:
                vms.add(n)
            a = e.get("action", "")
            if a:
                actions.add(a)

        self._vm_filter.blockSignals(True)
        cur_vm = self._vm_filter.currentData()
        self._vm_filter.clear()
        self._vm_filter.addItem("All VMs", "")
        for v in sorted(vms):
            self._vm_filter.addItem(v, v)
        idx = self._vm_filter.findData(cur_vm)
        if idx >= 0:
            self._vm_filter.setCurrentIndex(idx)
        self._vm_filter.blockSignals(False)

        self._action_filter.blockSignals(True)
        cur_act = self._action_filter.currentData()
        self._action_filter.clear()
        self._action_filter.addItem("All Actions", "")
        for a in sorted(actions):
            self._action_filter.addItem(a, a)
        idx2 = self._action_filter.findData(cur_act)
        if idx2 >= 0:
            self._action_filter.setCurrentIndex(idx2)
        self._action_filter.blockSignals(False)

        self._apply_filter()

    def _apply_filter(self) -> None:
        vm_f = self._vm_filter.currentData() or ""
        act_f = self._action_filter.currentData() or ""
        filtered = self._entries
        if vm_f:
            filtered = [e for e in filtered if e.get("vm_name") == vm_f]
        if act_f:
            filtered = [e for e in filtered if e.get("action") == act_f]
        self._table.setRowCount(len(filtered))
        for i, e in enumerate(reversed(filtered)):
            ts = (e.get("timestamp") or "")[:19].replace("T", " ")
            self._table.setItem(i, 0, QTableWidgetItem(ts))
            self._table.setItem(i, 1, QTableWidgetItem(e.get("action", "")))
            self._table.setItem(i, 2, QTableWidgetItem(e.get("vm_name", "")))
            self._table.setItem(i, 3, QTableWidgetItem(e.get("user", "")))
            self._table.setItem(i, 4, QTableWidgetItem(
                json.dumps(e.get("details", {}))[:200]))
        self._count_label.setText(f"{len(filtered)} entries")

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Audit Log", "audit_log.csv",
            "CSV Files (*.csv);;All Files (*)")
        if path:
            export_csv(path)
