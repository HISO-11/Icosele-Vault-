from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY, LABEL_STYLE,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style,
)
from config.vm_config import NET_MODE_BRIDGE, NET_MODE_HOSTONLY, NET_MODE_NAT, VMConfig


def _list_host_interfaces() -> list[str]:
    try:
        out = subprocess.check_output(["ip", "-o", "link", "show"], text=True, timeout=2)
    except (subprocess.SubprocessError, FileNotFoundError):
        return ["br0"]
    ifaces = []
    for line in out.strip().splitlines():
        parts = line.split(": ")
        if len(parts) >= 2:
            name = parts[1].split("@")[0]
            if name != "lo":
                ifaces.append(name)
    return ifaces or ["br0"]


MODE_LABELS = {NET_MODE_NAT: "NAT (User mode)", NET_MODE_BRIDGE: "Bridged", NET_MODE_HOSTONLY: "Host-only"}
MODE_KEYS = [NET_MODE_NAT, NET_MODE_BRIDGE, NET_MODE_HOSTONLY]
MODE_DESCRIPTIONS = {
    NET_MODE_NAT: "Guest accesses the network through QEMU's built-in NAT.",
    NET_MODE_BRIDGE: "Guest appears on the host's network bridge.",
    NET_MODE_HOSTONLY: "Guest can only communicate with the host.",
}


class NetworkPanel(QFrame):
    config_changed = Signal(str, str)
    port_forwards_changed = Signal(list)  # list of {host_port, guest_port, proto}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host_ifaces: list[str] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("NETWORK", styleSheet=SECTION_LABEL_STYLE))

        mr = QHBoxLayout()
        ml = QLabel("Mode")
        ml.setStyleSheet(LABEL_STYLE)
        ml.setFixedWidth(90)
        self.mode_combo = QComboBox()
        self.mode_combo.setStyleSheet(COMBO_STYLE)
        for k in MODE_KEYS:
            self.mode_combo.addItem(MODE_LABELS[k], k)
        mr.addWidget(ml)
        mr.addWidget(self.mode_combo, 1)
        layout.addLayout(mr)

        self.desc_label = QLabel(MODE_DESCRIPTIONS[NET_MODE_NAT])
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(self.desc_label)

        self._bridge_warning = QLabel(
            "\u26a0  Bridged mode exposes the VM directly to the local network. "
            "Host firewall rules (iptables/nftables) may need updating to "
            "control VM traffic.")
        self._bridge_warning.setWordWrap(True)
        self._bridge_warning.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 10px; color: {WARNING}; font-size: 11px;")
        self._bridge_warning.hide()
        layout.addWidget(self._bridge_warning)

        self.bridge_row = QWidget()
        self.bridge_row.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(self.bridge_row)
        bl.setContentsMargins(0, 0, 0, 0)
        blbl = QLabel("Interface")
        blbl.setStyleSheet(LABEL_STYLE)
        blbl.setFixedWidth(90)
        self.iface_combo = QComboBox()
        self.iface_combo.setStyleSheet(COMBO_STYLE)
        bl.addWidget(blbl)
        bl.addWidget(self.iface_combo, 1)
        layout.addWidget(self.bridge_row)
        self.bridge_row.hide()

        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self.args_preview = QLabel()
        self.args_preview.setWordWrap(True)
        self.args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self.args_preview)

        br = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(save_btn_style())
        br.addWidget(self.btn_save)
        br.addStretch()
        layout.addLayout(br)

        # vhost-net badge
        layout.addWidget(QLabel("ACCELERATION", styleSheet=SECTION_LABEL_STYLE))
        self._vhost_badge = QLabel()
        self._vhost_badge.setFixedHeight(28)
        self._update_vhost_badge()
        layout.addWidget(self._vhost_badge)

        # Port forwarding section
        layout.addWidget(QLabel("PORT FORWARDING (NAT)", styleSheet=SECTION_LABEL_STYLE))
        pf_desc = QLabel("Forward host ports to guest ports (NAT mode only).")
        pf_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(pf_desc)

        self._pf_list = QListWidget()
        self._pf_list.setMaximumHeight(80)
        self._pf_list.setStyleSheet(
            f"QListWidget {{ background: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 4px; color: {TEXT_PRIMARY}; font-size: 11px;"
            f" font-family: monospace; }}"
            f"QListWidget::item {{ padding: 3px; }}")
        layout.addWidget(self._pf_list)

        pf_add_row = QHBoxLayout()
        pf_add_row.setSpacing(4)
        self._pf_host = QSpinBox()
        self._pf_host.setRange(1, 65535)
        self._pf_host.setValue(8080)
        self._pf_host.setPrefix("Host: ")
        self._pf_host.setStyleSheet(f"QSpinBox {{ background: {BG_CARD}; color: {TEXT_PRIMARY};"
                                     f" border: 1px solid {BORDER}; border-radius: 4px;"
                                     f" padding: 2px 4px; font-size: 11px; }}")
        self._pf_guest = QSpinBox()
        self._pf_guest.setRange(1, 65535)
        self._pf_guest.setValue(80)
        self._pf_guest.setPrefix("Guest: ")
        self._pf_guest.setStyleSheet(self._pf_host.styleSheet())
        self._pf_proto = QComboBox()
        self._pf_proto.addItems(["tcp", "udp"])
        self._pf_proto.setStyleSheet(COMBO_STYLE)
        self._pf_proto.setFixedWidth(60)
        btn_add_pf = QPushButton("+")
        btn_add_pf.setFixedSize(28, 28)
        btn_add_pf.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_pf.setStyleSheet(save_btn_style())
        btn_add_pf.clicked.connect(self._on_add_port_forward)
        btn_rm_pf = QPushButton("-")
        btn_rm_pf.setFixedSize(28, 28)
        btn_rm_pf.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rm_pf.setStyleSheet(save_btn_style())
        btn_rm_pf.clicked.connect(self._on_remove_port_forward)
        pf_add_row.addWidget(self._pf_host)
        pf_add_row.addWidget(self._pf_guest)
        pf_add_row.addWidget(self._pf_proto)
        pf_add_row.addWidget(btn_add_pf)
        pf_add_row.addWidget(btn_rm_pf)
        pf_add_row.addStretch()
        layout.addLayout(pf_add_row)

        self._port_rules: list[dict] = []

        layout.addStretch()

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.iface_combo.currentIndexChanged.connect(self._update_preview)
        self.btn_save.clicked.connect(self._on_save)
        self._update_preview()

    def _ensure_ifaces_loaded(self) -> None:
        if self._host_ifaces is None:
            self._host_ifaces = _list_host_interfaces()
            self.iface_combo.clear()
            for iface in self._host_ifaces:
                self.iface_combo.addItem(iface)

    def set_config(self, net_mode: str, bridge_iface: str) -> None:
        idx = MODE_KEYS.index(net_mode) if net_mode in MODE_KEYS else 0
        self.mode_combo.setCurrentIndex(idx)
        if net_mode == NET_MODE_BRIDGE:
            self._ensure_ifaces_loaded()
            ii = self.iface_combo.findText(bridge_iface)
            if ii >= 0:
                self.iface_combo.setCurrentIndex(ii)
        self._on_mode_changed()

    def _on_mode_changed(self, _i: int = 0) -> None:
        mode = self.mode_combo.currentData()
        self.desc_label.setText(MODE_DESCRIPTIONS.get(mode, ""))
        is_bridge = mode == NET_MODE_BRIDGE
        self._bridge_warning.setVisible(is_bridge)
        if is_bridge:
            self._ensure_ifaces_loaded()
            self.bridge_row.show()
        else:
            self.bridge_row.hide()
        self._update_preview()

    def _current_mode(self) -> str:
        return self.mode_combo.currentData() or NET_MODE_NAT

    def _current_iface(self) -> str:
        return self.iface_combo.currentText() or "br0"

    def _update_preview(self) -> None:
        m = self._current_mode()
        if m == NET_MODE_BRIDGE:
            a = f"-netdev bridge,id=net0,br={self._current_iface()} -device virtio-net-pci,netdev=net0"
        elif m == NET_MODE_HOSTONLY:
            a = "-netdev socket,id=net0,listen=:1234 -device virtio-net-pci,netdev=net0"
        else:
            a = "-netdev user,id=net0 -device virtio-net-pci,netdev=net0"
        self.args_preview.setText(a)

    def _update_vhost_badge(self) -> None:
        if VMConfig.vhost_net_available():
            self._vhost_badge.setText("  vhost-net active  ")
            self._vhost_badge.setStyleSheet(
                f"background-color: #1a3328; color: {ACCENT}; border: 1px solid {ACCENT};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700;"
                f" padding: 4px 12px; font-family: {FONT_FAMILY};")
        else:
            self._vhost_badge.setText("  vhost-net unavailable  ")
            self._vhost_badge.setStyleSheet(
                f"background-color: #2a2a2a; color: {TEXT_MUTED}; border: 1px solid {TEXT_MUTED};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700;"
                f" padding: 4px 12px; font-family: {FONT_FAMILY};")
            self._vhost_badge.setToolTip("Run: sudo modprobe vhost_net")

    def set_port_forwards(self, rules: list[dict]) -> None:
        self._port_rules = list(rules)
        self._rebuild_pf_list()

    def _rebuild_pf_list(self) -> None:
        self._pf_list.clear()
        for r in self._port_rules:
            self._pf_list.addItem(
                f"{r.get('proto', 'tcp')}  :{r.get('host_port', '')} -> :{r.get('guest_port', '')}")

    def _on_add_port_forward(self) -> None:
        self._port_rules.append({
            "host_port": str(self._pf_host.value()),
            "guest_port": str(self._pf_guest.value()),
            "proto": self._pf_proto.currentText(),
        })
        self._rebuild_pf_list()
        self.port_forwards_changed.emit(self._port_rules)

    def _on_remove_port_forward(self) -> None:
        row = self._pf_list.currentRow()
        if 0 <= row < len(self._port_rules):
            self._port_rules.pop(row)
            self._rebuild_pf_list()
            self.port_forwards_changed.emit(self._port_rules)

    def _on_save(self) -> None:
        self.config_changed.emit(self._current_mode(), self._current_iface())

    def apply_theme(self) -> None:
        from app.ui import theme
        self.setStyleSheet(f"background-color: {theme.get('BG_PANEL')}; border: none;")
        self.mode_combo.setStyleSheet(theme.COMBO_STYLE)
        self.iface_combo.setStyleSheet(theme.COMBO_STYLE)
        self.args_preview.setStyleSheet(
            f"color: {theme.get('ACCENT')}; font-size: 11px; font-family: monospace;"
            f" background-color: {theme.get('BG_CARD')}; border: 1px solid {theme.get('BORDER')};"
            f" border-radius: 6px; padding: 10px 12px;")
        self.btn_save.setStyleSheet(theme.save_btn_style())
