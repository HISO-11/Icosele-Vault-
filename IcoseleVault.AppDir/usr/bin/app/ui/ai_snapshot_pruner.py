"""Task 6 — AI snapshot pruning advisor panel."""
from __future__ import annotations

import json
import logging
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.ollama_client import check_available, query, extract_json
from app.snapshot_store import delete_snapshot, load_snapshots
from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, STOP_RED, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING, save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a snapshot management advisor for a VM named {vm_name}. "
    "Here are all snapshots: {snapshots_json}. Each has id, name, tag, "
    "created_at, size_mb, parent_id. The user wants to free up disk "
    "space. Identify snapshots that are safe to delete: old untagged "
    "snapshots, snapshots with no children that are over 30 days old, "
    "duplicate snapshots taken within 1 hour of each other. Never "
    "suggest deleting the most recent snapshot or any snapshot tagged "
    "with important keywords like working, clean, stable, release, demo. "
    "Respond with JSON only: "
    '{"safe_to_delete": [{"id": "...", "name": "...", "reason": "..."}], '
    '"space_recoverable_mb": number, "summary": "one sentence"}.'
)


class _Signals(QObject):
    result = Signal(dict)
    error = Signal(str)


class SnapshotPrunerPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_id = ""
        self._vm_name = ""
        self._checks: list[tuple[QCheckBox, str]] = []  # (checkbox, snap_id)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("AI SNAPSHOT PRUNING", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Ask AI to identify snapshots safe to delete to free up disk space. "
            "Nothing is deleted without your explicit confirmation.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        self._btn_analyze = QPushButton("Get Pruning Advice")
        self._btn_analyze.setStyleSheet(save_btn_style())
        self._btn_analyze.setFixedHeight(32)
        self._btn_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_analyze.clicked.connect(self._on_analyze)
        lay.addWidget(self._btn_analyze)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {BORDER}; border-radius: 6px; background: {BG_DEEP}; }}")
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list_widget)
        self._scroll.setMaximumHeight(200)
        lay.addWidget(self._scroll)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(self._summary_lbl)

        br = QHBoxLayout()
        self._btn_delete = QPushButton("Delete Selected")
        self._btn_delete.setStyleSheet(
            f"QPushButton {{ background-color: {STOP_RED}; color: #fff;"
            f" border: none; border-radius: 6px; padding: 8px 16px;"
            f" font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #e74c3c; }}")
        self._btn_delete.setFixedHeight(32)
        self._btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_delete.hide()
        self._btn_delete.clicked.connect(self._on_delete)
        br.addWidget(self._btn_delete)
        br.addStretch()
        lay.addLayout(br)
        lay.addStretch()

    def set_vm(self, vm_id: str, vm_name: str = ""):
        self._vm_id = vm_id
        self._vm_name = vm_name

    def _on_analyze(self):
        if not self._vm_id:
            return
        snaps = load_snapshots(self._vm_id)
        if not snaps:
            self._status.setText("No snapshots to analyze.")
            return

        if not check_available():
            self._status.setText("Ollama unavailable — cannot get AI advice.")
            return

        self._btn_analyze.setEnabled(False)
        self._status.setText("Analyzing snapshots with AI...")
        self._sigs = _Signals()
        self._sigs.result.connect(self._on_result)
        self._sigs.error.connect(self._on_error)

        snap_data = [{
            "id": s["id"], "name": s["name"],
            "tag": s.get("tag", ""),
            "created_at": s.get("created_at", ""),
            "size_mb": s.get("disk_size_mb", 0),
            "parent_id": s.get("parent_id"),
        } for s in snaps]
        threading.Thread(
            target=self._worker,
            args=(self._vm_name, snap_data),
            daemon=True,
        ).start()

    def _worker(self, vm_name, snap_data):
        try:
            system = _SYSTEM_PROMPT.replace(
                "{vm_name}", vm_name
            ).replace("{snapshots_json}", json.dumps(snap_data))
            raw = query("Identify snapshots safe to delete.", system=system, timeout=30)
            parsed = extract_json(raw)
            if parsed and "safe_to_delete" in parsed:
                self._sigs.result.emit(parsed)
            else:
                self._sigs.error.emit("AI returned invalid response.")
        except Exception as exc:
            self._sigs.error.emit(str(exc))

    def _on_result(self, data: dict):
        self._btn_analyze.setEnabled(True)
        self._status.setText("")
        self._checks.clear()
        while self._list_layout.count() > 1:
            w = self._list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        safe = data.get("safe_to_delete", [])
        space = data.get("space_recoverable_mb", 0)
        summary = data.get("summary", "")

        if not safe:
            self._summary_lbl.setText("No snapshots recommended for deletion.")
            self._btn_delete.hide()
            return

        for item in safe:
            cb = QCheckBox(f"{item.get('name', '?')} — {item.get('reason', '')}")
            cb.setStyleSheet(
                f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 11px;"
                f" background: transparent; spacing: 6px; }}")
            cb.setChecked(True)
            snap_id = item.get("id", "")
            self._checks.append((cb, snap_id))
            idx = self._list_layout.count() - 1
            self._list_layout.insertWidget(idx, cb)

        self._summary_lbl.setText(
            f"{len(safe)} snapshots identified  |  ~{space:.0f} MB recoverable  |  {summary}")
        self._btn_delete.show()

    def _on_error(self, msg: str):
        self._btn_analyze.setEnabled(True)
        self._status.setText(f"Error: {msg}")

    def _on_delete(self):
        to_delete = [(cb.text(), sid) for cb, sid in self._checks if cb.isChecked()]
        if not to_delete:
            return
        if QMessageBox.question(
                self, "Confirm Deletion",
                f"Delete {len(to_delete)} snapshot(s)?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        import app.audit_log as audit
        for name, sid in to_delete:
            delete_snapshot(self._vm_id, sid)
            audit.record("snapshot_delete", self._vm_id, self._vm_name,
                         {"snapshot_id": sid, "reason": "AI pruning recommendation"})
        self._summary_lbl.setText(f"Deleted {len(to_delete)} snapshots.")
        self._btn_delete.hide()
        self._checks.clear()
        while self._list_layout.count() > 1:
            w = self._list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
