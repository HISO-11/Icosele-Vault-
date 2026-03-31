from __future__ import annotations

import os
import platform
import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
)


def _kernel_version() -> tuple[int, int]:
    try:
        parts = platform.release().split("-")[0].split(".")
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return 0, 0


def io_uring_available() -> bool:
    major, minor = _kernel_version()
    return major > 5 or (major == 5 and minor >= 1)


class DiskPerfPanel(QFrame):
    config_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("DISK PERFORMANCE", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Configure the disk I/O backend for virtio-blk devices. "
            "io_uring provides higher throughput and lower latency than "
            "the default threads backend on modern Linux kernels."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # io_uring toggle
        self.io_uring_check = QCheckBox("Enable io_uring async I/O backend")
        self.io_uring_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self.io_uring_check)

        # Status card
        self._status_card = QFrame()
        self._status_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 12px;"
        )
        sc_layout = QVBoxLayout(self._status_card)
        sc_layout.setContentsMargins(12, 10, 12, 10)
        sc_layout.setSpacing(6)

        self._aio_label = QLabel("Current backend: threads")
        self._aio_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        sc_layout.addWidget(self._aio_label)

        self._kernel_label = QLabel()
        self._kernel_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        sc_layout.addWidget(self._kernel_label)

        layout.addWidget(self._status_card)

        # Info label
        info = QLabel(
            "Requires Linux kernel 5.1+ and QEMU 5.0+. "
            "Falls back to aio=threads automatically if io_uring is unavailable."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(info)

        # QEMU args preview
        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self._args_preview = QLabel()
        self._args_preview.setWordWrap(True)
        self._args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self._args_preview)

        # ── Disk Expansion Section ──
        layout.addWidget(QLabel("DISK EXPANSION", styleSheet=SECTION_LABEL_STYLE))

        expand_desc = QLabel(
            "Expand the VM's disk image. The VM must be stopped. "
            "You may also need to resize the partition inside the guest OS.")
        expand_desc.setWordWrap(True)
        expand_desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(expand_desc)

        expand_row = QHBoxLayout()
        expand_row.setSpacing(8)
        self._expand_spin = QSpinBox()
        self._expand_spin.setRange(1, 1024)
        self._expand_spin.setValue(10)
        self._expand_spin.setSuffix(" GB")
        self._expand_spin.setStyleSheet(
            f"QSpinBox {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER}; border-radius: 4px;"
            f" padding: 4px 8px; font-size: 12px; }}")
        self._expand_spin.setFixedWidth(100)
        expand_row.addWidget(self._expand_spin)
        self._btn_expand = QPushButton("Expand Disk")
        self._btn_expand.setFixedHeight(32)
        self._btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_expand.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT}; color: #fff;"
            f" border: none; border-radius: 6px; padding: 6px 16px;"
            f" font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY}; }}"
            f"QPushButton:hover {{ opacity: 0.9; }}")
        self._btn_expand.clicked.connect(self._on_expand_disk)
        expand_row.addWidget(self._btn_expand)
        expand_row.addStretch()
        layout.addLayout(expand_row)

        self._expand_status = QLabel("")
        self._expand_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        layout.addWidget(self._expand_status)

        layout.addStretch()

        self.io_uring_check.toggled.connect(self._on_toggled)
        self._update_status()

    def set_config(self, enabled: bool, disk_path: str = "") -> None:
        self.io_uring_check.blockSignals(True)
        self.io_uring_check.setChecked(enabled)
        self.io_uring_check.blockSignals(False)
        self._disk_path = disk_path
        self._update_status()

    def _on_toggled(self, checked: bool) -> None:
        self._update_status()
        self.config_changed.emit(checked)

    def _update_status(self) -> None:
        enabled = self.io_uring_check.isChecked()
        avail = io_uring_available()
        major, minor = _kernel_version()

        self._kernel_label.setText(
            f"Kernel: {major}.{minor} - io_uring {'supported' if avail else 'NOT supported (need 5.1+)'}")

        if enabled and avail:
            self._aio_label.setText("Current backend: io_uring")
            self._aio_label.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
        elif enabled and not avail:
            self._aio_label.setText("Current backend: threads (io_uring unavailable, falling back)")
            self._aio_label.setStyleSheet(
                f"color: {WARNING}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
        else:
            self._aio_label.setText("Current backend: threads")
            self._aio_label.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")

        disk_path = getattr(self, "_disk_path", "")
        if disk_path:
            fmt = "raw" if disk_path.lower().endswith(".raw") else "qcow2"
            aio = "io_uring" if (enabled and avail) else "threads"
            self._args_preview.setText(
                f"-drive file=...,format={fmt},if=virtio,aio={aio}")
        else:
            self._args_preview.setText("(no disk attached)")

    def _on_expand_disk(self) -> None:
        disk_path = getattr(self, "_disk_path", "")
        if not disk_path or not os.path.exists(disk_path):
            self._expand_status.setText("No disk image found.")
            return
        size_gb = self._expand_spin.value()
        reply = QMessageBox.question(
            self, "Expand Disk",
            f"Expand disk by +{size_gb}G?\n{disk_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            result = subprocess.run(
                ["qemu-img", "resize", disk_path, f"+{size_gb}G"],
                capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                self._expand_status.setText(
                    f"Disk expanded by +{size_gb}G successfully.")
            else:
                self._expand_status.setText(
                    f"Error: {result.stderr.strip()}")
        except FileNotFoundError:
            self._expand_status.setText("qemu-img not found.")
        except subprocess.TimeoutExpired:
            self._expand_status.setText("Timeout expanding disk.")
