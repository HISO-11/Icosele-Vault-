# Icosele Vault

A PySide6-based virtual machine management GUI that communicates with QEMU via QMP (QEMU Machine Protocol).

## Requirements

- Python 3.11+
- PySide6
- QEMU installed (`qemu-system-x86_64`)
- Inter font recommended (falls back to SF Pro Display / Segoe UI / sans-serif)

## Linux (Primary Platform)

**Tested on:** Manjaro, Arch, Ubuntu, Fedora (GNOME/Wayland/X11)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

For hardware acceleration, ensure KVM is available:
```bash
sudo pacman -S qemu-full        # Arch/Manjaro
sudo apt install qemu-system-x86 # Debian/Ubuntu
sudo usermod -aG kvm $USER       # Add yourself to kvm group
```

Build AppImage for distribution:
```bash
bash scripts/build_appimage.sh
```

## Windows

**Requirements:** Windows 10/11, Python 3.11+, QEMU for Windows

1. Install Python 3.11+ from https://python.org/downloads/ (check "Add to PATH")
2. Download QEMU for Windows from https://qemu.weilnetz.de/w64/
3. Enable hardware acceleration (optional but recommended):
   - Open Settings > Apps > Optional Features > More Windows Features
   - Enable "Windows Hypervisor Platform" or "Hyper-V"
   - Reboot

```batch
scripts\build_windows.bat
IcoseleVault.bat
```

## macOS

**Requirements:** macOS 12+, Python 3.11+, Homebrew, QEMU via brew

Apple Silicon (M1/M2/M3/M4) is supported natively via the Hypervisor Framework (HVF).

```bash
bash scripts/install_mac.sh
icosele-vault
```

Or manually:
```bash
brew install qemu python@3.11
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

## Usage

```bash
python main.py
```

The application loads VM configurations from `data/vms/*.json`. A default `test-vm.json` is included.

## Architecture

- **app/qemu/process.py** -- QEMU subprocess lifecycle management
- **app/qemu/qmp.py** -- QMP socket protocol (connect, negotiate, send commands)
- **app/main_window.py** -- Main window wiring QMP to UI
- **app/platform_utils.py** -- Cross-platform detection (Linux/Windows/macOS)
- **app/ui/theme.py** -- Icosele Vault design system
- **app/ui/vm_list.py** -- Sidebar machine list
- **app/ui/vm_controls.py** -- Tabbed control panel
- **config/vm_config.py** -- VM configuration dataclass with JSON serialization

Communication with QEMU is via QMP over a Unix socket (Linux/macOS) or named pipe (Windows) — QEMU runs as a separate GPL-licensed process.
