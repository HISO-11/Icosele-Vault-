"""Task 3 — Team VM Library for sharing templates across LAN."""
from __future__ import annotations

import fcntl
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

import app.audit_log as audit
from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    LABEL_STYLE, SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, primary_btn_style, save_btn_style,
    secondary_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "team_library_path.txt"


def _get_library_path() -> str:
    if _SETTINGS_PATH.exists():
        return _SETTINGS_PATH.read_text().strip()
    return ""


def _set_library_path(path: str) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(path)


def _load_index(lib_path: str) -> list[dict]:
    idx_file = Path(lib_path) / "library_index.json"
    if not idx_file.exists():
        return []
    try:
        with open(idx_file, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(lib_path: str, entries: list[dict]) -> None:
    idx_file = Path(lib_path) / "library_index.json"
    Path(lib_path).mkdir(parents=True, exist_ok=True)
    with open(idx_file, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(entries, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


class _TemplateCard(QFrame):
    deploy_clicked = Signal(dict)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self._entry = entry
        self.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        nm = QLabel(f"{entry.get('name', '?')}  v{entry.get('version', '?')}")
        nm.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(nm)
        desc = entry.get("description", "")
        if desc:
            dl = QLabel(desc[:80])
            dl.setWordWrap(True)
            dl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
            lay.addWidget(dl)
        meta = f"by {entry.get('author', '?')}  |  {entry.get('date', '')[:10]}"
        ml = QLabel(meta)
        ml.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        lay.addWidget(ml)
        btn = QPushButton("Deploy")
        btn.setStyleSheet(save_btn_style())
        btn.setFixedHeight(24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.deploy_clicked.emit(self._entry))
        lay.addWidget(btn)


class TeamLibraryPanel(QFrame):
    deploy_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("TEAM VM LIBRARY", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Shared VM templates published to a team folder on the LAN.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Library path
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Library path:", styleSheet=LABEL_STYLE))
        self._path_input = QLineEdit(_get_library_path())
        self._path_input.setStyleSheet(INPUT_STYLE)
        self._path_input.setPlaceholderText("/mnt/nas/vm-library")
        pr.addWidget(self._path_input, 1)
        self._btn_browse = QPushButton("Browse")
        self._btn_browse.setStyleSheet(subtle_btn_style())
        self._btn_browse.setFixedHeight(28)
        self._btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browse.clicked.connect(self._browse)
        pr.addWidget(self._btn_browse)
        self._btn_save_path = QPushButton("Save")
        self._btn_save_path.setStyleSheet(save_btn_style())
        self._btn_save_path.setFixedHeight(28)
        self._btn_save_path.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save_path.clicked.connect(self._save_path)
        pr.addWidget(self._btn_save_path)
        lay.addLayout(pr)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search templates...")
        self._search.setStyleSheet(INPUT_STYLE)
        self._search.textChanged.connect(lambda: self.refresh())
        lay.addWidget(self._search)

        # Buttons
        br = QHBoxLayout()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setStyleSheet(subtle_btn_style())
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.clicked.connect(self.refresh)
        br.addWidget(self._btn_refresh)
        br.addStretch()
        lay.addLayout(br)

        # Template grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BG_PANEL}; }}")
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(10)
        self._scroll.setWidget(self._grid_widget)
        lay.addWidget(self._scroll, 1)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Team Library Folder")
        if path:
            self._path_input.setText(path)

    def _save_path(self):
        _set_library_path(self._path_input.text().strip())

    def refresh(self):
        while self._grid_layout.count():
            w = self._grid_layout.takeAt(0).widget()
            if w: w.deleteLater()
        lib = _get_library_path()
        if not lib:
            return
        query = self._search.text().strip().lower()
        entries = _load_index(lib)
        filtered = [e for e in entries if not query or query in e.get("name", "").lower()]
        for i, e in enumerate(filtered):
            card = _TemplateCard(e)
            card.deploy_clicked.connect(self.deploy_requested.emit)
            self._grid_layout.addWidget(card, i // 2, i % 2)

    def publish(self, vm_name: str, vm_id: str, disk_path: str, config_dict: dict):
        lib = _get_library_path()
        if not lib:
            return
        from PySide6.QtWidgets import QInputDialog
        version, ok = QInputDialog.getText(None, "Publish", "Version tag:")
        if not ok or not version:
            return
        desc, ok2 = QInputDialog.getText(None, "Publish", "Description:")
        ts = datetime.now().strftime("%Y%m%d")
        folder_name = f"{vm_name}_{version}_{ts}"
        dest = Path(lib) / folder_name
        dest.mkdir(parents=True, exist_ok=True)
        # Compress disk
        out_disk = str(dest / "disk.qcow2")
        try:
            subprocess.run(
                ["qemu-img", "convert", "-c", "-O", "qcow2", disk_path, out_disk],
                check=True, capture_output=True, timeout=600)
        except (subprocess.SubprocessError, FileNotFoundError):
            return
        # Save config
        (dest / "config.json").write_text(json.dumps(config_dict, indent=2))
        # Update index
        entries = _load_index(lib)
        entries.append({
            "name": vm_name, "version": version, "description": desc or "",
            "author": os.environ.get("USER", "unknown"),
            "date": datetime.now(timezone.utc).isoformat(),
            "folder": folder_name, "disk_path": out_disk,
        })
        _save_index(lib, entries)
        audit.record("team_library_publish", vm_id, vm_name,
                      {"version": version, "library": lib})
