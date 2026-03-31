"""Task 2 — Plugin management panel for Settings."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from app.plugin_manager import (
    discover_plugins, get_plugins, install_plugin_zip,
)
from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, SECTION_LABEL_STYLE,
    STOP_RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    save_btn_style, subtle_btn_style,
)


class PluginPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("PLUGINS", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Third-party plugins extend Icosele VM. "
            "See plugins/PLUGIN_SDK.md for the developer guide.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        self._plugin_list = QVBoxLayout()
        self._plugin_list.setSpacing(6)
        lay.addLayout(self._plugin_list)

        br = QHBoxLayout()
        br.setSpacing(8)
        self._btn_install = QPushButton("Install Plugin (.zip)")
        self._btn_install.setStyleSheet(save_btn_style())
        self._btn_install.setFixedHeight(30)
        self._btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_install.clicked.connect(self._on_install)
        self._btn_rescan = QPushButton("Rescan")
        self._btn_rescan.setStyleSheet(subtle_btn_style())
        self._btn_rescan.setFixedHeight(30)
        self._btn_rescan.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rescan.clicked.connect(self._refresh)
        br.addWidget(self._btn_install)
        br.addWidget(self._btn_rescan)
        br.addStretch()
        lay.addLayout(br)
        lay.addStretch()

    def _refresh(self):
        while self._plugin_list.count():
            w = self._plugin_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        plugins = get_plugins() or discover_plugins()
        if not plugins:
            lbl = QLabel("No plugins installed. Place plugins in the plugins/ directory.")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
            self._plugin_list.addWidget(lbl)
            return
        for pi in plugins:
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(8)
            info = QVBoxLayout()
            info.setSpacing(2)
            name_lbl = QLabel(f"{pi.name}  v{pi.version}")
            name_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            info.addWidget(name_lbl)
            author_lbl = QLabel(f"by {pi.author}  —  {pi.description[:60]}")
            author_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px; background: transparent;")
            info.addWidget(author_lbl)
            status_color = ACCENT if pi.loaded else STOP_RED
            status_text = "Loaded" if pi.loaded else f"Error: {pi.error[:40]}"
            status_lbl = QLabel(status_text)
            status_lbl.setStyleSheet(f"color: {status_color}; font-size: 9px; background: transparent;")
            info.addWidget(status_lbl)
            cl.addLayout(info, 1)
            tog = QCheckBox("On")
            tog.setChecked(pi.enabled)
            tog.setStyleSheet(f"QCheckBox {{ color: {TEXT_SECONDARY}; font-size: 10px; background: transparent; }}")
            tog.toggled.connect(lambda checked, p=pi: setattr(p, "enabled", checked))
            cl.addWidget(tog)
            self._plugin_list.addWidget(card)

    def _on_install(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Install Plugin", "", "ZIP Files (*.zip)")
        if path:
            result = install_plugin_zip(path)
            discover_plugins()
            self._refresh()
