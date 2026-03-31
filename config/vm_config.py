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
    "virtio_blk_io_uring": bool,
    "balloon_enabled": bool,
    "balloon_min_mb": int,
    "hugepages_enabled": bool,
    "instant_boot": bool,
    "audio_enabled": bool,
    "clipboard_sync": bool,
    "shared_folders": list,
    "spice_config": dict,
    "netsim_config": dict,
    "dns_servers": list,
    "encrypted": bool,
    "firewall_rules": list,
    "dns_filter_enabled": bool,
    "repo_path": str,
    "devcontainer_config": dict,
    "port_forwards": list,
    "usb_remembered_devices": list,
    "sandbox_mode": bool,
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
NET_MODE_NONE = "none"


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
        "vga_type": "std",
        "vnc_port": 5900,
        "resolution": "",
    })
    virtio_blk_io_uring: bool = False
    balloon_enabled: bool = False
    balloon_min_mb: int = 0
    hugepages_enabled: bool = False
    instant_boot: bool = False
    audio_enabled: bool = False
    clipboard_sync: bool = False
    shared_folders: list[dict] = field(default_factory=list)
    spice_config: dict = field(default_factory=lambda: {
        "spice_mode": "default",
        "spice_port": 5930,
    })
    netsim_config: dict = field(default_factory=lambda: {
        "bandwidth_mbps": 0,
        "latency_ms": 0,
        "loss_pct": 0,
    })
    dns_servers: list[str] = field(default_factory=list)
    encrypted: bool = False
    firewall_rules: list[dict] = field(default_factory=list)
    dns_filter_enabled: bool = False
    repo_path: str = ""
    devcontainer_config: dict = field(default_factory=dict)
    port_forwards: list[int] = field(default_factory=list)
    usb_remembered_devices: list[dict] = field(default_factory=list)
    sandbox_mode: bool = False

    @property
    def vm_id(self) -> str:
        slug = self.name.lower().replace(" ", "-")
        return re.sub(r'[^a-z0-9_\-]', '', slug) or "vm"

    @staticmethod
    def vhost_net_available() -> bool:
        return Path("/dev/vhost-net").exists()

    def net_args(self) -> list[str]:
        if self.net_mode == NET_MODE_NONE:
            return []
        vhost = ",vhost=on" if self.vhost_net_available() else ""
        if self.net_mode == NET_MODE_BRIDGE:
            iface = self.net_bridge_iface or "virbr0"
            return [
                "-netdev", f"bridge,id=net0,br={iface}",
                "-device", "virtio-net-pci,netdev=net0",
            ]
        if self.net_mode == NET_MODE_HOSTONLY:
            return [
                "-netdev", f"socket,id=net0,listen=:1234",
                "-device", "virtio-net-pci,netdev=net0",
            ]
        dns_part = ""
        if self.dns_servers:
            dns_part = f",dns={self.dns_servers[0]}"
        return [
            "-netdev", f"user,id=net0{dns_part}",
            "-device", "virtio-net-pci,netdev=net0",
        ]

    def usb_args(self) -> list[str]:
        if not self.usb_devices:
            return []
        args = ["-device", "usb-ehci,id=ehci-usb", "-usb"]
        for dev in self.usb_devices:
            vid = dev.get("vendor_id", "")
            pid = dev.get("product_id", "")
            bus = dev.get("bus", "")
            addr = dev.get("addr", "")
            if vid and pid:
                args += [
                    "-device",
                    f"usb-host,vendorid=0x{vid},productid=0x{pid}",
                ]
            elif bus and addr:
                dev_id = f"usb-host-{bus}-{addr}"
                args += [
                    "-device",
                    f"usb-host,hostbus={bus},hostaddr={addr},id={dev_id}",
                ]
        return args

    def display_args(self) -> list[str]:
        dc = self.display_config
        backend = dc.get("display_backend", "gtk")
        vga = dc.get("vga_type", "std")
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

    def shared_folder_args(self) -> list[str]:
        args: list[str] = []
        for i, f in enumerate(self.shared_folders):
            host_path = f.get("host_path", "")
            mount_tag = f.get("mount_tag", "shared")
            if not host_path:
                continue
            ro = ",readonly=on" if f.get("readonly") else ""
            args += [
                "-virtfs",
                f"local,path={host_path},mount_tag={mount_tag},"
                f"security_model=passthrough,id=fsdev{i}{ro}",
            ]
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

        # Validate paths: clear any disk_path or iso_path that doesn't exist on disk
        for path_field in ("disk_path", "iso_path"):
            p = data.get(path_field, "")
            if p and not Path(p).exists():
                log.warning("Path does not exist for %s in %s: %r — clearing",
                            path_field, path.name, p)
                data[path_field] = ""

        return cls(**{k: v for k, v in data.items() if k in _SCHEMA})

    @classmethod
    def load_all(cls, directory: Path | None = None) -> list[VMConfig]:
        directory = directory or DATA_DIR
        if not directory.exists():
            return []
        configs = []
        for p in sorted(directory.glob("*.json")):
            if "_snapshots" in p.name:
                continue
            try:
                configs.append(cls.load(p))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                log.warning("Skipping malformed config %s: %s", p.name, exc)
                continue
        return configs
