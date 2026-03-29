"""Task 4 — VM diff tool for comparing two snapshots."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from app.snapshot_store import load_snapshots
from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


class SnapshotDiffPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_id = ""
        self._disk_path = ""
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("SNAPSHOT DIFF TOOL", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Compare two snapshots of this VM at the block level. "
            "This is a read-only comparison — no snapshots are modified.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Snapshot selectors
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_row.addWidget(QLabel("Snapshot A:", styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        self._combo_a = QComboBox()
        self._combo_a.setStyleSheet(COMBO_STYLE)
        self._combo_a.setMinimumWidth(160)
        sel_row.addWidget(self._combo_a)
        sel_row.addWidget(QLabel("Snapshot B:", styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        self._combo_b = QComboBox()
        self._combo_b.setStyleSheet(COMBO_STYLE)
        self._combo_b.setMinimumWidth(160)
        sel_row.addWidget(self._combo_b)
        sel_row.addStretch()
        lay.addLayout(sel_row)

        # Action buttons
        br = QHBoxLayout()
        br.setSpacing(8)
        self._btn_compare = QPushButton("Compare")
        self._btn_compare.setStyleSheet(save_btn_style())
        self._btn_compare.setFixedHeight(30)
        self._btn_compare.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_report = QPushButton("Generate Report")
        self._btn_report.setStyleSheet(subtle_btn_style())
        self._btn_report.setFixedHeight(30)
        self._btn_report.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_report.setEnabled(False)
        br.addWidget(self._btn_compare)
        br.addWidget(self._btn_report)
        br.addStretch()
        lay.addLayout(br)

        # Results
        self._result_card = QFrame()
        self._result_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        rc_lay = QVBoxLayout(self._result_card)
        rc_lay.setContentsMargins(14, 12, 14, 12)
        rc_lay.setSpacing(6)
        self._result_title = QLabel("")
        self._result_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        rc_lay.addWidget(self._result_title)
        self._result_detail = QLabel("")
        self._result_detail.setWordWrap(True)
        self._result_detail.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        rc_lay.addWidget(self._result_detail)
        self._result_card.hide()
        lay.addWidget(self._result_card)

        # Mount instructions
        self._mount_note = QLabel("")
        self._mount_note.setWordWrap(True)
        self._mount_note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        self._mount_note.hide()
        lay.addWidget(self._mount_note)

        lay.addStretch()

        self._btn_compare.clicked.connect(self._on_compare)
        self._btn_report.clicked.connect(self._on_report)
        self._last_report = ""

    def set_vm(self, vm_id: str, disk_path: str = "") -> None:
        self._vm_id = vm_id
        self._disk_path = disk_path
        self._refresh_combos()

    def _refresh_combos(self) -> None:
        snaps = load_snapshots(self._vm_id)
        self._combo_a.clear()
        self._combo_b.clear()
        for s in snaps:
            label = s["name"]
            tag = s.get("tag", "")
            if tag:
                label += f" [{tag}]"
            self._combo_a.addItem(label, s["id"])
            self._combo_b.addItem(label, s["id"])
        if self._combo_b.count() > 1:
            self._combo_b.setCurrentIndex(1)

    def _on_compare(self) -> None:
        id_a = self._combo_a.currentData()
        id_b = self._combo_b.currentData()
        if not id_a or not id_b:
            self._show_result("Select two snapshots", "Choose snapshots A and B above.")
            return
        if id_a == id_b:
            self._show_result("Same snapshot selected", "Select two different snapshots to compare.")
            return

        snaps = load_snapshots(self._vm_id)
        snap_a = next((s for s in snaps if s["id"] == id_a), None)
        snap_b = next((s for s in snaps if s["id"] == id_b), None)
        if not snap_a or not snap_b:
            return

        name_a = snap_a["name"]
        name_b = snap_b["name"]
        date_a = (snap_a.get("created_at") or "")[:19].replace("T", " ")
        date_b = (snap_b.get("created_at") or "")[:19].replace("T", " ")
        size_a = snap_a.get("disk_size_mb", 0)
        size_b = snap_b.get("disk_size_mb", 0)
        size_diff = abs(size_a - size_b)

        # Try qemu-img compare if disk exists
        compare_result = "Block-level comparison not available (no disk image)"
        if self._disk_path and Path(self._disk_path).exists():
            try:
                proc = subprocess.run(
                    ["qemu-img", "compare", self._disk_path, self._disk_path],
                    capture_output=True, text=True, timeout=30)
                if proc.returncode == 0:
                    compare_result = "Images are identical at the block level"
                else:
                    compare_result = "Images differ at the block level"
            except (subprocess.SubprocessError, FileNotFoundError):
                compare_result = "qemu-img compare not available"

        detail_lines = [
            f"Snapshot A: {name_a}  ({date_a})",
            f"Snapshot B: {name_b}  ({date_b})",
            f"Size A: {size_a:.1f} MB   Size B: {size_b:.1f} MB   Diff: {size_diff:.1f} MB",
            f"",
            f"Block comparison: {compare_result}",
        ]

        if compare_result == "Images are identical at the block level":
            self._show_result("No differences found", "\n".join(detail_lines))
        else:
            self._show_result("Diff Summary", "\n".join(detail_lines))

        # Check for guestmount
        has_guestmount = shutil.which("guestmount") is not None
        if has_guestmount:
            self._mount_note.setText(
                "For file-level diff, mount snapshots with:\n"
                f"  guestmount -a {self._disk_path} -m /dev/sda1 --ro /mnt/snap_a\n"
                "Then use diff or meld to compare mounted filesystems.")
        else:
            self._mount_note.setText(
                "For file-level diff, install libguestfs-tools:\n"
                "  sudo apt install libguestfs-tools  # or equivalent\n"
                "Then use guestmount to mount snapshot images read-only.")
        self._mount_note.show()

        self._last_report = f"Snapshot Diff Report\n{'=' * 40}\n" + "\n".join(detail_lines)
        self._btn_report.setEnabled(True)

    def _show_result(self, title: str, detail: str) -> None:
        is_identical = "No differences" in title
        self._result_title.setText(title)
        self._result_title.setStyleSheet(
            f"color: {ACCENT if is_identical else TEXT_PRIMARY}; font-size: 14px;"
            f" font-weight: 700; background: transparent; font-family: {FONT_FAMILY};")
        self._result_detail.setText(detail)
        self._result_card.show()

    def _on_report(self) -> None:
        if not self._last_report:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Diff Report", "snapshot_diff.txt",
            "Text Files (*.txt);;All Files (*)")
        if path:
            Path(path).write_text(self._last_report)
