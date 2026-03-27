from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from datetime import datetime, timezone

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, SECTION_LABEL_STYLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TREE_STYLE,
    save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


@dataclass
class USBDeviceInfo:
    bus: str; addr: str; vendor_id: str; product_id: str; vendor_name: str; product_name: str

    @property
    def display_name(self) -> str:
        return self.product_name or self.vendor_name or f"{self.vendor_id}:{self.product_id}"

    def config_dict(self) -> dict:
        return {"bus": self.bus, "addr": self.addr, "vendor_id": self.vendor_id,
                "product_id": self.product_id, "vendor_name": self.vendor_name, "product_name": self.product_name}

    @classmethod
    def from_config_dict(cls, d: dict) -> USBDeviceInfo:
        return cls(**{k: d.get(k, "") for k in ("bus", "addr", "vendor_id", "product_id", "vendor_name", "product_name")})


def _read_sysfs_attr(path: Path, attr: str) -> str:
    try:
        return (path / attr).read_text().strip()
    except (OSError, ValueError):
        return ""


def scan_host_usb_devices() -> list[USBDeviceInfo]:
    base = Path("/sys/bus/usb/devices")
    if not base.exists():
        return []
    devices: list[USBDeviceInfo] = []
    for entry in sorted(base.iterdir()):
        if ":" in entry.name:
            continue
        vid = _read_sysfs_attr(entry, "idVendor")
        pid = _read_sysfs_attr(entry, "idProduct")
        if not vid or not pid:
            continue
        if _read_sysfs_attr(entry, "bDeviceClass") == "09":
            continue
        bn = _read_sysfs_attr(entry, "busnum")
        dn = _read_sysfs_attr(entry, "devnum")
        if bn and dn:
            devices.append(USBDeviceInfo(bn, dn, vid, pid,
                                          _read_sysfs_attr(entry, "manufacturer"),
                                          _read_sysfs_attr(entry, "product")))
    return devices


def _setup_tree(tree: QTreeWidget, height: int) -> None:
    tree.setHeaderLabels(["Device", "ID", "Bus", "Addr"])
    tree.setStyleSheet(TREE_STYLE)
    tree.setRootIsDecorated(False)
    tree.setFixedHeight(height)
    h = tree.header()
    h.setStretchLastSection(False)
    h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for c in (1, 2, 3):
        h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)


class USBPanel(QFrame):
    usb_action = Signal(str, str, str, str)
    config_changed = Signal(list)
    remembered_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._assigned: list[USBDeviceInfo] = []
        self._remembered: list[dict] = []
        self._vm_running = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._sl("HOST DEVICES"))
        self.host_tree = QTreeWidget()
        _setup_tree(self.host_tree, 155)
        layout.addWidget(self.host_tree)

        mid = QHBoxLayout()
        mid.setSpacing(8)
        self.btn_add = QPushButton("Assign to VM")
        self.btn_add.setStyleSheet(save_btn_style())
        self.btn_add.setFixedHeight(32)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setStyleSheet(subtle_btn_style())
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_host_devices)
        mid.addWidget(self.btn_add)
        mid.addWidget(self.btn_refresh)
        mid.addStretch()
        layout.addLayout(mid)

        layout.addWidget(self._sl("ASSIGNED DEVICES"))
        self.assigned_tree = QTreeWidget()
        _setup_tree(self.assigned_tree, 120)
        layout.addWidget(self.assigned_tree)

        bot = QHBoxLayout()
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setStyleSheet(subtle_btn_style())
        self.btn_remove.setFixedHeight(32)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.clicked.connect(self._on_remove)
        bot.addWidget(self.btn_remove)
        bot.addStretch()
        layout.addLayout(bot)

        # Remembered devices (Task 1)
        layout.addWidget(self._sl("REMEMBERED DEVICES"))
        self._remembered_list = QVBoxLayout()
        self._remembered_list.setSpacing(4)
        layout.addLayout(self._remembered_list)
        layout.addStretch()
        self.refresh_host_devices()

    @staticmethod
    def _sl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(SECTION_LABEL_STYLE)
        return lbl

    def refresh_host_devices(self) -> None:
        self.host_tree.clear()
        for dev in scan_host_usb_devices():
            item = QTreeWidgetItem([dev.display_name, f"{dev.vendor_id}:{dev.product_id}", dev.bus, dev.addr])
            item.setData(0, Qt.ItemDataRole.UserRole, dev)
            self.host_tree.addTopLevelItem(item)

    def set_assigned_devices(self, devices: list[dict]) -> None:
        self._assigned = [USBDeviceInfo.from_config_dict(d) for d in devices]
        self._rebuild()

    def set_vm_running(self, running: bool) -> None:
        self._vm_running = running

    def _rebuild(self) -> None:
        self.assigned_tree.clear()
        for dev in self._assigned:
            item = QTreeWidgetItem([dev.display_name, f"{dev.vendor_id}:{dev.product_id}", dev.bus, dev.addr])
            item.setData(0, Qt.ItemDataRole.UserRole, dev)
            self.assigned_tree.addTopLevelItem(item)

    def set_remembered_devices(self, devices: list[dict]) -> None:
        self._remembered = list(devices)
        self._rebuild_remembered()

    def _rebuild_remembered(self) -> None:
        while self._remembered_list.count():
            w = self._remembered_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self._remembered:
            lbl = QLabel("No remembered devices.")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
            self._remembered_list.addWidget(lbl)
            return
        for i, rd in enumerate(self._remembered):
            from PySide6.QtWidgets import QCheckBox
            row = QFrame()
            row.setStyleSheet(f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 4px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)
            name = rd.get("device_name", f"{rd.get('vendor_id', '?')}:{rd.get('product_id', '?')}")
            last = (rd.get("last_connected") or "")[:16].replace("T", " ")
            lbl = QLabel(f"{name}  ({last})")
            lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; background: transparent;")
            rl.addWidget(lbl, 1)
            auto_cb = QCheckBox("Auto")
            auto_cb.setChecked(rd.get("auto_connect", False))
            auto_cb.setStyleSheet(f"QCheckBox {{ color: {TEXT_SECONDARY}; font-size: 10px; background: transparent; }}")
            auto_cb.toggled.connect(lambda checked, idx=i: self._on_auto_toggle(idx, checked))
            rl.addWidget(auto_cb)
            rm_btn = QPushButton("\u2715")
            rm_btn.setFixedSize(22, 22)
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {TEXT_MUTED}; border: none; font-size: 12px; }} QPushButton:hover {{ color: #e74c3c; }}")
            rm_btn.clicked.connect(lambda checked, idx=i: self._on_forget(idx))
            rl.addWidget(rm_btn)
            self._remembered_list.addWidget(row)

    def _on_auto_toggle(self, idx: int, checked: bool) -> None:
        if 0 <= idx < len(self._remembered):
            self._remembered[idx]["auto_connect"] = checked
            self.remembered_changed.emit(self._remembered)

    def _on_forget(self, idx: int) -> None:
        if 0 <= idx < len(self._remembered):
            self._remembered.pop(idx)
            self._rebuild_remembered()
            self.remembered_changed.emit(self._remembered)

    def _remember_device(self, dev: USBDeviceInfo) -> None:
        for rd in self._remembered:
            if rd.get("vendor_id") == dev.vendor_id and rd.get("product_id") == dev.product_id:
                rd["last_connected"] = datetime.now(timezone.utc).isoformat()
                self.remembered_changed.emit(self._remembered)
                self._rebuild_remembered()
                return
        self._remembered.append({
            "vendor_id": dev.vendor_id,
            "product_id": dev.product_id,
            "device_name": dev.display_name,
            "last_connected": datetime.now(timezone.utc).isoformat(),
            "auto_connect": False,
        })
        self.remembered_changed.emit(self._remembered)
        self._rebuild_remembered()

    def check_auto_connect(self, vendor_id: str, product_id: str) -> bool:
        for rd in self._remembered:
            if (rd.get("vendor_id") == vendor_id and
                    rd.get("product_id") == product_id and
                    rd.get("auto_connect", False)):
                return True
        return False

    def _on_add(self) -> None:
        item = self.host_tree.currentItem()
        if item is None:
            return
        dev: USBDeviceInfo = item.data(0, Qt.ItemDataRole.UserRole)
        if any(e.bus == dev.bus and e.addr == dev.addr for e in self._assigned):
            return
        self._assigned.append(dev)
        self._rebuild()
        self._remember_device(dev)
        self.config_changed.emit([d.config_dict() for d in self._assigned])
        if self._vm_running:
            self.usb_action.emit("add", dev.bus, dev.addr, f"usb-host-{dev.bus}-{dev.addr}")

    def _on_remove(self) -> None:
        item = self.assigned_tree.currentItem()
        if item is None:
            return
        dev: USBDeviceInfo = item.data(0, Qt.ItemDataRole.UserRole)
        self._assigned = [d for d in self._assigned if not (d.bus == dev.bus and d.addr == dev.addr)]
        self._rebuild()
        self.config_changed.emit([d.config_dict() for d in self._assigned])
        if self._vm_running:
            self.usb_action.emit("remove", dev.bus, dev.addr, f"usb-host-{dev.bus}-{dev.addr}")

    def apply_theme(self) -> None:
        from app.ui import theme
        self.setStyleSheet(f"background-color: {theme.get('BG_PANEL')}; border: none;")
        self.host_tree.setStyleSheet(theme.TREE_STYLE)
        self.assigned_tree.setStyleSheet(theme.TREE_STYLE)
        self.btn_add.setStyleSheet(theme.save_btn_style())
        self.btn_refresh.setStyleSheet(theme.subtle_btn_style())
        self.btn_remove.setStyleSheet(theme.subtle_btn_style())
