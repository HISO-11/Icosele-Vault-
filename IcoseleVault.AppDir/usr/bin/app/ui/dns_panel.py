from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    save_btn_style, subtle_btn_style,
)

_IP_RE = re.compile(
    r'^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$')


def _valid_ip(text: str) -> bool:
    return bool(_IP_RE.match(text.strip()))


DNS_PRESETS = {
    "system": {"label": "System Default", "dns": ""},
    "cloudflare": {"label": "Cloudflare", "dns": "1.1.1.1"},
    "google": {"label": "Google", "dns": "8.8.8.8"},
    "quad9": {"label": "Quad9", "dns": "9.9.9.9"},
    "none": {"label": "No DNS (isolated)", "dns": "0.0.0.0"},
}
PRESET_ORDER = ["system", "cloudflare", "google", "quad9", "none"]


class DNSPanel(QFrame):
    config_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("DNS CONFIGURATION", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Set custom DNS servers for this VM. The primary DNS is passed "
            "to QEMU's user-mode networking via the dns= parameter."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Quick preset buttons
        layout.addWidget(QLabel("PRESETS", styleSheet=SECTION_LABEL_STYLE))
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        for key in PRESET_ORDER:
            p = DNS_PRESETS[key]
            btn = QPushButton(p["label"])
            btn.setStyleSheet(subtle_btn_style())
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._apply_preset(k))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        # DNS inputs
        layout.addWidget(QLabel("CUSTOM DNS SERVERS", styleSheet=SECTION_LABEL_STYLE))

        self._dns_inputs: list[QLineEdit] = []
        labels = ["Primary DNS", "Secondary DNS", "Tertiary DNS"]
        for i, lbl_text in enumerate(labels):
            row = QHBoxLayout()
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
            lbl.setFixedWidth(100)
            inp = QLineEdit()
            inp.setPlaceholderText("e.g. 1.1.1.1")
            inp.setStyleSheet(INPUT_STYLE)
            inp.setFixedWidth(200)
            row.addWidget(lbl)
            row.addWidget(inp)
            row.addStretch()
            layout.addLayout(row)
            self._dns_inputs.append(inp)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            f"color: #c0392b; font-size: 11px; background: transparent;")
        layout.addWidget(self._error_label)

        # Save button
        br = QHBoxLayout()
        self._btn_save = QPushButton("Save")
        self._btn_save.setFixedHeight(34)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setStyleSheet(save_btn_style())
        br.addWidget(self._btn_save)
        br.addStretch()
        layout.addLayout(br)

        # QEMU args preview
        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self._args_preview = QLabel()
        self._args_preview.setWordWrap(True)
        self._args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self._args_preview)

        layout.addStretch()

        for inp in self._dns_inputs:
            inp.textChanged.connect(self._update_preview)
        self._btn_save.clicked.connect(self._on_save)
        self._update_preview()

    def set_config(self, dns_servers: list[str]) -> None:
        for i, inp in enumerate(self._dns_inputs):
            inp.blockSignals(True)
            inp.setText(dns_servers[i] if i < len(dns_servers) else "")
            inp.blockSignals(False)
        self._update_preview()

    def _apply_preset(self, key: str) -> None:
        dns = DNS_PRESETS[key]["dns"]
        self._dns_inputs[0].setText(dns)
        for inp in self._dns_inputs[1:]:
            inp.clear()
        self._update_preview()

    def _get_valid_servers(self) -> list[str]:
        servers = []
        for inp in self._dns_inputs:
            text = inp.text().strip()
            if text:
                servers.append(text)
        return servers

    def _update_preview(self) -> None:
        servers = self._get_valid_servers()
        if not servers:
            self._args_preview.setText("-netdev user,id=net0\n(using system DNS)")
            return
        primary = servers[0]
        self._args_preview.setText(f"-netdev user,id=net0,dns={primary}")

    def _on_save(self) -> None:
        servers = self._get_valid_servers()
        for s in servers:
            if not _valid_ip(s):
                self._error_label.setText(f"Invalid IP address: {s}")
                return
        self._error_label.setText("")
        self.config_changed.emit(servers)
