"""Task 3 — Snapshot timeline visualisation with horizontal scrollable axis."""
from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QVBoxLayout, QWidget,
)

from app.snapshot_store import load_snapshots, get_branches
from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL,
    BORDER, FONT_FAMILY, SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, subtle_btn_style,
)

_BRANCH_HUES = [
    "#a6e3a1", "#89b4fa", "#cba6f7", "#f9e2af",
    "#fab387", "#f38ba8", "#94e2d5", "#74c7ec",
]


class TimelineCanvas(QWidget):
    node_clicked = Signal(str)
    node_right_clicked = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._snaps: list[dict] = []
        self._branches: list[str] = ["main"]
        self._current_id: str | None = None
        self._zoom = 1.0
        self._node_x: dict[str, float] = {}
        self.setMinimumHeight(180)
        self.setMouseTracking(True)

    def set_data(self, snaps, branches, current_id=None):
        self._snaps = list(snaps)
        self._branches = branches or ["main"]
        self._current_id = current_id
        self._layout()
        self.update()

    def wheelEvent(self, ev: QWheelEvent):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            d = ev.angleDelta().y()
            self._zoom = max(0.3, min(5.0, self._zoom * (1.2 if d > 0 else 1 / 1.2)))
            self._layout()
            self.update()
            ev.accept()
        else:
            super().wheelEvent(ev)

    def _layout(self):
        self._node_x.clear()
        if not self._snaps:
            return
        spacing = 120 * self._zoom
        for i, s in enumerate(self._snaps):
            self._node_x[s["id"]] = 60 + i * spacing
        total_w = 60 + len(self._snaps) * spacing + 60
        self.setMinimumWidth(int(total_w))

    def _hit(self, pos):
        y_center = self.height() / 2
        for sid, x in self._node_x.items():
            if abs(pos.x() - x) < 14 and abs(pos.y() - y_center) < 14:
                return sid
        return None

    def mousePressEvent(self, ev):
        pt = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        sid = self._hit(pt)
        if sid:
            if ev.button() == Qt.MouseButton.RightButton:
                self.node_right_clicked.emit(sid, self.mapToGlobal(pt))
            else:
                self.node_clicked.emit(sid)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_DEEP))
        if not self._snaps:
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Inter", 11))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "No snapshots")
            p.end()
            return

        y_mid = h / 2
        branch_lanes: dict[str, int] = {}
        for s in self._snaps:
            b = s.get("branch_name", "main")
            if b not in branch_lanes:
                branch_lanes[b] = len(branch_lanes)

        # Timeline axis
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(QPointF(30, y_mid), QPointF(w - 30, y_mid))

        # Today marker
        p.setPen(QPen(QColor(ACCENT), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(w - 50, 30), QPointF(w - 50, h - 10))
        p.setFont(QFont("Inter", 7))
        p.setPen(QColor(ACCENT))
        p.drawText(QRectF(w - 80, h - 18, 60, 14), Qt.AlignmentFlag.AlignCenter, "today")

        # Edges
        id_map = {s["id"]: s for s in self._snaps}
        for s in self._snaps:
            pid = s.get("parent_id")
            if pid and pid in self._node_x and s["id"] in self._node_x:
                bci = branch_lanes.get(s.get("branch_name", "main"), 0)
                col = _BRANCH_HUES[bci % len(_BRANCH_HUES)]
                p.setPen(QPen(QColor(col), 2))
                py_off = branch_lanes.get(id_map[pid].get("branch_name", "main"), 0) * 24
                cy_off = bci * 24
                p.drawLine(QPointF(self._node_x[pid], y_mid - 40 + py_off),
                           QPointF(self._node_x[s["id"]], y_mid - 40 + cy_off))

        # Nodes
        for s in self._snaps:
            if s["id"] not in self._node_x:
                continue
            x = self._node_x[s["id"]]
            bci = branch_lanes.get(s.get("branch_name", "main"), 0)
            y = y_mid - 40 + bci * 24
            col = _BRANCH_HUES[bci % len(_BRANCH_HUES)]
            is_cur = s["id"] == self._current_id
            disk = max(s.get("disk_size_mb", 0), 1)
            radius = max(6, min(16, 6 + disk / 50))

            p.setPen(QPen(QColor(ACCENT if is_cur else col), 2.5 if is_cur else 1.5))
            p.setBrush(QColor("#1e1e2e"))
            p.drawEllipse(QPointF(x, y), radius, radius)

            # Name below
            p.setPen(QColor(TEXT_PRIMARY if is_cur else TEXT_SECONDARY))
            p.setFont(QFont("Inter", 7, QFont.Weight.Bold if is_cur else QFont.Weight.Normal))
            fm = p.fontMetrics()
            name = fm.elidedText(s["name"], Qt.TextElideMode.ElideRight, 80)
            p.drawText(QRectF(x - 40, y + radius + 3, 80, 14),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, name)

            # Date above
            p.setFont(QFont("Inter", 6))
            p.setPen(QColor(TEXT_MUTED))
            date_str = (s.get("created_at") or "")[:10]
            p.drawText(QRectF(x - 40, y - radius - 16, 80, 12),
                       Qt.AlignmentFlag.AlignHCenter, date_str)

            # Tag pill
            tag = s.get("tag", "")
            if tag:
                p.setFont(QFont("Inter", 6, QFont.Weight.Bold))
                tw = fm.horizontalAdvance(tag) + 8
                pill_x = x - tw / 2
                pill_y = y + radius + 18
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col))
                p.drawRoundedRect(QRectF(pill_x, pill_y, tw, 11), 3, 3)
                p.setPen(QColor("#1e1e2e"))
                p.drawText(QRectF(pill_x, pill_y, tw, 11), Qt.AlignmentFlag.AlignCenter, tag)

        p.end()


class TimelinePanel(QFrame):
    snapshot_action = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_id = ""
        self._current_snap_id = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(QLabel("SNAPSHOT TIMELINE", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Ctrl+Scroll to zoom. Click a node for details. Right-click for actions.")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        lay.addWidget(desc)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BG_DEEP}; }}")
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._canvas = TimelineCanvas()
        scroll.setWidget(self._canvas)
        lay.addWidget(scroll, 1)
        # Detail bar
        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background-color: {BG_CARD};"
            f" border: 1px solid {BORDER}; border-radius: 6px; padding: 8px;")
        self._detail.setFixedHeight(50)
        lay.addWidget(self._detail)
        self._canvas.node_clicked.connect(self._on_click)
        self._canvas.node_right_clicked.connect(self._on_right_click)

    def set_vm(self, vm_id: str):
        self._vm_id = vm_id
        self.refresh()

    def refresh(self):
        snaps = load_snapshots(self._vm_id)
        branches = get_branches(self._vm_id)
        self._canvas.set_data(snaps, branches, self._current_snap_id)

    def _on_click(self, snap_id):
        self._current_snap_id = snap_id
        snaps = load_snapshots(self._vm_id)
        s = next((x for x in snaps if x["id"] == snap_id), None)
        if s:
            self._detail.setText(
                f"{s['name']}  |  {(s.get('created_at') or '')[:19].replace('T', ' ')}  |  "
                f"Branch: {s.get('branch_name', 'main')}  |  "
                f"Tag: {s.get('tag') or '—'}  |  "
                f"Disk: {s.get('disk_size_mb', 0):.1f} MB  |  Parent: {s.get('parent_id') or '(root)'}")
        self._canvas.set_data(snaps, get_branches(self._vm_id), snap_id)

    def _on_right_click(self, snap_id, gpos):
        from PySide6.QtWidgets import QMenu, QInputDialog
        snaps = load_snapshots(self._vm_id)
        s = next((x for x in snaps if x["id"] == snap_id), None)
        if not s:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 0; }}"
            f"QMenu::item {{ padding: 6px 20px; }}"
            f"QMenu::item:selected {{ background-color: {BG_ELEVATED}; }}")
        a_restore = menu.addAction("Restore")
        a_delete = menu.addAction("Delete")
        a_tag = menu.addAction("Edit tag")
        act = menu.exec(gpos)
        if act == a_restore:
            self.snapshot_action.emit("restore", s["name"])
        elif act == a_delete:
            self.snapshot_action.emit("delete", s["name"])
            from app.snapshot_store import delete_snapshot
            delete_snapshot(self._vm_id, snap_id)
            self.refresh()
        elif act == a_tag:
            tag, ok = QInputDialog.getText(self, "Edit Tag", "Tag:")
            if ok:
                from app.snapshot_store import update_snapshot
                update_snapshot(self._vm_id, snap_id, tag=tag.strip())
                self.refresh()
