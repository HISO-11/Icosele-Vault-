"""Task 3 — VM Archaeology panel: historical OS library."""
from __future__ import annotations

import json
import logging
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL, BORDER,
    COMBO_STYLE, FONT_FAMILY, INPUT_STYLE, LABEL_STYLE,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING, primary_btn_style, save_btn_style,
    secondary_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_LIB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "archaeology_library.json"

_DEFAULT_LIBRARY = [
    {"name": "MS-DOS 6.22", "year": 1994, "machine": "pc", "ram_mb": 16, "cpu": 1,
     "display": "std", "notes": "Use freedos.org for legal free image",
     "extra_args": []},
    {"name": "Windows 95", "year": 1995, "machine": "pc", "ram_mb": 64, "cpu": 1,
     "display": "std", "notes": "Requires original licence",
     "extra_args": ["-no-acpi"]},
    {"name": "Windows 98 SE", "year": 1999, "machine": "pc", "ram_mb": 128, "cpu": 1,
     "display": "std", "notes": "", "extra_args": []},
    {"name": "Windows XP", "year": 2001, "machine": "pc", "ram_mb": 512, "cpu": 1,
     "display": "std", "notes": "Requires original licence", "extra_args": []},
    {"name": "Ubuntu 4.10 Warty", "year": 2004, "machine": "pc", "ram_mb": 256, "cpu": 1,
     "display": "std", "notes": "", "extra_args": []},
    {"name": "FreeDOS 1.3", "year": 2022, "machine": "pc", "ram_mb": 64, "cpu": 1,
     "display": "std", "iso_url": "https://www.freedos.org/download/",
     "notes": "Free and open source", "extra_args": []},
    {"name": "ReactOS 0.4", "year": 2023, "machine": "pc", "ram_mb": 512, "cpu": 1,
     "display": "std", "iso_url": "https://reactos.org/download/",
     "notes": "Free open-source Windows-compatible OS", "extra_args": []},
    {"name": "Haiku R1", "year": 2022, "machine": "pc", "ram_mb": 512, "cpu": 2,
     "display": "std", "iso_url": "https://www.haiku-os.org/get-haiku/",
     "notes": "Spiritual successor to BeOS", "extra_args": []},
    {"name": "TempleOS", "year": 2017, "machine": "pc", "ram_mb": 512, "cpu": 1,
     "display": "std", "iso_url": "https://templeos.org",
     "notes": "Terry Davis' divine operating system", "extra_args": []},
]


def load_library() -> list[dict]:
    if _LIB_PATH.exists():
        try:
            data = json.loads(_LIB_PATH.read_text())
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return list(_DEFAULT_LIBRARY)


def save_library(entries: list[dict]) -> None:
    _LIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LIB_PATH.write_text(json.dumps(entries, indent=2))


def _ensure_library() -> None:
    if not _LIB_PATH.exists():
        save_library(_DEFAULT_LIBRARY)


class _OSCard(QFrame):
    create_clicked = Signal(dict)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self._entry = entry
        self.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        name = QLabel(f"{entry['name']}  ({entry.get('year', '?')})")
        name.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(name)
        specs = f"RAM: {entry.get('ram_mb', '?')} MB  |  CPU: {entry.get('cpu', 1)}  |  Machine: {entry.get('machine', 'pc')}"
        sp = QLabel(specs)
        sp.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        lay.addWidget(sp)
        notes = entry.get("notes", "")
        if notes:
            nl = QLabel(notes)
            nl.setWordWrap(True)
            nl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-style: italic; background: transparent;")
            lay.addWidget(nl)
        br = QHBoxLayout()
        br.setSpacing(6)
        iso_url = entry.get("iso_url", "")
        if iso_url:
            ib = QPushButton("Get ISO")
            ib.setStyleSheet(subtle_btn_style())
            ib.setFixedHeight(24)
            ib.setCursor(Qt.CursorShape.PointingHandCursor)
            ib.clicked.connect(lambda: webbrowser.open(iso_url))
            br.addWidget(ib)
        cb = QPushButton("Create VM")
        cb.setStyleSheet(save_btn_style())
        cb.setFixedHeight(24)
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.clicked.connect(lambda: self.create_clicked.emit(self._entry))
        br.addWidget(cb)
        br.addStretch()
        lay.addLayout(br)


class ArchaeologyPanel(QFrame):
    create_vm_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        _ensure_library()
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("VM ARCHAEOLOGY — HISTORICAL OS LIBRARY", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "A curated collection of historical operating systems with the correct "
            "QEMU settings to run each one. Obtain ISOs legally from the linked sources.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Search bar
        sr = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search OS library...")
        self._search.setStyleSheet(INPUT_STYLE)
        self._search.textChanged.connect(self._refresh)
        sr.addWidget(self._search, 1)
        self._btn_add = QPushButton("+ Add Custom")
        self._btn_add.setStyleSheet(subtle_btn_style())
        self._btn_add.setFixedHeight(30)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add.clicked.connect(self._on_add_custom)
        sr.addWidget(self._btn_add)
        lay.addLayout(sr)

        # Grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BG_PANEL}; }}")
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(10)
        self._scroll.setWidget(self._grid_widget)
        lay.addWidget(self._scroll, 1)

    def _refresh(self):
        while self._grid_layout.count():
            w = self._grid_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        query = self._search.text().strip().lower() if hasattr(self, "_search") else ""
        entries = load_library()
        filtered = [e for e in entries if not query or query in e.get("name", "").lower()]
        for i, entry in enumerate(filtered):
            card = _OSCard(entry)
            card.create_clicked.connect(self.create_vm_requested.emit)
            self._grid_layout.addWidget(card, i // 2, i % 2)

    def _on_add_custom(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Custom OS Entry")
        dlg.setFixedSize(400, 340)
        dlg.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 16, 20, 12)
        lay.setSpacing(8)
        form = QFormLayout()
        form.setSpacing(6)
        _n = QLineEdit(); _n.setStyleSheet(INPUT_STYLE)
        _y = QSpinBox(); _y.setRange(1970, 2030); _y.setValue(2000); _y.setStyleSheet(INPUT_STYLE)
        _r = QSpinBox(); _r.setRange(1, 131072); _r.setValue(512); _r.setSuffix(" MB"); _r.setStyleSheet(INPUT_STYLE)
        _c = QSpinBox(); _c.setRange(1, 32); _c.setValue(1); _c.setStyleSheet(INPUT_STYLE)
        _u = QLineEdit(); _u.setStyleSheet(INPUT_STYLE); _u.setPlaceholderText("https://...")
        _nt = QLineEdit(); _nt.setStyleSheet(INPUT_STYLE)
        for lbl, w in [("Name", _n), ("Year", _y), ("RAM", _r), ("CPUs", _c),
                        ("ISO URL", _u), ("Notes", _nt)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE)
            form.addRow(l, w)
        lay.addLayout(form)
        lay.addStretch()
        br = QHBoxLayout()
        bc = QPushButton("Cancel"); bc.setStyleSheet(secondary_btn_style()); bc.setFixedHeight(30)
        bc.clicked.connect(dlg.reject)
        bs = QPushButton("Add"); bs.setStyleSheet(primary_btn_style()); bs.setFixedHeight(30)
        br.addStretch(); br.addWidget(bc); br.addSpacing(6); br.addWidget(bs)
        lay.addLayout(br)

        def _save():
            name = _n.text().strip()
            if not name:
                return
            lib = load_library()
            lib.append({
                "name": name, "year": _y.value(), "machine": "pc",
                "ram_mb": _r.value(), "cpu": _c.value(), "display": "std",
                "iso_url": _u.text().strip(), "notes": _nt.text().strip(),
                "extra_args": [],
            })
            save_library(lib)
            dlg.accept()
            self._refresh()

        bs.clicked.connect(_save)
        dlg.exec()
