"""Host resource monitor — cross-platform, stdlib only."""
from __future__ import annotations

import shutil
import subprocess
import time
from collections import deque
from pathlib import Path

from app.platform_utils import is_linux, is_mac, is_windows


def read_cpu_percent() -> float:
    """Read CPU usage percent — platform-aware."""
    if is_linux():
        return _cpu_linux()
    elif is_windows():
        return _cpu_windows()
    elif is_mac():
        return _cpu_mac()
    return 0.0


def _cpu_linux() -> float:
    try:
        def _read():
            line = Path("/proc/stat").read_text().splitlines()[0]
            vals = [int(v) for v in line.split()[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            total = sum(vals)
            return idle, total
        idle1, total1 = _read()
        time.sleep(0.1)
        idle2, total2 = _read()
        d_idle = idle2 - idle1
        d_total = total2 - total1
        if d_total == 0:
            return 0.0
        return max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100))
    except (OSError, ValueError, IndexError):
        return 0.0


def _cpu_windows() -> float:
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             "(Get-CimInstance Win32_Processor).LoadPercentage"],
            text=True, timeout=5)
        return float(out.strip())
    except Exception:
        return 0.0


def _cpu_mac() -> float:
    try:
        out = subprocess.check_output(["top", "-l", "1", "-n", "0"], text=True, timeout=5)
        for line in out.splitlines():
            if "CPU usage" in line:
                # "CPU usage: 5.0% user, 3.0% sys, 92.0% idle"
                parts = line.split()
                for i, p in enumerate(parts):
                    if "idle" in p and i > 0:
                        idle = float(parts[i - 1].rstrip("%,"))
                        return 100.0 - idle
        return 0.0
    except Exception:
        return 0.0


def read_ram_info() -> dict:
    """Read RAM info — platform-aware."""
    if is_linux():
        return _ram_linux()
    elif is_windows():
        return _ram_windows()
    elif is_mac():
        return _ram_mac()
    return {"total_mb": 0, "used_mb": 0, "available_mb": 0, "percent": 0}


def _ram_linux() -> dict:
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
        total = info.get("MemTotal", 0) / 1024
        avail = info.get("MemAvailable", info.get("MemFree", 0)) / 1024
        used = total - avail
        pct = (used / total * 100) if total > 0 else 0
        return {"total_mb": total, "used_mb": used, "available_mb": avail, "percent": pct}
    except (OSError, ValueError):
        return {"total_mb": 0, "used_mb": 0, "available_mb": 0, "percent": 0}


def _ram_windows() -> dict:
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             "Get-CimInstance Win32_OperatingSystem | "
             "Select-Object TotalVisibleMemorySize,FreePhysicalMemory | "
             "ConvertTo-Json"],
            text=True, timeout=5)
        import json
        data = json.loads(out)
        total = data.get("TotalVisibleMemorySize", 0) / 1024
        free = data.get("FreePhysicalMemory", 0) / 1024
        used = total - free
        pct = (used / total * 100) if total > 0 else 0
        return {"total_mb": total, "used_mb": used, "available_mb": free, "percent": pct}
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "available_mb": 0, "percent": 0}


def _ram_mac() -> dict:
    try:
        import os
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=5)
        total = int(out.strip()) / (1024 * 1024)
        vm_out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
        free_pages = 0
        for line in vm_out.splitlines():
            if "Pages free" in line:
                free_pages = int(line.split(":")[1].strip().rstrip("."))
        free = free_pages * 4096 / (1024 * 1024)
        used = total - free
        pct = (used / total * 100) if total > 0 else 0
        return {"total_mb": total, "used_mb": used, "available_mb": free, "percent": pct}
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "available_mb": 0, "percent": 0}


def read_disk_usage(path: str = "") -> dict:
    """Disk usage — works on all platforms via shutil."""
    from app.platform_utils import get_data_dir
    target = path or get_data_dir()
    try:
        u = shutil.disk_usage(target)
        pct = (u.used / u.total * 100) if u.total > 0 else 0
        return {"total_gb": u.total / (1024**3), "used_gb": u.used / (1024**3),
                "free_gb": u.free / (1024**3), "percent": pct}
    except OSError:
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}


class ResourceHistory:
    """Rolling window of CPU and RAM readings."""
    def __init__(self, maxlen: int = 60):
        self.cpu: deque[float] = deque(maxlen=maxlen)
        self.ram: deque[float] = deque(maxlen=maxlen)
        self._high_pressure_count = 0

    def record(self, cpu: float, ram: float) -> None:
        self.cpu.append(cpu)
        self.ram.append(ram)
        if cpu > 90 or ram > 85:
            self._high_pressure_count += 1
        else:
            self._high_pressure_count = 0

    @property
    def under_pressure(self) -> bool:
        return self._high_pressure_count >= 6
