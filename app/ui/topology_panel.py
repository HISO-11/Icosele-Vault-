from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from app.ui.theme import (
    ACCENT, BG_DEEP, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)

# Catppuccin Mocha-inspired node colors
_GATEWAY_COLOR = "#cba6f7"   # Mauve
_RUNNING_COLOR = "#a6e3a1"   # Green
_STOPPED_COLOR = "#585b70"   # Surface2
_LINE_COLOR = "#6c7086"      # Overlay1
_TEXT_COLOR = "#cdd6f4"       # Text
_SUBTEXT_COLOR = "#a6adc8"   # Subtext0
_RED_CROSS = "#f38ba8"       # Red


class TopologyCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(350)
        self._vm_nodes: list[dict] = []

    def set_nodes(self, nodes: list[dict]) -> None:
        self._vm_nodes = nodes
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_DEEP))

        cx, cy = w / 2, h / 2

        # Draw gateway node
        gw_r = 28
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_GATEWAY_COLOR))
        p.drawEllipse(QPointF(cx, cy), gw_r, gw_r)
        p.setPen(QColor("#1e1e2e"))
        p.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        p.drawText(QRectF(cx - gw_r, cy - gw_r, gw_r * 2, gw_r * 2),
                   Qt.AlignmentFlag.AlignCenter, "GW")
        p.setPen(QColor(_SUBTEXT_COLOR))
        p.setFont(QFont("Inter", 8))
        p.drawText(QRectF(cx - 50, cy + gw_r + 4, 100, 16),
                   Qt.AlignmentFlag.AlignCenter, "10.0.2.2")

        if not self._vm_nodes:
            p.setPen(QColor(_SUBTEXT_COLOR))
            p.setFont(QFont("Inter", 11))
            p.drawText(QRectF(0, h - 40, w, 30),
                       Qt.AlignmentFlag.AlignCenter, "No VMs configured")
            p.end()
            return

        n = len(self._vm_nodes)
        radius = min(w, h) * 0.33
        if radius < 80:
            radius = 80

        for i, node in enumerate(self._vm_nodes):
            angle = (2 * math.pi * i / n) - math.pi / 2
            nx = cx + radius * math.cos(angle)
            ny = cy + radius * math.sin(angle)

            running = node.get("running", False)
            line_color = QColor(_LINE_COLOR)
            node_color = QColor(_RUNNING_COLOR if running else _STOPPED_COLOR)

            # Draw connection line
            pen = QPen(line_color, 1.5)
            if not running:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(cx, cy), QPointF(nx, ny))

            # Draw node box
            box_w, box_h = 100, 52
            box_x = nx - box_w / 2
            box_y = ny - box_h / 2

            p.setPen(QPen(node_color, 2))
            p.setBrush(QColor("#1e1e2e"))
            p.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 6, 6)

            # VM name
            p.setPen(QColor(_TEXT_COLOR))
            p.setFont(QFont("Inter", 9, QFont.Weight.Bold))
            name = node.get("name", "VM")
            fm = p.fontMetrics()
            elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, int(box_w - 10))
            p.drawText(QRectF(box_x, box_y + 4, box_w, 20),
                       Qt.AlignmentFlag.AlignCenter, elided)

            # IP / DHCP
            p.setPen(QColor(_SUBTEXT_COLOR))
            p.setFont(QFont("Inter", 7))
            ip_text = node.get("ip", "DHCP")
            p.drawText(QRectF(box_x, box_y + 20, box_w, 14),
                       Qt.AlignmentFlag.AlignCenter, ip_text)

            # Network mode badge
            net_mode = node.get("net_mode", "user")
            badge_color = QColor(ACCENT) if net_mode == "user" else QColor("#89b4fa")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(badge_color)
            badge_w = fm.horizontalAdvance(net_mode) + 12
            badge_x = nx - badge_w / 2
            badge_y = box_y + box_h - 16
            p.drawRoundedRect(QRectF(badge_x, badge_y, badge_w, 14), 3, 3)
            p.setPen(QColor("#1e1e2e"))
            p.setFont(QFont("Inter", 7, QFont.Weight.Bold))
            p.drawText(QRectF(badge_x, badge_y, badge_w, 14),
                       Qt.AlignmentFlag.AlignCenter, net_mode)

            # Red X overlay on stopped VMs
            if not running:
                p.setPen(QPen(QColor(_RED_CROSS), 3))
                margin = 8
                p.drawLine(QPointF(box_x + margin, box_y + margin),
                           QPointF(box_x + box_w - margin, box_y + box_h - margin))
                p.drawLine(QPointF(box_x + box_w - margin, box_y + margin),
                           QPointF(box_x + margin, box_y + box_h - margin))

        p.end()


class TopologyPanel(QFrame):
    def __init__(self, configs=None, processes=None, qmp_conns=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._configs = configs or []
        self._processes = processes or {}
        self._qmp_conns = qmp_conns or {}
        self._build_ui()
        self._start_timer()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(8)

        from PySide6.QtWidgets import QLabel
        layout.addWidget(QLabel("NETWORK TOPOLOGY", styleSheet=SECTION_LABEL_STYLE))

        self._canvas = TopologyCanvas()
        layout.addWidget(self._canvas, 1)

    def _start_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(10000)

    def set_data(self, configs, processes, qmp_conns) -> None:
        self._configs = configs
        self._processes = processes
        self._qmp_conns = qmp_conns
        self.refresh()

    def refresh(self) -> None:
        from app.qemu.process import ProcessState
        nodes = []
        for cfg in self._configs:
            proc = self._processes.get(cfg.vm_id)
            running = bool(proc and proc.refresh_state() == ProcessState.RUNNING)

            ip = "DHCP"
            if running:
                qmp = self._qmp_conns.get(cfg.vm_id)
                if qmp and qmp.connected:
                    try:
                        resp = qmp.execute("guest-network-get-interfaces")
                        ifaces = resp.get("return", [])
                        for iface in ifaces:
                            for addr in iface.get("ip-addresses", []):
                                a = addr.get("ip-address", "")
                                if a and not a.startswith("127.") and addr.get("ip-address-type") == "ipv4":
                                    ip = a
                                    break
                            if ip != "DHCP":
                                break
                    except Exception:
                        pass

            nodes.append({
                "name": cfg.name,
                "running": running,
                "net_mode": cfg.net_mode,
                "ip": ip,
            })
        self._canvas.set_nodes(nodes)
