# Icosele Vault

A PySide6-based virtual machine management GUI that communicates with QEMU via QMP (QEMU Machine Protocol).

## Requirements

- Python 3.11+
- PySide6
- QEMU installed (`qemu-system-x86_64`)
- Linux (tested on Manjaro, GNOME/Wayland)
- Inter font recommended (falls back to SF Pro Display / Segoe UI / sans-serif)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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
- **app/ui/theme.py** -- Icosele Vault design system (dark green palette)
- **app/ui/vm_list.py** -- Sidebar machine list
- **app/ui/vm_controls.py** -- Tabbed control panel (Overview, Performance, Network, USB, GPU, Display, Snapshots)
- **config/vm_config.py** -- VM configuration dataclass with JSON serialization

Communication with QEMU is via QMP over a Unix socket -- QEMU runs as a separate GPL-licensed process.
