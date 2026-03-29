"""Tasks 6 & 7 — Dashboard with activity feed, quick stats, and resource charts."""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from app.audit_log import load_entries
from PySide6.QtCore import Signal

from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL,
    BORDER, FONT_FAMILY, SECTION_LABEL_STYLE, STOP_RED, SUCCESS,
    TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

_VM_COLORS = [
    "#a6e3a1", "#89b4fa", "#cba6f7", "#f9e2af",
    "#fab387", "#f38ba8", "#94e2d5", "#74c7ec",
]

_ACTION_ICONS = {
    "vm_started": ("\u25b6", SUCCESS),
    "vm_stopped": ("\u25a0", STOP_RED),
    "vm_created": ("+", ACCENT),
    "vm_deleted": ("\u2717", STOP_RED),
    "vm_crashed": ("\u26a0", WARNING),
    "snapshot_create": ("\u2b24", ACCENT_LIGHT),
    "snapshot_restore": ("\u21ba", ACCENT),
    "snapshot_delete": ("\u2715", TEXT_MUTED),
    "vm_cloned": ("\u2398", ACCENT_LIGHT),
    "network_quarantine": ("\u2622", STOP_RED),
    "encryption_enabled": ("\U0001f512", ACCENT),
    "firewall_changed": ("\u2694", WARNING),
}


def _time_ago(ts_str: str) -> str:
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            m = secs // 60
            return f"{m}m ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h}h ago"
        d = secs // 86400
        return f"{d}d ago"
    except (ValueError, TypeError):
        return ""


class _StatCard(QFrame):
    def __init__(self, label: str, value: str = "0", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px;")
        self.setFixedHeight(72)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 24px; font-weight: 900;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._lbl = QLabel(label.upper())
        self._lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700;"
            f" letter-spacing: 1.5px; background: transparent;")
        lay.addWidget(self._val)
        lay.addWidget(self._lbl)

    def set_value(self, v: str):
        self._val.setText(v)


class ResourceBarWidget(QWidget):
    """Horizontal stacked bar for CPU or RAM allocation."""
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._title = title
        self._segments: list[tuple[str, float, str]] = []
        self._total = 1.0
        self.setMinimumHeight(40)
        self.setMaximumHeight(40)

    def set_data(self, segments: list[tuple[str, float, str]], total: float):
        self._segments = segments
        self._total = max(total, 0.01)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_DEEP))
        # Title
        p.setPen(QColor(TEXT_MUTED))
        p.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        p.drawText(QRectF(4, 0, 100, 14), Qt.AlignmentFlag.AlignLeft, self._title)
        bar_y, bar_h = 16, h - 18
        x = 0.0
        for label, val, color in self._segments:
            seg_w = max((val / self._total) * w, 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, bar_y, seg_w - 1, bar_h), 3, 3)
            if seg_w > 30:
                p.setPen(QColor("#1e1e2e"))
                p.setFont(QFont("Inter", 6, QFont.Weight.Bold))
                p.drawText(QRectF(x, bar_y, seg_w - 1, bar_h), Qt.AlignmentFlag.AlignCenter, label)
            x += seg_w
        p.end()


class DiskPieWidget(QWidget):
    """Simple pie chart for disk usage."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._slices: list[tuple[str, float, str]] = []
        self.setMinimumSize(120, 120)
        self.setMaximumSize(120, 120)

    def set_data(self, slices: list[tuple[str, float, str]]):
        self._slices = slices
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_PANEL))
        total = sum(s[1] for s in self._slices) or 1
        rect = QRectF(4, 4, w - 8, h - 8)
        start = 90 * 16  # Start from top
        for name, val, color in self._slices:
            span = int((val / total) * 360 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawPie(rect, start, span)
            start += span
        p.end()


class DashboardPanel(QFrame):
    create_requested = Signal()
    start_all_requested = Signal()
    stop_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._configs = []
        self._processes = {}
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 16)
        lay.setSpacing(16)

        # Title
        title = QLabel("Dashboard")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 28px; font-weight: 900;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(title)

        # Quick Stats row
        lay.addWidget(QLabel("QUICK STATS", styleSheet=SECTION_LABEL_STYLE))
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self._stat_total = _StatCard("Total VMs")
        self._stat_running = _StatCard("Running")
        self._stat_stopped = _StatCard("Stopped")
        self._stat_snaps = _StatCard("Snapshots")
        self._stat_disk = _StatCard("Disk Usage")
        for s in (self._stat_total, self._stat_running, self._stat_stopped,
                  self._stat_snaps, self._stat_disk):
            s.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            stats_row.addWidget(s)
        lay.addLayout(stats_row)

        # Quick Actions
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        self._btn_new = QPushButton("+ New VM")
        self._btn_new.setStyleSheet(save_btn_style())
        self._btn_new.setFixedHeight(34)
        self._btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start_all = QPushButton("Start All")
        self._btn_start_all.setStyleSheet(subtle_btn_style())
        self._btn_start_all.setFixedHeight(34)
        self._btn_start_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop_all = QPushButton("Stop All")
        self._btn_stop_all.setStyleSheet(subtle_btn_style())
        self._btn_stop_all.setFixedHeight(34)
        self._btn_stop_all.setCursor(Qt.CursorShape.PointingHandCursor)
        for b in (self._btn_new, self._btn_start_all, self._btn_stop_all):
            act_row.addWidget(b)
        act_row.addStretch()
        lay.addLayout(act_row)

        # Resource charts row
        lay.addWidget(QLabel("RESOURCE ALLOCATION", styleSheet=SECTION_LABEL_STYLE))
        res_row = QHBoxLayout()
        res_row.setSpacing(12)
        charts_col = QVBoxLayout()
        charts_col.setSpacing(8)
        self._cpu_bar = ResourceBarWidget("CPU CORES")
        self._ram_bar = ResourceBarWidget("RAM (MB)")
        charts_col.addWidget(self._cpu_bar)
        charts_col.addWidget(self._ram_bar)
        res_row.addLayout(charts_col, 2)
        self._disk_pie = DiskPieWidget()
        pie_col = QVBoxLayout()
        pie_col.addWidget(QLabel("DISK", styleSheet=SECTION_LABEL_STYLE))
        pie_col.addWidget(self._disk_pie)
        self._disk_total_lbl = QLabel("")
        self._disk_total_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        pie_col.addWidget(self._disk_total_lbl)
        pie_col.addStretch()
        res_row.addLayout(pie_col, 1)
        lay.addLayout(res_row)

        # Activity Feed
        lay.addWidget(QLabel("RECENT ACTIVITY", styleSheet=SECTION_LABEL_STYLE))
        self._feed_area = QScrollArea()
        self._feed_area.setWidgetResizable(True)
        self._feed_area.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {BORDER}; border-radius: 6px; background: {BG_CARD}; }}")
        self._feed_widget = QWidget()
        self._feed_layout = QVBoxLayout(self._feed_widget)
        self._feed_layout.setContentsMargins(8, 8, 8, 8)
        self._feed_layout.setSpacing(4)
        self._feed_area.setWidget(self._feed_widget)
        lay.addWidget(self._feed_area, 1)

        self._btn_new.clicked.connect(lambda: self.create_requested.emit())
        self._btn_start_all.clicked.connect(lambda: self.start_all_requested.emit())
        self._btn_stop_all.clicked.connect(lambda: self.stop_all_requested.emit())

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)

    def set_data(self, configs, processes):
        self._configs = configs
        self._processes = processes
        self.refresh()

    def refresh(self):
        from app.qemu.process import ProcessState
        from app.snapshot_store import load_snapshots

        total = len(self._configs)
        running = sum(1 for c in self._configs
                      if c.vm_id in self._processes and
                      self._processes[c.vm_id].refresh_state() == ProcessState.RUNNING)
        stopped = total - running
        total_snaps = sum(len(load_snapshots(c.vm_id)) for c in self._configs)
        total_disk = 0.0
        for c in self._configs:
            if c.disk_path and Path(c.disk_path).exists():
                try:
                    total_disk += Path(c.disk_path).stat().st_size / (1024**3)
                except OSError:
                    pass

        self._stat_total.set_value(str(total))
        self._stat_running.set_value(str(running))
        self._stat_stopped.set_value(str(stopped))
        self._stat_snaps.set_value(str(total_snaps))
        self._stat_disk.set_value(f"{total_disk:.1f} GB")

        # CPU bar
        try:
            host_cpus = os.cpu_count() or 4
        except Exception:
            host_cpus = 4
        cpu_segs = []
        for i, c in enumerate(self._configs):
            if c.vm_id in self._processes:
                p = self._processes[c.vm_id]
                if p.state == ProcessState.RUNNING:
                    col = _VM_COLORS[i % len(_VM_COLORS)]
                    cpu_segs.append((c.name[:8], c.cpu_cores, col))
        self._cpu_bar.set_data(cpu_segs, host_cpus)

        # RAM bar
        try:
            import psutil
            host_ram = psutil.virtual_memory().total / (1024**2)
        except ImportError:
            host_ram = 16384
        ram_segs = []
        for i, c in enumerate(self._configs):
            if c.vm_id in self._processes:
                p = self._processes[c.vm_id]
                if p.state == ProcessState.RUNNING:
                    col = _VM_COLORS[i % len(_VM_COLORS)]
                    ram_segs.append((c.name[:8], c.ram_mb, col))
        self._ram_bar.set_data(ram_segs, host_ram)

        # Disk pie
        disk_slices = []
        for i, c in enumerate(self._configs):
            if c.disk_path and Path(c.disk_path).exists():
                try:
                    sz = Path(c.disk_path).stat().st_size / (1024**2)
                    col = _VM_COLORS[i % len(_VM_COLORS)]
                    disk_slices.append((c.name[:10], sz, col))
                except OSError:
                    pass
        self._disk_pie.set_data(disk_slices)
        self._disk_total_lbl.setText(f"Total: {total_disk:.1f} GB")

        # Activity feed
        while self._feed_layout.count():
            w = self._feed_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        entries = load_entries()[-50:]
        for e in reversed(entries):
            action = e.get("action", "")
            icon, color = _ACTION_ICONS.get(action, ("\u2022", TEXT_MUTED))
            vm = e.get("vm_name", "")
            ago = _time_ago(e.get("timestamp", ""))
            row = QLabel(f'<span style="color:{color}">{icon}</span>  '
                         f'<b>{action.replace("_", " ")}</b>  '
                         f'{vm}  '
                         f'<span style="color:{TEXT_MUTED}">{ago}</span>')
            row.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;"
                f" padding: 3px 0; font-family: {FONT_FAMILY};")
            row.setTextFormat(Qt.TextFormat.RichText)
            self._feed_layout.addWidget(row)
        self._feed_layout.addStretch()

