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


def main() -> None:
    configs = VMConfig.load_all()
    if not configs:
        logging.warning("No VM configs found in data/vms/ — creating default")
        default = VMConfig(name="test-vm")
        default.save()
        configs = [default]

    app = QApplication(sys.argv)
    app.setApplicationName("NovaMachine")

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    _check_qemu_version()

    window = MainWindow(configs)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
