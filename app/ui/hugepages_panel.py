from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
)


def _read_meminfo_huge() -> dict[str, int]:
    result: dict[str, int] = {}
    try:
        text = Path("/proc/meminfo").read_text()
        for line in text.splitlines():
            if "Huge" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val_parts = parts[1].strip().split()
                    val = int(val_parts[0]) if val_parts else 0
                    result[key] = val
    except (OSError, ValueError):
        pass
    return result


def hugepages_available() -> bool:
    return Path("/dev/hugepages").exists()


class HugepagesPanel(QFrame):
    config_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_ram_mb = 2048
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("HUGEPAGES", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Hugepages reduce TLB misses by using larger memory pages (typically 2 MB). "
            "This can improve VM memory performance, especially for memory-intensive workloads."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        avail = hugepages_available()

        if not avail:
            warn = QLabel(
                "/dev/hugepages does not exist on this system.\n"
                "Mount it with: mount -t hugetlbfs hugetlbfs /dev/hugepages"
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"background-color: #2d2010; border: 1px solid {WARNING};"
                f" border-radius: 6px; padding: 12px; color: {WARNING}; font-size: 12px;")
            layout.addWidget(warn)
            layout.addStretch()
            return

        # Toggle
        self._enable_check = QCheckBox("Enable hugepages for this VM")
        self._enable_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self._enable_check)

        # Stats card
        stats_card = QFrame()
        stats_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        sg = QGridLayout(stats_card)
        sg.setContentsMargins(16, 14, 16, 14)
        sg.setSpacing(10)

        stat_label_style = f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;"
        stat_value_style = (
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")

        self._lbl_total = QLabel("--")
        self._lbl_total.setStyleSheet(stat_value_style)
        self._lbl_free = QLabel("--")
        self._lbl_free.setStyleSheet(stat_value_style)
        self._lbl_size = QLabel("--")
        self._lbl_size.setStyleSheet(stat_value_style)
        self._lbl_needed = QLabel("--")
        self._lbl_needed.setStyleSheet(
            f"color: {ACCENT}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")

        for col, (label_text, value_widget) in enumerate([
            ("Total Pages", self._lbl_total),
            ("Free Pages", self._lbl_free),
            ("Page Size", self._lbl_size),
            ("Needed for VM", self._lbl_needed),
        ]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(stat_label_style)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sg.addWidget(lbl, 0, col)
            sg.addWidget(value_widget, 1, col)

        layout.addWidget(stats_card)

        # Warning area
        self._warning = QLabel()
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 10px; color: {WARNING}; font-size: 11px;")
        self._warning.hide()
        layout.addWidget(self._warning)

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

        self._enable_check.toggled.connect(self._on_toggled)
        self._refresh()

    def set_config(self, enabled: bool, ram_mb: int) -> None:
        self._vm_ram_mb = ram_mb
        if not hasattr(self, "_enable_check"):
            return
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(enabled)
        self._enable_check.blockSignals(False)
        self._refresh()

    def _on_toggled(self, checked: bool) -> None:
        self._refresh()
        self.config_changed.emit(checked)

    def _refresh(self) -> None:
        if not hasattr(self, "_lbl_total"):
            return
        info = _read_meminfo_huge()
        total = info.get("HugePages_Total", 0)
        free = info.get("HugePages_Free", 0)
        size_kb = info.get("Hugepagesize", 2048)

        self._lbl_total.setText(str(total))
        self._lbl_free.setText(str(free))
        self._lbl_size.setText(f"{size_kb} kB")

        needed = (self._vm_ram_mb * 1024) // size_kb if size_kb > 0 else 0
        self._lbl_needed.setText(str(needed))

        enabled = hasattr(self, "_enable_check") and self._enable_check.isChecked()

        if enabled and free < needed:
            self._warning.setText(
                f"Not enough hugepages! Need {needed}, only {free} free.\n"
                f"Run: echo {needed} | sudo tee /proc/sys/vm/nr_hugepages")
            self._warning.show()
        else:
            self._warning.hide()

        if enabled:
            self._args_preview.setText("-mem-prealloc -mem-path /dev/hugepages")
        else:
            self._args_preview.setText("(hugepages disabled)")
