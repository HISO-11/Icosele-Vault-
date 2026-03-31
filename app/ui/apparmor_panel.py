"""Task 7 — AppArmor profile generator panel."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

_PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "apparmor"


def _apparmor_available() -> bool:
    return Path("/sys/kernel/security/apparmor").exists()


def generate_profile(vm_id: str, qemu_binary: str, disk_path: str,
                     iso_path: str = "") -> str:
    lines = [
        f"# AppArmor profile for Icosele VM VM: {vm_id}",
        f"# Auto-generated — do not edit manually",
        f"",
        f"profile icosele_vm_{vm_id} {qemu_binary} flags=(enforce) {{",
        f"  #include <abstractions/base>",
        f"  #include <abstractions/nameservice>",
        f"",
        f"  # QEMU binary",
        f"  {qemu_binary} mr,",
        f"",
        f"  # KVM device",
        f"  /dev/kvm rw,",
        f"",
        f"  # Network devices",
        f"  /dev/net/tun rw,",
        f"  /dev/vhost-net rw,",
        f"",
        f"  # Per-VM runtime directory",
        f"  owner /tmp/icosele-vm/{vm_id}/ rw,",
        f"  owner /tmp/icosele-vm/{vm_id}/** rw,",
    ]
    if disk_path:
        lines.append(f"")
        lines.append(f"  # Disk image")
        lines.append(f"  owner {disk_path} rw,")
    if iso_path:
        lines.append(f"")
        lines.append(f"  # ISO image (read-only)")
        lines.append(f"  {iso_path} r,")
    lines += [
        f"",
        f"  # Deny everything else",
        f"  deny /** w,",
        f"}}",
    ]
    return "\n".join(lines)


def profile_loaded(vm_id: str) -> bool:
    try:
        out = subprocess.check_output(
            ["aa-status", "--json"], timeout=5,
            stderr=subprocess.DEVNULL).decode(errors="replace")
        return f"icosele_vm_{vm_id}" in out
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


class AppArmorPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_id = ""
        self._qemu_binary = ""
        self._disk_path = ""
        self._iso_path = ""
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(QLabel("APPARMOR PROFILE", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "AppArmor restricts what files and devices the QEMU process can access, "
            "providing mandatory access control for VM isolation. "
            "A custom profile is generated per-VM based on its disk and ISO paths.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Status
        status_card = QFrame()
        status_card.setStyleSheet(
            f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
        sc_lay = QVBoxLayout(status_card)
        sc_lay.setContentsMargins(14, 12, 14, 12)
        sc_lay.setSpacing(6)

        self._aa_status = QLabel("")
        self._aa_status.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        sc_lay.addWidget(self._aa_status)

        self._profile_status = QLabel("")
        self._profile_status.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        sc_lay.addWidget(self._profile_status)
        layout.addWidget(status_card)

        # Buttons
        br = QHBoxLayout()
        br.setSpacing(8)
        self._btn_generate = QPushButton("Generate Profile")
        self._btn_generate.setStyleSheet(save_btn_style())
        self._btn_generate.setFixedHeight(30)
        self._btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_load = QPushButton("Load Profile")
        self._btn_load.setStyleSheet(subtle_btn_style())
        self._btn_load.setFixedHeight(30)
        self._btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        br.addWidget(self._btn_generate)
        br.addWidget(self._btn_load)
        br.addStretch()
        layout.addLayout(br)

        # Preview
        layout.addWidget(QLabel("PROFILE PREVIEW", styleSheet=SECTION_LABEL_STYLE))
        self._preview = QLabel("")
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 10px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 8px;")
        layout.addWidget(self._preview)

        note = QLabel(
            "AppArmor provides mandatory access control (MAC), confining QEMU "
            "to only the files it needs. This prevents a compromised VM from "
            "accessing host files outside its sandbox.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(note)
        layout.addStretch()

        self._btn_generate.clicked.connect(self._on_generate)
        self._btn_load.clicked.connect(self._on_load)

    def set_config(self, vm_id: str, qemu_binary: str,
                   disk_path: str, iso_path: str = "") -> None:
        self._vm_id = vm_id
        self._qemu_binary = qemu_binary
        self._disk_path = disk_path
        self._iso_path = iso_path
        self._refresh_status()

    def _refresh_status(self) -> None:
        if not _apparmor_available():
            self._aa_status.setText("AppArmor: unavailable")
            self._aa_status.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            self._profile_status.setText("AppArmor is not enabled on this system.")
            return
        self._aa_status.setText("AppArmor: available")
        if self._vm_id and profile_loaded(self._vm_id):
            self._profile_status.setText("Profile: Loaded and enforcing")
            self._aa_status.setStyleSheet(
                f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
        else:
            self._profile_status.setText("Profile: Not loaded")
            self._aa_status.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
        # Update preview
        if self._vm_id:
            self._preview.setText(generate_profile(
                self._vm_id, self._qemu_binary, self._disk_path, self._iso_path))

    def _on_generate(self) -> None:
        if not self._vm_id:
            return
        profile = generate_profile(
            self._vm_id, self._qemu_binary, self._disk_path, self._iso_path)
        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        path = _PROFILE_DIR / f"{self._vm_id}_qemu.profile"
        path.write_text(profile)
        self._preview.setText(profile)
        QMessageBox.information(self, "Profile Generated", f"Saved to:\n{path}")

    def _on_load(self) -> None:
        if not self._vm_id:
            return
        src = _PROFILE_DIR / f"{self._vm_id}_qemu.profile"
        if not src.exists():
            QMessageBox.warning(self, "Not Found",
                                "Generate the profile first.")
            return
        dest = f"/etc/apparmor.d/icosele_vm_{self._vm_id}"
        try:
            subprocess.run(
                ["pkexec", "cp", str(src), dest],
                check=True, capture_output=True, timeout=15)
            subprocess.run(
                ["pkexec", "apparmor_parser", "-r", dest],
                check=True, capture_output=True, timeout=15)
            self._refresh_status()
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "Error", f"Failed to load profile:\n{exc}")
