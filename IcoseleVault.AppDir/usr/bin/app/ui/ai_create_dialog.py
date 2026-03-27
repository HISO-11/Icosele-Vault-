from __future__ import annotations

import json
import logging
import re
import threading
import urllib.request
import urllib.error
from typing import Any

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    primary_btn_style, secondary_btn_style,
)

log = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODEL = "llama3"

SYSTEM_PROMPT = (
    "You are a VM configuration assistant. Given a natural language description of a virtual machine, "
    "return ONLY a valid JSON object with these fields (no markdown, no explanation):\n"
    '{"name": "string", "os_type": "linux|windows", "ram_mb": int, "cpu_cores": int, '
    '"disk_gb": int, "enable_gpu_passthrough": bool, "machine_type": "q35|pc", '
    '"enable_hugepages": bool, "network_type": "user|tap"}\n'
    "Use sensible defaults for any field not specified. "
    "For Windows 11, always use machine_type q35."
)


def _check_ollama() -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _query_ollama(prompt: str) -> str:
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
        return data.get("response", "")


def _extract_json(text: str) -> dict | None:
    # Try to find JSON object in the response
    for m in re.finditer(r'\{[^{}]*\}', text, re.DOTALL):
        try:
            obj = json.loads(m.group())
            if "name" in obj or "ram_mb" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _fallback_parse(text: str) -> dict:
    result: dict[str, Any] = {}
    lower = text.lower()

    # OS detection
    if "windows 11" in lower or "win11" in lower or "win 11" in lower:
        result["os_type"] = "windows"
        result["machine_type"] = "q35"
        result["name"] = "Windows 11 VM"
    elif "windows 10" in lower or "win10" in lower or "win 10" in lower:
        result["os_type"] = "windows"
        result["machine_type"] = "q35"
        result["name"] = "Windows 10 VM"
    elif "windows" in lower:
        result["os_type"] = "windows"
        result["machine_type"] = "q35"
        result["name"] = "Windows VM"
    elif "ubuntu" in lower:
        result["os_type"] = "linux"
        result["name"] = "Ubuntu VM"
    elif "fedora" in lower:
        result["os_type"] = "linux"
        result["name"] = "Fedora VM"
    elif "arch" in lower:
        result["os_type"] = "linux"
        result["name"] = "Arch VM"
    elif "debian" in lower:
        result["os_type"] = "linux"
        result["name"] = "Debian VM"
    else:
        result["os_type"] = "linux"

    # Gaming => GPU passthrough
    if "gaming" in lower or "game" in lower:
        result["enable_gpu_passthrough"] = True
        if "name" not in result:
            result["name"] = "Gaming VM"
        elif "gaming" not in result.get("name", "").lower():
            result["name"] = result.get("name", "VM").replace(" VM", "") + " Gaming VM"

    # RAM detection: "16gb ram", "16 gb", "16gb"
    ram_match = re.search(r'(\d+)\s*(?:gb|g)\s*(?:ram|memory)?', lower)
    if ram_match:
        result["ram_mb"] = int(ram_match.group(1)) * 1024

    # CPU detection: "8 cores", "8 cpu", "8 vcpu"
    cpu_match = re.search(r'(\d+)\s*(?:core|cpu|vcpu|thread)', lower)
    if cpu_match:
        result["cpu_cores"] = int(cpu_match.group(1))

    # Disk detection: "100gb disk", "200gb storage"
    disk_match = re.search(r'(\d+)\s*(?:gb|g)\s*(?:disk|storage|ssd|hdd)', lower)
    if disk_match:
        result["disk_gb"] = int(disk_match.group(1))

    # GPU passthrough explicit
    if "gpu" in lower and "passthrough" in lower:
        result["enable_gpu_passthrough"] = True

    # Hugepages
    if "hugepage" in lower or "huge page" in lower:
        result["enable_hugepages"] = True

    # Network
    if "tap" in lower or "bridge" in lower:
        result["network_type"] = "tap"

    # Server hints
    if "server" in lower:
        if "name" not in result:
            result["name"] = "Server VM"
        result.setdefault("cpu_cores", 2)
        result.setdefault("ram_mb", 2048)

    return result


class _OllamaSignals(QObject):
    finished = Signal(dict)
    error = Signal(str)


class AICreateDialog(QDialog):
    result_values: dict | None = None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Create with AI")
        self.setFixedSize(540, 420)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        title = QLabel("Create VM with AI")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(title)

        sub = QLabel("Describe the VM you want in plain English.")
        sub.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(sub)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText(
            "e.g. Windows 11 gaming VM with 16GB RAM and GPU passthrough")
        self._input.setStyleSheet(
            f"QPlainTextEdit {{"
            f" background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER}; border-radius: 6px;"
            f" padding: 10px; font-size: 13px; font-family: {FONT_FAMILY};"
            f"}}"
            f"QPlainTextEdit:focus {{ border-color: {ACCENT}; }}")
        self._input.setMinimumHeight(80)
        self._input.setMaximumHeight(120)
        layout.addWidget(self._input)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._status)

        # Ollama-unavailable banner (hidden by default)
        self._unavail_banner = QWidget()
        self._unavail_banner.setStyleSheet("background: transparent;")
        ub_layout = QVBoxLayout(self._unavail_banner)
        ub_layout.setContentsMargins(0, 0, 0, 0)
        ub_layout.setSpacing(8)
        ub_msg = QLabel(
            "Ollama is not running. Install Ollama at ollama.com "
            "to enable AI-powered VM creation.")
        ub_msg.setWordWrap(True)
        ub_msg.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 10px; color: {WARNING}; font-size: 12px;")
        ub_layout.addWidget(ub_msg)
        ub_btns = QHBoxLayout()
        self._ollama_link_btn = QPushButton("Get Ollama")
        self._ollama_link_btn.setStyleSheet(primary_btn_style())
        self._ollama_link_btn.setFixedHeight(32)
        self._ollama_link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ollama_link_btn.clicked.connect(self._open_ollama_site)
        self._manual_btn = QPushButton("Create manually instead")
        self._manual_btn.setStyleSheet(secondary_btn_style())
        self._manual_btn.setFixedHeight(32)
        self._manual_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manual_btn.clicked.connect(self._on_manual)
        ub_btns.addWidget(self._ollama_link_btn)
        ub_btns.addWidget(self._manual_btn)
        ub_btns.addStretch()
        ub_layout.addLayout(ub_btns)
        self._unavail_banner.hide()
        layout.addWidget(self._unavail_banner)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(secondary_btn_style())
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        self._btn_generate = QPushButton("Generate")
        self._btn_generate.setStyleSheet(primary_btn_style())
        self._btn_generate.setFixedHeight(34)
        self._btn_generate.setMinimumWidth(100)
        self._btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_generate.clicked.connect(self._on_generate)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(8)
        btn_row.addWidget(self._btn_generate)
        layout.addLayout(btn_row)

    def _open_ollama_site(self) -> None:
        import webbrowser
        webbrowser.open("https://ollama.com")

    def _on_manual(self) -> None:
        self.result_values = {"_manual": True}
        self.accept()

    def _on_generate(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            self._status.setText("Please enter a description.")
            return

        self._btn_generate.setEnabled(False)
        self._status.setText("Checking Ollama availability...")
        self._unavail_banner.hide()

        self._signals = _OllamaSignals()
        self._signals.finished.connect(self._on_result)
        self._signals.error.connect(self._on_error)
        self._user_text = text

        thread = threading.Thread(target=self._worker, args=(text,), daemon=True)
        thread.start()

    def _worker(self, text: str) -> None:
        if not _check_ollama():
            # Fall back to rule-based parsing
            result = _fallback_parse(text)
            result["_fallback"] = True
            result["_ollama_unavailable"] = True
            self._signals.finished.emit(result)
            return
        try:
            raw = _query_ollama(text)
            parsed = _extract_json(raw)
            if parsed:
                self._signals.finished.emit(parsed)
            else:
                # Ollama returned non-JSON, use fallback
                result = _fallback_parse(text)
                result["_fallback"] = True
                self._signals.finished.emit(result)
        except Exception as exc:
            # Timeout or error, use fallback
            result = _fallback_parse(text)
            result["_fallback"] = True
            self._signals.finished.emit(result)

    def _on_result(self, values: dict) -> None:
        self._btn_generate.setEnabled(True)
        ollama_unavail = values.pop("_ollama_unavailable", False)
        was_fallback = values.pop("_fallback", False)

        if ollama_unavail:
            self._unavail_banner.show()

        if was_fallback:
            self._status.setText("Used rule-based parsing (Ollama unavailable or returned invalid JSON).")
        else:
            self._status.setText("AI configuration generated successfully.")

        self.result_values = values
        self.accept()

    def _on_error(self, msg: str) -> None:
        self._btn_generate.setEnabled(True)
        self._status.setText(f"Error: {msg}")
