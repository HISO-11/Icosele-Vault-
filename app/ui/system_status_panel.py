"""System status panel — platform checks, auto-update, isolation levels."""
from __future__ import annotations

import logging
import os
import platform
import shutil
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_VERSION = "1.0.0"


def _check_platform() -> list[dict]:
    """Check platform-specific virtualisation support."""
    checks = []
    system = platform.system()

    if system == "Linux":
        kvm_ok = os.access("/dev/kvm", os.R_OK | os.W_OK) if os.path.exists("/dev/kvm") else False
        checks.append({
            "name": "KVM",
            "ok": kvm_ok,
            "detail": "Hardware acceleration available" if kvm_ok
                      else "KVM not available — VMs will run slowly. Enable VT-x/AMD-V in BIOS.",
        })
        iommu_ok = os.path.exists("/sys/kernel/iommu_groups") and bool(
            os.listdir("/sys/kernel/iommu_groups"))
        checks.append({
            "name": "IOMMU",
            "ok": iommu_ok,
            "detail": "IOMMU enabled — GPU passthrough available" if iommu_ok
                      else "IOMMU not enabled — GPU passthrough unavailable",
        })
    elif system == "Darwin":
        is_arm = platform.machine() == "arm64"
        checks.append({
            "name": "Apple Silicon",
            "ok": not is_arm,
            "detail": "x86_64 VMs will run via emulation (slow)" if is_arm
                      else "Intel Mac — x86_64 VMs run natively",
        })
    elif system == "Windows":
        whpx = shutil.which("qemu-system-x86_64") is not None
        checks.append({
            "name": "WHPX/Hyper-V",
            "ok": whpx,
            "detail": "QEMU with WHPX available" if whpx
                      else "Install QEMU and enable Hyper-V for acceleration",
        })

    checks.append({
        "name": "QEMU",
        "ok": shutil.which("qemu-system-x86_64") is not None,
        "detail": shutil.which("qemu-system-x86_64") or "Not found",
    })

    return checks


class _UpdateSignals(QObject):
    result = Signal(str, str)  # version, url


class SystemStatusPanel(QFrame):
    isolation_changed = Signal(str)  # isolation level

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._check_update_async()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(QLabel("SYSTEM STATUS", styleSheet=SECTION_LABEL_STYLE))

        # Platform checks
        for check in _check_platform():
            icon = "\u2705" if check["ok"] else "\u274c"
            row = QLabel(f"{icon}  {check['name']}:  {check['detail']}")
            row.setWordWrap(True)
            row.setStyleSheet(
                f"color: {ACCENT if check['ok'] else '#f38ba8'}; font-size: 12px;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            layout.addWidget(row)

        # Update banner
        self._update_banner = QLabel("")
        self._update_banner.setWordWrap(True)
        self._update_banner.setOpenExternalLinks(True)
        self._update_banner.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        self._update_banner.hide()
        layout.addWidget(self._update_banner)

        # Version
        ver_label = QLabel(f"Icosele Vault v{_VERSION}  ({platform.system()} {platform.machine()})")
        ver_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        layout.addWidget(ver_label)

        # Isolation level selector
        layout.addWidget(QLabel("VM ISOLATION LEVEL", styleSheet=SECTION_LABEL_STYLE))
        iso_desc = QLabel(
            "Standard: normal networking  |  "
            "Restricted: no network, clipboard, shared folders  |  "
            "Air-gapped: completely isolated")
        iso_desc.setWordWrap(True)
        iso_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(iso_desc)

        iso_row = QHBoxLayout()
        self._iso_combo = QComboBox()
        self._iso_combo.setStyleSheet(COMBO_STYLE)
        self._iso_combo.addItem("Standard", "standard")
        self._iso_combo.addItem("Restricted", "restricted")
        self._iso_combo.addItem("Air-gapped", "airgapped")
        self._iso_combo.currentIndexChanged.connect(self._on_isolation_changed)
        iso_row.addWidget(self._iso_combo)
        iso_row.addStretch()
        layout.addLayout(iso_row)

        layout.addStretch()

    def set_isolation(self, level: str) -> None:
        idx = {"standard": 0, "restricted": 1, "airgapped": 2}.get(level, 0)
        self._iso_combo.blockSignals(True)
        self._iso_combo.setCurrentIndex(idx)
        self._iso_combo.blockSignals(False)

    def _on_isolation_changed(self) -> None:
        self.isolation_changed.emit(self._iso_combo.currentData() or "standard")

    def _check_update_async(self) -> None:
        self._update_sig = _UpdateSignals()
        self._update_sig.result.connect(self._on_update_result)
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self) -> None:
        try:
            import requests
            resp = requests.get(
                "https://api.github.com/repos/HISO-11/Icosele-Vault-/releases/latest",
                timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                tag = data.get("tag_name", "")
                url = data.get("html_url", "")
                if tag and tag.lstrip("v") != _VERSION:
                    self._update_sig.result.emit(tag, url)
        except Exception:
            pass

    def _on_update_result(self, version: str, url: str) -> None:
        self._update_banner.setText(
            f"Icosele Vault {version} is available — "
            f'<a href="{url}" style="color: {ACCENT};">Download update</a>')
        self._update_banner.show()
