"""VM Clone dialog — linked (fast CoW) or full (independent copy)."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QVBoxLayout,
)

from app.snapshot_store import copy_snapshots
from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY,
    INPUT_STYLE, LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    primary_btn_style, secondary_btn_style,
)
from config.vm_config import VMConfig, _SCHEMA

log = logging.getLogger(__name__)


class _Sig(QObject):
    finished = Signal(object)
    error = Signal(str)
    status = Signal(str)


class CloneDialog(QDialog):
    def __init__(self, config: VMConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.result_config: VMConfig | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle(f"Clone \u2014 {self.config.name}")
        self.setFixedSize(460, 340)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(12)

        title = QLabel("Clone Virtual Machine")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(title)
        sub = QLabel(f"Source: {self.config.name}")
        sub.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(sub)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("New name:", styleSheet=LABEL_STYLE))
        self._name = QLineEdit(f"{self.config.name} (clone)")
        self._name.setStyleSheet(INPUT_STYLE)
        r1.addWidget(self._name, 1)
        lay.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Mode:", styleSheet=LABEL_STYLE))
        self._mode = QComboBox()
        self._mode.setStyleSheet(COMBO_STYLE)
        self._mode.addItem("Linked Clone (fast, CoW overlay)", "linked")
        self._mode.addItem("Full Clone (independent copy)", "full")
        r2.addWidget(self._mode, 1)
        lay.addLayout(r2)

        desc = QLabel(
            "Linked clone shares the base disk (fast, small). "
            "Full clone is fully independent (slower, larger).")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic; background: transparent;")
        lay.addWidget(desc)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)

        self._prog = QProgressBar()
        self._prog.setFixedHeight(18)
        self._prog.setStyleSheet(f"""
            QProgressBar {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 4px;
                           color: {TEXT_PRIMARY}; font-size: 9px; text-align: center; }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}""")
        self._prog.hide()
        lay.addWidget(self._prog)
        lay.addStretch()

        br = QHBoxLayout()
        bc = QPushButton("Cancel")
        bc.setStyleSheet(secondary_btn_style())
        bc.setFixedHeight(34)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.clicked.connect(self.reject)
        self._btn = QPushButton("Clone")
        self._btn.setStyleSheet(primary_btn_style())
        self._btn.setFixedHeight(34)
        self._btn.setMinimumWidth(90)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._on_clone)
        br.addStretch(); br.addWidget(bc); br.addSpacing(8); br.addWidget(self._btn)
        lay.addLayout(br)

    def _on_clone(self) -> None:
        name = self._name.text().strip()
        if not name:
            self._status.setText("Name is required.")
            return
        if not self.config.disk_path:
            self._status.setText("Source VM has no disk to clone.")
            return
        self._btn.setEnabled(False)
        self._prog.show()
        self._prog.setMaximum(0)
        self._status.setText("Cloning...")
        self._sig = _Sig()
        self._sig.finished.connect(self._done)
        self._sig.error.connect(self._err)
        self._sig.status.connect(lambda m: self._status.setText(m))
        mode = self._mode.currentData() or "linked"
        threading.Thread(target=self._worker, args=(name, mode), daemon=True).start()

    def _worker(self, new_name: str, mode: str) -> None:
        try:
            src = self.config.disk_path
            ext = Path(src).suffix or ".qcow2"
            slug = "".join(c for c in new_name.lower().replace(" ", "-") if c.isalnum() or c in "-_")
            new_disk = os.path.join(str(Path(src).parent), f"{slug}{ext}")
            if mode == "linked":
                self._sig.status.emit("Creating linked clone (CoW overlay)...")
                subprocess.run(
                    ["qemu-img", "create", "-f", "qcow2", "-b", src, "-F", "qcow2", new_disk],
                    check=True, capture_output=True, timeout=60)
            else:
                self._sig.status.emit("Creating full clone (copying entire disk)...")
                subprocess.run(
                    ["qemu-img", "convert", "-p", "-O", "qcow2", src, new_disk],
                    check=True, capture_output=True, timeout=1200)
            self._sig.status.emit("Saving config...")
            data = asdict(self.config)
            data["name"] = new_name
            data["disk_path"] = new_disk
            cfg = VMConfig(**{k: v for k, v in data.items() if k in _SCHEMA})
            cfg.save()
            copy_snapshots(self.config.vm_id, cfg.vm_id)
            self._sig.finished.emit(cfg)
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            self._sig.error.emit(str(exc))

    def _done(self, cfg) -> None:
        self._prog.hide()
        self.result_config = cfg
        self._status.setText("Clone complete!")
        self._btn.setEnabled(True)
        self.accept()

    def _err(self, msg: str) -> None:
        self._prog.hide()
        self._status.setText(f"Error: {msg}")
        self._btn.setEnabled(True)
