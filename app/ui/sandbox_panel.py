"""Task 1 — Malware sandbox panel with isolation controls."""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

import app.audit_log as audit
from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, SECTION_LABEL_STYLE,
    STOP_RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sandbox"


class SandboxPanel(QFrame):
    reset_baseline = Signal()
    snapshot_action = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_id = ""
        self._vm_name = ""
        self._is_sandbox = False
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(12)

        # Red sandbox banner
        self._banner = QLabel("SANDBOX MODE — FULLY ISOLATED")
        self._banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner.setFixedHeight(36)
        self._banner.setStyleSheet(
            f"background-color: {STOP_RED}; color: #ffffff; font-size: 14px;"
            f" font-weight: 800; font-family: {FONT_FAMILY}; border-radius: 0;")
        self._banner.hide()
        lay.addWidget(self._banner)

        lay.addWidget(QLabel("MALWARE SANDBOX", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "This VM is configured for malware analysis. Network is isolated, "
            "clipboard sync is disabled, USB passthrough is off, and shared "
            "folders are disabled. A clean-baseline snapshot should be taken "
            "before first boot.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Status card
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(6)
        self._status = QLabel("Sandbox mode: inactive")
        self._status.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        cl.addWidget(self._status)
        self._drop_count = QLabel("Files dropped: 0")
        self._drop_count.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        cl.addWidget(self._drop_count)
        lay.addWidget(card)

        # Action buttons
        br = QHBoxLayout()
        br.setSpacing(8)
        self._btn_drop = QPushButton("Drop File for Analysis")
        self._btn_drop.setStyleSheet(save_btn_style())
        self._btn_drop.setFixedHeight(32)
        self._btn_drop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset = QPushButton("Reset to Baseline")
        self._btn_reset.setStyleSheet(
            f"QPushButton {{ background-color: {STOP_RED}; color: #fff;"
            f" border: none; border-radius: 6px; padding: 8px 16px;"
            f" font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY}; }}"
            f"QPushButton:hover {{ background-color: #e74c3c; }}")
        self._btn_reset.setFixedHeight(32)
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_report = QPushButton("Generate Report")
        self._btn_report.setStyleSheet(subtle_btn_style())
        self._btn_report.setFixedHeight(32)
        self._btn_report.setCursor(Qt.CursorShape.PointingHandCursor)
        br.addWidget(self._btn_drop)
        br.addWidget(self._btn_reset)
        br.addWidget(self._btn_report)
        br.addStretch()
        lay.addLayout(br)

        # Instructions
        self._instructions = QLabel("")
        self._instructions.setWordWrap(True)
        self._instructions.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        lay.addWidget(self._instructions)
        lay.addStretch()

        self._btn_drop.clicked.connect(self._on_drop)
        self._btn_reset.clicked.connect(self._on_reset)
        self._btn_report.clicked.connect(self._on_report)

    def set_vm(self, vm_id: str, vm_name: str, is_sandbox: bool):
        self._vm_id = vm_id
        self._vm_name = vm_name
        self._is_sandbox = is_sandbox
        self._banner.setVisible(is_sandbox)
        if is_sandbox:
            self._status.setText("Sandbox mode: ACTIVE")
            self._status.setStyleSheet(
                f"color: {STOP_RED}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
        else:
            self._status.setText("Sandbox mode: inactive (not a sandbox VM)")
            self._status.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
        self._refresh_drop_count()

    def _incoming_dir(self) -> Path:
        d = _SANDBOX_DIR / self._vm_id / "incoming"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _refresh_drop_count(self):
        d = _SANDBOX_DIR / self._vm_id / "incoming"
        count = len(list(d.iterdir())) if d.exists() else 0
        self._drop_count.setText(f"Files dropped: {count}")

    def _on_drop(self):
        if not self._vm_id:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select File for Analysis")
        if not path:
            return
        dest = self._incoming_dir() / Path(path).name
        shutil.copy2(path, dest)
        self._refresh_drop_count()
        self._instructions.setText(
            f"File copied to: {dest}\n"
            f"Inside the VM, mount the staging folder or use virtio-fs "
            f"to access files from data/sandbox/{self._vm_id}/incoming/")
        audit.record("sandbox_file_dropped", self._vm_id, self._vm_name,
                     {"file": Path(path).name})

    def _on_reset(self):
        self.snapshot_action.emit("restore", "clean-baseline")
        audit.record("sandbox_reset", self._vm_id, self._vm_name)

    def _on_report(self):
        if not self._vm_id:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"sandbox_report_{self._vm_id}.txt",
            "Text Files (*.txt)")
        if not path:
            return
        d = _SANDBOX_DIR / self._vm_id / "incoming"
        files = [f.name for f in d.iterdir()] if d.exists() else []
        entries = audit.load_entries()
        vm_entries = [e for e in entries if e.get("vm_id") == self._vm_id]
        lines = [
            f"Malware Sandbox Report",
            f"=" * 40,
            f"VM: {self._vm_name}",
            f"Date: {datetime.now(timezone.utc).isoformat()[:19]}",
            f"Files dropped: {len(files)}",
        ]
        for f in files:
            lines.append(f"  - {f}")
        lines.append(f"\nAudit log entries ({len(vm_entries)}):")
        for e in vm_entries[-30:]:
            lines.append(f"  {e.get('timestamp', '')[:19]}  {e.get('action', '')}")
        Path(path).write_text("\n".join(lines))
