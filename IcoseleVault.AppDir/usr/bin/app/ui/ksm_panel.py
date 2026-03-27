from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style,
)

log = logging.getLogger(__name__)

KSM_BASE = Path("/sys/kernel/mm/ksm")


def ksm_available() -> bool:
    return (KSM_BASE / "run").exists()


def ksm_enabled() -> bool:
    try:
        return (KSM_BASE / "run").read_text().strip() == "1"
    except OSError:
        return False


def _read_ksm_stat(name: str) -> int:
    try:
        return int((KSM_BASE / name).read_text().strip())
    except (OSError, ValueError):
        return 0


class KSMPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._start_timer()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("KERNEL SAME-PAGE MERGING (KSM)", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "KSM scans memory for identical pages across all processes and "
            "merges them copy-on-write. This can significantly reduce memory "
            "usage when running multiple VMs with similar guest OSes."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        avail = ksm_available()

        if not avail:
            warn = QLabel(
                "KSM is not available on this system.\n"
                "/sys/kernel/mm/ksm/run does not exist.\n\n"
                "Your kernel may not have CONFIG_KSM enabled."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"background-color: #2d2010; border: 1px solid {WARNING};"
                f" border-radius: 6px; padding: 12px; color: {WARNING}; font-size: 12px;")
            layout.addWidget(warn)
            layout.addStretch()
            return

        # Toggle
        toggle_row = QHBoxLayout()
        self._toggle = QCheckBox("Enable KSM")
        self._toggle.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        self._toggle.setChecked(ksm_enabled())
        self._toggle.toggled.connect(self._on_toggle)
        toggle_row.addWidget(self._toggle)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        priv_note = QLabel(
            "Toggling KSM requires root privileges (pkexec will prompt for authentication)."
        )
        priv_note.setWordWrap(True)
        priv_note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(priv_note)

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

        self._lbl_shared = QLabel("0")
        self._lbl_shared.setStyleSheet(stat_value_style)
        self._lbl_sharing = QLabel("0")
        self._lbl_sharing.setStyleSheet(stat_value_style)
        self._lbl_unshared = QLabel("0")
        self._lbl_unshared.setStyleSheet(stat_value_style)
        self._lbl_saved = QLabel("0 MB")
        self._lbl_saved.setStyleSheet(
            f"color: {ACCENT}; font-size: 16px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")

        for col, (label_text, value_widget) in enumerate([
            ("Pages Shared", self._lbl_shared),
            ("Pages Sharing", self._lbl_sharing),
            ("Pages Unshared", self._lbl_unshared),
            ("Memory Saved", self._lbl_saved),
        ]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(stat_label_style)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sg.addWidget(lbl, 0, col)
            sg.addWidget(value_widget, 1, col)

        layout.addWidget(stats_card)
        layout.addStretch()
        self._refresh_stats()

    def _start_timer(self) -> None:
        if not ksm_available():
            return
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_stats)
        self._timer.start(5000)

    def _refresh_stats(self) -> None:
        if not hasattr(self, "_lbl_shared"):
            return
        shared = _read_ksm_stat("pages_shared")
        sharing = _read_ksm_stat("pages_sharing")
        unshared = _read_ksm_stat("pages_unshared")
        saved_mb = (sharing * 4096) / (1024 * 1024)

        self._lbl_shared.setText(f"{shared:,}")
        self._lbl_sharing.setText(f"{sharing:,}")
        self._lbl_unshared.setText(f"{unshared:,}")
        self._lbl_saved.setText(f"{saved_mb:.1f} MB")

        if hasattr(self, "_toggle"):
            self._toggle.blockSignals(True)
            self._toggle.setChecked(ksm_enabled())
            self._toggle.blockSignals(False)

    def _on_toggle(self, checked: bool) -> None:
        val = "1" if checked else "0"
        try:
            subprocess.run(
                ["pkexec", "tee", "/sys/kernel/mm/ksm/run"],
                input=val.encode(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            log.error("Failed to toggle KSM: %s", exc)
        self._refresh_stats()
