"""Task 2 — Isolated network simulation with fake internet server."""
from __future__ import annotations

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, STOP_RED, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING, save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_FAKE_HTML = """<!DOCTYPE html><html><head><title>Simulated Internet</title></head>
<body style="font-family:sans-serif;background:#1e1e2e;color:#cdd6f4;text-align:center;padding:60px">
<h1>Simulated Internet</h1>
<p>This is a fake response served by Icosele VM sandbox mode.</p>
<p>The VM has no real internet access.</p>
</body></html>"""


class _FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.request_count += 1
        url = self.path
        self.server.intercepted_urls.append(url)
        if len(self.server.intercepted_urls) > 200:
            self.server.intercepted_urls = self.server.intercepted_urls[-100:]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_FAKE_HTML.encode())

    do_POST = do_GET

    def log_message(self, fmt, *args):
        pass  # silence


class FakeInternetServer:
    def __init__(self):
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0
        self.request_count = 0
        self.intercepted_urls: list[str] = []

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> int:
        self._server = HTTPServer(("127.0.0.1", 0), _FakeHandler)
        self._server.request_count = 0
        self._server.intercepted_urls = []
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info("Fake internet server started on port %d", self.port)
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None
            log.info("Fake internet server stopped")

    def get_stats(self) -> tuple[int, list[str]]:
        if self._server:
            return self._server.request_count, list(self._server.intercepted_urls)
        return self.request_count, list(self.intercepted_urls)


class FakeInternetPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = FakeInternetServer()
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_stats)
        self._timer.start(2000)

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("NETWORK SIMULATION", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Run a fake internet server that responds to all HTTP requests with a "
            "dummy page. Malware will believe it has internet access while being "
            "fully contained.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        self._enable = QCheckBox("Enable Fake Internet")
        self._enable.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}")
        lay.addWidget(self._enable)

        # Status card
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(6)
        self._status_lbl = QLabel("Server: stopped")
        self._status_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        cl.addWidget(self._status_lbl)
        self._port_lbl = QLabel("")
        self._port_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        cl.addWidget(self._port_lbl)
        self._count_lbl = QLabel("Requests intercepted: 0")
        self._count_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        cl.addWidget(self._count_lbl)
        lay.addWidget(card)

        # Intercepted URLs log
        lay.addWidget(QLabel("INTERCEPTED URLS", styleSheet=SECTION_LABEL_STYLE))
        self._log_scroll = QScrollArea()
        self._log_scroll.setWidgetResizable(True)
        self._log_scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {BORDER}; border-radius: 6px; background: {BG_DEEP}; }}")
        self._log_scroll.setMaximumHeight(160)
        self._log_widget = QWidget()
        self._log_layout = QVBoxLayout(self._log_widget)
        self._log_layout.setContentsMargins(8, 8, 8, 8)
        self._log_layout.setSpacing(2)
        self._log_layout.addStretch()
        self._log_scroll.setWidget(self._log_widget)
        lay.addWidget(self._log_scroll)
        lay.addStretch()

        self._enable.toggled.connect(self._on_toggle)

    def _on_toggle(self, checked):
        if checked:
            port = self._server.start()
            self._status_lbl.setText("Server: RUNNING")
            self._status_lbl.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._port_lbl.setText(f"Listening on 127.0.0.1:{port}")
        else:
            self._server.stop()
            self._status_lbl.setText("Server: stopped")
            self._status_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._port_lbl.setText("")

    def _update_stats(self):
        count, urls = self._server.get_stats()
        self._count_lbl.setText(f"Requests intercepted: {count}")
        # Update URL log
        while self._log_layout.count() > 1:
            w = self._log_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        for url in urls[-20:]:
            lbl = QLabel(url)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px; font-family: monospace; background: transparent;")
            idx = self._log_layout.count() - 1
            self._log_layout.insertWidget(idx, lbl)

    def stop_server(self):
        self._server.stop()
