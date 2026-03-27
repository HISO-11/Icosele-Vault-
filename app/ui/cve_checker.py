"""Task 6 — QEMU CVE version checker (no network requests)."""
from __future__ import annotations

import re
import subprocess

# Hardcoded CVE database: (max_affected_version, cve_id, description)
_CVE_DB: list[tuple[tuple[int, int, int], str, str]] = [
    ((5, 255, 255), "CVE-2021-3527", "USB host device emulation use-after-free"),
    ((6, 255, 255), "CVE-2022-0216", "LSI SCSI double-free vulnerability"),
    ((7, 255, 255), "CVE-2023-3301", "NVME-oF invalid memory access"),
]


def get_qemu_version() -> tuple[int, int, int] | None:
    try:
        out = subprocess.check_output(
            ["qemu-system-x86_64", "--version"],
            text=True, timeout=5, stderr=subprocess.DEVNULL)
        m = re.search(r"version\s+(\d+)\.(\d+)\.(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


def check_cves(version: tuple[int, int, int] | None = None) -> list[dict]:
    if version is None:
        version = get_qemu_version()
    if version is None:
        return []
    hits = []
    for max_ver, cve_id, desc in _CVE_DB:
        if version <= max_ver:
            hits.append({"cve": cve_id, "description": desc,
                         "max_affected": f"{max_ver[0]}.x"})
    return hits
