from __future__ import annotations

import logging
import os
import stat
import subprocess
import signal
import tempfile
import time
from enum import Enum
from pathlib import Path

from config.vm_config import VMConfig

log = logging.getLogger(__name__)


class ProcessState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"


VM_RUN_BASE = Path("/tmp/novamachine")

def kvm_available() -> bool:
    """Check if /dev/kvm exists and is accessible by the current user."""
    try:
        return os.access("/dev/kvm", os.R_OK | os.W_OK)
    except OSError:
        return False


_SANDBOX_INCOMPATIBLE_DISPLAYS = {"gtk", "sdl"}


def _can_use_sandbox(qemu_binary: str, display: str) -> bool:
    """Check whether -sandbox can be used with the given display backend.

    The spawn=deny flag prevents GTK/SDL from spawning pixbuf loaders
    and other subprocesses, causing crashes. Only enable sandbox for
    headless backends (none, vnc, spice).
    """
    if display in _SANDBOX_INCOMPATIBLE_DISPLAYS:
        log.info("Sandbox disabled: spawn=deny is incompatible with -display %s", display)
        return False
    # Quick probe: start QEMU with sandbox, kill after 1s. If it survives
    # 1s without crashing, sandbox is supported.
    try:
        proc = subprocess.Popen(
            [qemu_binary, "-sandbox", "on", "-M", "none", "-display", "none"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            proc.wait(timeout=1)
            # Exited within 1s — check if it was an error
            stderr = proc.stderr.read().decode(errors="replace")
            if proc.returncode != 0:
                log.warning("QEMU sandbox not supported: %s", stderr.strip()[:200])
                return False
            return True
        except subprocess.TimeoutExpired:
            # Still running after 1s — sandbox works, kill it
            proc.kill()
            proc.wait()
            return True
    except (FileNotFoundError, OSError):
        return False


class QemuProcess:
    def __init__(self, config: VMConfig) -> None:
        self.config = config
        self.state = ProcessState.STOPPED
        self._proc: subprocess.Popen | None = None

    @property
    def _vm_run_dir(self) -> Path:
        return VM_RUN_BASE / self.config.vm_id

    @property
    def socket_path(self) -> str:
        return str(self._vm_run_dir / "qmp.sock")

    @property
    def pid_path(self) -> str:
        return str(self._vm_run_dir / "qemu.pid")

    def _ensure_run_dir(self) -> None:
        """Create per-VM temp directory with 700 permissions."""
        d = self._vm_run_dir
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, stat.S_IRWXU)

    def _cleanup_run_dir(self) -> None:
        """Remove per-VM temp directory and its contents."""
        d = self._vm_run_dir
        if d.exists():
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def build_args(self) -> list[str]:
        use_kvm = kvm_available()
        if not use_kvm:
            log.warning("KVM not available (/dev/kvm missing or not accessible) — VM will run slowly")

        args = [
            self.config.qemu_binary,
            "-name", self.config.name,
            "-m", str(self.config.ram_mb),
            "-smp", str(self.config.cpu_cores),
            "-qmp", f"unix:{self.socket_path},server,nowait",
            "-pidfile", self.pid_path,
        ]

        if use_kvm:
            args += ["-enable-kvm"]

        display = self.config.display_config.get("display_backend", "gtk")
        if _can_use_sandbox(self.config.qemu_binary, display):
            args += ["-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny"]

        disk = self.config.disk_path
        iso = self.config.iso_path
        log.debug("disk_path raw value: %r", disk)
        log.debug("iso_path raw value: %r", iso)

        if disk:
            fmt = "raw" if disk.lower().endswith(".raw") else "qcow2"
            args += ["-drive", f"file={disk},format={fmt},if=virtio"]

        if iso:
            args += ["-drive", f"file={iso},media=cdrom,format=raw,readonly=on"]
            args += ["-boot", "order=d"]

        args += self.config.net_args()
        args += self.config.display_args()
        args += self.config.usb_args()
        args += self.config.gpu_args()

        # Inject accel=kvm into any -machine arg from extra_args
        extra = list(self.config.extra_args)
        if use_kvm:
            for i, a in enumerate(extra):
                if i > 0 and extra[i - 1] == "-machine" and "accel=" not in a:
                    extra[i] = a + ",accel=kvm"
        args += extra
        return args

    def start(self) -> None:
        if self.state != ProcessState.STOPPED:
            return

        self._ensure_run_dir()

        sock = Path(self.socket_path)
        if sock.exists():
            sock.unlink()

        self.state = ProcessState.STARTING
        args = self.build_args()

        log.info("Starting QEMU for VM %r", self.config.name)
        log.info("QEMU command: %s", " ".join(args))
        log.info("QMP socket path (passed to QEMU): %s", self.socket_path)

        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait briefly and check if QEMU crashed immediately
        time.sleep(0.5)
        retcode = self._proc.poll()
        if retcode is not None:
            stderr = ""
            try:
                stderr = self._proc.stderr.read().decode(errors="replace")
            except Exception:
                pass
            stdout = ""
            try:
                stdout = self._proc.stdout.read().decode(errors="replace")
            except Exception:
                pass
            log.error("QEMU exited immediately with code %d for VM %r", retcode, self.config.name)
            if stderr:
                log.error("QEMU stderr:\n%s", stderr)
            if stdout:
                log.error("QEMU stdout:\n%s", stdout)
            self._proc = None
            self.state = ProcessState.STOPPED
            self._cleanup_run_dir()
            return

        self.state = ProcessState.RUNNING
        log.info("QEMU process started (PID %d) for VM %r", self._proc.pid, self.config.name)

        # Restrict QMP socket permissions to owner-only once QEMU creates it
        self._chmod_socket()

    def _chmod_socket(self) -> None:
        """Set QMP socket to 600 (owner-only) once it appears."""
        sock = Path(self.socket_path)
        for _ in range(20):
            if sock.exists():
                try:
                    os.chmod(sock, stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass
                log.info("QMP socket ready at %s", self.socket_path)
                return
            time.sleep(0.1)
        log.warning("QMP socket did not appear at %s within 2s", self.socket_path)

    def stop(self) -> None:
        if self._proc is None:
            self.state = ProcessState.STOPPED
            return

        try:
            self._proc.send_signal(signal.SIGTERM)
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=2)
        finally:
            self._proc = None
            self.state = ProcessState.STOPPED
            self._cleanup_run_dir()

    def is_alive(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def refresh_state(self) -> ProcessState:
        if self._proc is not None and not self.is_alive():
            self._proc = None
            self.state = ProcessState.STOPPED
            self._cleanup_run_dir()
        return self.state
