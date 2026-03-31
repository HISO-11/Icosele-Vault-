from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QLabel, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
)


class ClipboardPanel(QFrame):
    config_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_id = ""
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("CLIPBOARD SYNC", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Enable clipboard sharing between host and guest via the QEMU Guest Agent. "
            "This adds a virtio-serial channel for guest agent communication."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Toggle
        self._enable_check = QCheckBox("Enable clipboard sync (Guest Agent)")
        self._enable_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px;"
            f" background: transparent; font-family: {FONT_FAMILY}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self._enable_check)

        # Status card
        status_card = QFrame()
        status_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        sc_layout = QVBoxLayout(status_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(6)

        self._status_label = QLabel("Clipboard sync: disabled")
        self._status_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        sc_layout.addWidget(self._status_label)

        self._socket_label = QLabel("")
        self._socket_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        sc_layout.addWidget(self._socket_label)

        layout.addWidget(status_card)

        # Install instructions
        install_note = QLabel(
            "The guest agent must be installed inside the VM for clipboard sync to work."
        )
        install_note.setWordWrap(True)
        install_note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(install_note)

        install_card = QFrame()
        install_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px;")
        ic_layout = QVBoxLayout(install_card)
        ic_layout.setContentsMargins(14, 12, 14, 12)
        ic_layout.setSpacing(8)

        ubuntu_lbl = QLabel("Ubuntu / Debian:")
        ubuntu_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
            f" background: transparent;")
        ic_layout.addWidget(ubuntu_lbl)

        ubuntu_cmd = QLabel("sudo apt install qemu-guest-agent")
        ubuntu_cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ubuntu_cmd.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background: transparent; padding: 2px 0;")
        ic_layout.addWidget(ubuntu_cmd)

        win_lbl = QLabel("Windows:")
        win_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
            f" background: transparent;")
        ic_layout.addWidget(win_lbl)

        win_url = QLabel(
            "Download VirtIO guest tools from:\n"
            "https://fedorapeople.org/groups/virt/virtio-win/")
        win_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        win_url.setWordWrap(True)
        win_url.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background: transparent; padding: 2px 0;")
        ic_layout.addWidget(win_url)

        layout.addWidget(install_card)

        # Active sync indicator
        self._sync_indicator = QLabel("\u25cf  Clipboard sync active — polling every 500ms")
        self._sync_indicator.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._sync_indicator.hide()
        layout.addWidget(self._sync_indicator)

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
        self._update_ui()

    def set_vm_running(self, running: bool) -> None:
        enabled = self._enable_check.isChecked()
        self._sync_indicator.setVisible(running and enabled)

    def set_config(self, enabled: bool, vm_id: str = "") -> None:
        self._vm_id = vm_id
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(enabled)
        self._enable_check.blockSignals(False)
        self._update_ui()

    def _on_toggled(self, checked: bool) -> None:
        self._update_ui()
        self.config_changed.emit(checked)

    def _update_ui(self) -> None:
        enabled = self._enable_check.isChecked()
        sock = f"/tmp/icosele-vm/{self._vm_id}/qga.sock" if self._vm_id else "/tmp/icosele-vm/<vm>/qga.sock"
        if enabled:
            self._status_label.setText("Clipboard sync: enabled")
            self._status_label.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._socket_label.setText(f"Socket: {sock}")
            self._args_preview.setText(
                f"-chardev socket,path={sock},"
                f"server=on,wait=off,id=qga0\n"
                f"-device virtio-serial\n"
                f"-device virtserialport,chardev=qga0,"
                f"name=org.qemu.guest_agent.0")
        else:
            self._status_label.setText("Clipboard sync: disabled")
            self._status_label.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._socket_label.setText("")
            self._args_preview.setText("(clipboard sync disabled)")
