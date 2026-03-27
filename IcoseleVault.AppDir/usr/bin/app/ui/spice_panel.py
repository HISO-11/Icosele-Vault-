from __future__ import annotations

import shutil
import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY,
    INPUT_STYLE, LABEL_STYLE, SECTION_LABEL_STYLE, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)


def _find_viewer() -> str | None:
    for name in ("virt-viewer", "remote-viewer"):
        if shutil.which(name):
            return name
    return None


class SpicePanel(QFrame):
    config_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._viewer = _find_viewer()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(QLabel("SPICE DISPLAY", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "SPICE provides high-performance remote display with clipboard sharing, "
            "USB redirection, and multi-monitor support."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Mode selector
        mode_row = QHBoxLayout()
        mode_lbl = QLabel("Display Mode")
        mode_lbl.setStyleSheet(LABEL_STYLE)
        mode_lbl.setFixedWidth(90)
        self._mode_combo = QComboBox()
        self._mode_combo.setStyleSheet(COMBO_STYLE)
        self._mode_combo.addItem("Default (use Display tab)", "default")
        self._mode_combo.addItem("VNC", "vnc")
        self._mode_combo.addItem("SPICE", "spice")
        mode_row.addWidget(mode_lbl)
        mode_row.addWidget(self._mode_combo, 1)
        layout.addLayout(mode_row)

        # SPICE port
        self._spice_port_row = QWidget()
        self._spice_port_row.setStyleSheet("background: transparent;")
        sp_layout = QHBoxLayout(self._spice_port_row)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_lbl = QLabel("SPICE Port")
        sp_lbl.setStyleSheet(LABEL_STYLE)
        sp_lbl.setFixedWidth(90)
        self._spice_port = QSpinBox()
        self._spice_port.setRange(5900, 6100)
        self._spice_port.setValue(5930)
        self._spice_port.setStyleSheet(INPUT_STYLE)
        sp_layout.addWidget(sp_lbl)
        sp_layout.addWidget(self._spice_port, 1)
        self._spice_port_row.hide()
        layout.addWidget(self._spice_port_row)

        # Connection string (shown when running)
        self._conn_card = QFrame()
        self._conn_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        cc_layout = QVBoxLayout(self._conn_card)
        cc_layout.setContentsMargins(14, 12, 14, 12)
        cc_layout.setSpacing(8)

        self._conn_label = QLabel("Connection:")
        self._conn_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        cc_layout.addWidget(self._conn_label)

        self._conn_string = QLabel("")
        self._conn_string.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._conn_string.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
            f" font-family: monospace; background: transparent;")
        cc_layout.addWidget(self._conn_string)

        conn_btns = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setStyleSheet(save_btn_style())
        self._btn_connect.setFixedHeight(30)
        self._btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copy = QPushButton("Copy")
        self._btn_copy.setStyleSheet(subtle_btn_style())
        self._btn_copy.setFixedHeight(30)
        self._btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        conn_btns.addWidget(self._btn_connect)
        conn_btns.addWidget(self._btn_copy)
        conn_btns.addStretch()
        cc_layout.addLayout(conn_btns)

        self._conn_card.hide()
        layout.addWidget(self._conn_card)

        # Viewer status
        if self._viewer:
            viewer_note = QLabel(f"Viewer found: {self._viewer}")
            viewer_note.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        else:
            viewer_note = QLabel(
                "No SPICE viewer found. Install virt-viewer or remote-viewer "
                "to connect. The connection string can still be copied.")
            viewer_note.setWordWrap(True)
            viewer_note.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
                f" background: transparent;")
        layout.addWidget(viewer_note)

        # QEMU args preview
        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self._args_preview = QLabel()
        self._args_preview.setWordWrap(True)
        self._args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self._args_preview)

        # Save button
        br = QHBoxLayout()
        self._btn_save = QPushButton("Save")
        self._btn_save.setFixedHeight(34)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setStyleSheet(save_btn_style())
        br.addWidget(self._btn_save)
        br.addStretch()
        layout.addLayout(br)

        layout.addStretch()

        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._spice_port.valueChanged.connect(self._update_preview)
        self._btn_connect.clicked.connect(self._on_connect)
        self._btn_copy.clicked.connect(self._on_copy)
        self._btn_save.clicked.connect(self._on_save)
        self._update_preview()

    def set_config(self, spice_config: dict) -> None:
        mode = spice_config.get("spice_mode", "default")
        idx = self._mode_combo.findData(mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        self._spice_port.setValue(spice_config.get("spice_port", 5930))
        self._on_mode_changed()

    def set_vm_running(self, running: bool) -> None:
        mode = self._mode_combo.currentData()
        show_conn = running and mode == "spice"
        self._conn_card.setVisible(show_conn)
        if show_conn:
            port = self._spice_port.value()
            self._conn_string.setText(f"spice://localhost:{port}")

    def get_config(self) -> dict:
        return {
            "spice_mode": self._mode_combo.currentData() or "default",
            "spice_port": self._spice_port.value(),
        }

    def _on_mode_changed(self, _i: int = 0) -> None:
        mode = self._mode_combo.currentData()
        self._spice_port_row.setVisible(mode == "spice")
        self._update_preview()

    def _update_preview(self) -> None:
        mode = self._mode_combo.currentData()
        if mode == "spice":
            port = self._spice_port.value()
            self._args_preview.setText(
                f"-vga qxl\n"
                f"-device virtio-serial\n"
                f"-chardev spicevmc,id=vdagent,debug=0,name=vdagent\n"
                f"-device virtserialport,chardev=vdagent,"
                f"name=com.redhat.spice.0\n"
                f"-spice port={port},disable-ticketing=on")
        elif mode == "vnc":
            self._args_preview.setText("(uses VNC settings from Display tab)")
        else:
            self._args_preview.setText("(uses default settings from Display tab)")

    def _on_connect(self) -> None:
        if not self._viewer:
            return
        port = self._spice_port.value()
        uri = f"spice://localhost:{port}"
        try:
            subprocess.Popen([self._viewer, uri],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, OSError):
            pass

    def _on_copy(self) -> None:
        port = self._spice_port.value()
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(f"spice://localhost:{port}")

    def _on_save(self) -> None:
        self.config_changed.emit(self.get_config())
