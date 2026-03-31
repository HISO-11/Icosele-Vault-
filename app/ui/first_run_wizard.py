"""First-run setup wizard — checks and helps install required dependencies."""
from __future__ import annotations

import platform
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    primary_btn_style, secondary_btn_style, subtle_btn_style,
)

_SETTINGS_DIR = Path.home() / ".icosele-vault"
_FIRST_RUN_FLAG = _SETTINGS_DIR / ".first_run_done"


def needs_first_run() -> bool:
    return not _FIRST_RUN_FLAG.exists()


def mark_first_run_done() -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _FIRST_RUN_FLAG.touch()


def _detect_distro() -> str:
    """Detect package manager family."""
    if shutil.which("pacman"):
        return "arch"
    if shutil.which("apt"):
        return "debian"
    if shutil.which("dnf"):
        return "fedora"
    if shutil.which("brew"):
        return "macos"
    return "unknown"


_INSTALL_CMDS = {
    "arch": {
        "qemu": "sudo pacman -S qemu-full",
        "swtpm": "sudo pacman -S swtpm",
        "ovmf": "sudo pacman -S edk2-ovmf",
    },
    "debian": {
        "qemu": "sudo apt install qemu-system-x86",
        "swtpm": "sudo apt install swtpm",
        "ovmf": "sudo apt install ovmf",
    },
    "fedora": {
        "qemu": "sudo dnf install qemu-system-x86",
        "swtpm": "sudo dnf install swtpm",
        "ovmf": "sudo dnf install edk2-ovmf",
    },
    "macos": {
        "qemu": "brew install qemu",
        "swtpm": "brew install swtpm",
        "ovmf": "(not available on macOS)",
    },
}

_OVMF_PATHS = [
    "/usr/share/OVMF/x64/OVMF_CODE.4m.fd",
    "/usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd",
    "/usr/share/OVMF/OVMF_CODE.secboot.fd",
    "/usr/share/OVMF/OVMF_CODE.fd",
    "/usr/share/ovmf/OVMF.fd",
    "/usr/share/edk2-ovmf/x64/OVMF_CODE.fd",
    "/usr/share/qemu/OVMF.fd",
]


class FirstRunWizard(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._distro = _detect_distro()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Icosele Vault — First Run Setup")
        self.setFixedSize(520, 440)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = QLabel("Welcome to Icosele Vault")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(title)

        sub = QLabel("Checking required dependencies for virtual machine management.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(sub)
        layout.addSpacing(8)

        # Dependency checks
        checks = [
            ("QEMU", shutil.which("qemu-system-x86_64") is not None, "qemu"),
            ("swtpm (TPM 2.0)", shutil.which("swtpm") is not None, "swtpm"),
            ("OVMF (UEFI firmware)", any(Path(p).exists() for p in _OVMF_PATHS), "ovmf"),
            ("virtio-win.iso", (Path.home() / "Downloads" / "virtio-win.iso").exists(), None),
        ]

        cmds = _INSTALL_CMDS.get(self._distro, {})

        for name, installed, pkg_key in checks:
            row = QHBoxLayout()
            row.setSpacing(8)

            icon = "\u2705" if installed else "\u274c"
            status = "Installed" if installed else "Missing"
            lbl = QLabel(f"{icon}  {name}  —  {status}")
            lbl.setStyleSheet(
                f"color: {ACCENT if installed else '#f38ba8'}; font-size: 13px;"
                f" font-weight: 600; background: transparent; font-family: {FONT_FAMILY};")
            row.addWidget(lbl, 1)

            if not installed and pkg_key and pkg_key in cmds:
                cmd_lbl = QLabel(cmds[pkg_key])
                cmd_lbl.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 10px; font-family: monospace;"
                    f" background: transparent;")
                cmd_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(cmd_lbl)
            elif not installed and name == "virtio-win.iso":
                note = QLabel("Auto-downloaded when creating Windows VM")
                note.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
                row.addWidget(note)

            layout.addLayout(row)

        layout.addSpacing(8)

        distro_label = QLabel(f"Detected package manager: {self._distro}")
        distro_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(distro_label)

        all_ok = all(ok for _, ok, _ in checks[:3])  # QEMU + swtpm + OVMF
        if all_ok:
            msg = QLabel("All required dependencies are installed. You're ready to go!")
            msg.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            layout.addWidget(msg)
        else:
            msg = QLabel("Install missing dependencies above, then restart Icosele Vault.\n"
                         "You can still use the app — features requiring missing deps will be limited.")
            msg.setWordWrap(True)
            msg.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
            layout.addWidget(msg)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cont_btn = QPushButton("Continue")
        cont_btn.setStyleSheet(primary_btn_style())
        cont_btn.setFixedHeight(36)
        cont_btn.setMinimumWidth(100)
        cont_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cont_btn.clicked.connect(self._on_continue)
        btn_row.addWidget(cont_btn)
        layout.addLayout(btn_row)

    def _on_continue(self) -> None:
        mark_first_run_done()
        self.accept()
