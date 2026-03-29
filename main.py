#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.main_window import MainWindow
from config.vm_config import VMConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

MIN_QEMU_VERSION = (8, 0, 0)


def _check_qemu_version() -> None:
    """Warn if the installed QEMU version is older than 8.0.0."""
    try:
        out = subprocess.check_output(
            ["qemu-system-x86_64", "--version"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
        match = re.search(r"version\s+(\d+)\.(\d+)\.(\d+)", out)
        if not match:
            return
        version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if version < MIN_QEMU_VERSION:
            QMessageBox.warning(
                None,
                "Outdated QEMU Version",
                f"Your QEMU version ({match.group(1)}.{match.group(2)}.{match.group(3)}) "
                f"is older than {'.'.join(str(v) for v in MIN_QEMU_VERSION)} and may have "
                f"known security vulnerabilities.\n\n"
                f"Please update via your package manager:\n"
                f"  sudo pacman -S qemu-full        (Arch/Manjaro)\n"
                f"  sudo apt install qemu-system-x86 (Debian/Ubuntu)\n"
                f"  sudo dnf install qemu-system-x86 (Fedora)",
            )
            log.warning("QEMU %s is below minimum recommended %s",
                         ".".join(str(v) for v in version),
                         ".".join(str(v) for v in MIN_QEMU_VERSION))
    except (FileNotFoundError, subprocess.SubprocessError):
        log.info("qemu-system-x86_64 not found, skipping version check")


def _install_desktop_file() -> None:
    """Copy .desktop file to ~/.local/share/applications/ for Wayland taskbar integration."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icosele-vault.desktop")
    dest_dir = os.path.expanduser("~/.local/share/applications")
    dest = os.path.join(dest_dir, "icosele-vault.desktop")
    try:
        if not os.path.exists(src):
            return
        os.makedirs(dest_dir, exist_ok=True)
        # Only copy if source is newer or dest doesn't exist
        if not os.path.exists(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
            import shutil
            shutil.copy2(src, dest)
            subprocess.run(
                ["update-desktop-database", dest_dir],
                capture_output=True, timeout=5,
            )
            log.info("Installed desktop file to %s", dest)
    except Exception as exc:
        log.debug("Could not install desktop file: %s", exc)


def main() -> None:
    configs = VMConfig.load_all()
    if not configs:
        logging.warning("No VM configs found in data/vms/ — creating default")
        default = VMConfig(name="test-vm")
        default.save()
        configs = [default]

    _install_desktop_file()

    app = QApplication(sys.argv)
    app.setApplicationName("")
    app.setDesktopFileName("icosele-vault")

    app_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(app_dir, "assets", "icon.png")
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
        app.setWindowIcon(icon)

    _check_qemu_version()

    window = MainWindow(configs)
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
