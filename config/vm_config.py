from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "vms"

_SCHEMA = {
    "name": str,
    "ram_mb": int,
    "cpu_cores": int,
    "disk_path": str,
    "iso_path": str,
    "qemu_binary": str,
    "extra_args": list,
    "net_mode": str,
    "net_bridge_iface": str,
    "usb_devices": list,
    "gpu_passthrough": list,
    "display_config": dict,
}


def validate_config_data(data: dict, source: str = "<unknown>") -> bool:
    """Validate that a config dict has the expected fields and types.

    Returns True if valid, False if malformed.
    """
    if not isinstance(data, dict):
        log.warning("Config %s: not a dict, skipping", source)
        return False
    if "name" not in data or not isinstance(data["name"], str) or not data["name"].strip():
        log.warning("Config %s: missing or invalid 'name' field, skipping", source)
        return False
    for field_name, expected_type in _SCHEMA.items():
        if field_name in data and not isinstance(data[field_name], expected_type):
            log.warning(
                "Config %s: field '%s' has type %s, expected %s, skipping",
                source, field_name, type(data[field_name]).__name__, expected_type.__name__,
            )
            return False
    return True

NET_MODE_NAT = "nat"
NET_MODE_BRIDGE = "bridge"
NET_MODE_HOSTONLY = "hostonly"


@dataclass
class VMConfig:
    name: str
    ram_mb: int = 2048
    cpu_cores: int = 2
    disk_path: str = ""
    iso_path: str = ""
    qemu_binary: str = "/usr/bin/qemu-system-x86_64"
    extra_args: list[str] = field(default_factory=list)
    net_mode: str = NET_MODE_NAT
    net_bridge_iface: str = ""
    usb_devices: list[dict] = field(default_factory=list)
    gpu_passthrough: list[str] = field(default_factory=list)
    display_config: dict = field(default_factory=lambda: {
        "display_backend": "gtk",
        "vga_type": "virtio",
        "vnc_port": 5900,
        "resolution": "",
    })

    @property
    def vm_id(self) -> str:
        slug = self.name.lower().replace(" ", "-")
        return re.sub(r'[^a-z0-9_\-]', '', slug) or "vm"

    def net_args(self) -> list[str]:
        if self.net_mode == NET_MODE_BRIDGE:
            iface = self.net_bridge_iface or "br0"
            return [
                "-netdev", f"bridge,id=net0,br={iface}",
                "-device", "virtio-net-pci,netdev=net0",
            ]
        if self.net_mode == NET_MODE_HOSTONLY:
            return [
                "-netdev", "socket,id=net0,listen=:1234",
                "-device", "virtio-net-pci,netdev=net0",
            ]
        return [
            "-netdev", "user,id=net0",
            "-device", "virtio-net-pci,netdev=net0",
        ]

    def usb_args(self) -> list[str]:
        if not self.usb_devices:
            return []
        args = ["-usb"]
        for dev in self.usb_devices:
            bus = dev.get("bus", "")
            addr = dev.get("addr", "")
            dev_id = f"usb-host-{bus}-{addr}"
            if bus and addr:
                args += [
                    "-device",
                    f"usb-host,hostbus={bus},hostaddr={addr},id={dev_id}",
                ]
        return args

    def display_args(self) -> list[str]:
        dc = self.display_config
        backend = dc.get("display_backend", "gtk")
        vga = dc.get("vga_type", "virtio")
        args: list[str] = []

        if backend == "vnc":
            port = dc.get("vnc_port", 5900)
            display_num = port - 5900
            args += ["-display", f"vnc=:{display_num}"]
        elif backend == "spice":
            args += ["-display", "spice-app"]
        elif backend == "none":
            args += ["-display", "none"]
        else:
            args += ["-display", backend]

        args += ["-vga", vga]

        return args

    def gpu_args(self) -> list[str]:
        args: list[str] = []
        for addr in self.gpu_passthrough:
            args += ["-device", f"vfio-pci,host={addr}"]
        return args

    def rename(self, new_name: str, directory: Path | None = None) -> Path:
        """Rename the VM: delete old file, update name, save new file."""
        directory = directory or DATA_DIR
        old_path = directory / f"{self.vm_id}.json"
        if old_path.exists():
            old_path.unlink()
        self.name = new_name
        return self.save(directory)

    def save(self, directory: Path | None = None) -> Path:
        directory = directory or DATA_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.vm_id}.json"
        path.write_text(json.dumps(asdict(self), indent=2))
        return path

    @classmethod
    def load(cls, path: Path) -> VMConfig:
        data = json.loads(path.read_text())
        if not validate_config_data(data, source=str(path)):
            raise ValueError(f"Invalid config: {path}")

        # Migrate: if disk_path is an ISO and iso_path is empty, move it
        dp = data.get("disk_path", "")
        if dp and dp.lower().endswith(".iso") and not data.get("iso_path"):
            data["iso_path"] = dp
            data["disk_path"] = ""
            log.info("Migrated ISO from disk_path to iso_path in %s", path.name)

        # Migrate: fix broken disk_path with appended junk after a space
        # e.g. "disk.qcow2- ubutnu test.qcow2" -> "disk.qcow2"
        dp = data.get("disk_path", "")
        if dp and " " in dp:
            clean = dp.split(" ")[0].rstrip("-")
            if clean != dp:
                log.warning("Fixed broken disk_path in %s: %r -> %r", path.name, dp, clean)
                data["disk_path"] = clean

        return cls(**{k: v for k, v in data.items() if k in _SCHEMA})

    @classmethod
    def load_all(cls, directory: Path | None = None) -> list[VMConfig]:
        directory = directory or DATA_DIR
        if not directory.exists():
            return []
        configs = []
        for p in sorted(directory.glob("*.json")):
            try:
                configs.append(cls.load(p))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                log.warning("Skipping malformed config %s: %s", p.name, exc)
                continue
        return configs
