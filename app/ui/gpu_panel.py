from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_ELEVATED, BG_PANEL, BORDER, GPU_TREE_STYLE,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING, save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)


def _read_sysfs(path: Path) -> str:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return ""


def _check_iommu() -> tuple[bool, int]:
    groups = Path("/sys/kernel/iommu_groups")
    if not groups.exists():
        return False, 0
    entries = [e for e in groups.iterdir() if e.is_dir()]
    return len(entries) > 0, len(entries)


@dataclass
class GPUDeviceInfo:
    pci_addr: str; vendor_id: str; device_id: str
    vendor_name: str; device_name: str; current_driver: str; iommu_group: str

    @property
    def is_vfio(self) -> bool:
        return self.current_driver == "vfio-pci"

    @property
    def display_name(self) -> str:
        return self.device_name if self.device_name and self.device_name != self.device_id else f"{self.vendor_id}:{self.device_id}"


def _resolve_pci_name(vendor_id: str, device_id: str) -> tuple[str, str]:
    vn, dn = vendor_id, device_id
    for p in (Path("/usr/share/hwdata/pci.ids"), Path("/usr/share/misc/pci.ids")):
        if p.exists():
            try:
                inv = False
                for line in p.read_text(errors="replace").splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    if not line.startswith("\t"):
                        if line.lower().startswith(vendor_id.lower()):
                            vn = line.split(None, 1)[1] if " " in line else vendor_id
                            inv = True
                        elif inv:
                            break
                    elif inv and line.startswith("\t") and not line.startswith("\t\t"):
                        parts = line.strip().split(None, 1)
                        if parts and parts[0].lower() == device_id.lower():
                            dn = parts[1] if len(parts) > 1 else device_id
                            break
            except OSError:
                pass
            break
    return vn, dn


def scan_gpu_devices() -> list[GPUDeviceInfo]:
    base = Path("/sys/bus/pci/devices")
    if not base.exists():
        return []
    gpus: list[GPUDeviceInfo] = []
    for entry in sorted(base.iterdir()):
        cv = _read_sysfs(entry / "class")
        if not cv:
            continue
        try:
            ch = (int(cv, 16) >> 8) & 0xFFFF
        except ValueError:
            continue
        if ch not in (0x0300, 0x0302):
            continue
        vid = _read_sysfs(entry / "vendor").removeprefix("0x")
        did = _read_sysfs(entry / "device").removeprefix("0x")
        if not vid or not did:
            continue
        dl = entry / "driver"
        cd = ""
        if dl.is_symlink() or dl.exists():
            try:
                cd = dl.resolve().name
            except OSError:
                pass
        il = entry / "iommu_group"
        ig = ""
        if il.is_symlink() or il.exists():
            try:
                ig = il.resolve().name
            except OSError:
                pass
        vn, dn = _resolve_pci_name(vid, did)
        gpus.append(GPUDeviceInfo(entry.name, vid, did, vn, dn, cd, ig))
    return gpus


def generate_vfio_commands(gpu: GPUDeviceInfo) -> str:
    lines = [f"# Bind {gpu.display_name} ({gpu.pci_addr}) to vfio-pci",
             "# Run as root:", "", "modprobe vfio-pci", ""]
    if gpu.current_driver:
        lines.append(f"echo '{gpu.pci_addr}' > /sys/bus/pci/devices/{gpu.pci_addr}/driver/unbind")
    else:
        lines.append("# (no driver bound)")
    lines += ["", f"echo '{gpu.vendor_id} {gpu.device_id}' > /sys/bus/pci/drivers/vfio-pci/new_id",
              "", f"# Persistent: options vfio-pci ids={gpu.vendor_id}:{gpu.device_id}"]
    return "\n".join(lines)


WARN_STYLE = (
    f"background-color: #2d2010; border: 1px solid {WARNING};"
    f" border-radius: 6px; padding: 12px; color: {WARNING}; font-size: 12px;"
)
_GPU_TREE_CSS = f"""
QTreeWidget {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    font-size: 12px;
    outline: none;
    gridline-color: {BORDER};
}}
QTreeWidget::item {{
    border: none;
    padding: 6px;
}}
QTreeWidget::item:selected {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
}}
QHeaderView {{
    border: none;
    background: {BG_CARD};
}}
QHeaderView::section {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-size: 11px;
    font-weight: 600;
}}
QHeaderView::section:first {{
    border-top-left-radius: 6px;
}}
QHeaderView::section:last {{
    border-top-right-radius: 6px;
}}
"""

CODE_STYLE = f"""
QPlainTextEdit {{
    background-color: {BG_CARD}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER}; border-radius: 6px;
    padding: 10px; font-family: monospace; font-size: 11px;
}}
"""


class GPUPanel(QFrame):
    config_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._assigned: list[str] = []
        self._gpus: list[GPUDeviceInfo] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG_PANEL}; border: none; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {BG_PANEL};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(14)

        self.iommu_banner = QLabel()
        self.iommu_banner.setWordWrap(True)
        self.iommu_banner.setStyleSheet(WARN_STYLE)
        layout.addWidget(self.iommu_banner)
        self._update_iommu_banner()

        layout.addWidget(self._sl("HOST GPU DEVICES"))

        # Bordered container for tree + buttons
        host_box = QWidget()
        host_box.setStyleSheet(f"background: transparent; border: none;")
        host_box_layout = QVBoxLayout(host_box)
        host_box_layout.setContentsMargins(0, 0, 0, 8)
        host_box_layout.setSpacing(0)

        self.gpu_tree = QTreeWidget()
        self.gpu_tree.setHeaderLabels(["Device", "PCI Address", "Driver", "IOMMU"])
        self.gpu_tree.setStyleSheet(_GPU_TREE_CSS)
        self.gpu_tree.setRootIsDecorated(False)
        self.gpu_tree.setItemsExpandable(False)
        self.gpu_tree.setFixedHeight(130)
        h = self.gpu_tree.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        host_box_layout.addWidget(self.gpu_tree)

        self.btn_assign = QPushButton("Assign to VM")
        self.btn_assign.setFixedHeight(36)
        self.btn_assign.setMaximumWidth(130)
        self.btn_assign.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_assign.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.btn_assign.setStyleSheet(
            f"background:{ACCENT}; color:{TEXT_ON_ACCENT};"
            f" border-radius:6px; font-weight:700;"
            f" font-size:12px; border:none; padding:0 12px;")
        self.btn_assign.clicked.connect(self._on_assign)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setFixedHeight(36)
        self.btn_refresh.setMaximumWidth(90)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.btn_refresh.setStyleSheet(
            f"background:transparent; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER};"
            f" border-radius:6px; font-size:12px; padding:0 12px;")
        self.btn_refresh.clicked.connect(self.refresh_gpu_list)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 8, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addWidget(self.btn_assign)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addStretch()
        host_box_layout.addLayout(btn_row)

        layout.addWidget(host_box)

        layout.addWidget(self._sl("ASSIGNED GPUS"))

        self._passthrough_warning = QLabel(
            "\u26a0  GPU passthrough grants the VM direct hardware access, "
            "bypassing IOMMU protections. Only assign GPUs to trusted VMs.")
        self._passthrough_warning.setWordWrap(True)
        self._passthrough_warning.setStyleSheet(
            f"background-color: #2d1a00; border: 1px solid #e67e00;"
            f" border-radius: 6px; padding: 10px; color: #e67e00; font-size: 11px;")
        self._passthrough_warning.hide()
        layout.addWidget(self._passthrough_warning)

        self.assigned_tree = QTreeWidget()
        self.assigned_tree.setHeaderLabels(["Device", "PCI Address", "Driver", "IOMMU"])
        self.assigned_tree.setStyleSheet(_GPU_TREE_CSS)
        self.assigned_tree.setRootIsDecorated(False)
        self.assigned_tree.setItemsExpandable(False)
        self.assigned_tree.setFixedHeight(80)
        ah = self.assigned_tree.header()
        ah.setStretchLastSection(False)
        ah.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            ah.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.assigned_tree)

        r2 = QHBoxLayout()
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setStyleSheet(subtle_btn_style())
        self.btn_remove.setFixedHeight(32)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.clicked.connect(self._on_remove)
        r2.addWidget(self.btn_remove)
        r2.addStretch()
        layout.addLayout(r2)

        layout.addWidget(self._sl("VFIO SETUP ASSISTANT"))
        self.vfio_explain = QLabel(
            "GPU passthrough requires the device to be bound to vfio-pci. "
            "Select a GPU and click 'Generate VFIO Commands'.")
        self.vfio_explain.setWordWrap(True)
        self.vfio_explain.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(self.vfio_explain)

        r3 = QHBoxLayout()
        self.btn_gen_vfio = QPushButton("Generate VFIO Commands")
        self.btn_gen_vfio.setStyleSheet(subtle_btn_style())
        self.btn_gen_vfio.setFixedHeight(32)
        self.btn_gen_vfio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen_vfio.clicked.connect(self._on_gen_vfio)
        r3.addWidget(self.btn_gen_vfio)
        r3.addStretch()
        layout.addLayout(r3)

        self.vfio_commands = QPlainTextEdit()
        self.vfio_commands.setReadOnly(True)
        self.vfio_commands.setStyleSheet(CODE_STYLE)
        self.vfio_commands.setFixedHeight(160)
        self.vfio_commands.setPlaceholderText("Select a GPU and click 'Generate VFIO Commands'...")
        layout.addWidget(self.vfio_commands)
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.refresh_gpu_list()

    @staticmethod
    def _sl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(SECTION_LABEL_STYLE)
        return lbl

    def _update_iommu_banner(self) -> None:
        enabled, count = _check_iommu()
        if enabled:
            self.iommu_banner.setText(f"IOMMU enabled ({count} group{'s' if count != 1 else ''}).")
            self.iommu_banner.setStyleSheet(
                f"background-color: #1a2d1e; border: 1px solid #2d5a3d;"
                f" border-radius: 6px; padding: 12px; color: {TEXT_PRIMARY}; font-size: 12px;")
        else:
            self.iommu_banner.setText("IOMMU not enabled. Add intel_iommu=on or amd_iommu=on to kernel params.")
            self.iommu_banner.setStyleSheet(WARN_STYLE)

    def refresh_gpu_list(self) -> None:
        self._gpus = scan_gpu_devices()
        self.gpu_tree.clear()
        for gpu in self._gpus:
            dt = gpu.current_driver or "(none)"
            if gpu.is_vfio:
                dt += " (ready)"
            it = f"Group {gpu.iommu_group}" if gpu.iommu_group else "N/A"
            item = QTreeWidgetItem([gpu.display_name, gpu.pci_addr, dt, it])
            item.setData(0, Qt.ItemDataRole.UserRole, gpu)
            self.gpu_tree.addTopLevelItem(item)
        self._update_iommu_banner()

    def set_assigned_gpus(self, pci_addrs: list[str]) -> None:
        self._assigned = list(pci_addrs)
        self._rebuild()

    def _rebuild(self) -> None:
        self.assigned_tree.clear()
        self._passthrough_warning.setVisible(len(self._assigned) > 0)
        gm = {g.pci_addr: g for g in self._gpus}
        for addr in self._assigned:
            gpu = gm.get(addr)
            if gpu:
                dt = gpu.current_driver or "(none)"
                if gpu.is_vfio:
                    dt += " (ready)"
                it = f"Group {gpu.iommu_group}" if gpu.iommu_group else "N/A"
                item = QTreeWidgetItem([gpu.display_name, addr, dt, it])
            else:
                item = QTreeWidgetItem([addr, addr, "?", "?"])
            item.setData(0, Qt.ItemDataRole.UserRole, addr)
            self.assigned_tree.addTopLevelItem(item)

    def _on_assign(self) -> None:
        item = self.gpu_tree.currentItem()
        if item is None:
            return
        gpu: GPUDeviceInfo = item.data(0, Qt.ItemDataRole.UserRole)
        if gpu.pci_addr not in self._assigned:
            self._assigned.append(gpu.pci_addr)
            self._rebuild()
            self.config_changed.emit(list(self._assigned))

    def _on_remove(self) -> None:
        item = self.assigned_tree.currentItem()
        if item is None:
            return
        addr = item.data(0, Qt.ItemDataRole.UserRole)
        self._assigned = [a for a in self._assigned if a != addr]
        self._rebuild()
        self.config_changed.emit(list(self._assigned))

    def _on_gen_vfio(self) -> None:
        item = self.gpu_tree.currentItem()
        if item is None:
            self.vfio_commands.setPlainText("# Select a GPU first.")
            return
        self.vfio_commands.setPlainText(generate_vfio_commands(item.data(0, Qt.ItemDataRole.UserRole)))

    def apply_theme(self) -> None:
        from app.ui import theme
        self.setStyleSheet(f"background-color: {theme.get('BG_PANEL')}; border: none;")
        self.gpu_tree.setStyleSheet(theme.GPU_TREE_STYLE)
        self.assigned_tree.setStyleSheet(theme.GPU_TREE_STYLE)
        self.btn_assign.setStyleSheet(
            f"background:{theme.get('ACCENT')}; color:{theme.get('TEXT_ON_ACCENT')};"
            f" border-radius:6px; font-weight:700; font-size:12px; border:none;")
        self.btn_refresh.setStyleSheet(
            f"background:transparent; color:{theme.get('TEXT_SECONDARY')};"
            f" border:1px solid {theme.get('BORDER')}; border-radius:6px; font-size:12px;")
