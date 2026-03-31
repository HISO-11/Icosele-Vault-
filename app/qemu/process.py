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


def _io_uring_available() -> bool:
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


VM_RUN_BASE = Path("/tmp/icosele-vault")

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


def _needs_swtpm(extra_args: list[str]) -> bool:
    """Check if extra_args reference a TPM chardev that needs swtpm."""
    for arg in extra_args:
        if "chrtpm" in arg and "socket" in arg:
            return True
    return False


def _swtpm_available() -> bool:
    """Check if swtpm binary is installed."""
    import shutil
    return shutil.which("swtpm") is not None


# Persistent base for TPM state and OVMF vars (survives reboots)
_PERSISTENT_BASE = Path.home() / ".icosele-vault"

# OVMF firmware paths — secboot variants preferred for Secure Boot.
_OVMF_CODE_PATHS = [
    # Manjaro / Arch (edk2-ovmf) — 4M variants
    "/usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd",
    "/usr/share/edk2/x64/OVMF_CODE.4m.fd",
    # Debian / Ubuntu
    "/usr/share/OVMF/OVMF_CODE.secboot.fd",
    "/usr/share/OVMF/OVMF_CODE.fd",
    "/usr/share/ovmf/OVMF.fd",
    # Fedora / openSUSE / edk2
    "/usr/share/edk2-ovmf/x64/OVMF_CODE.secboot.fd",
    "/usr/share/edk2-ovmf/x64/OVMF_CODE.fd",
    "/usr/share/edk2/x64/OVMF_CODE.secboot.fd",
    "/usr/share/edk2/x64/OVMF_CODE.fd",
    # Generic / QEMU bundled
    "/usr/share/qemu/OVMF.fd",
    "/usr/share/qemu/OVMF_CODE.fd",
]

_OVMF_VARS_PATHS = [
    # Manjaro / Arch
    "/usr/share/edk2/x64/OVMF_VARS.4m.fd",
    # Debian / Ubuntu
    "/usr/share/OVMF/OVMF_VARS.fd",
    "/usr/share/ovmf/OVMF_VARS.fd",
    # Fedora / openSUSE / edk2
    "/usr/share/edk2-ovmf/x64/OVMF_VARS.fd",
    "/usr/share/edk2/x64/OVMF_VARS.fd",
    # Generic
    "/usr/share/qemu/OVMF_VARS.fd",
]


def _find_ovmf_code() -> str | None:
    for p in _OVMF_CODE_PATHS:
        if Path(p).exists():
            return p
    return None


def _find_ovmf_vars() -> str | None:
    for p in _OVMF_VARS_PATHS:
        if Path(p).exists():
            return p
    return None


class QemuProcess:
    def __init__(self, config: VMConfig) -> None:
        self.config = config
        self.state = ProcessState.STOPPED
        self._proc: subprocess.Popen | None = None
        self._swtpm_proc: subprocess.Popen | None = None
        self._last_exit_code: int | None = None
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

    @property
    def _tpm_state_dir(self) -> Path:
        """Persistent per-VM TPM state directory at ~/.icosele-vault/tpm/{vm_id}/."""
        return _PERSISTENT_BASE / "tpm" / self.config.vm_id

    @property
    def _swtpm_sock_path(self) -> str:
        return str(self._tpm_state_dir / "swtpm.sock")

    @property
    def _ovmf_vars_vm_path(self) -> Path:
        """Per-VM copy of OVMF_VARS at ~/.icosele-vault/ovmf/{vm_id}/."""
        return _PERSISTENT_BASE / "ovmf" / self.config.vm_id / "OVMF_VARS.fd"

    def _prepare_ovmf_vars(self) -> Path | None:
        """Copy the system OVMF_VARS template into the VM's persistent dir.

        Returns the path to the per-VM copy, or None if OVMF is not installed.
        Only copies once — subsequent boots reuse the existing vars.
        """
        src = _find_ovmf_vars()
        if src is None:
            return None
        dest = self._ovmf_vars_vm_path
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil as _sh
            _sh.copy2(src, dest)
            log.info("Copied OVMF_VARS to %s", dest)
        return dest

    def _start_swtpm(self) -> bool:
        """Start swtpm if the VM config needs TPM emulation.

        Returns True if swtpm started (or not needed/available), False on failure.
        If swtpm is not installed, TPM args are stripped in build_args() instead.
        """
        if not _needs_swtpm(self.config.extra_args):
            return True
        if not _swtpm_available():
            log.warning("swtpm not installed — VM will start without TPM support")
            return True

        tpm_dir = self._tpm_state_dir
        tpm_dir.mkdir(parents=True, exist_ok=True)

        sock = self._swtpm_sock_path
        # Remove stale socket from a previous unclean shutdown
        sock_path = Path(sock)
        if sock_path.exists():
            sock_path.unlink()

        cmd = [
            "swtpm", "socket",
            "--tpmstate", f"dir={tpm_dir}",
            "--ctrl", f"type=unixio,path={sock}",
            "--tpm2",
            "--daemon",
        ]
        log.info("Starting swtpm: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode != 0:
                log.error("swtpm failed to start: %s",
                          result.stderr.decode(errors="replace").strip()[:200])
                return False
        except FileNotFoundError:
            log.error("swtpm binary not found")
            return False

        # Wait for socket to appear
        for _ in range(30):
            if sock_path.exists():
                log.info("swtpm socket ready at %s", sock)
                return True
            time.sleep(0.1)

        log.error("swtpm socket did not appear at %s", sock)
        return False

    def _stop_swtpm(self) -> None:
        """Stop the daemonized swtpm by removing its socket.

        swtpm --daemon exits when its control socket is removed and the
        connected client (QEMU) disconnects.  We also clean up the socket
        file explicitly.
        """
        sock = Path(self._swtpm_sock_path)
        if sock.exists():
            try:
                sock.unlink()
                log.info("Removed swtpm socket %s", sock)
            except OSError:
                pass
        # Legacy: if _swtpm_proc was set by older non-daemon code path
        if self._swtpm_proc is not None:
            try:
                self._swtpm_proc.terminate()
                self._swtpm_proc.wait(timeout=3)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self._swtpm_proc.kill()
                    self._swtpm_proc.wait(timeout=2)
                except OSError:
                    pass
            self._swtpm_proc = None

    def missing_deps(self) -> list[str]:
        """Return list of human-readable strings for missing optional deps."""
        msgs: list[str] = []
        if _needs_swtpm(self.config.extra_args) and not _swtpm_available():
            msgs.append(
                "TPM 2.0: swtpm is not installed.\n"
                "  Manjaro/Arch:  sudo pacman -S swtpm\n"
                "  Ubuntu/Debian: sudo apt install swtpm\n"
                "The VM will start without TPM support."
            )
        if _needs_swtpm(self.config.extra_args) and _swtpm_available() and not _find_ovmf_code():
            msgs.append(
                "UEFI Secure Boot: OVMF firmware not found.\n"
                "  Manjaro/Arch:  sudo pacman -S edk2-ovmf\n"
                "  Ubuntu/Debian: sudo apt install ovmf\n"
                "TPM will work but Secure Boot is unavailable."
            )
        return msgs

    def _ensure_disk_image(self) -> str:
        """Create a fresh qcow2 disk image if disk_path is empty or missing.

        Stores it at ~/.icosele-vault/vms/{vm_id}/{vm_id}.qcow2 and updates
        the config's disk_path.  Returns the path to the disk image.
        """
        disk = self.config.disk_path
        if disk and Path(disk).exists():
            return disk

        vm_dir = _PERSISTENT_BASE / "vms" / self.config.vm_id
        vm_dir.mkdir(parents=True, exist_ok=True)
        disk = str(vm_dir / f"{self.config.vm_id}.qcow2")

        if not Path(disk).exists():
            log.info("Creating 40G qcow2 disk at %s", disk)
            subprocess.run(
                ["qemu-img", "create", "-f", "qcow2", disk, "40G"],
                check=True, capture_output=True, timeout=30,
            )

        # Persist into config so future launches reuse it
        self.config.disk_path = disk
        self.config.save()
        return disk

    def _extract_virtio_iso(self) -> str | None:
        """Extract VirtIO ISO path from extra_args."""
        for a in self.config.extra_args:
            if "media=cdrom" in a and "virtio" in a.lower():
                for part in a.split(","):
                    if part.startswith("file="):
                        return part[5:]
        return None

    def build_args(self) -> list[str]:
        use_kvm = kvm_available()
        if not use_kvm:
            log.warning("KVM not available — VM will run slowly")

        iso = self.config.iso_path
        disk = self._ensure_disk_image()
        virtio_iso = self._extract_virtio_iso()
        extra = list(self.config.extra_args)

        # Validate paths
        for label, path in [("QEMU binary", self.config.qemu_binary),
                            ("ISO", iso), ("Disk", disk)]:
            if path and not Path(path).exists():
                log.error("%s not found: %s", label, path)

        # Determine machine type and CPU from extra_args or defaults
        has_machine = any(a == "-machine" for a in extra)
        has_cpu = any(a == "-cpu" for a in extra)

        args = [
            self.config.qemu_binary,
            "-enable-kvm",
            "-m", str(self.config.ram_mb),
            "-smp", str(self.config.cpu_cores),
            "-rtc", "base=localtime,clock=host",
            "-global", "kvm-pit.lost_tick_policy=discard",
            "-qmp", f"unix:{self.socket_path},server,nowait",
            "-pidfile", self.pid_path,
        ]

        if not has_cpu:
            args += ["-cpu", "host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time"]
        if not has_machine:
            args += ["-machine", "pc"]

        # OVMF/UEFI firmware (needed for TPM / Secure Boot)
        needs_tpm = _needs_swtpm(extra)
        if needs_tpm:
            ovmf_code = _find_ovmf_code()
            ovmf_vars = self._prepare_ovmf_vars()
            if ovmf_code and ovmf_vars:
                args += [
                    "-drive", f"if=pflash,format=raw,readonly=on,file={ovmf_code}",
                    "-drive", f"if=pflash,format=raw,file={ovmf_vars}",
                ]
                log.info("UEFI firmware: %s", ovmf_code)
            else:
                log.warning("OVMF not found — Secure Boot unavailable")

            # Rewrite TPM chardev path to use per-VM persistent socket
            if _swtpm_available():
                extra = [
                    self._swtpm_sock_path if a == "swtpm-sock" else
                    a.replace("path=swtpm-sock", f"path={self._swtpm_sock_path}")
                    for a in extra
                ]
            else:
                # Strip TPM args if swtpm not installed
                skip = False
                filtered: list[str] = []
                for a in extra:
                    if skip:
                        skip = False
                        continue
                    if a in ("-chardev", "-tpmdev") and any(
                            "chrtpm" in x or "tpm0" in x for x in extra[extra.index(a)+1:extra.index(a)+2]):
                        skip = True
                        continue
                    if a == "-device" and any("tpm" in x for x in extra[extra.index(a)+1:extra.index(a)+2]):
                        skip = True
                        continue
                    filtered.append(a)
                extra = filtered
                log.warning("swtpm not installed — TPM args stripped")

        # Drives — assign sequential IDE indices to avoid conflicts
        drive_idx = 0
        if iso:
            args += ["-drive", f"file={iso},media=cdrom,index={drive_idx},if=ide"]
            drive_idx += 1
        if disk:
            args += ["-drive", f"file={disk},format=qcow2,index={drive_idx},if=ide"]
            drive_idx += 1
        if virtio_iso and Path(virtio_iso).exists():
            args += ["-drive", f"file={virtio_iso},media=cdrom,index={drive_idx},if=ide"]
            drive_idx += 1

        args += ["-boot", "order=dc"]
        args += ["-netdev", "user,id=net0", "-device", "e1000,netdev=net0"]
        args += ["-vga", "std", "-display", "gtk"]
        args += ["-device", "usb-ehci", "-device", "usb-tablet"]

        # Strip -drive entries from extra_args (already handled above)
        cleaned: list[str] = []
        skip_next = False
        for i, a in enumerate(extra):
            if skip_next:
                skip_next = False
                continue
            if a == "-drive" and i + 1 < len(extra) and "media=cdrom" in extra[i + 1]:
                skip_next = True
                continue
            cleaned.append(a)

        args += cleaned

        return args

    @property
    def last_error(self) -> str:
        """Return the stderr from the last failed QEMU launch."""
        return getattr(self, "_last_stderr", "")

    def start(self) -> None:
        if self.state != ProcessState.STOPPED:
            return

        self._last_stderr = ""
        self._ensure_run_dir()

        sock = Path(self.socket_path)
        if sock.exists():
            sock.unlink()

        self.state = ProcessState.STARTING

        # Start swtpm daemon if TPM is configured
        if not self._start_swtpm():
            log.error("Failed to start swtpm — aborting VM launch")
            self.state = ProcessState.STOPPED
            self._cleanup_run_dir()
            return

        args = self.build_args()

        # Print full command to console for debugging
        cmd_str = " ".join(args)
        log.info("Starting QEMU for VM %r", self.config.name)
        log.info("QEMU command:\n  %s", cmd_str)
        print(f"\n{'='*60}")
        print(f"QEMU LAUNCH COMMAND:")
        print(f"  {cmd_str}")
        print(f"{'='*60}\n")

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
            self._last_stderr = stderr
            log.error("QEMU exited with code %d for VM %r", retcode, self.config.name)
            if stderr:
                log.error("QEMU stderr:\n%s", stderr)
                print(f"QEMU ERROR: {stderr}")
            self._proc = None
            self.state = ProcessState.STOPPED
            self._stop_swtpm()
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
            self._stop_swtpm()
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
            self._stop_swtpm()
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
            self._stop_swtpm()
            self._cleanup_run_dir()
        return self.state
