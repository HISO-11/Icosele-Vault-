"""Task 3 — GPU Passthrough one-checkbox setup wizard."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, SECTION_LABEL_STYLE,
    STOP_RED, TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY,
    WARNING, primary_btn_style, secondary_btn_style, save_btn_style,
    subtle_btn_style,
)

_PCI_BASE = Path("/sys/bus/pci/devices")


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except (OSError, ValueError):
        return ""


def _scan_gpus() -> list[dict]:
    gpus = []
    if not _PCI_BASE.exists():
        return gpus
    for dev in sorted(_PCI_BASE.iterdir()):
        cls = _read(dev / "class")
        if not cls:
            continue
        cls_int = int(cls, 16) >> 8
        if cls_int not in (0x0300, 0x0302):
            continue
        vid = _read(dev / "vendor").replace("0x", "")
        did = _read(dev / "device").replace("0x", "")
        driver = ""
        drv_link = dev / "driver"
        if drv_link.is_symlink():
            driver = drv_link.resolve().name
        iommu = ""
        ig = dev / "iommu_group"
        if ig.is_symlink():
            iommu = ig.resolve().name
        gpus.append({
            "pci_addr": dev.name,
            "vendor_id": vid,
            "device_id": did,
            "driver": driver,
            "iommu_group": iommu,
            "class": "Display" if cls_int == 0x0300 else "3D",
        })
    return gpus


def _iommu_group_devices(group: str) -> list[dict]:
    gp = Path(f"/sys/kernel/iommu_groups/{group}/devices")
    if not gp.exists():
        return []
    devs = []
    for link in sorted(gp.iterdir()):
        pci = link.name
        dev_path = _PCI_BASE / pci
        vid = _read(dev_path / "vendor").replace("0x", "")
        did = _read(dev_path / "device").replace("0x", "")
        driver = ""
        drv = dev_path / "driver"
        if drv.is_symlink():
            driver = drv.resolve().name
        devs.append({"pci_addr": pci, "vendor_id": vid, "device_id": did, "driver": driver})
    return devs


def _iommu_enabled() -> bool:
    g = Path("/sys/kernel/iommu_groups")
    return g.exists() and any(g.iterdir()) if g.exists() else False


def _vfio_loaded() -> bool:
    try:
        out = subprocess.check_output(["lsmod"], text=True, timeout=5)
        return "vfio_pci" in out
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _is_primary_gpu(pci_addr: str) -> bool:
    drm = Path("/sys/class/drm/card0")
    if drm.is_symlink():
        return pci_addr in str(drm.resolve())
    return False


class GPUPassthroughWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result_pci_addrs: list[str] = []
        self._gpus = _scan_gpus()
        self._selected_gpu: dict | None = None
        self._group_devs: list[dict] = []
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("GPU Passthrough Setup")
        self.setFixedSize(600, 560)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        root.addWidget(self._stack)
        self._stack.addWidget(self._build_step1())
        self._stack.addWidget(self._build_step2())
        self._stack.addWidget(self._build_step3())
        self._stack.addWidget(self._build_step4())
        self._stack.addWidget(self._build_step5())
        self._stack.setCurrentIndex(0)

    def _page(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(12)
        t = QLabel(title)
        t.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
                        f" background: transparent; font-family: {FONT_FAMILY};")
        lay.addWidget(t)
        return w, lay

    def _nav(self, lay, back_idx=None, next_fn=None, finish=False):
        br = QHBoxLayout()
        if back_idx is not None:
            b = QPushButton("Back")
            b.setStyleSheet(secondary_btn_style()); b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: self._stack.setCurrentIndex(back_idx))
            br.addWidget(b)
        br.addStretch()
        if next_fn:
            label = "Done" if finish else "Next"
            n = QPushButton(label)
            n.setStyleSheet(primary_btn_style()); n.setFixedHeight(34)
            n.setMinimumWidth(80)
            n.setCursor(Qt.CursorShape.PointingHandCursor)
            n.clicked.connect(next_fn)
            br.addWidget(n)
        lay.addLayout(br)

    # Step 1 — Detection
    def _build_step1(self):
        w, lay = self._page("Step 1: GPU Detection")
        if not self._gpus:
            lay.addWidget(QLabel("No discrete GPUs found in /sys/bus/pci/devices.",
                                  styleSheet=f"color: {WARNING}; font-size: 12px; background: transparent;"))
            lay.addStretch()
            self._nav(lay, next_fn=self.reject)
            return w
        for gpu in self._gpus:
            card = QLabel(
                f"PCI: {gpu['pci_addr']}  |  {gpu['vendor_id']}:{gpu['device_id']}  |  "
                f"Driver: {gpu['driver'] or 'none'}  |  IOMMU group: {gpu['iommu_group'] or '?'}  |  "
                f"Type: {gpu['class']}")
            card.setWordWrap(True)
            card.setStyleSheet(
                f"background-color: {BG_CARD}; border: 1px solid {BORDER};"
                f" border-radius: 6px; padding: 10px; font-size: 11px;"
                f" color: {TEXT_PRIMARY}; font-family: monospace;")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda e, g=gpu: self._select_gpu(g)
            lay.addWidget(card)
        lay.addStretch()
        self._nav(lay, next_fn=lambda: self._stack.setCurrentIndex(1))
        return w

    def _select_gpu(self, gpu):
        self._selected_gpu = gpu
        ig = gpu.get("iommu_group", "")
        self._group_devs = _iommu_group_devices(ig) if ig else [gpu]
        self._stack.setCurrentIndex(1)

    # Step 2 — Compatibility
    def _build_step2(self):
        w, lay = self._page("Step 2: Compatibility Check")
        self._checks_area = QVBoxLayout()
        lay.addLayout(self._checks_area)
        lay.addStretch()
        recheck = QPushButton("Re-check")
        recheck.setStyleSheet(subtle_btn_style()); recheck.setFixedHeight(28)
        recheck.setCursor(Qt.CursorShape.PointingHandCursor)
        recheck.clicked.connect(self._run_checks)
        lay.addWidget(recheck)
        self._nav(lay, back_idx=0, next_fn=lambda: self._stack.setCurrentIndex(2))
        return w

    def _run_checks(self):
        while self._checks_area.count():
            w = self._checks_area.takeAt(0).widget()
            if w: w.deleteLater()
        checks = [
            ("IOMMU enabled", _iommu_enabled()),
            ("vfio-pci module loaded", _vfio_loaded()),
        ]
        if self._selected_gpu:
            is_primary = _is_primary_gpu(self._selected_gpu["pci_addr"])
            checks.append(("Not primary display (safe to unbind)", not is_primary))
        for label, ok in checks:
            icon = "\u2705" if ok else "\u274c"
            color = ACCENT if ok else STOP_RED
            lbl = QLabel(f"{icon}  {label}")
            lbl.setStyleSheet(f"color: {color}; font-size: 13px; background: transparent;")
            self._checks_area.addWidget(lbl)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._run_checks()

    # Step 3 — Commands
    def _build_step3(self):
        w, lay = self._page("Step 3: Bind to vfio-pci")
        lay.addWidget(QLabel("Run these commands as root to bind the GPU to vfio-pci:",
                              styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        self._cmd_box = QPlainTextEdit()
        self._cmd_box.setReadOnly(True)
        self._cmd_box.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {BG_CARD}; color: {ACCENT};"
            f" border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;"
            f" font-size: 11px; font-family: monospace; }}")
        self._cmd_box.setMaximumHeight(160)
        lay.addWidget(self._cmd_box)
        cr = QHBoxLayout()
        cp = QPushButton("Copy All")
        cp.setStyleSheet(subtle_btn_style()); cp.setFixedHeight(28)
        cp.setCursor(Qt.CursorShape.PointingHandCursor)
        cp.clicked.connect(self._copy_cmds)
        term = QPushButton("Open Terminal")
        term.setStyleSheet(subtle_btn_style()); term.setFixedHeight(28)
        term.setCursor(Qt.CursorShape.PointingHandCursor)
        term.clicked.connect(self._open_terminal)
        cr.addWidget(cp); cr.addWidget(term); cr.addStretch()
        lay.addLayout(cr)
        warn = QLabel("These commands will unbind the GPU from its current driver. "
                       "Do not run on your primary display GPU.")
        warn.setWordWrap(True)
        warn.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 8px; color: {WARNING}; font-size: 11px;")
        lay.addWidget(warn)
        lay.addStretch()
        self._nav(lay, back_idx=1, next_fn=lambda: self._stack.setCurrentIndex(3))
        return w

    def _generate_cmds(self):
        lines = ["modprobe vfio-pci"]
        for d in self._group_devs:
            lines.append(f'echo "{d["vendor_id"]} {d["device_id"]}" > /sys/bus/pci/drivers/vfio-pci/new_id')
        self._cmd_box.setPlainText("\n".join(lines))

    def _copy_cmds(self):
        from PySide6.QtGui import QGuiApplication
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self._cmd_box.toPlainText())

    def _open_terminal(self):
        for term in ("gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
            try:
                subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue

    # Step 4 — Verify
    def _build_step4(self):
        w, lay = self._page("Step 4: Verify & Apply")
        self._verify_status = QLabel("")
        self._verify_status.setWordWrap(True)
        self._verify_status.setStyleSheet(
            f"font-size: 12px; background: transparent; color: {TEXT_PRIMARY};")
        lay.addWidget(self._verify_status)
        chk = QPushButton("Check Again")
        chk.setStyleSheet(subtle_btn_style()); chk.setFixedHeight(28)
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        chk.clicked.connect(self._verify)
        lay.addWidget(chk)
        self._args_preview = QLabel("")
        self._args_preview.setWordWrap(True)
        self._args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px;")
        lay.addWidget(self._args_preview)
        lay.addStretch()
        self._nav(lay, back_idx=2, next_fn=lambda: self._stack.setCurrentIndex(4))
        return w

    def _verify(self):
        if not self._selected_gpu:
            return
        ig = self._selected_gpu.get("iommu_group", "")
        devs = _iommu_group_devices(ig) if ig else []
        all_vfio = all(d.get("driver") == "vfio-pci" for d in devs)
        if all_vfio and devs:
            self._verify_status.setText("\u2705 All devices in IOMMU group are bound to vfio-pci!")
            self._verify_status.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600; background: transparent;")
            self.result_pci_addrs = [d["pci_addr"] for d in devs]
            args = " ".join(f"-device vfio-pci,host={a}" for a in self.result_pci_addrs)
            self._args_preview.setText(f"QEMU args:\n{args}")
        else:
            drivers = ", ".join(f"{d['pci_addr']}={d.get('driver', '?')}" for d in devs)
            self._verify_status.setText(f"\u274c Not all devices bound to vfio-pci yet.\n{drivers}")
            self._verify_status.setStyleSheet(
                f"color: {WARNING}; font-size: 12px; background: transparent;")
            self._args_preview.setText("")

    # Step 5 — Looking Glass
    def _build_step5(self):
        w, lay = self._page("Step 5: Looking Glass (Optional)")
        info = QLabel(
            "For Windows VMs, Looking Glass provides ultra-low latency "
            "display capture without needing a second monitor.\n\n"
            "Website: https://looking-glass.io\n\n"
            "It requires an IVSHMEM shared memory device. Add these QEMU args:")
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(info)
        args_lbl = QLabel(
            "-device ivshmem-plain,memdev=ivshmem,bus=pcie.0\n"
            "-object memory-backend-file,id=ivshmem,share=on,"
            "mem-path=/dev/shm/looking-glass,size=128M")
        args_lbl.setWordWrap(True)
        args_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        args_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px;")
        lay.addWidget(args_lbl)
        lay.addStretch()
        self._nav(lay, back_idx=3, next_fn=self.accept, finish=True)
        return w

    def showEvent(self, ev):
        super().showEvent(ev)
        self._generate_cmds()
