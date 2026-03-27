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

from app.platform_utils import (
    get_accel_flags, get_kvm_available, get_temp_dir, is_linux,
)
from config.vm_config import VMConfig

log = logging.getLogger(__name__)


def _io_uring_available() -> bool:
    if not is_linux():
        return False
    try:
        parts = __import__("platform").release().split("-")[0].split(".")
        major, minor = int(parts[0]), int(parts[1])
        return major > 5 or (major == 5 and minor >= 1)
    except (IndexError, ValueError):
        return False


class ProcessState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"


VM_RUN_BASE = Path(get_temp_dir())

def kvm_available() -> bool:
    """Cross-platform hardware acceleration check."""
    return get_kvm_available()


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
        self._last_exit_code: int | None = None
        self._kvm_enabled: bool = False
        self.encryption_password: str | None = None

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
        self._kvm_enabled = use_kvm
        if not use_kvm:
            log.warning("KVM not available (/dev/kvm missing or not accessible) — VM will run slowly")

        cores = self.config.cpu_cores

        args = [
            self.config.qemu_binary,
            "-name", self.config.name,
            "-m", str(self.config.ram_mb),
            "-smp", f"{cores},sockets=1,cores={cores},threads=1",
            "-qmp", f"unix:{self.socket_path},server,nowait",
            "-pidfile", self.pid_path,
        ]

        if use_kvm:
            args += get_accel_flags()
            args += ["-rtc", "base=localtime,clock=host"]

        display = self.config.display_config.get("display_backend", "gtk")
        if _can_use_sandbox(self.config.qemu_binary, display):
            args += ["-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny"]

        disk = self.config.disk_path
        iso = self.config.iso_path
        log.debug("disk_path raw value: %r", disk)
        log.debug("iso_path raw value: %r", iso)

        # Check if disk has an installed OS (>1GB means likely installed)
        disk_size = 0
        if disk:
            try:
                disk_size = os.path.getsize(disk)
            except OSError:
                pass

        if disk:
            if self.config.encrypted and self.encryption_password:
                args += ["-object",
                         f"secret,id=sec0,data={self.encryption_password},format=raw"]
                args += ["-drive", f"file={disk},format=luks,key-secret=sec0,if=virtio"]
            else:
                fmt = "raw" if disk.lower().endswith(".raw") else "qcow2"
                use_io_uring = _io_uring_available()
                if fmt == "qcow2":
                    if use_io_uring:
                        args += ["-drive", f"file={disk},format=qcow2,if=virtio,aio=io_uring,cache=writeback,discard=unmap"]
                    else:
                        args += ["-drive", f"file={disk},format=qcow2,if=virtio,cache=writeback"]
                else:
                    aio = "io_uring" if use_io_uring else "threads"
                    args += ["-drive", f"file={disk},format={fmt},if=virtio,aio={aio}"]

        os_installed = disk_size > 1073741824  # 1GB

        # Only add ISO cdrom if OS is not yet installed
        if iso and not os_installed:
            args += ["-drive", f"file={iso},media=cdrom,format=raw,readonly=on"]
            args += ["-boot", "order=d,menu=off,splash-time=0"]
        else:
            # Boot from disk — fastest path
            args += ["-boot", "order=c,menu=off,splash-time=0"]

        args += self.config.net_args()

        # Stable display: no GL, no virtio-gpu-gl
        args += ["-display", "gtk"]
        args += ["-device", "virtio-vga"]

        args += self.config.usb_args()
        args += self.config.gpu_args()

        if self.config.hugepages_enabled and Path("/dev/hugepages").exists():
            args += ["-mem-path", "/dev/hugepages"]

        # Audio — only add if pipewire is running (avoids boot delay from bad backend)
        if self.config.audio_enabled:
            try:
                pw = subprocess.check_output(["ps", "aux"], text=True, timeout=3)
                if "pipewire" in pw.lower():
                    args += ["-audiodev", "pipewire,id=audio0",
                             "-device", "ich9-intel-hda",
                             "-device", "hda-duplex,audiodev=audio0"]
                else:
                    args += ["-audiodev", "pa,id=audio0",
                             "-device", "ich9-intel-hda",
                             "-device", "hda-duplex,audiodev=audio0"]
            except (subprocess.SubprocessError, FileNotFoundError):
                pass  # skip audio entirely if we can't detect backend

        # Clipboard sync via guest agent
        if self.config.clipboard_sync:
            qga_sock = str(self._vm_run_dir / "qga.sock")
            args += ["-chardev", f"socket,path={qga_sock},server=on,wait=off,id=qga0",
                     "-device", "virtio-serial",
                     "-device", "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0"]

        # Shared folders (virtio-fs chardev/device args)
        for i, folder in enumerate(self.config.shared_folders):
            sock = str(self._vm_run_dir / f"virtiofs{i}.sock")
            tag = folder.get("mount_tag", f"share{i}")
            args += ["-chardev", f"socket,id=char{i},path={sock}",
                     "-device", f"vhost-user-fs-pci,queue-size=1024,chardev=char{i},tag={tag}"]
        if self.config.shared_folders:
            args += ["-object", f"memory-backend-file,id=mem,size={self.config.ram_mb}M,mem-path=/dev/hugepages,share=on",
                     "-numa", "node,memdev=mem"]

        # SPICE display mode
        spice_cfg = self.config.spice_config
        if spice_cfg.get("spice_mode") == "spice":
            port = spice_cfg.get("spice_port", 5930)
            args += ["-vga", "qxl",
                     "-device", "virtio-serial",
                     "-chardev", "spicevmc,id=vdagent,debug=0,name=vdagent",
                     "-device", "virtserialport,chardev=vdagent,name=com.redhat.spice.0",
                     "-spice", f"port={port},disable-ticketing=on"]

        # Ensure -machine flag with correct accel
        extra = list(self.config.extra_args)
        has_machine = any(a == "-machine" for a in extra)
        if has_machine:
            if use_kvm:
                for i, a in enumerate(extra):
                    if i > 0 and extra[i - 1] == "-machine" and "accel=" not in a:
                        extra[i] = a + ",accel=kvm"
        else:
            if use_kvm:
                extra = ["-machine", "type=q35,accel=kvm"] + extra
            else:
                extra = ["-machine", "type=q35"] + extra
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

    @property
    def exit_code(self) -> int | None:
        if self._proc is not None:
            return self._proc.poll()
        return self._last_exit_code

    def refresh_state(self) -> ProcessState:
        if self._proc is not None and not self.is_alive():
            self._last_exit_code = self._proc.poll()
            self._proc = None
            self.state = ProcessState.STOPPED
            self._cleanup_run_dir()
        return self.state
