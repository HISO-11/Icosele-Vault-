from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from app.ui.theme import ACCENT, ACCENT_LIGHT, BG_DEEP, BG_PANEL, BORDER, FONT_FAMILY, TEXT_PRIMARY, TEXT_SECONDARY

GRID_COLOR = "#2e3432"
MAX_POINTS = 30


class LineGraph(QWidget):
    def __init__(self, title: str, unit: str, max_value: float,
                 color: str = ACCENT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.max_value = max_value
        self.line_color = QColor(color)
        self._data: deque[float] = deque(maxlen=MAX_POINTS)
        self.setMinimumHeight(170)

    def add_point(self, value: float) -> None:
        self._data.append(value)
        self.update()

    def clear_data(self) -> None:
        self._data.clear()
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_DEEP))
        ml, mr, mt, mb = 48, 16, 36, 28
        gx, gy, gw, gh = ml, mt, w - ml - mr, h - mt - mb
        if gw < 10 or gh < 10:
            p.end()
            return
        p.setPen(QColor(TEXT_PRIMARY))
        p.setFont(QFont("Inter", 10, QFont.Weight.DemiBold))
        p.drawText(QRectF(ml, 6, gw, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        if self._data:
            p.setPen(QColor(self.line_color))
            p.drawText(QRectF(ml, 6, gw, 24), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        f"{self._data[-1]:.1f} {self.unit}")
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(gx, gy, gw, gh), 4, 4)
        p.setFont(QFont("Inter", 8))
        for i in range(1, 4):
            frac = i / 4.0
            y = gy + gh * (1.0 - frac)
            p.setPen(QPen(QColor(GRID_COLOR), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(gx + 1, y), QPointF(gx + gw - 1, y))
            p.setPen(QColor(TEXT_SECONDARY))
            p.drawText(QRectF(0, y - 8, ml - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        f"{self.max_value * frac:.0f}")
        p.setPen(QColor(TEXT_SECONDARY))
        p.drawText(QRectF(0, gy + gh - 8, ml - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "0")
        p.drawText(QRectF(gx, gy + gh + 6, gw, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "now")
        p.drawText(QRectF(gx, gy + gh + 6, gw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "-60s")
        if len(self._data) < 2:
            p.end()
            return
        points = [QPointF(gx + (i / (MAX_POINTS - 1)) * gw,
                           gy + gh * (1.0 - min(val / self.max_value, 1.0) if self.max_value > 0 else 0))
                  for i, val in enumerate(self._data)]
        fill = QPainterPath()
        fill.moveTo(QPointF(points[0].x(), gy + gh))
        for pt in points:
            fill.lineTo(pt)
        fill.lineTo(QPointF(points[-1].x(), gy + gh))
        fill.closeSubpath()
        fc = QColor(self.line_color)
        fc.setAlpha(20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fc)
        p.drawPath(fill)
        pen = QPen(self.line_color, 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        lp = QPainterPath()
        lp.moveTo(points[0])
        for pt in points[1:]:
            lp.lineTo(pt)
        p.drawPath(lp)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.line_color)
        p.drawEllipse(points[-1], 3, 3)
        p.end()


class PerformancePanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)
        self.cpu_graph = LineGraph("CPU Usage", "%", 100.0, ACCENT)
        self.ram_graph = LineGraph("RAM Usage", "MB", 2048.0, ACCENT_LIGHT)
        layout.addWidget(self.cpu_graph)
        layout.addWidget(self.ram_graph)
        layout.addStretch()

    def set_ram_max(self, max_mb: float) -> None:
        self.ram_graph.max_value = max_mb

    def add_cpu_point(self, percent: float) -> None:
        self.cpu_graph.add_point(percent)

    def add_ram_point(self, used_mb: float) -> None:
        self.ram_graph.add_point(used_mb)

    def clear(self) -> None:
        self.cpu_graph.clear_data()
        self.ram_graph.clear_data()

    def apply_theme(self) -> None:
        from app.ui import theme
        self.setStyleSheet(f"background-color: {theme.get('BG_PANEL')}; border: none;")
