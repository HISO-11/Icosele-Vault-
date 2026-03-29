"""Task 4 — DNS filtering panel with local proxy."""
from __future__ import annotations

import logging
import queue
import socketserver
import struct
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_BLOCKLIST_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "dns_blocklists"

_PRESET_DOMAINS = {
    "ads": [
        "ad.doubleclick.net", "pagead2.googlesyndication.com",
        "ads.facebook.com", "analytics.google.com",
        "tracking.example.com", "adservice.google.com",
    ],
    "malware": [
        "malware.example.com", "phishing.example.com",
        "botnet-c2.example.com", "exploit-kit.example.com",
    ],
    "adult": [
        "adult-content.example.com", "nsfw-site.example.com",
    ],
}


def _load_blocklist(vm_id: str) -> list[str]:
    p = _BLOCKLIST_DIR / f"{vm_id}.txt"
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]


def _save_blocklist(vm_id: str, domains: list[str]) -> None:
    _BLOCKLIST_DIR.mkdir(parents=True, exist_ok=True)
    (_BLOCKLIST_DIR / f"{vm_id}.txt").write_text("\n".join(domains) + "\n")


def _extract_domain(data: bytes) -> str:
    """Extract queried domain from a raw DNS query packet."""
    try:
        offset = 12
        labels = []
        while offset < len(data):
            length = data[offset]
            if length == 0:
                break
            offset += 1
            labels.append(data[offset:offset + length].decode("ascii", errors="replace"))
            offset += length
        return ".".join(labels).lower()
    except Exception:
        return ""


class _DNSProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = self.request[0]
        sock = self.request[1]
        domain = _extract_domain(data)
        server = self.server
        if domain in server.blocked:
            server.block_count += 1
            if server.block_queue:
                server.block_queue.put(domain)
            return
        # Forward to upstream
        import socket as _sock
        try:
            upstream = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
            upstream.settimeout(3)
            upstream.sendto(data, (server.upstream_dns, 53))
            resp, _ = upstream.recvfrom(4096)
            upstream.close()
            sock.sendto(resp, self.client_address)
        except Exception:
            pass


class DNSProxy(socketserver.UDPServer):
    allow_reuse_address = True

    def __init__(self, upstream: str, blocked: set[str],
                 block_queue: queue.Queue | None = None):
        super().__init__(("127.0.0.1", 0), _DNSProxyHandler)
        self.upstream_dns = upstream
        self.blocked = blocked
        self.block_count = 0
        self.block_queue = block_queue


class DNSFilterPanel(QFrame):
    config_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_id = ""
        self._proxy: DNSProxy | None = None
        self._proxy_thread: threading.Thread | None = None
        self._block_queue: queue.Queue = queue.Queue()
        self._blocked_count = 0
        self._build_ui()
        self._start_counter_timer()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(QLabel("DNS FILTERING", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Block DNS queries for specific domains using a local UDP proxy. "
            "Blocked queries are silently dropped.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        self._enable_check = QCheckBox("Enable DNS filtering for this VM")
        self._enable_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}")
        layout.addWidget(self._enable_check)

        # Blocked count
        self._count_label = QLabel("Blocked queries: 0")
        self._count_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(self._count_label)

        # Preset buttons
        layout.addWidget(QLabel("PRESET BLOCKLISTS", styleSheet=SECTION_LABEL_STYLE))
        pr = QHBoxLayout()
        pr.setSpacing(8)
        for name in ("ads", "malware", "adult"):
            btn = QPushButton(name.capitalize())
            btn.setStyleSheet(subtle_btn_style())
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self._add_preset(n))
            pr.addWidget(btn)
        pr.addStretch()
        layout.addLayout(pr)

        # Domain editor
        layout.addWidget(QLabel("BLOCKED DOMAINS", styleSheet=SECTION_LABEL_STYLE))
        self._domain_edit = QTextEdit()
        self._domain_edit.setPlaceholderText("One domain per line, e.g.:\nad.example.com\ntracker.example.com")
        self._domain_edit.setStyleSheet(
            f"QTextEdit {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER}; border-radius: 6px;"
            f" padding: 8px; font-size: 12px; font-family: monospace; }}")
        self._domain_edit.setMaximumHeight(150)
        layout.addWidget(self._domain_edit)

        # Add single domain
        ar = QHBoxLayout()
        ar.setSpacing(6)
        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText("example.com")
        self._add_input.setStyleSheet(INPUT_STYLE)
        ar.addWidget(self._add_input, 1)
        self._btn_add = QPushButton("Add")
        self._btn_add.setStyleSheet(save_btn_style())
        self._btn_add.setFixedHeight(30)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        ar.addWidget(self._btn_add)
        layout.addLayout(ar)

        # Save
        sr = QHBoxLayout()
        self._btn_save = QPushButton("Save Blocklist")
        self._btn_save.setStyleSheet(save_btn_style())
        self._btn_save.setFixedHeight(30)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        sr.addWidget(self._btn_save)
        sr.addStretch()
        layout.addLayout(sr)
        layout.addStretch()

        self._btn_add.clicked.connect(self._on_add_domain)
        self._btn_save.clicked.connect(self._on_save)
        self._enable_check.toggled.connect(self._on_toggle)

    def set_config(self, enabled: bool, vm_id: str = "") -> None:
        self._vm_id = vm_id
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(enabled)
        self._enable_check.blockSignals(False)
        domains = _load_blocklist(vm_id)
        self._domain_edit.setPlainText("\n".join(domains))

    def _on_toggle(self, checked: bool) -> None:
        self.config_changed.emit(checked)

    def _add_preset(self, name: str) -> None:
        current = self._domain_edit.toPlainText().strip()
        existing = set(current.splitlines()) if current else set()
        for d in _PRESET_DOMAINS.get(name, []):
            existing.add(d)
        self._domain_edit.setPlainText("\n".join(sorted(existing)))

    def _on_add_domain(self) -> None:
        d = self._add_input.text().strip().lower()
        if not d:
            return
        current = self._domain_edit.toPlainText().strip()
        lines = current.splitlines() if current else []
        if d not in lines:
            lines.append(d)
        self._domain_edit.setPlainText("\n".join(lines))
        self._add_input.clear()

    def _on_save(self) -> None:
        domains = [l.strip().lower() for l in self._domain_edit.toPlainText().splitlines()
                   if l.strip() and not l.strip().startswith("#")]
        _save_blocklist(self._vm_id, domains)

    def _start_counter_timer(self) -> None:
        self._counter_timer = QTimer(self)
        self._counter_timer.timeout.connect(self._update_count)
        self._counter_timer.start(1000)

    def _update_count(self) -> None:
        while not self._block_queue.empty():
            try:
                self._block_queue.get_nowait()
                self._blocked_count += 1
            except queue.Empty:
                break
        self._count_label.setText(f"Blocked queries: {self._blocked_count}")
