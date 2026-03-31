"""Task 1 — Natural language VM management chat panel."""
from __future__ import annotations

import json
import logging
import threading
import webbrowser

from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.ollama_client import check_available, query, extract_json
from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL,
    BORDER, FONT_FAMILY, INPUT_STYLE, SECTION_LABEL_STYLE,
    TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an AI assistant embedded in Icosele VM, a VM management "
    "application. You help users manage their virtual machines. You have "
    "access to the following VM data: {vm_list_json}. When the user asks "
    "to perform an action, respond with a JSON block in this exact format: "
    '{"action": "start|stop|pause|snapshot|clone|quarantine|create_vm|diagnose|none", '
    '"vm_name": "name or null", "snapshot_name": "name or null", '
    '"create_config": {"os": "ubuntu/windows/fedora/etc", "ram_mb": 4096, "cpu_cores": 4, "disk_gb": 40} or null, '
    '"message": "friendly explanation to show the user"}. '
    "When the user asks to create a VM (e.g. 'create a Ubuntu VM with 4GB RAM'), "
    "set action to create_vm and fill create_config with extracted values. "
    "When the user reports an error, set action to diagnose and message should contain the fix. "
    "For questions that don't need an action, set action to none. Always be concise."
)


class _Signals(QObject):
    response = Signal(str)
    error = Signal(str)


class AIAssistantPanel(QFrame):
    action_requested = Signal(str, str, str)  # action, vm_name, snapshot_name
    create_vm_requested = Signal(dict)  # create_config dict
    diagnose_requested = Signal(str)  # error text for AI diagnosis

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_data_fn = None  # callable returning list[dict]
        self._messages: list[tuple[str, str]] = []  # (role, text)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(QLabel("AI ASSISTANT", styleSheet=SECTION_LABEL_STYLE))

        # Ollama unavailable banner
        self._unavail = QWidget()
        ub_lay = QVBoxLayout(self._unavail)
        ub_lay.setContentsMargins(0, 0, 0, 0)
        ub_lay.setSpacing(6)
        ub_msg = QLabel(
            "Ollama is not running. Install at ollama.com to enable AI features.")
        ub_msg.setWordWrap(True)
        ub_msg.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 10px; color: {WARNING}; font-size: 12px;")
        ub_lay.addWidget(ub_msg)
        btn_get = QPushButton("Get Ollama")
        btn_get.setStyleSheet(subtle_btn_style())
        btn_get.setFixedHeight(28)
        btn_get.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_get.clicked.connect(lambda: webbrowser.open("https://ollama.com"))
        ub_lay.addWidget(btn_get)
        self._unavail.hide()
        lay.addWidget(self._unavail)

        # Chat history
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {BORDER}; border-radius: 6px;"
            f" background: {BG_DEEP}; }}")
        self._chat_widget = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_widget)
        self._chat_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_layout.setSpacing(6)
        self._chat_layout.addStretch()
        self._scroll.setWidget(self._chat_widget)
        lay.addWidget(self._scroll, 1)

        # Typing indicator
        self._typing = QLabel("AI is thinking...")
        self._typing.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-style: italic;"
            f" background: transparent; padding: 2px 4px;")
        self._typing.hide()
        lay.addWidget(self._typing)

        # Input row
        inp_row = QHBoxLayout()
        inp_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask about your VMs... (e.g. 'start my ubuntu VM')")
        self._input.setStyleSheet(INPUT_STYLE)
        self._input.returnPressed.connect(self._on_send)
        inp_row.addWidget(self._input, 1)
        self._btn_send = QPushButton("Send")
        self._btn_send.setStyleSheet(f"""
            QPushButton {{
                background-color: #F47B1F; color: {TEXT_ON_ACCENT};
                border: none; border-radius: 6px; padding: 8px 20px;
                font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{ background-color: #FF922B; }}
        """)
        self._btn_send.setFixedHeight(34)
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.clicked.connect(self._on_send)
        inp_row.addWidget(self._btn_send)
        lay.addLayout(inp_row)

    def set_vm_data_provider(self, fn):
        self._vm_data_fn = fn

    def _get_vm_json(self) -> str:
        if not self._vm_data_fn:
            return "[]"
        try:
            data = self._vm_data_fn()
            return json.dumps(data)
        except Exception:
            return "[]"

    def _add_bubble(self, role: str, text: str):
        self._messages.append((role, text))
        is_user = role == "user"
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if is_user:
            bubble.setStyleSheet(
                f"background-color: {BG_ELEVATED}; color: {TEXT_PRIMARY};"
                f" border-radius: 8px; padding: 8px 12px; font-size: 12px;"
                f" font-family: {FONT_FAMILY}; margin-left: 40px;")
        else:
            bubble.setStyleSheet(
                f"background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
                f" border: 1px solid {BORDER}; border-radius: 8px;"
                f" padding: 8px 12px; font-size: 12px;"
                f" font-family: {FONT_FAMILY}; margin-right: 40px;")
        idx = self._chat_layout.count() - 1  # before the stretch
        self._chat_layout.insertWidget(idx, bubble)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))

    def _on_send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()

        if not check_available():
            self._unavail.show()
            return
        self._unavail.hide()
        self._add_bubble("user", text)
        self._btn_send.setEnabled(False)
        self._typing.show()

        sigs = _Signals()
        sigs.response.connect(self._on_response)
        sigs.error.connect(self._on_error)
        self._sigs = sigs

        vm_json = self._get_vm_json()
        system = _SYSTEM_PROMPT.replace("{vm_list_json}", vm_json)
        threading.Thread(
            target=self._worker, args=(text, system, sigs), daemon=True
        ).start()

    @staticmethod
    def _worker(prompt, system, sigs):
        try:
            raw = query(prompt, system=system, timeout=60)
            sigs.response.emit(raw)
        except Exception as exc:
            sigs.error.emit(str(exc))

    def _on_response(self, raw: str):
        self._btn_send.setEnabled(True)
        self._typing.hide()
        parsed = extract_json(raw)
        if parsed and "message" in parsed:
            msg = parsed["message"]
            action = parsed.get("action", "none")
            vm_name = parsed.get("vm_name") or ""
            snap_name = parsed.get("snapshot_name") or ""
            self._add_bubble("ai", msg)
            if action == "create_vm" and parsed.get("create_config"):
                self.create_vm_requested.emit(parsed["create_config"])
            elif action and action != "none" and action != "diagnose":
                self.action_requested.emit(action, vm_name, snap_name)
        else:
            self._add_bubble("ai", raw[:500])

    def diagnose_error(self, error_text: str) -> None:
        """Send a QEMU error to AI for diagnosis."""
        if not check_available():
            return
        prompt = f"This QEMU error occurred: {error_text}. What is the fix? Be concise."
        self._add_bubble("user", f"[Auto-diagnosis] {error_text[:200]}")
        self._btn_send.setEnabled(False)
        self._typing.show()
        sigs = _Signals()
        sigs.response.connect(self._on_response)
        sigs.error.connect(self._on_error)
        self._sigs = sigs
        threading.Thread(
            target=self._worker, args=(prompt, _SYSTEM_PROMPT, sigs), daemon=True
        ).start()

    def _on_error(self, msg: str):
        self._btn_send.setEnabled(True)
        self._typing.hide()
        self._add_bubble("ai", f"Error: {msg}")
