"""Snapshot DAG panel — branching, tagging, storage visualiser, sync.

Implements Tasks 1-3 and 5-6 of the snapshot feature set.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QObject
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from app.snapshot_store import (
    add_snapshot, delete_snapshot, get_branches, get_snap_by_id,
    load_snapshots, load_sync_config, save_snapshots, save_sync_config,
    update_snapshot,
)
from app.ui.snapshot_diff_panel import SnapshotDiffPanel
from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL,
    BORDER, COMBO_STYLE, FONT_FAMILY, INPUT_STYLE, LABEL_STYLE,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING, save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

# Catppuccin Mocha palette for branches
_BRANCH_HUES = [
    "#a6e3a1",  # green
    "#89b4fa",  # blue
    "#cba6f7",  # mauve
    "#f9e2af",  # yellow
    "#fab387",  # peach
    "#f38ba8",  # red
    "#94e2d5",  # teal
    "#74c7ec",  # sapphire
]

_MOCHA_BG = "#1e1e2e"
_MOCHA_TEXT = "#cdd6f4"
_MOCHA_SUBTEXT = "#a6adc8"
_MOCHA_SURFACE0 = "#313244"

NODE_W = 160
NODE_H = 68
PAD_X = 50
PAD_Y = 36


def _branch_color(branch: str, branches: list[str]) -> str:
    idx = branches.index(branch) if branch in branches else 0
    return _BRANCH_HUES[idx % len(_BRANCH_HUES)]


# ── DAG Canvas (Task 2) ───────────────────────────────────────────────

class SnapshotDAGCanvas(QWidget):
    """QPainter-based DAG tree for snapshot visualization."""
    node_clicked = Signal(str)
    node_double_clicked = Signal(str)
    node_right_clicked = Signal(str, object)  # snap_id, global QPoint

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._snaps: list[dict] = []
        self._branches: list[str] = ["main"]
        self._current_id: str | None = None
        self._tag_filter: str = ""
        self._zoom: float = 1.0
        self._positions: dict[str, tuple[float, float]] = {}
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def set_data(self, snaps: list[dict], branches: list[str],
                 current_id: str | None = None) -> None:
        self._snaps = list(snaps)
        self._branches = branches or ["main"]
        self._current_id = current_id
        self._layout_dag()
        self.update()

    def set_tag_filter(self, text: str) -> None:
        self._tag_filter = text.strip().lower()
        self.update()

    # -- zoom --
    def wheelEvent(self, ev: QWheelEvent) -> None:
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            d = ev.angleDelta().y()
            self._zoom = max(0.3, min(3.0, self._zoom * (1.15 if d > 0 else 1 / 1.15)))
            self._layout_dag()
            self.update()
            ev.accept()
        else:
            super().wheelEvent(ev)

    # -- layout --
    def _layout_dag(self) -> None:
        self._positions.clear()
        if not self._snaps:
            return
        # Assign each branch to a lane (column)
        branch_lanes: dict[str, int] = {}
        for s in self._snaps:
            b = s.get("branch_name", "main")
            if b not in branch_lanes:
                branch_lanes[b] = len(branch_lanes)
        # Topological order: respect parent_id chains
        id_set = {s["id"] for s in self._snaps}
        placed: dict[str, int] = {}  # id -> row
        row = 0
        remaining = list(self._snaps)
        while remaining:
            progress = False
            nxt = []
            for s in remaining:
                pid = s.get("parent_id")
                if pid is None or pid not in id_set or pid in placed:
                    placed[s["id"]] = row
                    row += 1
                    progress = True
                else:
                    nxt.append(s)
            remaining = nxt
            if not progress:
                # Cycle breaker — place everything left
                for s in remaining:
                    placed[s["id"]] = row
                    row += 1
                break
        for s in self._snaps:
            lane = branch_lanes.get(s.get("branch_name", "main"), 0)
            r = placed.get(s["id"], 0)
            x = 24 + lane * (NODE_W + PAD_X)
            y = 24 + r * (NODE_H + PAD_Y)
            self._positions[s["id"]] = (x, y)
        max_x = max((p[0] for p in self._positions.values()), default=200) + NODE_W + 40
        max_y = max((p[1] for p in self._positions.values()), default=200) + NODE_H + 40
        self.setMinimumSize(int(max_x * self._zoom), int(max_y * self._zoom))

    def _visible(self, s: dict) -> bool:
        if not self._tag_filter:
            return True
        return self._tag_filter in (s.get("tag") or "").lower()

    # -- hit test --
    def _hit(self, pos) -> str | None:
        z = self._zoom
        for sid, (x, y) in self._positions.items():
            if QRectF(x * z, y * z, NODE_W * z, NODE_H * z).contains(
                    QPointF(pos.x(), pos.y())):
                return sid
        return None

    def mousePressEvent(self, ev) -> None:
        pt = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        sid = self._hit(pt)
        if sid:
            if ev.button() == Qt.MouseButton.RightButton:
                self.node_right_clicked.emit(sid, self.mapToGlobal(pt))
            else:
                self.node_clicked.emit(sid)

    def mouseDoubleClickEvent(self, ev) -> None:
        pt = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        sid = self._hit(pt)
        if sid:
            self.node_double_clicked.emit(sid)

    # -- paint --
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_DEEP))
        z = self._zoom
        nw, nh = NODE_W * z, NODE_H * z

        if not self._snaps:
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Inter", 11))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "No snapshots yet — create one to get started")
            p.end()
            return

        id_pos = self._positions

        # Edges (parent → child arrows)
        for s in self._snaps:
            if not self._visible(s):
                continue
            pid = s.get("parent_id")
            if not pid or pid not in id_pos or s["id"] not in id_pos:
                continue
            px, py = id_pos[pid]
            cx, cy = id_pos[s["id"]]
            col = _branch_color(s.get("branch_name", "main"), self._branches)
            pen = QPen(QColor(col), 2 * z)
            p.setPen(pen)
            # Line from bottom-center of parent to top-center of child
            x1, y1 = (px + NODE_W / 2) * z, (py + NODE_H) * z
            x2, y2 = (cx + NODE_W / 2) * z, cy * z
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            # Arrowhead
            ah = 5 * z
            p.drawLine(QPointF(x2 - ah, y2 - ah * 1.4), QPointF(x2, y2))
            p.drawLine(QPointF(x2 + ah, y2 - ah * 1.4), QPointF(x2, y2))

        # Nodes
        for s in self._snaps:
            if not self._visible(s):
                continue
            if s["id"] not in id_pos:
                continue
            x, y = id_pos[s["id"]]
            rx, ry = x * z, y * z
            is_cur = s["id"] == self._current_id
            bcol = _branch_color(s.get("branch_name", "main"), self._branches)

            # Rounded rectangle
            bw = 3 if is_cur else 1.5
            p.setPen(QPen(QColor(ACCENT if is_cur else bcol), bw * z))
            p.setBrush(QColor(_MOCHA_BG))
            p.drawRoundedRect(QRectF(rx, ry, nw, nh), 8 * z, 8 * z)

            pad = 7 * z

            # Name (bold)
            p.setPen(QColor(_MOCHA_TEXT))
            p.setFont(QFont("Inter", max(int(9 * z), 6), QFont.Weight.Bold))
            fm = p.fontMetrics()
            name = fm.elidedText(s["name"], Qt.TextElideMode.ElideRight, int(nw - 2 * pad))
            p.drawText(QRectF(rx + pad, ry + 5 * z, nw - 2 * pad, 16 * z),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

            # Date + size
            p.setPen(QColor(_MOCHA_SUBTEXT))
            p.setFont(QFont("Inter", max(int(7 * z), 5)))
            date_str = (s.get("created_at") or "")[:16].replace("T", " ")
            disk = s.get("disk_size_mb", 0)
            info = date_str
            if disk:
                info += f"  {disk:.1f} MB"
            p.drawText(QRectF(rx + pad, ry + 22 * z, nw - 2 * pad, 13 * z),
                       Qt.AlignmentFlag.AlignLeft, info)

            # Branch label
            branch = s.get("branch_name", "main")
            p.setFont(QFont("Inter", max(int(6.5 * z), 5)))
            p.setPen(QColor(_MOCHA_SUBTEXT))
            p.drawText(QRectF(rx + pad, ry + 36 * z, nw - 2 * pad, 12 * z),
                       Qt.AlignmentFlag.AlignLeft, branch)

            # Tag pill (Task 3)
            tag = s.get("tag", "")
            if tag:
                p.setFont(QFont("Inter", max(int(7 * z), 5), QFont.Weight.Bold))
                tfm = p.fontMetrics()
                tw = tfm.horizontalAdvance(tag) + 10 * z
                pill_x = rx + nw - tw - pad
                pill_y = ry + nh - 18 * z
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(bcol))
                p.drawRoundedRect(QRectF(pill_x, pill_y, tw, 14 * z), 4 * z, 4 * z)
                p.setPen(QColor(_MOCHA_BG))
                p.drawText(QRectF(pill_x, pill_y, tw, 14 * z),
                           Qt.AlignmentFlag.AlignCenter, tag)

        p.end()


# ── Detail panel (right side) ─────────────────────────────────────────

class SnapDetailPanel(QFrame):
    tag_changed = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid #313244; border-radius: 8px;")
        self.setFixedWidth(240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        _HEADING = (f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700;"
                     f" background: transparent; font-family: {FONT_FAMILY};")
        _LABEL = (f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;"
                   f" letter-spacing: 1px; background: transparent; text-transform: uppercase;")
        _VALUE = (f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 500;"
                   f" background: transparent; font-family: {FONT_FAMILY};")

        self._heading = QLabel("Snapshot Details")
        self._heading.setStyleSheet(_HEADING)
        lay.addWidget(self._heading)

        self._empty_msg = QLabel("Select a snapshot to view details")
        self._empty_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_msg.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent; padding: 20px 0;")
        lay.addWidget(self._empty_msg)

        # Detail fields — label/value pairs
        self._fields_widget = QWidget()
        self._fields_widget.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(self._fields_widget)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)

        self._name_lbl = QLabel("NAME"); self._name_lbl.setStyleSheet(_LABEL)
        self._name_val = QLabel(""); self._name_val.setStyleSheet(_VALUE)
        self._tag_lbl2 = QLabel("TAG"); self._tag_lbl2.setStyleSheet(_LABEL)
        self._tag_val = QLabel(""); self._tag_val.setStyleSheet(_VALUE)
        self._branch_lbl = QLabel("BRANCH"); self._branch_lbl.setStyleSheet(_LABEL)
        self._branch_val = QLabel(""); self._branch_val.setStyleSheet(_VALUE)
        self._date_lbl = QLabel("CREATED"); self._date_lbl.setStyleSheet(_LABEL)
        self._date_val = QLabel(""); self._date_val.setStyleSheet(_VALUE)
        self._size_lbl = QLabel("SIZE"); self._size_lbl.setStyleSheet(_LABEL)
        self._size_val = QLabel(""); self._size_val.setStyleSheet(_VALUE)

        for lbl, val in [(self._name_lbl, self._name_val), (self._tag_lbl2, self._tag_val),
                          (self._branch_lbl, self._branch_val), (self._date_lbl, self._date_val),
                          (self._size_lbl, self._size_val)]:
            fl.addWidget(lbl)
            fl.addWidget(val)

        self._btn_edit_tag = QPushButton("Edit Tag")
        self._btn_edit_tag.setStyleSheet(subtle_btn_style())
        self._btn_edit_tag.setFixedHeight(28)
        self._btn_edit_tag.setCursor(Qt.CursorShape.PointingHandCursor)
        fl.addSpacing(8)
        fl.addWidget(self._btn_edit_tag)
        fl.addStretch()
        self._fields_widget.hide()
        lay.addWidget(self._fields_widget, 1)

        self._snap_id = ""
        self._btn_edit_tag.clicked.connect(self._on_edit_tag)

    def set_snap(self, s: dict | None) -> None:
        if not s:
            self._empty_msg.show()
            self._fields_widget.hide()
            self._snap_id = ""
            return
        self._empty_msg.hide()
        self._fields_widget.show()
        self._snap_id = s["id"]
        self._name_val.setText(s["name"])
        self._tag_val.setText(s.get("tag") or "\u2014")
        self._branch_val.setText(s.get("branch_name", "main"))
        self._date_val.setText((s.get("created_at") or "")[:19].replace("T", " "))
        d, r = s.get("disk_size_mb", 0), s.get("ram_size_mb", 0)
        self._size_val.setText(f"Disk: {d:.1f} MB  RAM: {r:.1f} MB")

    def _on_edit_tag(self) -> None:
        if not self._snap_id:
            return
        tag, ok = QInputDialog.getText(self, "Edit Tag", "Tag (e.g. 'working', 'before-update'):")
        if ok:
            self.tag_changed.emit(self._snap_id, tag.strip())


# ── Storage bar chart (Task 5) ────────────────────────────────────────

class StorageBarWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._segments: list[tuple[str, float, str]] = []
        self.setMinimumHeight(36)
        self.setMaximumHeight(36)

    def set_segments(self, segs: list[tuple[str, float, str]]) -> None:
        self._segments = segs
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_DEEP))
        total = sum(s[1] for s in self._segments) or 1
        x = 0.0
        for label, size, color in self._segments:
            seg_w = max((size / total) * w, 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, 2, seg_w - 1, h - 4), 3, 3)
            if seg_w > 50:
                p.setPen(QColor(_MOCHA_BG))
                p.setFont(QFont("Inter", 7, QFont.Weight.Bold))
                p.drawText(QRectF(x, 2, seg_w - 1, h - 4),
                           Qt.AlignmentFlag.AlignCenter, label)
            x += seg_w
        p.end()


# ── Sync worker signals ───────────────────────────────────────────────

class _SyncSignals(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)


# ── Main panel ─────────────────────────────────────────────────────────

class SnapshotDAGPanel(QFrame):
    snapshot_action = Signal(str, str)  # action, name — for QMP bridge
    clone_requested = Signal()
    branch_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._vm_id = ""
        self._disk_path = ""
        self._vm_name = ""
        self._current_snap_id: str | None = None
        self._current_branch = "main"
        self._is_running = False
        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(8)

        # Top bar: Branch input | Tag filter | Create Snapshot button
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(QLabel("Branch:", styleSheet=LABEL_STYLE))
        self._branch_combo = QComboBox()
        self._branch_combo.setStyleSheet(COMBO_STYLE)
        self._branch_combo.setFixedWidth(140)
        top.addWidget(self._branch_combo)
        top.addSpacing(8)
        top.addWidget(QLabel("Filter tag:", styleSheet=LABEL_STYLE))
        self._tag_filter = QLineEdit()
        self._tag_filter.setPlaceholderText("e.g. working")
        self._tag_filter.setStyleSheet(INPUT_STYLE)
        self._tag_filter.setFixedWidth(140)
        top.addWidget(self._tag_filter)
        top.addStretch()
        self._btn_create = QPushButton("Create Snapshot")
        self._btn_create.setStyleSheet(save_btn_style())
        self._btn_create.setFixedHeight(34)
        self._btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        top.addWidget(self._btn_create)
        outer.addLayout(top)

        # Sub-tabs: DAG Tree | Storage | Diff | Sync — green underline, text only
        self._sub_tabs = QTabWidget()
        self._sub_tabs.setDocumentMode(True)
        self._sub_tabs.setStyleSheet(f"""
            QTabWidget {{ border: none; }}
            QTabWidget::pane {{ border: none; background: #1e1e1e; }}
            QTabBar {{ background: transparent; border: none; }}
            QTabBar::tab {{
                background: transparent; color: #6c7086;
                border: none; border-bottom: 2px solid transparent;
                padding: 10px 20px; font-size: 12px; font-weight: 500;
                font-family: {FONT_FAMILY};
            }}
            QTabBar::tab:selected {{ color: {TEXT_PRIMARY}; border-bottom: 2px solid {ACCENT}; }}
            QTabBar::tab:hover:!selected {{ color: #8a9e90; }}
        """)
        self._diff_panel = SnapshotDiffPanel()
        self._sub_tabs.addTab(self._build_dag_tab(), "DAG Tree")
        self._sub_tabs.addTab(self._build_storage_tab(), "Storage")
        self._sub_tabs.addTab(self._diff_panel, "Diff")
        self._sub_tabs.addTab(self._build_sync_tab(), "Sync")
        outer.addWidget(self._sub_tabs, 1)

        # Bottom action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        _BTN = (f"QPushButton {{ background-color: #313244; color: {TEXT_PRIMARY};"
                f" border: none; border-radius: 6px; padding: 0 16px;"
                f" font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY}; }}"
                f"QPushButton:hover {{ background-color: #45475a; }}")
        self._btn_restore = QPushButton("Restore")
        self._btn_restore.setStyleSheet(_BTN)
        self._btn_restore.setFixedHeight(40)
        self._btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setStyleSheet(_BTN)
        self._btn_delete.setFixedHeight(40)
        self._btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_clone = QPushButton("Clone VM")
        self._btn_clone.setStyleSheet(_BTN)
        self._btn_clone.setFixedHeight(40)
        self._btn_clone.setCursor(Qt.CursorShape.PointingHandCursor)
        for b in (self._btn_restore, self._btn_delete, self._btn_clone):
            btn_row.addWidget(b)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        # Connect shared signals
        self._btn_create.clicked.connect(self._on_create)
        self._btn_restore.clicked.connect(self._on_restore)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_clone.clicked.connect(lambda: self.clone_requested.emit())
        self._branch_combo.currentTextChanged.connect(self._on_branch_switch)
        self._tag_filter.textChanged.connect(self._dag.set_tag_filter if hasattr(self, '_dag') else lambda t: None)

    # -- DAG tab --
    def _build_dag_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(0)
        # Full-width DAG canvas
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BG_DEEP}; }}")
        self._dag = SnapshotDAGCanvas()
        scroll.setWidget(self._dag)
        lay.addWidget(scroll, 1)
        # Click shows details in modal dialog
        self._dag.node_clicked.connect(self._on_node_clicked)
        self._dag.node_double_clicked.connect(self._on_node_dblclicked)
        self._dag.node_right_clicked.connect(self._on_node_right_click)
        # Wire tag filter after _dag exists
        self._tag_filter.textChanged.connect(self._dag.set_tag_filter)
        return w

    # -- Storage tab (Task 5) --
    def _build_storage_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("DISK CHAIN USAGE", styleSheet=SECTION_LABEL_STYLE))
        self._storage_bar = StorageBarWidget()
        lay.addWidget(self._storage_bar)
        self._storage_table = QLabel("")
        self._storage_table.setWordWrap(True)
        self._storage_table.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px;")
        lay.addWidget(self._storage_table)
        self._storage_total = QLabel("")
        self._storage_total.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(self._storage_total)
        br = QHBoxLayout()
        self._btn_flatten = QPushButton("Flatten Chain")
        self._btn_flatten.setStyleSheet(subtle_btn_style())
        self._btn_flatten.setFixedHeight(30)
        self._btn_flatten.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_flatten.clicked.connect(self._on_flatten)
        br.addWidget(self._btn_flatten)
        br.addStretch()
        lay.addLayout(br)
        lay.addStretch()
        return w

    # -- Sync tab (Task 6) --
    def _build_sync_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("SNAPSHOT SYNC", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Export snapshots to a local path or NAS via rsync.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        # Mode
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Mode:", styleSheet=LABEL_STYLE))
        self._sync_mode = QComboBox()
        self._sync_mode.setStyleSheet(COMBO_STYLE)
        self._sync_mode.addItem("Local path", "local")
        self._sync_mode.addItem("rsync (NAS)", "rsync")
        self._sync_mode.setFixedWidth(160)
        r1.addWidget(self._sync_mode); r1.addStretch()
        lay.addLayout(r1)
        # Local path
        lp = QHBoxLayout()
        lp.addWidget(QLabel("Path:", styleSheet=LABEL_STYLE))
        self._sync_local = QLineEdit()
        self._sync_local.setPlaceholderText("/mnt/backup/vms")
        self._sync_local.setStyleSheet(INPUT_STYLE)
        lp.addWidget(self._sync_local, 1)
        self._sync_browse = QPushButton("Browse")
        self._sync_browse.setStyleSheet(subtle_btn_style())
        self._sync_browse.setFixedHeight(28)
        self._sync_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_browse.clicked.connect(self._browse_sync)
        lp.addWidget(self._sync_browse)
        lay.addLayout(lp)
        # rsync fields
        for attr, ph in [("_sync_host", "nas.local"),
                         ("_sync_user", "user"),
                         ("_sync_rpath", "/volume1/vms")]:
            r = QHBoxLayout()
            r.addWidget(QLabel(attr.replace("_sync_", "").capitalize() + ":", styleSheet=LABEL_STYLE))
            inp = QLineEdit(); inp.setPlaceholderText(ph); inp.setStyleSheet(INPUT_STYLE)
            setattr(self, attr, inp)
            r.addWidget(inp, 1)
            lay.addLayout(r)
        self._auto_sync = QCheckBox("Sync on every snapshot creation")
        self._auto_sync.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; }}")
        lay.addWidget(self._auto_sync)
        self._sync_info = QLabel("")
        self._sync_info.setWordWrap(True)
        self._sync_info.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._sync_info)
        self._sync_progress = QProgressBar()
        self._sync_progress.setFixedHeight(18)
        self._sync_progress.setStyleSheet(f"""
            QProgressBar {{ background: {BG_CARD}; border: 1px solid {BORDER};
                           border-radius: 4px; color: {TEXT_PRIMARY}; font-size: 9px; text-align: center; }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}""")
        self._sync_progress.hide()
        lay.addWidget(self._sync_progress)
        sr = QHBoxLayout()
        self._btn_save_sync = QPushButton("Save Config")
        self._btn_save_sync.setStyleSheet(save_btn_style())
        self._btn_save_sync.setFixedHeight(28)
        self._btn_save_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_sync_now = QPushButton("Sync Now")
        self._btn_sync_now.setStyleSheet(subtle_btn_style())
        self._btn_sync_now.setFixedHeight(28)
        self._btn_sync_now.setCursor(Qt.CursorShape.PointingHandCursor)
        sr.addWidget(self._btn_save_sync); sr.addWidget(self._btn_sync_now); sr.addStretch()
        lay.addLayout(sr)
        lay.addStretch()
        self._btn_save_sync.clicked.connect(self._save_sync_cfg)
        self._btn_sync_now.clicked.connect(self._do_sync)
        self._load_sync_cfg()
        return w

    # ── Public API ─────────────────────────────────────────────────────

    def set_vm(self, vm_id: str, disk_path: str = "", vm_name: str = "") -> None:
        self._vm_id = vm_id
        self._disk_path = disk_path
        self._vm_name = vm_name
        self._current_snap_id = None
        self._diff_panel.set_vm(vm_id, disk_path)
        self._refresh()

    def set_enabled(self, enabled: bool) -> None:
        self._is_running = enabled
        self._btn_create.setEnabled(enabled)
        self._btn_restore.setEnabled(enabled)
        self._btn_delete.setEnabled(enabled)

    def set_snapshots(self, names: list[str]) -> None:
        """Compat shim — called by main_window after QMP ops."""
        self._refresh()

    def get_current_branch(self) -> str:
        return self._current_branch

    # ── Refresh ────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if not self._vm_id:
            return
        snaps = load_snapshots(self._vm_id)
        branches = get_branches(self._vm_id)
        self._branch_combo.blockSignals(True)
        self._branch_combo.clear()
        for b in branches:
            self._branch_combo.addItem(b)
        idx = self._branch_combo.findText(self._current_branch)
        if idx >= 0:
            self._branch_combo.setCurrentIndex(idx)
        self._branch_combo.blockSignals(False)
        self._dag.set_data(snaps, branches, self._current_snap_id)
        self._refresh_storage(snaps)

    # ── Storage (Task 5) ───────────────────────────────────────────────

    def _refresh_storage(self, snaps: list[dict]) -> None:
        segs: list[tuple[str, float, str]] = []
        lines = [f"{'Name':<24} {'Delta MB':>10} {'Cumul MB':>10}"]
        lines.append("-" * 46)
        # Base image size — try qemu-img info first
        base_mb = 0.0
        if self._disk_path and Path(self._disk_path).exists():
            base_mb = self._qemu_img_size(self._disk_path)
            if base_mb == 0:
                try:
                    base_mb = Path(self._disk_path).stat().st_size / (1024 * 1024)
                except OSError:
                    pass
            segs.append(("base", base_mb, _BRANCH_HUES[0]))
            lines.append(f"{'[base image]':<24} {base_mb:>10.1f} {base_mb:>10.1f}")
        cumul = base_mb
        for i, s in enumerate(snaps):
            d = s.get("disk_size_mb", 0)
            cumul += d
            col = _BRANCH_HUES[(i + 1) % len(_BRANCH_HUES)]
            segs.append((s["name"][:14], max(d, 0.1), col))
            lines.append(f"{s['name'][:24]:<24} {d:>10.1f} {cumul:>10.1f}")
        self._storage_bar.set_segments(segs)
        self._storage_table.setText("\n".join(lines))
        self._storage_total.setText(f"Total chain: {cumul:.1f} MB")

    @staticmethod
    def _qemu_img_size(path: str) -> float:
        try:
            out = subprocess.check_output(
                ["qemu-img", "info", "--output=json", path],
                timeout=10, stderr=subprocess.DEVNULL)
            info = json.loads(out)
            return info.get("actual-size", 0) / (1024 * 1024)
        except Exception:
            return 0.0

    # ── DAG interactions (Tasks 1-3) ───────────────────────────────────

    def _on_node_clicked(self, snap_id: str) -> None:
        self._current_snap_id = snap_id
        s = get_snap_by_id(self._vm_id, snap_id)
        snaps = load_snapshots(self._vm_id)
        self._dag.set_data(snaps, get_branches(self._vm_id), snap_id)
        if s:
            self._show_detail_dialog(s)

    def _show_detail_dialog(self, s: dict) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Snapshot Details")
        dlg.setFixedSize(360, 300)
        dlg.setStyleSheet(
            f"background-color: #313244; color: {TEXT_PRIMARY}; border-radius: 8px;")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(8)
        _L = f"color: {TEXT_SECONDARY}; font-size: 11px; letter-spacing: 1px; background: transparent;"
        _V = f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 500; background: transparent; font-family: {FONT_FAMILY};"
        for label, value in [
            ("NAME", s["name"]),
            ("TAG", s.get("tag") or "\u2014"),
            ("BRANCH", s.get("branch_name", "main")),
            ("CREATED", (s.get("created_at") or "")[:19].replace("T", " ")),
            ("SIZE", f"Disk: {s.get('disk_size_mb', 0):.1f} MB  RAM: {s.get('ram_size_mb', 0):.1f} MB"),
        ]:
            lay.addWidget(QLabel(label, styleSheet=_L))
            lay.addWidget(QLabel(value, styleSheet=_V))
        lay.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()

    def _on_node_dblclicked(self, snap_id: str) -> None:
        # Edit tag via input dialog
        tag, ok = QInputDialog.getText(self, "Edit Tag", "Tag:")
        if ok:
            self._on_tag_changed(snap_id, tag.strip())

    def _on_node_right_click(self, snap_id: str, gpos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};
                    border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 0; }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{ background-color: {BG_ELEVATED}; }}
        """)
        a_branch = menu.addAction("Branch from here")
        a_tag = menu.addAction("Edit tag")
        a_restore = menu.addAction("Restore")
        a_delete = menu.addAction("Delete")
        act = menu.exec(gpos)
        if act == a_branch:
            self._branch_from(snap_id)
        elif act == a_tag:
            self._on_node_dblclicked(snap_id)
        elif act == a_restore:
            self._current_snap_id = snap_id
            self._on_restore()
        elif act == a_delete:
            self._current_snap_id = snap_id
            self._on_delete()

    def _branch_from(self, snap_id: str) -> None:
        name, ok = QInputDialog.getText(self, "New Branch", "Branch name:")
        if not ok or not name.strip():
            return
        self._current_branch = name.strip()
        self._current_snap_id = snap_id
        self._refresh()
        self.branch_changed.emit(self._current_branch)

    def _on_branch_switch(self, text: str) -> None:
        if not text:
            return
        if self._is_running and text != self._current_branch:
            QMessageBox.warning(
                self, "VM Running",
                "Stop the VM before switching branches.\n"
                "Switching branches while running may corrupt snapshot state.")
            self._branch_combo.blockSignals(True)
            idx = self._branch_combo.findText(self._current_branch)
            if idx >= 0:
                self._branch_combo.setCurrentIndex(idx)
            self._branch_combo.blockSignals(False)
            return
        self._current_branch = text
        self.branch_changed.emit(text)

    def _on_tag_changed(self, snap_id: str, tag: str) -> None:
        update_snapshot(self._vm_id, snap_id, tag=tag)
        self._refresh()

    def _on_create(self) -> None:
        name, ok = QInputDialog.getText(self, "Create Snapshot", "Snapshot name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        add_snapshot(self._vm_id, name,
                     parent_id=self._current_snap_id,
                     branch_name=self._current_branch)
        self.snapshot_action.emit("create", name)
        cfg = load_sync_config()
        if cfg.get("auto_sync"):
            self._do_sync()

    def _on_restore(self) -> None:
        if not self._current_snap_id:
            return
        s = get_snap_by_id(self._vm_id, self._current_snap_id)
        if not s:
            return
        if QMessageBox.question(
                self, "Restore Snapshot", f"Restore '{s['name']}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.snapshot_action.emit("restore", s["name"])

    def _on_delete(self) -> None:
        if not self._current_snap_id:
            return
        s = get_snap_by_id(self._vm_id, self._current_snap_id)
        if not s:
            return
        if QMessageBox.question(
                self, "Delete Snapshot", f"Delete '{s['name']}'? Cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.snapshot_action.emit("delete", s["name"])
            delete_snapshot(self._vm_id, self._current_snap_id)
            self._current_snap_id = None
            self._refresh()

    # ── Flatten (Task 5) ───────────────────────────────────────────────

    def _on_flatten(self) -> None:
        if not self._disk_path:
            return
        if QMessageBox.warning(
                self, "Flatten Chain",
                "This merges ALL snapshots into a single flat image.\n"
                "This is IRREVERSIBLE. The VM must be stopped.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        src = self._disk_path
        dst = src + ".flat.qcow2"
        try:
            subprocess.run(["qemu-img", "convert", "-O", "qcow2", src, dst],
                           check=True, capture_output=True, timeout=600)
            os.replace(dst, src)
            save_snapshots(self._vm_id, [])
            self._current_snap_id = None
            self._refresh()
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            QMessageBox.critical(self, "Error", f"Flatten failed:\n{exc}")

    # ── Sync (Task 6) ─────────────────────────────────────────────────

    def _load_sync_cfg(self) -> None:
        cfg = load_sync_config()
        idx = self._sync_mode.findData(cfg.get("mode", "local"))
        if idx >= 0:
            self._sync_mode.setCurrentIndex(idx)
        self._sync_local.setText(cfg.get("local_path", ""))
        self._sync_host.setText(cfg.get("rsync_host", ""))
        self._sync_user.setText(cfg.get("rsync_user", ""))
        self._sync_rpath.setText(cfg.get("rsync_path", ""))
        self._auto_sync.setChecked(cfg.get("auto_sync", False))
        last = cfg.get("last_sync", "")
        free = ""
        lp = cfg.get("local_path", "")
        if lp and Path(lp).exists():
            try:
                u = shutil.disk_usage(lp)
                free = f"  |  Free: {u.free / (1024**3):.1f} GB"
            except OSError:
                pass
        self._sync_info.setText(f"Last sync: {last or 'never'}{free}")

    def _save_sync_cfg(self) -> None:
        old = load_sync_config()
        cfg = {
            "mode": self._sync_mode.currentData() or "local",
            "local_path": self._sync_local.text().strip(),
            "rsync_host": self._sync_host.text().strip(),
            "rsync_user": self._sync_user.text().strip(),
            "rsync_path": self._sync_rpath.text().strip(),
            "auto_sync": self._auto_sync.isChecked(),
            "last_sync": old.get("last_sync", ""),
        }
        save_sync_config(cfg)
        self._load_sync_cfg()

    def _browse_sync(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Sync Destination")
        if path:
            self._sync_local.setText(path)

    def _do_sync(self) -> None:
        if not self._disk_path:
            return
        self._save_sync_cfg()
        cfg = load_sync_config()
        snaps = load_snapshots(self._vm_id)
        if not snaps:
            self._sync_info.setText("No snapshots to sync.")
            return
        self._sync_progress.show()
        self._sync_progress.setMaximum(len(snaps))
        self._sync_progress.setValue(0)
        self._sigs = _SyncSignals()
        self._sigs.progress.connect(lambda d, _t: self._sync_progress.setValue(d))
        self._sigs.finished.connect(self._on_sync_done)
        self._sigs.error.connect(self._on_sync_err)
        threading.Thread(
            target=self._sync_worker,
            args=(cfg, snaps, self._disk_path, self._vm_name),
            daemon=True,
        ).start()

    def _sync_worker(self, cfg, snaps, disk_path, vm_name):
        from datetime import datetime as dt
        mode = cfg.get("mode", "local")
        dest_base = cfg.get("local_path", "") if mode == "local" else "/tmp/icosele-vault-sync"
        if not dest_base:
            self._sigs.error.emit("No destination path configured")
            return
        Path(dest_base).mkdir(parents=True, exist_ok=True)
        for i, s in enumerate(snaps):
            tag = s.get("tag") or s["name"]
            tag = "".join(c for c in tag if c.isalnum() or c in "-_.")
            date_str = dt.now().strftime("%Y%m%d")
            fname = f"{vm_name}_{tag}_{date_str}.qcow2"
            dest = os.path.join(dest_base, fname)
            try:
                subprocess.run(
                    ["qemu-img", "convert", "-c", "-O", "qcow2", disk_path, dest],
                    check=True, capture_output=True, timeout=600)
            except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
                self._sigs.error.emit(str(exc))
                return
            self._sigs.progress.emit(i + 1, len(snaps))
        if mode == "rsync":
            host = cfg.get("rsync_host", "")
            user = cfg.get("rsync_user", "")
            rpath = cfg.get("rsync_path", "")
            if host and rpath:
                target = f"{user}@{host}:{rpath}" if user else f"{host}:{rpath}"
                try:
                    subprocess.run(["rsync", "-avz", dest_base + "/", target],
                                   check=True, capture_output=True, timeout=600)
                except (subprocess.SubprocessError, FileNotFoundError) as exc:
                    self._sigs.error.emit(f"rsync failed: {exc}")
                    return
        self._sigs.finished.emit(dt.now().isoformat()[:19])

    def _on_sync_done(self, timestamp: str) -> None:
        self._sync_progress.hide()
        cfg = load_sync_config()
        cfg["last_sync"] = timestamp
        save_sync_config(cfg)
        self._sync_info.setText(f"Last sync: {timestamp}")

    def _on_sync_err(self, msg: str) -> None:
        self._sync_progress.hide()
        self._sync_info.setText(f"Sync error: {msg}")
