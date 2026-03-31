# Icosele VM

A modern, cross-platform virtual machine manager built with Python and PySide6.

## Features

- Manage QEMU virtual machines with a clean modern UI
- Cross-platform: Linux, macOS, Windows
- KVM/HVF/WHPX hardware acceleration
- One-click Windows 10/11 VM setup with TPM, UEFI, VirtIO
- Android VM support
- AI Assistant powered by Ollama
- Snapshot system with branching, comparison, and preview
- VM encryption (LUKS AES-256)
- Network modes: NAT, Bridge, Host-only, None
- Port forwarding with UI
- USB and GPU passthrough
- Shared folders (virtio-9p)
- Remote VM management via SSH
- ISO download manager and library
- VM import/export (.ivault archives)
- Clipboard sync via QEMU Guest Agent
- CPU pinning and hugepages support
- Memory ballooning
- Live performance graphs (CPU, RAM)
- VM groups and tags
- Auto-snapshot every 30 minutes
- Auto-update checker
- VM isolation levels (Standard, Restricted, Air-gapped)
- Community templates marketplace
- Audit logging
- First-run setup wizard

## Requirements

- Python 3.11+
- QEMU
- PySide6

## Installation

### Linux

```bash
pip install -r requirements.txt
python main.py
```

### macOS

```bash
brew install qemu
pip install -r requirements.txt
python main.py
```

### Windows

Download the latest release from GitHub releases.

## Building

```bash
pip install pyinstaller
pyinstaller qemu-gui/IcoseleVM.spec
```

## Architecture

- **app/qemu/process.py** -- QEMU subprocess lifecycle management
- **app/qemu/qmp.py** -- QMP socket protocol
- **app/main_window.py** -- Main window wiring QMP to UI
- **app/ui/theme.py** -- Icosele VM design system
- **app/ui/vm_list.py** -- Sidebar machine list
- **app/ui/vm_controls.py** -- Tabbed control panel
- **config/vm_config.py** -- VM configuration dataclass with JSON serialization

Communication with QEMU is via QMP over a Unix socket.

## License

MIT License
