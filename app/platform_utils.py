"""Cross-platform utilities — Windows, macOS, Linux support."""
from __future__ import annotations

import os
import sys


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_windows() -> bool:
    return sys.platform == "win32"


def is_mac() -> bool:
    return sys.platform == "darwin"


def get_qemu_binary() -> str:
    if is_windows():
        paths = [
            r"C:\Program Files\qemu\qemu-system-x86_64.exe",
            r"C:\Program Files (x86)\qemu\qemu-system-x86_64.exe",
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return "qemu-system-x86_64.exe"
    elif is_mac():
        paths = [
            "/usr/local/bin/qemu-system-x86_64",
            "/opt/homebrew/bin/qemu-system-x86_64",
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return "qemu-system-x86_64"
    else:
        return "/usr/bin/qemu-system-x86_64"


def get_kvm_available() -> bool:
    if is_linux():
        try:
            return os.access("/dev/kvm", os.R_OK | os.W_OK)
        except OSError:
            return False
    elif is_windows():
        import subprocess
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform"],
                capture_output=True, text=True, timeout=10,
            )
            return "Enabled" in result.stdout
        except Exception:
            return False
    elif is_mac():
        return True  # HVF always available on macOS
    return False


def get_accel_flags() -> list[str]:
    if is_linux() and get_kvm_available():
        return ["-enable-kvm", "-cpu", "host"]
    elif is_windows() and get_kvm_available():
        return ["-accel", "whpx", "-cpu", "host"]
    elif is_mac():
        return ["-accel", "hvf", "-cpu", "host"]
    else:
        return ["-cpu", "qemu64"]


def get_temp_dir() -> str:
    if is_windows():
        import tempfile
        return os.path.join(tempfile.gettempdir(), "icosele-vault")
    elif is_mac():
        return os.path.join("/tmp", "icosele-vault")
    else:
        return "/tmp/icosele-vault"


def get_data_dir() -> str:
    if is_windows():
        return os.path.join(os.environ.get("APPDATA", ""), "IcoseleVault")
    elif is_mac():
        return os.path.expanduser("~/Library/Application Support/IcoseleVault")
    else:
        return str(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
