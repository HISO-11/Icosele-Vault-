from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL,
    BORDER, COMBO_STYLE, FONT_FAMILY, INPUT_STYLE, LABEL_STYLE,
    STOP_RED, TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY,
    primary_btn_style, secondary_btn_style, subtle_btn_style,
)
from config.vm_config import NET_MODE_BRIDGE, NET_MODE_HOSTONLY, NET_MODE_NAT, VMConfig

log = logging.getLogger(__name__)

MODE_LABELS = {NET_MODE_NAT: "NAT (User mode)", NET_MODE_BRIDGE: "Bridged", NET_MODE_HOSTONLY: "Host-only"}
MODE_KEYS = [NET_MODE_NAT, NET_MODE_BRIDGE, NET_MODE_HOSTONLY]

VIRTIO_WIN_URL = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso"

TEMPLATES = {
    "blank": {"label": "Blank", "desc": "Empty machine, no defaults", "cpu": 2, "ram": 2048, "disk": ""},
    "dev": {"label": "Developer Box", "desc": "4 CPU, 8 GB RAM, 60 GB disk", "cpu": 4, "ram": 8192, "disk": "60G"},
    "gaming": {"label": "Gaming PC", "desc": "8 CPU, 16 GB RAM, 100 GB disk", "cpu": 8, "ram": 16384, "disk": "100G"},
    "server": {"label": "Minimal Server", "desc": "1 CPU, 1 GB RAM, 20 GB disk", "cpu": 1, "ram": 1024, "disk": "20G"},
    "win10": {
        "label": "Windows 10",
        "desc": "q35, 4 GB RAM, 64 GB disk, Hyper-V enlightenments",
        "cpu": 4, "ram": 4096, "disk": "64G",
        "windows": True,
        "extra_args": [
            "-machine", "q35",
            "-device", "usb-ehci,id=usb-bus",
            "-device", "usb-tablet,bus=usb-bus.0",
            "-cpu", "host,hv_relaxed,hv_vapic,hv_spinlocks=0x1fff",
        ],
    },
    "win11": {
        "label": "Windows 11",
        "desc": "q35, 8 GB RAM, 64 GB disk, TPM 2.0, Secure Boot",
        "cpu": 4, "ram": 8192, "disk": "64G",
        "windows": True,
        "extra_args": [
            "-machine", "q35",
            "-device", "usb-ehci,id=usb-bus",
            "-device", "usb-tablet,bus=usb-bus.0",
            "-cpu", "host,hv_relaxed,hv_vapic,hv_spinlocks=0x1fff",
            "-chardev", "socket,id=chrtpm,path=swtpm-sock",
            "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
            "-device", "tpm-tis,tpmdev=tpm0",
            "-global", "driver=cfi.pflash01,property=secure,value=on",
        ],
    },
    "sandbox": {
        "label": "Malware Sandbox",
        "desc": "Isolated, no network, auto-snapshot, 4 GB RAM",
        "cpu": 2, "ram": 4096, "disk": "40G",
        "sandbox": True,
        "extra_args": ["-machine", "q35"],
    },
}

ISO_SOURCES = [
    ("Ubuntu 24.04 LTS", "https://releases.ubuntu.com/24.04/ubuntu-24.04.2-desktop-amd64.iso"),
    ("Ubuntu 22.04 LTS", "https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.iso"),
    ("Debian 12", "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.10.0-amd64-netinst.iso"),
    ("Fedora 39", "https://download.fedoraproject.org/pub/fedora/linux/releases/39/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-39-1.5.iso"),
    ("Arch Linux", "https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"),
]


class _TemplateCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, label: str, desc: str, parent=None) -> None:
        super().__init__(parent)
        self._key = key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            _TemplateCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            _TemplateCard:hover {{
                border-color: {ACCENT};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        t = QLabel(label)
        t.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;"
                        f" background: transparent; font-family: {FONT_FAMILY};")
        d = QLabel(desc)
        d.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;"
                        f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(t)
        layout.addWidget(d)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._key)


class _DownloadSignals(QObject):
    progress = Signal(int, int, float)
    finished = Signal(str)
    error = Signal(str)


class ISODownloadDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.downloaded_path = ""
        self._thread: threading.Thread | None = None
        self._cancel = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Download ISO")
        self.setFixedSize(480, 400)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Download ISO Image")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
                            f" background: transparent;")
        layout.addWidget(title)

        for name, url in ISO_SOURCES:
            row = QHBoxLayout()
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent;")
            btn = QPushButton("Download")
            btn.setFixedHeight(28)
            btn.setFixedWidth(80)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(subtle_btn_style())
            btn.clicked.connect(lambda checked, u=url, n=name: self._start_download(u, n))
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(btn)
            layout.addLayout(row)

        layout.addSpacing(8)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 4px;
                text-align: center;
                color: {TEXT_PRIMARY};
                font-size: 10px;
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT};
                border-radius: 3px;
            }}
        """)
        self._progress.setFixedHeight(20)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(secondary_btn_style())
        close_btn.setFixedHeight(34)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._on_close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _start_download(self, url: str, name: str) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._cancel = False
        dest = Path.home() / "Downloads" / url.rsplit("/", 1)[-1]
        self._status.setText(f"Downloading {name}...")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress.setMaximum(100)

        self._signals = _DownloadSignals()
        self._signals.progress.connect(self._on_progress)
        self._signals.finished.connect(self._on_finished)
        self._signals.error.connect(self._on_error)

        self._thread = threading.Thread(target=self._download_worker, args=(url, dest), daemon=True)
        self._thread.start()

    def _download_worker(self, url: str, dest: Path) -> None:
        try:
            import requests
            dest.parent.mkdir(parents=True, exist_ok=True)
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            import time
            start = time.monotonic()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if self._cancel:
                        return
                    f.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.monotonic() - start
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    self._signals.progress.emit(downloaded, total, speed)
            self._signals.finished.emit(str(dest))
        except Exception as exc:
            self._signals.error.emit(str(exc))

    def _on_progress(self, downloaded: int, total: int, speed: float) -> None:
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._progress.setValue(pct)
            eta = (total - downloaded) / speed if speed > 0 else 0
            mb_done = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            speed_mb = speed / (1024 * 1024)
            self._status.setText(
                f"{mb_done:.1f} / {mb_total:.1f} MB  |  {speed_mb:.1f} MB/s  |  ETA {int(eta)}s")
        else:
            mb_done = downloaded / (1024 * 1024)
            speed_mb = speed / (1024 * 1024)
            self._status.setText(f"{mb_done:.1f} MB  |  {speed_mb:.1f} MB/s")
            self._progress.setMaximum(0)

    def _on_finished(self, path: str) -> None:
        self.downloaded_path = path
        self._status.setText(f"Done: {path}")
        self._progress.setValue(100)
        self._progress.setMaximum(100)

    def _on_error(self, msg: str) -> None:
        self._status.setText(f"Error: {msg}")
        self._progress.setVisible(False)

    def _on_close(self) -> None:
        self._cancel = True
        self.accept()


class VMCreateDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result_config: VMConfig | None = None
        self._selected_template: str = "blank"
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Icosele Vault - New Machine")
        self.setFixedSize(580, 720)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # Page 0: Template selection
        self._page_template = QWidget()
        self._build_template_page()
        self._stack.addWidget(self._page_template)

        # Page 1: Configuration form
        self._page_form = QWidget()
        self._build_form_page()
        self._stack.addWidget(self._page_form)

        self._stack.setCurrentIndex(0)

    def _build_template_page(self) -> None:
        layout = QVBoxLayout(self._page_template)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)

        title = QLabel("Choose a Template")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: 700;"
                            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(title)

        sub = QLabel("Select a starting point for your new machine")
        sub.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(sub)

        layout.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (key, tpl) in enumerate(TEMPLATES.items()):
            card = _TemplateCard(key, tpl["label"], tpl["desc"])
            card.clicked.connect(self._on_template_selected)
            grid.addWidget(card, i // 2, i % 2)
        layout.addLayout(grid)

        layout.addStretch()

        btn_row = QHBoxLayout()
        git_btn = QPushButton("Import from Git Repo")
        git_btn.setStyleSheet(subtle_btn_style())
        git_btn.setFixedHeight(34)
        git_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        git_btn.clicked.connect(self._on_import_git_repo)
        btn_row.addWidget(git_btn)
        btn_row.addStretch()
        skip_btn = QPushButton("Skip")
        skip_btn.setStyleSheet(secondary_btn_style())
        skip_btn.setFixedHeight(34)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.clicked.connect(lambda: self._on_template_selected("blank"))
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

    def _on_template_selected(self, key: str) -> None:
        self._selected_template = key
        tpl = TEMPLATES[key]
        self.cpu_input.setValue(tpl["cpu"])
        self.ram_input.setValue(tpl["ram"])

        is_windows = tpl.get("windows", False)
        self._virtio_banner.setVisible(is_windows)
        self._virtio_iso_label.setVisible(is_windows)
        self._virtio_iso_widget.setVisible(is_windows)

        self._stack.setCurrentIndex(1)

    def _build_form_page(self) -> None:
        layout = QVBoxLayout(self._page_form)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)

        title = QLabel("Configure Machine")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: 700;"
                            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(title)
        layout.addSpacing(4)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("my-vm")
        self.name_input.setStyleSheet(INPUT_STYLE)

        self.ram_input = QSpinBox()
        self.ram_input.setRange(128, 131072)
        self.ram_input.setValue(2048)
        self.ram_input.setSuffix(" MB")
        self.ram_input.setSingleStep(256)
        self.ram_input.setStyleSheet(INPUT_STYLE)

        self.cpu_input = QSpinBox()
        self.cpu_input.setRange(1, 128)
        self.cpu_input.setValue(2)
        self.cpu_input.setStyleSheet(INPUT_STYLE)

        # --- ISO / Boot Image row ---
        iso_row = QHBoxLayout()
        iso_row.setContentsMargins(0, 0, 0, 0)
        iso_row.setSpacing(6)
        self.iso_input = QLineEdit()
        self.iso_input.setPlaceholderText("(optional) path to .iso installer")
        self.iso_input.setStyleSheet(INPUT_STYLE)
        self.iso_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.iso_browse = QPushButton("Browse")
        self.iso_browse.setFixedWidth(80)
        self.iso_browse.setStyleSheet(subtle_btn_style())
        self.iso_browse.clicked.connect(self._browse_iso)
        self.iso_dl_btn = QPushButton("Download")
        self.iso_dl_btn.setFixedWidth(80)
        self.iso_dl_btn.setStyleSheet(subtle_btn_style())
        self.iso_dl_btn.clicked.connect(self._open_iso_download)
        iso_row.addWidget(self.iso_input, 1)
        iso_row.addWidget(self.iso_browse, 0)
        iso_row.addWidget(self.iso_dl_btn, 0)
        iso_widget = QWidget()
        iso_widget.setLayout(iso_row)
        iso_widget.setStyleSheet("background: transparent;")

        # --- Disk Image row ---
        disk_row = QHBoxLayout()
        disk_row.setContentsMargins(0, 0, 0, 0)
        disk_row.setSpacing(6)
        self.disk_input = QLineEdit()
        self.disk_input.setPlaceholderText("(optional) path to .qcow2 / .img")
        self.disk_input.setStyleSheet(INPUT_STYLE)
        self.disk_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.disk_browse = QPushButton("Browse")
        self.disk_browse.setFixedWidth(80)
        self.disk_browse.setStyleSheet(subtle_btn_style())
        self.disk_browse.clicked.connect(self._browse_disk)
        self.disk_create_btn = QPushButton("Create")
        self.disk_create_btn.setFixedWidth(80)
        self.disk_create_btn.setStyleSheet(subtle_btn_style())
        self.disk_create_btn.clicked.connect(self._create_disk_image)
        disk_row.addWidget(self.disk_input, 1)
        disk_row.addWidget(self.disk_browse, 0)
        disk_row.addWidget(self.disk_create_btn, 0)
        disk_widget = QWidget()
        disk_widget.setLayout(disk_row)
        disk_widget.setStyleSheet("background: transparent;")

        # --- Disk size dropdown (for Create New) ---
        self._disk_size_combo = QComboBox()
        self._disk_size_combo.setStyleSheet(COMBO_STYLE)
        for size in ["20G", "40G", "60G", "80G", "100G"]:
            self._disk_size_combo.addItem(size, size)
        self._disk_size_combo.setCurrentIndex(1)  # 40G default
        self._disk_size_label = QLabel("New Disk Size")
        self._disk_size_label.setStyleSheet(LABEL_STYLE)

        self.qemu_input = QLineEdit("/usr/bin/qemu-system-x86_64")
        self.qemu_input.setStyleSheet(INPUT_STYLE)

        self.net_combo = QComboBox()
        self.net_combo.setStyleSheet(COMBO_STYLE)
        for key in MODE_KEYS:
            self.net_combo.addItem(MODE_LABELS[key], key)

        self.bridge_input = QLineEdit()
        self.bridge_input.setPlaceholderText("br0")
        self.bridge_input.setStyleSheet(INPUT_STYLE)
        self.bridge_label = QLabel("Bridge Iface")
        self.bridge_label.setStyleSheet(LABEL_STYLE)

        for lt, w in [("Name", self.name_input), ("RAM", self.ram_input),
                       ("CPU Cores", self.cpu_input), ("ISO / Boot", iso_widget),
                       ("Disk Image", disk_widget), ("New Disk Size", self._disk_size_combo),
                       ("QEMU Binary", self.qemu_input), ("Network", self.net_combo)]:
            lbl = QLabel(lt)
            lbl.setStyleSheet(LABEL_STYLE)
            form.addRow(lbl, w)
        form.addRow(self.bridge_label, self.bridge_input)
        self.bridge_label.hide()
        self.bridge_input.hide()

        # VirtIO driver ISO row (Windows templates only)
        virtio_row = QHBoxLayout()
        virtio_row.setContentsMargins(0, 0, 0, 0)
        virtio_row.setSpacing(6)
        self._virtio_iso_input = QLineEdit()
        self._virtio_iso_input.setPlaceholderText("(optional) path to virtio-win.iso")
        self._virtio_iso_input.setStyleSheet(INPUT_STYLE)
        self._virtio_iso_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        virtio_browse = QPushButton("Browse")
        virtio_browse.setFixedWidth(80)
        virtio_browse.setStyleSheet(subtle_btn_style())
        virtio_browse.clicked.connect(self._browse_virtio_iso)
        virtio_row.addWidget(self._virtio_iso_input, 1)
        virtio_row.addWidget(virtio_browse, 0)
        self._virtio_iso_widget = QWidget()
        self._virtio_iso_widget.setLayout(virtio_row)
        self._virtio_iso_widget.setStyleSheet("background: transparent;")
        self._virtio_iso_label = QLabel("VirtIO ISO")
        self._virtio_iso_label.setStyleSheet(LABEL_STYLE)
        self._virtio_iso_label.setToolTip(
            "Secondary CD-ROM with VirtIO drivers for Windows.\n"
            "Provides disk, network, and display drivers for best VM performance.")
        form.addRow(self._virtio_iso_label, self._virtio_iso_widget)
        self._virtio_iso_label.hide()
        self._virtio_iso_widget.hide()

        layout.addLayout(form)

        # Windows VirtIO info banner (hidden by default)
        from app.ui.theme import WARNING
        self._virtio_banner = QLabel(
            "\u26a0  A VirtIO drivers ISO is recommended for best Windows performance.\n"
            f"Download: {VIRTIO_WIN_URL}")
        self._virtio_banner.setWordWrap(True)
        self._virtio_banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._virtio_banner.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 10px; color: {WARNING}; font-size: 11px;")
        self._virtio_banner.hide()
        layout.addWidget(self._virtio_banner)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {STOP_RED}; font-size: 12px; background: transparent;")
        layout.addWidget(self.error_label)
        layout.addStretch()

        btn_row = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.setStyleSheet(secondary_btn_style())
        back_btn.setFixedHeight(36)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(secondary_btn_style())
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        create_btn = QPushButton("Create")
        create_btn.setStyleSheet(primary_btn_style())
        create_btn.setFixedHeight(36)
        create_btn.setMinimumWidth(90)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(cancel_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(create_btn)
        layout.addLayout(btn_row)

        self.net_combo.currentIndexChanged.connect(self._on_net_mode_changed)

    def _on_import_git_repo(self) -> None:
        repo_dir = QFileDialog.getExistingDirectory(
            self, "Select Git Repository", str(Path.home()))
        if not repo_dir:
            return
        from app.ui.dev_import_dialog import scan_repo, parse_devcontainer, DevImportDialog
        scan = scan_repo(repo_dir)
        if not scan:
            return
        devc = parse_devcontainer(repo_dir)
        dlg = DevImportDialog(scan, devc, self)
        if dlg.exec() and dlg.accepted_config:
            cfg = dlg.accepted_config
            self.name_input.setText(cfg["name"])
            self.ram_input.setValue(cfg["ram_mb"])
            self.cpu_input.setValue(cfg["cpu_cores"])
            # Store extras on the dialog for _on_create to pick up
            self._git_repo_path = cfg.get("repo_path", "")
            self._git_shared_folders = cfg.get("shared_folders", [])
            self._git_devcontainer = cfg.get("devcontainer_config", {})
            self._git_port_forwards = cfg.get("port_forwards", [])
            self._stack.setCurrentIndex(1)

    def _on_net_mode_changed(self) -> None:
        ib = self.net_combo.currentData() == NET_MODE_BRIDGE
        self.bridge_label.setVisible(ib)
        self.bridge_input.setVisible(ib)

    def _browse_iso(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO Image", str(Path.home()),
            "ISO Images (*.iso);;All Files (*)")
        if path:
            self.iso_input.setText(path)

    def _browse_virtio_iso(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select VirtIO Drivers ISO", str(Path.home()),
            "ISO Images (*.iso);;All Files (*)")
        if path:
            self._virtio_iso_input.setText(path)

    def _browse_disk(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Disk Image", str(Path.home()),
            "Disk Images (*.qcow2 *.img *.raw);;All Files (*)")
        if path:
            self.disk_input.setText(path)

    def _create_disk_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Create Disk Image", str(Path.home() / "disk.qcow2"),
            "QCOW2 Images (*.qcow2);;All Files (*)")
        if not path:
            return
        if not path.endswith(".qcow2"):
            path += ".qcow2"
        size = self._disk_size_combo.currentData() or "40G"
        try:
            import subprocess
            subprocess.run(
                ["qemu-img", "create", "-f", "qcow2", path, size],
                check=True, capture_output=True, text=True, timeout=30,
            )
            self.disk_input.setText(path)
            self.error_label.setText("")
        except FileNotFoundError:
            self.error_label.setText("qemu-img not found. Install QEMU tools.")
        except subprocess.CalledProcessError as exc:
            self.error_label.setText(f"Failed to create disk: {exc.stderr.strip()}")

    def _open_iso_download(self) -> None:
        dlg = ISODownloadDialog(self)
        dlg.exec()
        if dlg.downloaded_path:
            self.iso_input.setText(dlg.downloaded_path)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        return re.sub(r'[^\w\s\-.()\[\]]', '', name).strip()

    @staticmethod
    def _has_path_traversal(path: str) -> bool:
        try:
            Path(path).resolve()
            return ".." in Path(path).parts
        except (ValueError, OSError):
            return True

    def _validate_file_path(self, path: str, label: str) -> bool:
        if self._has_path_traversal(path):
            self.error_label.setText(f"{label} path contains invalid path traversal.")
            return False
        if not Path(path).exists() or not Path(path).is_file():
            self.error_label.setText(f"{label} not found or is not a file.")
            return False
        return True

    def _on_create(self) -> None:
        name = self._sanitize_name(self.name_input.text())
        if not name:
            self.error_label.setText("Name is required.")
            return
        self.name_input.setText(name)

        qemu_bin = self.qemu_input.text().strip()
        if not qemu_bin or not self._validate_file_path(qemu_bin, "QEMU binary"):
            return

        iso = self.iso_input.text().strip()
        if iso and not self._validate_file_path(iso, "ISO image"):
            return

        disk = self.disk_input.text().strip()
        if disk and not self._validate_file_path(disk, "Disk image"):
            return

        if not iso and not disk:
            self.error_label.setText("Provide at least an ISO or a disk image.")
            return

        # Validate VirtIO ISO if provided
        tpl = TEMPLATES[self._selected_template]
        virtio_iso = self._virtio_iso_input.text().strip()
        if virtio_iso and not self._validate_file_path(virtio_iso, "VirtIO ISO"):
            return

        # Build extra_args from template
        extra_args = list(tpl.get("extra_args", ["-machine", "q35"]))
        if not any(a == "-machine" for a in extra_args):
            extra_args = ["-machine", "q35"] + extra_args

        # Add VirtIO driver CD-ROM as secondary drive
        if virtio_iso:
            extra_args += ["-drive", f"file={virtio_iso},media=cdrom,index=2"]

        net_mode = self.net_combo.currentData() or NET_MODE_NAT
        bridge_iface = self.bridge_input.text().strip() if net_mode == NET_MODE_BRIDGE else ""
        self.error_label.setText("")
        self.result_config = VMConfig(
            name=name, ram_mb=self.ram_input.value(), cpu_cores=self.cpu_input.value(),
            disk_path=disk, iso_path=iso, qemu_binary=qemu_bin, extra_args=extra_args,
            net_mode=net_mode, net_bridge_iface=bridge_iface)
        # Apply git repo import data if present
        if hasattr(self, "_git_repo_path") and self._git_repo_path:
            self.result_config.repo_path = self._git_repo_path
        if hasattr(self, "_git_shared_folders") and self._git_shared_folders:
            self.result_config.shared_folders = self._git_shared_folders
        if hasattr(self, "_git_devcontainer") and self._git_devcontainer:
            self.result_config.devcontainer_config = self._git_devcontainer
        if hasattr(self, "_git_port_forwards") and self._git_port_forwards:
            self.result_config.port_forwards = self._git_port_forwards
        # Sandbox template: isolate network, disable sharing
        if tpl.get("sandbox"):
            self.result_config.sandbox_mode = True
            self.result_config.net_mode = "hostonly"
            self.result_config.clipboard_sync = False
            self.result_config.shared_folders = []
        self.accept()
