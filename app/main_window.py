from __future__ import annotations

import ctypes
import logging
import platform
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QLinearGradient, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from app.ui.instant_boot_panel import INSTANT_BOOT_TAG

import app.audit_log as audit
import app.web_console as web_console
import app.webhook_manager as webhooks
from app.plugin_manager import call_hook, discover_plugins
from app.qemu.process import ProcessState, QemuProcess, kvm_available
from app.qemu.qmp import QMPConnection, QMPError
from app.ui.ai_create_dialog import AICreateDialog
from app.ui.ai_disk_predictor import DiskPredictor, record_disk_size
from app.ui.ai_network_monitor import NetworkMonitor
from app.ui.ai_resource_advisor import AIResourceAdvisor
from app.ui.ai_snapshot_advisor import SnapshotAdvisor
from app.ui.clone_dialog import CloneDialog
from app.ui.command_palette import CommandPalette
from app.ui.cve_checker import check_cves, get_qemu_version
from app.ui.dashboard_panel import DashboardPanel
from app.ui.settings_store import load_settings, save_settings
from app.ui.shortcuts_dialog import ShortcutsDialog
from app.ui.gpu_passthrough_wizard import GPUPassthroughWizard
from app.ui.topology_panel import TopologyPanel
from app.usb_monitor import USBHotplugMonitor
from app.ui.vm_controls import VMControlPanel, VMEditDialog
from app.ui.vm_create_dialog import VMCreateDialog
from app.ui.vm_list import VMListPanel
from app.ui.welcome_dialog import WelcomeDialog, should_show_welcome
from config.vm_config import VMConfig

log = logging.getLogger(__name__)

from app.ui.theme import (
    ACCENT, BG_PANEL, FONT_FAMILY, STOP_RED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
)


class AccentBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("accentBar")
        self.setFixedHeight(3)


class MainWindow(QMainWindow):
    def __init__(self, configs: list[VMConfig]) -> None:
        super().__init__()
        self.configs = configs
        self._processes: dict[str, QemuProcess] = {}
        self._qmp_conns: dict[str, QMPConnection] = {}
        self._crash_shown: set[str] = set()
        self._current_vm: VMConfig | None = None
        self._last_cpu_times: dict[str, list[int]] = {}
        self._instant_boot_pending: dict[str, QTimer] = {}
        self._instant_boot_saved: set[str] = set()
        self._quarantined: dict[str, bool] = {}
        self._auto_snapshot_timers: dict[str, QTimer] = {}
        self._clipboard_syncs: dict[str, object] = {}

        self._vm_start_times: dict[str, float] = {}
        self._vm_start_disk_sizes: dict[str, int] = {}

        self._build_ui()
        self._apply_glassmorphism()
        self._connect_signals()
        self._setup_shortcuts()
        self._start_status_timer()
        self._start_thumb_timer()
        self._init_ai_systems()
        self._init_usb_monitor()
        discover_plugins()
        self._setup_web_console()
        self._check_cves()

        if self.configs:
            self._on_vm_selected(0)

    # ── Glassmorphism (platform-specific) ──────────────────────────
    _GLASS_OS = platform.system()  # "Windows", "Darwin", "Linux"

    def _is_glass_platform(self) -> bool:
        return self._GLASS_OS in ("Windows", "Darwin")

    def _apply_glassmorphism(self) -> None:
        """Enable blur-behind on Windows/macOS.  Linux is left untouched."""
        os_name = self._GLASS_OS
        if os_name == "Windows":
            self._apply_glass_windows()
        elif os_name == "Darwin":
            self._apply_glass_macos()

    def _apply_glass_windows(self) -> None:
        """Use DWM Acrylic blur via ctypes (Windows 10 1803+)."""
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            hwnd = int(self.winId())

            # --- DwmExtendFrameIntoClientArea (full glass) ---
            class MARGINS(ctypes.Structure):
                _fields_ = [("cxLeftWidth", ctypes.c_int),
                            ("cxRightWidth", ctypes.c_int),
                            ("cyTopHeight", ctypes.c_int),
                            ("cyBottomHeight", ctypes.c_int)]
            margins = MARGINS(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

            # --- SetWindowCompositionAttribute → Acrylic ---
            class ACCENT_POLICY(ctypes.Structure):
                _fields_ = [("AccentState", ctypes.c_int),
                            ("AccentFlags", ctypes.c_int),
                            ("GradientColor", ctypes.c_uint),
                            ("AnimationId", ctypes.c_int)]
            class WINCOMP_ATTR_DATA(ctypes.Structure):
                _fields_ = [("Attribute", ctypes.c_int),
                            ("Data", ctypes.POINTER(ACCENT_POLICY)),
                            ("SizeOfData", ctypes.c_uint)]

            ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
            # GradientColor: ABGR  – dark tint at ~70 % opacity
            accent = ACCENT_POLICY(ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, 0xB3190F0F, 0)
            data = WINCOMP_ATTR_DATA(19, ctypes.pointer(accent), ctypes.sizeof(accent))
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
            log.info("Glassmorphism: Windows Acrylic blur enabled")
        except Exception as exc:
            log.warning("Glassmorphism: Windows blur failed (%s), falling back to solid bg", exc)

    def _apply_glass_macos(self) -> None:
        """macOS glassmorphism via WA_TranslucentBackground only.

        Raw objc_msgSend calls to inject NSVisualEffectView are not safe
        via ctypes — ABI mismatches on ARM64 cause SIGABRT (exit 134)
        which Python cannot catch.  Instead we just make the window
        translucent and let the semi-transparent stylesheets provide
        the frosted-glass aesthetic against the desktop.
        """
        if sys.platform != "darwin":
            return
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            log.info("Glassmorphism: macOS translucent background enabled")
        except Exception as exc:
            log.warning("Glassmorphism: macOS setup failed (%s), using solid bg", exc)

    def _build_ui(self) -> None:
        self.setWindowTitle("Icosele VM")
        self.setMinimumSize(1200, 700)

        glass = self._is_glass_platform()
        # On glass platforms use semi-transparent backgrounds;
        # on Linux use solid #1e1e1e with no transparency.
        if glass:
            main_bg = "background: rgba(30,30,30,0.88)"
            panel_bg = "rgba(30,30,30,0.85)"
        else:
            main_bg = "background: #1e1e1e"
            panel_bg = None  # keep existing theme colours

        glass_extra = ""
        if glass:
            glass_extra = (
                f" QMainWindow {{ background: transparent; }}"
                f" #centralWidget {{ background: rgba(28,28,28,0.85); }}"
                f" #sidebar {{ background: rgba(24,24,24,0.90); }}"
            )
        self.setStyleSheet(
            f"* {{ font-family: {FONT_FAMILY}; }}"
            f" QMainWindow {{ {main_bg}; color: {TEXT_PRIMARY}; }}"
            f" QFrame {{ background: transparent; border: none; }}"
            f" #accentBar {{ background-color: #4caf7d; border: none; }}"
            f" QLabel {{ color: {TEXT_PRIMARY}; background: transparent; }}"
            f" QLineEdit {{ color: {TEXT_PRIMARY}; }}"
            f" QScrollBar:vertical {{ width: 4px; background: transparent; border: none; }}"
            f" QScrollBar::handle:vertical {{ background: #546058; border-radius: 2px; min-height: 20px; }}"
            f" QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f" QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}"
            f" QScrollBar:horizontal {{ height: 4px; background: transparent; border: none; }}"
            f" QScrollBar::handle:horizontal {{ background: #546058; border-radius: 2px; }}"
            f" QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}"
            + (f" QGroupBox, #SidebarPanel, #StatCard {{ background: {panel_bg}; }}"
               if panel_bg else "")
            + glass_extra)

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(AccentBar())

        # CVE warning banner (hidden by default)
        self._cve_banner = QLabel("")
        self._cve_banner.setWordWrap(True)
        self._cve_banner.setStyleSheet(
            f"background-color: #2d1010; color: {STOP_RED};"
            f" border: 1px solid {STOP_RED}; border-radius: 0;"
            f" padding: 8px 16px; font-size: 12px; font-family: {FONT_FAMILY};")
        self._cve_banner.hide()
        root.addWidget(self._cve_banner)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self.vm_list = VMListPanel(self.configs)
        self.vm_list.setObjectName("sidebar")
        self.vm_controls = VMControlPanel()
        self.topology_panel = TopologyPanel(
            self.configs, self._processes, self._qmp_conns)
        self.dashboard = DashboardPanel()
        self.dashboard.set_data(self.configs, self._processes)

        content.addWidget(self.vm_list)

        # Right side: stacked (dashboard | vm detail)
        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self.dashboard)     # index 0
        self._right_stack.addWidget(self.vm_controls)   # index 1
        self._right_stack.setCurrentIndex(0)
        content.addWidget(self._right_stack, 1)

        root.addLayout(content, 1)

    def show(self) -> None:
        self.showMaximized()
        if not self.configs or should_show_welcome():
            self._show_welcome()

    def _show_welcome(self) -> None:
        dlg = WelcomeDialog(self)
        dlg.exec()
        if dlg.wants_create:
            self._on_create_vm()
        elif dlg.import_path:
            self._import_config(dlg.import_path)

    def _import_config(self, path: str) -> None:
        from pathlib import Path
        try:
            cfg = VMConfig.load(Path(path))
            cfg.save()
            self.vm_list.add_vm(cfg)
            self._on_vm_selected(len(self.configs) - 1)
        except Exception as exc:
            log.error("Failed to import config: %s", exc)

    def _connect_signals(self) -> None:
        self.vm_list.vm_selected.connect(self._on_vm_selected)
        self.vm_list.create_requested.connect(self._on_create_vm)
        self.vm_list.ai_create_requested.connect(self._on_ai_create_vm)
        self.vm_controls.overview_tab.create_requested.connect(self._on_create_vm)
        self.vm_controls.overview_tab.clone_requested.connect(self._on_clone_vm)
        self.vm_controls.overview_tab.import_requested.connect(self._on_toolbar_import)
        self.vm_controls.overview_tab.export_requested.connect(self._on_toolbar_export)
        self.vm_controls.overview_tab.fullscreen_requested.connect(self._toggle_fullscreen)
        self.vm_list.clone_requested.connect(self._on_sidebar_clone)
        self.vm_list.vm_rename_requested.connect(self._on_sidebar_rename)
        self.vm_list.vm_delete_requested.connect(self._on_sidebar_delete)
        self.vm_controls.vm_renamed.connect(self._on_vm_renamed)
        self.vm_controls.console_panel.get_start_button().clicked.connect(self._on_start)
        self.vm_controls.btn_start.clicked.connect(self._on_start)
        self.vm_controls.btn_stop.clicked.connect(self._on_stop)
        self.vm_controls.btn_pause.clicked.connect(self._on_pause)
        self.vm_controls.snapshot_panel.snapshot_action.connect(self._on_snapshot_action)
        self.vm_controls.snapshot_panel.boot_from_snapshot.connect(self._on_boot_from_snapshot)
        self.vm_controls.snapshot_panel.screenshot_requested.connect(self._on_snapshot_screenshot)
        self.vm_controls.snap_dag_panel.snapshot_action.connect(self._on_snapshot_action)
        self.vm_controls.snap_dag_panel.clone_requested.connect(self._on_clone_vm)
        self.vm_controls.snap_dag_panel.branch_changed.connect(
            self.vm_controls.branch_badge.setText)
        self.vm_controls.network_panel.config_changed.connect(self._on_network_changed)
        self.vm_controls.network_panel.port_forwards_changed.connect(self._on_port_forwards_changed)
        self.vm_controls.usb_panel.usb_action.connect(self._on_usb_action)
        self.vm_controls.usb_panel.config_changed.connect(self._on_usb_config_changed)
        self.vm_controls.display_panel.config_changed.connect(self._on_display_changed)
        self.vm_controls.gpu_panel.config_changed.connect(self._on_gpu_changed)
        self.vm_controls.edit_requested.connect(self._on_edit_vm)
        self.vm_controls.overview_tab.card_ram.value_changed.connect(self._on_ram_changed)
        self.vm_controls.overview_tab.card_cpu.value_changed.connect(self._on_cpu_changed)
        self.vm_controls.disk_perf_panel.config_changed.connect(self._on_disk_perf_changed)
        self.vm_controls.balloon_panel.config_changed.connect(self._on_balloon_config_changed)
        self.vm_controls.balloon_panel.balloon_adjust.connect(self._on_balloon_adjust)
        self.vm_controls.hugepages_panel.config_changed.connect(self._on_hugepages_changed)
        self.vm_controls.instant_boot_panel.config_changed.connect(self._on_instant_boot_changed)
        self.vm_controls.instant_boot_panel.reset_requested.connect(self._on_instant_boot_reset)
        self.vm_controls.audio_panel.config_changed.connect(self._on_audio_changed)
        self.vm_controls.clipboard_panel.config_changed.connect(self._on_clipboard_changed)
        self.vm_controls.shared_folders_panel.config_changed.connect(self._on_shared_folders_changed)
        self.vm_controls.spice_panel.config_changed.connect(self._on_spice_changed)
        self.vm_controls.netsim_panel.config_changed.connect(self._on_netsim_changed)
        self.vm_controls.dns_panel.config_changed.connect(self._on_dns_changed)
        self.vm_controls.encryption_panel.config_changed.connect(self._on_encryption_changed)
        self.vm_controls.firewall_panel.config_changed.connect(self._on_firewall_changed)
        self.vm_controls.dns_filter_panel.config_changed.connect(self._on_dns_filter_changed)
        self.vm_controls.quarantine_panel.quarantine_requested.connect(self._on_quarantine)
        self.vm_controls.quarantine_panel.restore_requested.connect(self._on_restore_network)
        self.vm_controls.timeline_panel.snapshot_action.connect(self._on_snapshot_action)
        self.vm_controls.ai_assistant.action_requested.connect(self._on_ai_action)
        self.vm_controls.ai_assistant.create_vm_requested.connect(self._on_ai_create_config)
        self.vm_controls.usb_panel.remembered_changed.connect(self._on_usb_remembered_changed)
        self.vm_controls.webcam_panel.passthrough_requested.connect(self._on_webcam_passthrough)
        self.vm_controls.sandbox_panel.snapshot_action.connect(self._on_snapshot_action)
        self.vm_controls.system_status_panel.isolation_changed.connect(self._on_isolation_changed)
        self.vm_controls.archaeology_panel.create_vm_requested.connect(self._on_archaeology_create)
        self.vm_controls.team_library_panel.deploy_requested.connect(self._on_team_deploy)
        self.dashboard.create_requested.connect(self._on_create_vm)

    def _start_status_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_status)
        self._timer.start(2000)

    def _update_overview(self, cfg: VMConfig) -> None:
        dc = cfg.display_config
        display_disk = cfg.disk_path or cfg.iso_path or ""
        self.vm_controls.set_vm_info(
            cfg.name, cfg.ram_mb, cfg.cpu_cores, display_disk, cfg.net_mode,
            display_backend=dc.get("display_backend", "gtk"),
            vga_type=dc.get("vga_type", "virtio"),
            usb_count=len(cfg.usb_devices),
            gpu_count=len(cfg.gpu_passthrough))

    def _on_vm_renamed(self, old_name: str, new_name: str) -> None:
        cfg = self._current_vm
        if cfg is None or cfg.name != old_name:
            return
        cfg.rename(new_name)
        for i in range(self.vm_list.list_widget.count()):
            item = self.vm_list.list_widget.item(i)
            if item and item.text() == old_name:
                item.setText(new_name)
                break
        log.info("Renamed VM %r -> %r", old_name, new_name)

    def _on_sidebar_rename(self, index: int, new_name: str) -> None:
        if index < 0 or index >= len(self.configs):
            return
        cfg = self.configs[index]
        old_name = cfg.name
        cfg.rename(new_name)
        item = self.vm_list.list_widget.item(index)
        if item:
            item.setText(new_name)
        if self._current_vm is cfg:
            self.vm_controls.name_label.setText(new_name)
        log.info("Renamed VM %r -> %r", old_name, new_name)

    def _on_sidebar_delete(self, index: int) -> None:
        if index < 0 or index >= len(self.configs):
            return
        cfg = self.configs[index]
        from pathlib import Path
        from config.vm_config import DATA_DIR
        json_path = DATA_DIR / f"{cfg.vm_id}.json"
        if json_path.exists():
            json_path.unlink()
        proc = self._processes.pop(cfg.vm_id, None)
        if proc:
            proc.stop()
        qmp = self._qmp_conns.pop(cfg.vm_id, None)
        if qmp:
            if qmp.connected:
                try:
                    qmp.quit()
                except Exception:
                    pass
            qmp.disconnect()
        self.vm_list.remove_vm(index)
        if self._current_vm is cfg:
            self._current_vm = None
            if self.configs:
                self._on_vm_selected(0)
                self.vm_list.list_widget.setCurrentRow(0)
            else:
                self.vm_controls.name_label.setText("No VM selected")
        log.info("Deleted VM %r", cfg.name)
        audit.record("vm_deleted", cfg.vm_id, cfg.name)

    def _on_vm_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.configs):
            return
        self._right_stack.setCurrentIndex(1)
        self._current_vm = self.configs[index]
        cfg = self._current_vm
        self._update_overview(cfg)
        self.vm_controls.network_panel.set_config(cfg.net_mode, cfg.net_bridge_iface)
        self.vm_controls.network_panel.set_port_forwards(cfg.port_forward_rules)
        self.vm_controls.usb_panel.set_assigned_devices(cfg.usb_devices)
        self.vm_controls.usb_panel.set_remembered_devices(cfg.usb_remembered_devices)
        self.vm_controls.gpu_panel.set_assigned_gpus(cfg.gpu_passthrough)
        self.vm_controls.display_panel.set_config(cfg.display_config)
        self.vm_controls.disk_perf_panel.set_config(cfg.virtio_blk_io_uring, cfg.disk_path)
        self.vm_controls.balloon_panel.set_config(cfg.balloon_enabled, cfg.balloon_min_mb, cfg.ram_mb)
        self.vm_controls.hugepages_panel.set_config(cfg.hugepages_enabled, cfg.ram_mb)
        self.vm_controls.instant_boot_panel.set_config(cfg.instant_boot)
        self.vm_controls.audio_panel.set_config(cfg.audio_enabled)
        self.vm_controls.clipboard_panel.set_config(cfg.clipboard_sync, cfg.vm_id)
        self.vm_controls.shared_folders_panel.set_config(cfg.shared_folders, cfg.vm_id, cfg.ram_mb)
        self.vm_controls.spice_panel.set_config(cfg.spice_config)
        self.vm_controls.netsim_panel.set_config(cfg.netsim_config)
        self.vm_controls.dns_panel.set_config(cfg.dns_servers)
        self.vm_controls.snap_dag_panel.set_vm(cfg.vm_id, cfg.disk_path, cfg.name)
        self.vm_controls.timeline_panel.set_vm(cfg.vm_id)
        self.vm_controls.branch_badge.setText(
            self.vm_controls.snap_dag_panel.get_current_branch())
        self.vm_controls.encryption_panel.set_config(cfg.encrypted)
        self.vm_controls.firewall_panel.set_config(cfg.firewall_rules, cfg.vm_id)
        self.vm_controls.dns_filter_panel.set_config(cfg.dns_filter_enabled, cfg.vm_id)
        self.vm_controls.quarantine_panel.set_quarantined(
            self._quarantined.get(cfg.vm_id, False))
        self.vm_controls.apparmor_panel.set_config(
            cfg.vm_id, cfg.qemu_binary, cfg.disk_path, cfg.iso_path)
        self.vm_controls.ai_pruner.set_vm(cfg.vm_id, cfg.name)
        self.vm_controls.sandbox_panel.set_vm(cfg.vm_id, cfg.name, cfg.sandbox_mode)
        self.vm_controls.cloud_panel.export_panel.set_vm(cfg.name, cfg.disk_path)
        disk_gb = 0
        if cfg.disk_path and Path(cfg.disk_path).exists():
            try:
                disk_gb = Path(cfg.disk_path).stat().st_size / (1024**3)
            except OSError:
                pass
        self.vm_controls.cloud_panel.cost_panel.estimate(
            cfg.name, cfg.cpu_cores, cfg.ram_mb, disk_gb)
        self.vm_controls.vm_share_panel.set_vm(cfg.vm_id)
        self.vm_controls.vm_share_panel.set_qmp_provider(lambda vid: self._qmp_conns.get(vid))
        self.vm_controls.handoff_panel.set_vm(cfg.vm_id, cfg.name, cfg.disk_path)
        self.vm_controls.recording_panel.set_vm(cfg.vm_id, cfg.name)
        self.vm_controls.system_status_panel.set_isolation(cfg.isolation_level)
        self.vm_controls.recording_panel.set_qmp_provider(lambda vid: self._qmp_conns.get(vid))
        proc = self._processes.get(cfg.vm_id)
        is_running = bool(proc and proc.refresh_state() == ProcessState.RUNNING)
        self.vm_controls.balloon_panel.set_vm_running(is_running)
        if is_running:
            self._update_qmp_status(cfg.vm_id)
            self._refresh_snapshots(cfg.vm_id)
            self._refresh_instant_boot_status(cfg.vm_id)
        else:
            self.vm_controls.set_buttons_for_state("stopped")
            self.vm_controls.snapshot_panel.set_snapshots([])
            self.vm_controls.perf_panel.clear()
            self.vm_controls.instant_boot_panel.set_snapshot_info(
                cfg.vm_id in self._instant_boot_saved)

    def _on_toolbar_import(self) -> None:
        from app.ui.vm_list import import_vm
        path, _ = QFileDialog.getOpenFileName(
            self, "Import VM", str(Path.home()),
            "Icosele VM Archive (*.ivault);;Zip Files (*.zip);;All Files (*)")
        if not path:
            return
        try:
            cfg = import_vm(path)
            cfg.save()
            self.vm_list.add_vm(cfg)
            QMessageBox.information(self, "Import Complete",
                                    f"VM \"{cfg.name}\" imported successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Import Failed", str(exc))

    def _on_toolbar_export(self) -> None:
        from app.ui.vm_list import export_vm
        cfg = self._current_vm
        if not cfg:
            return
        default_name = f"{cfg.vm_id}.ivault"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export VM", str(Path.home() / default_name),
            "Icosele VM Archive (*.ivault);;All Files (*)")
        if not path:
            return
        try:
            export_vm(cfg, path)
            QMessageBox.information(self, "Export Complete",
                                    f"VM exported to:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))

    def _on_create_vm(self) -> None:
        dialog = VMCreateDialog(self)
        if dialog.exec() and dialog.result_config is not None:
            config = dialog.result_config
            config.save()
            self.vm_list.add_vm(config)
            audit.record("vm_created", config.vm_id, config.name)

    def _on_ai_create_vm(self) -> None:
        dlg = AICreateDialog(self)
        if not dlg.exec() or dlg.result_values is None:
            return
        vals = dlg.result_values
        if vals.get("_manual"):
            self._on_create_vm()
            return
        # Pre-fill the standard wizard and show it
        dialog = VMCreateDialog(self)
        if vals.get("name"):
            dialog.name_input.setText(vals["name"])
        if vals.get("ram_mb"):
            dialog.ram_input.setValue(int(vals["ram_mb"]))
        if vals.get("cpu_cores"):
            dialog.cpu_input.setValue(int(vals["cpu_cores"]))
        dialog._stack.setCurrentIndex(1)
        if dialog.exec() and dialog.result_config is not None:
            config = dialog.result_config
            if vals.get("enable_gpu_passthrough"):
                pass  # GPU passthrough requires manual PCI address selection
            if vals.get("enable_hugepages"):
                config.hugepages_enabled = True
            config.save()
            self.vm_list.add_vm(config)

    def _on_sidebar_clone(self, index: int) -> None:
        if 0 <= index < len(self.configs):
            old = self._current_vm
            self._current_vm = self.configs[index]
            self._on_clone_vm()
            self._current_vm = old

    def _on_team_deploy(self, entry: dict) -> None:
        """Deploy a VM template from the team library."""
        disk_src = entry.get("disk_path", "")
        name = entry.get("name", "team-vm")
        if not disk_src or not Path(disk_src).exists():
            QMessageBox.warning(self, "Deploy", "Template disk image not found.")
            return
        dialog = VMCreateDialog(self)
        dialog.name_input.setText(f"{name} (from library)")
        dialog._stack.setCurrentIndex(1)
        if dialog.exec() and dialog.result_config is not None:
            config = dialog.result_config
            # Create linked clone from template
            import subprocess
            new_disk = str(Path(disk_src).parent.parent / f"{config.vm_id}.qcow2")
            try:
                subprocess.run(
                    ["qemu-img", "create", "-f", "qcow2",
                     "-b", disk_src, "-F", "qcow2", new_disk],
                    check=True, capture_output=True, timeout=30)
                config.disk_path = new_disk
            except Exception:
                pass
            config.save()
            self.vm_list.add_vm(config)
            audit.record("team_library_deploy", config.vm_id, config.name,
                         {"template": name})

    def _on_archaeology_create(self, entry: dict) -> None:
        dialog = VMCreateDialog(self)
        dialog.name_input.setText(entry.get("name", "retro-vm"))
        dialog.ram_input.setValue(entry.get("ram_mb", 512))
        dialog.cpu_input.setValue(entry.get("cpu", 1))
        dialog._stack.setCurrentIndex(1)
        if dialog.exec() and dialog.result_config is not None:
            config = dialog.result_config
            # Apply historical OS specific QEMU args
            machine = entry.get("machine", "pc")
            extra = list(entry.get("extra_args", []))
            if not any(a == "-machine" for a in extra):
                extra = ["-machine", machine] + extra
            config.extra_args = extra
            config.display_config["vga_type"] = entry.get("display", "std")
            config.save()
            self.vm_list.add_vm(config)
            audit.record("vm_created", config.vm_id, config.name,
                         {"template": "archaeology", "os": entry.get("name", "")})

    def _on_clone_vm(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        dlg = CloneDialog(cfg, self)
        if dlg.exec() and dlg.result_config is not None:
            self.vm_list.add_vm(dlg.result_config)
            audit.record("vm_cloned", cfg.vm_id, cfg.name,
                         {"clone_name": dlg.result_config.name})

    def _on_edit_vm(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        old_name = cfg.name
        dlg = VMEditDialog(cfg, self)
        if dlg.exec() and dlg.accepted_changes:
            cfg.save()
            # Update sidebar if name changed
            if cfg.name != old_name:
                for i in range(self.vm_list.list_widget.count()):
                    item = self.vm_list.list_widget.item(i)
                    if item and item.text() == old_name:
                        item.setText(cfg.name)
                        break
            self._update_overview(cfg)
            log.info("VM settings updated for %r", cfg.name)

    def _on_ram_changed(self, value: int) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.ram_mb = value
        cfg.save()
        self.vm_controls.overview_tab.card_ram.set_value(str(value), "MB", "Allocated RAM")
        self.vm_controls.perf_panel.set_ram_max(float(value))

    def _on_cpu_changed(self, value: int) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.cpu_cores = value
        cfg.save()
        self.vm_controls.overview_tab.card_cpu.set_value(
            str(value), "vCPU" + ("s" if value != 1 else ""), "KVM accelerated")

    def _on_network_changed(self, net_mode: str, bridge_iface: str) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.net_mode = net_mode
        cfg.net_bridge_iface = bridge_iface
        cfg.save()
        self._update_overview(cfg)

    def _on_isolation_changed(self, level: str) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.isolation_level = level
        if level == "restricted":
            cfg.clipboard_sync = False
            cfg.shared_folders = []
        elif level == "airgapped":
            cfg.clipboard_sync = False
            cfg.shared_folders = []
            cfg.net_mode = "none"
        cfg.save()
        audit.record("isolation_changed", cfg.vm_id, cfg.name, {"level": level})

    def _on_port_forwards_changed(self, rules: list[dict]) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.port_forward_rules = rules
        cfg.save()

    def _on_usb_config_changed(self, devices: list[dict]) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.usb_devices = devices
        cfg.save()
        self._update_overview(cfg)

    def _on_usb_action(self, action: str, bus: str, addr: str, device_id: str) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            if action == "add":
                qmp.device_add("usb-host", device_id, hostbus=int(bus), hostaddr=int(addr))
            elif action == "remove":
                qmp.device_del(device_id)
        except QMPError as exc:
            log.error("USB %s failed: %s", action, exc)

    def _on_usb_remembered_changed(self, devices: list[dict]) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.usb_remembered_devices = devices
        cfg.save()

    def _on_webcam_passthrough(self, bus: str, addr: str, vid: str, pid: str) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            QMessageBox.information(self, "Webcam", "Start the VM first to pass through the webcam.")
            return
        dev_id = f"webcam-{vid}-{pid}"
        try:
            qmp.device_add("usb-host", dev_id, hostbus=int(bus), hostaddr=int(addr))
            log.info("Webcam passed through: bus=%s addr=%s", bus, addr)
        except QMPError as exc:
            log.error("Webcam passthrough failed: %s", exc)

    def _setup_web_console(self) -> None:
        def _get_web_data():
            from app.snapshot_store import load_snapshots
            vms = []
            for c in self.configs:
                proc = self._processes.get(c.vm_id)
                running = bool(proc and proc.state == ProcessState.RUNNING)
                disk_mb = 0
                if c.disk_path and Path(c.disk_path).exists():
                    try:
                        disk_mb = int(Path(c.disk_path).stat().st_size / (1024 * 1024))
                    except OSError:
                        pass
                vms.append({
                    "name": c.name, "vm_id": c.vm_id,
                    "status": "running" if running else "stopped",
                    "ram_mb": c.ram_mb, "cpu_cores": c.cpu_cores,
                    "disk_mb": disk_mb,
                })
            total = len(vms)
            running_count = sum(1 for v in vms if v["status"] == "running")
            total_snaps = sum(len(load_snapshots(c.vm_id)) for c in self.configs)
            total_disk = sum(v["disk_mb"] for v in vms) / 1024
            return {
                "vms": vms,
                "audit": audit.load_entries()[-50:],
                "stats": {
                    "total_vms": total,
                    "running": running_count,
                    "stopped": total - running_count,
                    "snapshots": total_snaps,
                    "disk_gb": f"{total_disk:.1f}",
                },
            }
        web_console.set_data_provider(_get_web_data)
        self.vm_controls.enterprise_panel.compliance_panel._configs_fn = lambda: self.configs
        self.vm_controls.enterprise_panel.replication_panel._configs_fn = lambda: self.configs
        self.vm_controls.enterprise_panel.dr_panel._configs_fn = lambda: self.configs
        self.vm_controls.cloud_panel.readiness_panel._configs_fn = lambda: self.configs

    def _init_usb_monitor(self) -> None:
        self._usb_monitor = USBHotplugMonitor(self)
        self._usb_monitor.device_connected.connect(self._on_usb_hotplug)
        self._usb_monitor.start()

    def _on_usb_hotplug(self, dev: dict) -> None:
        vid = dev.get("vendor_id", "")
        pid = dev.get("product_id", "")
        name = dev.get("device_name", f"{vid}:{pid}")
        bus = dev.get("bus", "")
        addr = dev.get("addr", "")
        # Check auto-connect for all running VMs
        for cfg in self.configs:
            proc = self._processes.get(cfg.vm_id)
            if not proc or proc.state != ProcessState.RUNNING:
                continue
            for rd in cfg.usb_remembered_devices:
                if (rd.get("vendor_id") == vid and rd.get("product_id") == pid
                        and rd.get("auto_connect", False)):
                    qmp = self._qmp_conns.get(cfg.vm_id)
                    if qmp and qmp.connected:
                        dev_id = f"usb-{vid}-{pid}"
                        try:
                            qmp.device_add("usb-host", dev_id,
                                           hostbus=int(bus), hostaddr=int(addr))
                            log.info("Auto-connected USB %s to VM %s", name, cfg.name)
                        except QMPError as exc:
                            log.warning("USB auto-connect failed: %s", exc)
                    return
        log.info("USB device %s plugged in, no auto-connect match", name)

    def _on_gpu_changed(self, pci_addrs: list[str]) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.gpu_passthrough = pci_addrs
        cfg.save()
        self._update_overview(cfg)

    def _on_display_changed(self, display_cfg: dict) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.display_config = display_cfg
        cfg.save()
        self._update_overview(cfg)

    def _get_or_create_process(self, cfg: VMConfig) -> QemuProcess:
        if cfg.vm_id not in self._processes:
            self._processes[cfg.vm_id] = QemuProcess(cfg)
        return self._processes[cfg.vm_id]

    def _on_start(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        self._crash_shown.discard(cfg.vm_id)
        if not kvm_available() and not getattr(self, '_kvm_warned', False):
            self._kvm_warned = True
            QMessageBox.warning(
                self, "KVM Unavailable",
                "Hardware virtualisation (KVM) is not available.\n"
                "/dev/kvm is missing or not accessible.\n\n"
                "The VM will still start but will run very slowly\n"
                "without hardware acceleration.\n\n"
                "To fix: ensure your CPU supports VT-x/AMD-V,\n"
                "enable it in BIOS, and add your user to the 'kvm' group.")
        # Encryption: prompt for password
        proc = self._get_or_create_process(cfg)
        if cfg.encrypted and proc.state == ProcessState.STOPPED:
            pwd, ok = self._prompt_password(cfg.name)
            if not ok or not pwd:
                return
            proc.encryption_password = pwd
        if proc.state == ProcessState.STOPPED:
            # Show notifications for missing optional dependencies
            for msg in proc.missing_deps():
                QMessageBox.information(self, "Missing Dependency", msg)
            proc.start()
            if proc.state != ProcessState.RUNNING:
                stderr = proc.last_error
                log.error("QEMU failed to start for VM %r — not attempting QMP", cfg.name)
                QMessageBox.critical(
                    self, "VM Failed to Start",
                    f"QEMU exited immediately for \"{cfg.name}\".\n\n"
                    f"{stderr if stderr else 'No error output captured.'}")
                # Send error to AI for diagnosis
                if stderr:
                    self.vm_controls.ai_assistant.diagnose_error(stderr[:500])
                return
            log.info("Attempting QMP connection to: %s", proc.socket_path)
            try:
                qmp = QMPConnection(proc.socket_path)
                qmp.connect()
                self._qmp_conns[cfg.vm_id] = qmp
                log.info("QMP connected successfully for VM %r", cfg.name)
            except QMPError as exc:
                log.error("QMP failed for %s: %s", cfg.vm_id, exc)
        qmp = self._qmp_conns.get(cfg.vm_id)
        if qmp and qmp.connected:
            # Instant boot: try to restore snapshot
            if cfg.instant_boot and cfg.vm_id in self._instant_boot_saved:
                try:
                    qmp.snapshot_restore(INSTANT_BOOT_TAG)
                    log.info("Restored instant-boot snapshot for VM %r", cfg.name)
                except QMPError as exc:
                    log.warning("Instant boot restore failed, cold booting: %s", exc)
                    try:
                        qmp.execute_cont()
                    except QMPError:
                        pass
            else:
                try:
                    qmp.execute_cont()
                except QMPError:
                    pass
            # Schedule instant-boot save if enabled and no snapshot yet
            if cfg.instant_boot and cfg.vm_id not in self._instant_boot_saved:
                self._schedule_instant_boot_save(cfg.vm_id)
        self.vm_controls.perf_panel.clear()
        self._last_cpu_times.pop(cfg.vm_id, None)
        self._update_qmp_status(cfg.vm_id)
        self.vm_controls.balloon_panel.set_vm_running(True)
        self.vm_controls.spice_panel.set_vm_running(True)
        self.topology_panel.refresh()
        audit.record("vm_started", cfg.vm_id, cfg.name)
        webhooks.dispatch("vm_started", cfg.vm_id, cfg.name)
        call_hook("on_vm_start", vm_id=cfg.vm_id, vm_name=cfg.name)
        # AI: record disk size on start, track start time
        import time as _time
        self._vm_start_times[cfg.vm_id] = _time.time()
        if cfg.disk_path and Path(cfg.disk_path).exists():
            sz = Path(cfg.disk_path).stat().st_size
            self._vm_start_disk_sizes[cfg.vm_id] = sz
            record_disk_size(cfg.vm_id, sz)
            self._disk_predictor.predict(cfg.vm_id, cfg.name, cfg.disk_path)
        # Update network monitor VM names
        names = {c.vm_id: c.name for c in self.configs}
        self._net_monitor.set_vm_names(names)
        # Auto-snapshot scheduling
        if cfg.auto_snapshot:
            self._start_auto_snapshot(cfg.vm_id)
        # Clipboard sync
        if cfg.clipboard_sync:
            from app.clipboard_sync import ClipboardSync
            sync = ClipboardSync(cfg.vm_id)
            sync.start()
            self._clipboard_syncs[cfg.vm_id] = sync

    def _start_auto_snapshot(self, vm_id: str) -> None:
        if vm_id in self._auto_snapshot_timers:
            return
        timer = QTimer(self)
        timer.setInterval(1800000)  # 30 minutes
        timer.timeout.connect(lambda vid=vm_id: self._do_auto_snapshot(vid))
        timer.start()
        self._auto_snapshot_timers[vm_id] = timer

    def _stop_auto_snapshot(self, vm_id: str) -> None:
        timer = self._auto_snapshot_timers.pop(vm_id, None)
        if timer:
            timer.stop()

    def _do_auto_snapshot(self, vm_id: str) -> None:
        qmp = self._qmp_conns.get(vm_id)
        if not qmp or not qmp.connected:
            self._stop_auto_snapshot(vm_id)
            return
        from datetime import datetime
        name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            qmp.snapshot_create(name)
            log.info("Auto-snapshot '%s' created for VM %s", name, vm_id)
        except QMPError as exc:
            log.warning("Auto-snapshot failed for %s: %s", vm_id, exc)
        self._refresh_snapshots(vm_id)

    def _on_stop(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.pop(cfg.vm_id, None)
        if qmp:
            if qmp.connected:
                try:
                    qmp.quit()
                except QMPError:
                    pass
            qmp.disconnect()
        proc = self._processes.get(cfg.vm_id)
        if proc:
            proc.stop()
        self._last_cpu_times.pop(cfg.vm_id, None)
        timer = self._instant_boot_pending.pop(cfg.vm_id, None)
        if timer:
            timer.stop()
        self._stop_auto_snapshot(cfg.vm_id)
        sync = self._clipboard_syncs.pop(cfg.vm_id, None)
        if sync:
            sync.stop()
        self.vm_controls.set_buttons_for_state("stopped")
        self.vm_controls.snapshot_panel.set_snapshots([])
        self.vm_controls.snap_dag_panel.set_snapshots([])
        self.vm_controls.perf_panel.clear()
        self.vm_controls.balloon_panel.set_vm_running(False)
        self.vm_controls.spice_panel.set_vm_running(False)
        self.vm_list.set_vm_running(cfg.vm_id, False)
        self.topology_panel.refresh()
        audit.record("vm_stopped", cfg.vm_id, cfg.name)
        webhooks.dispatch("vm_stopped", cfg.vm_id, cfg.name)
        call_hook("on_vm_stop", vm_id=cfg.vm_id, vm_name=cfg.name)
        # AI: evaluate session for auto-snapshot (Task 4)
        import time as _time
        start_t = self._vm_start_times.pop(cfg.vm_id, 0)
        duration = (_time.time() - start_t) / 60 if start_t else 0
        start_sz = self._vm_start_disk_sizes.pop(cfg.vm_id, 0)
        disk_growth = 0.0
        if cfg.disk_path and Path(cfg.disk_path).exists() and start_sz:
            cur_sz = Path(cfg.disk_path).stat().st_size
            disk_growth = (cur_sz - start_sz) / (1024 * 1024)
            record_disk_size(cfg.vm_id, cur_sz)
        self._snapshot_advisor.evaluate_session(
            cfg.vm_id, cfg.name, cfg.disk_path,
            duration_min=duration, disk_growth_mb=disk_growth,
            manual_count=0, crash_count=0)

    def _on_pause(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            # Check current state to toggle pause/resume
            st = qmp.query_status().get("return", {}).get("status", "")
            if st == "paused":
                qmp.execute_cont()
            else:
                qmp.execute_stop()
        except QMPError:
            pass
        self._update_qmp_status(cfg.vm_id)

    def _on_snapshot_screenshot(self, snapshot_name: str) -> None:
        """Capture a screenshot when a snapshot is created."""
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            return
        snap_dir = Path.home() / ".icosele-vm" / "snapshots" / cfg.vm_id
        snap_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(snap_dir / f"{snapshot_name}.ppm")
        try:
            qmp.execute("screendump", {"filename": screenshot_path})
            log.info("Snapshot screenshot saved: %s", screenshot_path)
        except QMPError as exc:
            log.warning("Failed to capture snapshot screenshot: %s", exc)

    def _on_boot_from_snapshot(self, snapshot_name: str) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        proc = self._get_or_create_process(cfg)
        if proc.state == ProcessState.RUNNING:
            return
        # Add -loadvm to extra_args temporarily for this boot
        original_extra = list(cfg.extra_args)
        cfg.extra_args = original_extra + ["-loadvm", snapshot_name]
        proc.start()
        cfg.extra_args = original_extra  # restore original
        if proc.state != ProcessState.RUNNING:
            stderr = proc.last_error
            QMessageBox.critical(self, "Boot Failed",
                                 f"Failed to boot from snapshot '{snapshot_name}'.\n\n{stderr}")
            return
        try:
            qmp = QMPConnection(proc.socket_path)
            qmp.connect()
            self._qmp_conns[cfg.vm_id] = qmp
            qmp.execute_cont()
        except QMPError as exc:
            log.error("QMP failed after boot-from-snapshot: %s", exc)
        self._update_qmp_status(cfg.vm_id)
        audit.record("vm_boot_from_snapshot", cfg.vm_id, cfg.name,
                     {"snapshot_name": snapshot_name})

    def _on_snapshot_action(self, action: str, name: str) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            getattr(qmp, f"snapshot_{action}")(name)
        except QMPError as exc:
            log.error("Snapshot %s failed: %s", action, exc)
        self._refresh_snapshots(cfg.vm_id)
        audit.record(f"snapshot_{action}", cfg.vm_id, cfg.name,
                     {"snapshot_name": name})
        if action == "create":
            webhooks.dispatch("snapshot_created", cfg.vm_id, cfg.name,
                              {"snapshot_name": name})
            call_hook("on_snapshot_created", vm_id=cfg.vm_id, snapshot_name=name)
        elif action == "restore":
            webhooks.dispatch("snapshot_restored", cfg.vm_id, cfg.name,
                              {"snapshot_name": name})

    def _refresh_snapshots(self, vm_id: str) -> None:
        qmp = self._qmp_conns.get(vm_id)
        if not qmp or not qmp.connected:
            self.vm_controls.snapshot_panel.set_snapshots([])
            self.vm_controls.snap_dag_panel.set_snapshots([])
            return
        try:
            snap_list = qmp.snapshot_list()
            self.vm_controls.snapshot_panel.set_snapshots(snap_list)
            self.vm_controls.snap_dag_panel.set_snapshots(snap_list)
        except QMPError:
            self.vm_controls.snapshot_panel.set_snapshots([])
            self.vm_controls.snap_dag_panel.set_snapshots([])

    # -- New config handlers --

    def _on_disk_perf_changed(self, enabled: bool) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.virtio_blk_io_uring = enabled
        cfg.save()

    def _on_balloon_config_changed(self, enabled: bool, min_mb: int) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.balloon_enabled = enabled
        cfg.balloon_min_mb = min_mb
        cfg.save()

    def _on_balloon_adjust(self, target_mb: int) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            qmp.execute("balloon", {"value": target_mb * 1024 * 1024})
        except QMPError as exc:
            log.error("Balloon adjust failed: %s", exc)

    def _on_hugepages_changed(self, enabled: bool) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.hugepages_enabled = enabled
        cfg.save()

    def _on_instant_boot_changed(self, enabled: bool) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.instant_boot = enabled
        cfg.save()

    def _on_instant_boot_reset(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if qmp and qmp.connected:
            try:
                qmp.snapshot_delete(INSTANT_BOOT_TAG)
            except QMPError as exc:
                log.warning("Failed to delete instant-boot snapshot: %s", exc)
        self._instant_boot_saved.discard(cfg.vm_id)
        timer = self._instant_boot_pending.pop(cfg.vm_id, None)
        if timer:
            timer.stop()
        self.vm_controls.instant_boot_panel.set_snapshot_info(False)

    def _on_audio_changed(self, enabled: bool) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.audio_enabled = enabled
        cfg.save()

    def _on_clipboard_changed(self, enabled: bool) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.clipboard_sync = enabled
        cfg.save()

    def _on_shared_folders_changed(self, folders: list[dict]) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.shared_folders = folders
        cfg.save()

    def _on_spice_changed(self, spice_cfg: dict) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.spice_config = spice_cfg
        cfg.save()

    def _on_netsim_changed(self, netsim_cfg: dict) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.netsim_config = netsim_cfg
        cfg.save()

    def _on_dns_changed(self, dns_servers: list[str]) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.dns_servers = dns_servers
        cfg.save()

    def _on_encryption_changed(self, enabled: bool) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.encrypted = enabled
        cfg.save()
        if enabled:
            audit.record("encryption_enabled", cfg.vm_id, cfg.name)

    def _on_firewall_changed(self, rules: list[dict]) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.firewall_rules = rules
        cfg.save()
        audit.record("firewall_changed", cfg.vm_id, cfg.name,
                     {"rule_count": len(rules)})

    def _on_dns_filter_changed(self, enabled: bool) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        cfg.dns_filter_enabled = enabled
        cfg.save()

    def _on_quarantine(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            qmp.device_del("virtio-net-pci-net0")
        except QMPError:
            pass
        try:
            qmp.execute("netdev_del", {"id": "net0"})
        except QMPError:
            pass
        self._quarantined[cfg.vm_id] = True
        self.vm_controls.quarantine_panel.set_quarantined(True)
        audit.record("network_quarantine", cfg.vm_id, cfg.name,
                     {"action": "quarantined"})

    def _on_restore_network(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        qmp = self._qmp_conns.get(cfg.vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            netdev_type = "user"
            dns_part = ""
            if cfg.dns_servers:
                dns_part = f",dns={cfg.dns_servers[0]}"
            qmp.execute("netdev_add", {"type": netdev_type, "id": "net0"})
        except QMPError:
            pass
        try:
            qmp.device_add("virtio-net-pci", "virtio-net-pci-net0", netdev="net0")
        except QMPError:
            pass
        self._quarantined[cfg.vm_id] = False
        self.vm_controls.quarantine_panel.set_quarantined(False)
        audit.record("network_quarantine", cfg.vm_id, cfg.name,
                     {"action": "restored"})

    def _prompt_password(self, vm_name: str) -> tuple[str, bool]:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Encrypted VM — {vm_name}")
        dlg.setFixedSize(400, 180)
        dlg.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel(f"Enter disk encryption password for \"{vm_name}\":"))
        pwd = QLineEdit()
        pwd.setEchoMode(QLineEdit.EchoMode.Password)
        pwd.setPlaceholderText("Password")
        from app.ui.theme import INPUT_STYLE
        pwd.setStyleSheet(INPUT_STYLE)
        lay.addWidget(pwd)
        warn = QLabel("Lost passwords cannot be recovered. There is no backdoor.")
        warn.setStyleSheet(f"color: {WARNING}; font-size: 10px; font-style: italic;"
                           f" background: transparent;")
        lay.addWidget(warn)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return pwd.text(), ok

    def _check_cves(self) -> None:
        ver = get_qemu_version()
        if ver is None:
            return
        hits = check_cves(ver)
        if not hits:
            return
        cve_list = ", ".join(h["cve"] for h in hits)
        ver_str = f"{ver[0]}.{ver[1]}.{ver[2]}"
        self._cve_banner.setText(
            f"Security Warning: QEMU {ver_str} has known vulnerabilities: "
            f"{cve_list}. Update at https://www.qemu.org/download/")
        self._cve_banner.show()

    # ── Thumbnails & activity (Tasks 1-2) ─────────────────────────────

    def _start_thumb_timer(self) -> None:
        self._thumb_timer = QTimer(self)
        self._thumb_timer.timeout.connect(self._poll_thumbnails)
        self._thumb_timer.start(3000)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self.vm_list.pulse_animation)
        self._pulse_timer.start(150)

    def _poll_thumbnails(self) -> None:
        for cfg in self.configs:
            qmp = self._qmp_conns.get(cfg.vm_id)
            if not qmp or not qmp.connected:
                continue
            thumb_path = f"/tmp/icosele-vm/{cfg.vm_id}/thumb.ppm"
            try:
                qmp.execute("screendump", {"filename": thumb_path})
            except QMPError:
                pass
            pix = QPixmap(thumb_path)
            if not pix.isNull():
                self.vm_list.update_thumbnail(cfg.vm_id, pix)
                if self._current_vm and cfg.vm_id == self._current_vm.vm_id:
                    self.vm_controls.display_preview_tab.set_thumbnail(pix)
            # Activity bars
            try:
                cpus_resp = qmp.query_cpus_fast().get("return", [])
                cpu_pct = min(100.0, len(cpus_resp) * 25.0) if cpus_resp else 0
            except QMPError:
                cpu_pct = 0
            try:
                balloon = qmp.query_balloon().get("return", {})
                actual = balloon.get("actual", 0)
                ram_pct = min(100.0, (actual / (cfg.ram_mb * 1048576)) * 100) if actual else 50.0
            except QMPError:
                ram_pct = 0
            self.vm_list.update_activity(cfg.vm_id, cpu_pct, ram_pct, 10.0)

    # ── Keyboard shortcuts (Tasks 4-5) ─────────────────────────────────

    def _setup_shortcuts(self) -> None:
        def _sc(key, slot):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(slot)
            return s
        _sc("Ctrl+N", self._on_create_vm)
        _sc("Ctrl+K", self._open_command_palette)
        _sc("Ctrl+S", self._on_start)
        _sc("Ctrl+Q", self._on_stop)
        _sc("Ctrl+P", self._on_pause)
        _sc("F5", self._refresh_all)
        _sc("F11", self._toggle_fullscreen)
        _sc("Ctrl+F", self._focus_search)
        _sc("Ctrl+L", self._open_audit_log)
        _sc("Ctrl+D", self._on_clone_vm)
        _sc("Alt+H", self._toggle_high_contrast)
        _sc("Alt+M", self._toggle_reduced_motion)
        _sc("Ctrl+A", self._open_ai_assistant)
        _sc("Ctrl+Shift+/", self._show_shortcuts)
        _sc("Ctrl+Shift+M", self._open_monitor_console)
        _sc("Delete", self._on_delete_selected)
        for i in range(9):
            _sc(f"Ctrl+{i + 1}", lambda idx=i: self._switch_vm(idx))

    def _open_command_palette(self) -> None:
        actions = [
            {"id": "new_vm", "label": "New VM", "shortcut": "Ctrl+N"},
            {"id": "audit_log", "label": "Open Audit Log", "shortcut": "Ctrl+L"},
            {"id": "shortcuts", "label": "Keyboard Shortcuts", "shortcut": "Ctrl+?"},
            {"id": "refresh", "label": "Refresh All", "shortcut": "F5"},
            {"id": "fullscreen", "label": "Toggle Fullscreen", "shortcut": "F11"},
            {"id": "dashboard", "label": "Show Dashboard"},
        ]
        for i, cfg in enumerate(self.configs):
            actions.append({"id": f"vm_{i}", "label": f"Switch to: {cfg.name}",
                            "shortcut": f"Ctrl+{i + 1}" if i < 9 else ""})
            proc = self._processes.get(cfg.vm_id)
            is_running = proc and proc.state == ProcessState.RUNNING
            if is_running:
                actions.append({"id": f"stop_{i}", "label": f"Stop {cfg.name}"})
                actions.append({"id": f"snap_{i}", "label": f"Snapshot {cfg.name}"})
            else:
                actions.append({"id": f"start_{i}", "label": f"Start {cfg.name}"})
        if self._current_vm:
            tab_count = self.vm_controls.tabs.count()
            for t in range(tab_count):
                tab_name = self.vm_controls.tabs.tabText(t)
                actions.append({"id": f"tab_{t}", "label": f"Tab: {tab_name}"})
        dlg = CommandPalette(actions, self)
        dlg.action_selected.connect(self._execute_palette_action)
        dlg.exec()

    def _execute_palette_action(self, action_id: str) -> None:
        if action_id == "new_vm":
            self._on_create_vm()
        elif action_id == "audit_log":
            self._open_audit_log()
        elif action_id == "shortcuts":
            self._show_shortcuts()
        elif action_id == "refresh":
            self._refresh_all()
        elif action_id == "fullscreen":
            self._toggle_fullscreen()
        elif action_id == "dashboard":
            self._right_stack.setCurrentIndex(0)
        elif action_id.startswith("vm_"):
            idx = int(action_id[3:])
            self._switch_vm(idx)
        elif action_id.startswith("start_"):
            idx = int(action_id[6:])
            self._switch_vm(idx)
            self._on_start()
        elif action_id.startswith("stop_"):
            idx = int(action_id[5:])
            self._switch_vm(idx)
            self._on_stop()
        elif action_id.startswith("snap_"):
            idx = int(action_id[5:])
            self._switch_vm(idx)
        elif action_id.startswith("tab_"):
            t = int(action_id[4:])
            self.vm_controls.tabs.setCurrentIndex(t)

    def _switch_vm(self, idx: int) -> None:
        if 0 <= idx < len(self.configs):
            self.vm_list.list_widget.setCurrentRow(idx)

    def _refresh_all(self) -> None:
        for cfg in self.configs:
            vm_id = cfg.vm_id
            proc = self._processes.get(vm_id)
            if proc:
                proc.refresh_state()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def _focus_search(self) -> None:
        self.vm_list._search.setFocus()
        self.vm_list._search.selectAll()

    def _open_audit_log(self) -> None:
        if self._current_vm:
            for i in range(self.vm_controls.tabs.count()):
                if self.vm_controls.tabs.tabText(i) == "Audit Log":
                    self.vm_controls.tabs.setCurrentIndex(i)
                    break

    def _show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def _on_delete_selected(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        idx = next((i for i, c in enumerate(self.configs) if c.vm_id == cfg.vm_id), -1)
        if idx >= 0:
            reply = QMessageBox.question(
                self, "Delete Machine",
                f"Delete \"{cfg.name}\"?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._on_sidebar_delete(idx)

    def _open_monitor_console(self) -> None:
        cfg = self._current_vm
        if not cfg:
            return
        proc = self._processes.get(cfg.vm_id)
        if not proc or proc.state != ProcessState.RUNNING:
            return
        from app.ui.monitor_console import MonitorConsoleDialog
        dlg = MonitorConsoleDialog(proc.monitor_path, self)
        dlg.exec()

    def _toggle_high_contrast(self) -> None:
        s = load_settings()
        s["high_contrast"] = not s.get("high_contrast", False)
        save_settings(s)

    def _toggle_reduced_motion(self) -> None:
        s = load_settings()
        s["reduced_motion"] = not s.get("reduced_motion", False)
        save_settings(s)
        if s["reduced_motion"]:
            self._pulse_timer.stop()
        else:
            self._pulse_timer.start(150)

    # ── AI systems (Tasks 1-6) ────────────────────────────────────────

    def _init_ai_systems(self) -> None:
        # Task 1: AI assistant VM data provider
        self.vm_controls.ai_assistant.set_vm_data_provider(self._get_vm_data_for_ai)

        # Task 2: Resource advisor
        self._resource_advisor = AIResourceAdvisor(self._get_resource_stats)
        self._resource_advisor.recommendations.connect(self._on_resource_recommendations)

        # Task 3: Disk predictor
        self._disk_predictor = DiskPredictor()
        self._disk_predictor.prediction.connect(self._on_disk_prediction)

        # Task 4: Snapshot advisor
        self._snapshot_advisor = SnapshotAdvisor()
        self._snapshot_advisor.snapshot_taken.connect(self._on_ai_snapshot_taken)

        # Task 5: Network monitor
        self._net_monitor = NetworkMonitor()
        self._net_monitor.set_qmp_provider(lambda vid: self._qmp_conns.get(vid))
        self._net_monitor.anomaly.connect(self._on_network_anomaly)

    def _get_vm_data_for_ai(self) -> list[dict]:
        result = []
        for cfg in self.configs:
            proc = self._processes.get(cfg.vm_id)
            running = bool(proc and proc.state == ProcessState.RUNNING)
            result.append({
                "name": cfg.name, "vm_id": cfg.vm_id,
                "ram_mb": cfg.ram_mb, "cpu_cores": cfg.cpu_cores,
                "status": "running" if running else "stopped",
                "disk_path": cfg.disk_path,
                "net_mode": cfg.net_mode,
            })
        return result

    def _get_resource_stats(self) -> list[dict]:
        stats = []
        for cfg in self.configs:
            proc = self._processes.get(cfg.vm_id)
            if not proc or proc.state != ProcessState.RUNNING:
                continue
            stats.append({
                "vm_name": cfg.name,
                "allocated_ram_mb": cfg.ram_mb,
                "allocated_cpus": cfg.cpu_cores,
                "used_ram_pct": 50,  # placeholder — would need QMP
                "used_cpu_pct": 25,  # placeholder
            })
        return stats

    def _on_resource_recommendations(self, recs: list) -> None:
        for r in recs:
            log.info("AI resource recommendation: %s", r)

    def _on_disk_prediction(self, vm_id: str, result: dict) -> None:
        level = result.get("warning_level", "none")
        if level in ("medium", "high"):
            log.warning("Disk prediction for %s: %s", vm_id, result.get("message", ""))

    def _on_ai_snapshot_taken(self, vm_id: str, tag: str, reason: str) -> None:
        log.info("AI auto-snapshot for %s: %s — %s", vm_id, tag, reason)

    def _on_network_anomaly(self, vm_id: str, result: dict) -> None:
        severity = result.get("severity", "none")
        desc = result.get("description", "Unknown anomaly")
        vm_name = next((c.name for c in self.configs if c.vm_id == vm_id), vm_id)
        if severity in ("medium", "high"):
            QMessageBox.warning(
                self, f"Network Anomaly — {vm_name}",
                f"Severity: {severity.upper()}\n{desc}")

    def _on_ai_create_config(self, config: dict) -> None:
        """Handle AI-requested VM creation with extracted config."""
        os_type = config.get("os", "linux")
        ram = config.get("ram_mb", 4096)
        cpus = config.get("cpu_cores", 4)
        disk_gb = config.get("disk_gb", 40)
        name = f"{os_type}-ai-vm"
        from config.vm_config import VMConfig
        cfg = VMConfig(name=name, ram_mb=ram, cpu_cores=cpus)
        cfg.extra_args = ["-machine", "q35"]
        cfg.save()
        self.vm_list.add_vm(cfg)
        audit.record("vm_created", cfg.vm_id, cfg.name, {"source": "ai", "config": config})

    def _on_ai_action(self, action: str, vm_name: str, snap_name: str) -> None:
        # Find VM by name
        cfg = None
        idx = -1
        for i, c in enumerate(self.configs):
            if c.name.lower() == (vm_name or "").lower():
                cfg = c
                idx = i
                break
        if action == "start" and cfg:
            self._switch_vm(idx)
            self._on_start()
        elif action == "stop" and cfg:
            self._switch_vm(idx)
            self._on_stop()
        elif action == "pause" and cfg:
            self._switch_vm(idx)
            self._on_pause()
        elif action == "snapshot" and cfg:
            self._switch_vm(idx)
            qmp = self._qmp_conns.get(cfg.vm_id)
            if qmp and qmp.connected:
                try:
                    name = snap_name or "ai-snapshot"
                    qmp.snapshot_create(name)
                except QMPError:
                    pass
        elif action == "clone" and cfg:
            self._switch_vm(idx)
            self._on_clone_vm()
        elif action == "quarantine" and cfg:
            self._switch_vm(idx)
            self._on_quarantine()

    def _open_ai_assistant(self) -> None:
        if self._current_vm:
            self._right_stack.setCurrentIndex(1)
            for i in range(self.vm_controls.tabs.count()):
                if self.vm_controls.tabs.tabText(i) == "AI Assistant":
                    self.vm_controls.tabs.setCurrentIndex(i)
                    break

    def _schedule_instant_boot_save(self, vm_id: str) -> None:
        if vm_id in self._instant_boot_pending:
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda vid=vm_id: self._do_instant_boot_save(vid))
        timer.start(30000)
        self._instant_boot_pending[vm_id] = timer

    def _do_instant_boot_save(self, vm_id: str) -> None:
        self._instant_boot_pending.pop(vm_id, None)
        qmp = self._qmp_conns.get(vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            qmp.snapshot_create(INSTANT_BOOT_TAG)
            self._instant_boot_saved.add(vm_id)
            log.info("Saved instant-boot snapshot for VM %s", vm_id)
            if self._current_vm and self._current_vm.vm_id == vm_id:
                self.vm_controls.instant_boot_panel.set_snapshot_info(True)
        except QMPError as exc:
            log.error("Failed to save instant-boot snapshot: %s", exc)

    def _refresh_instant_boot_status(self, vm_id: str) -> None:
        qmp = self._qmp_conns.get(vm_id)
        if not qmp or not qmp.connected:
            return
        try:
            snapshots = qmp.snapshot_list()
            has_ib = INSTANT_BOOT_TAG in snapshots
            if has_ib:
                self._instant_boot_saved.add(vm_id)
            else:
                self._instant_boot_saved.discard(vm_id)
            self.vm_controls.instant_boot_panel.set_snapshot_info(has_ib)
        except QMPError:
            pass

    def _poll_performance(self, vm_id: str) -> None:
        qmp = self._qmp_conns.get(vm_id)
        if not qmp or not qmp.connected:
            return
        cfg = self._current_vm
        if not cfg or cfg.vm_id != vm_id:
            return
        try:
            cpus = qmp.query_cpus_fast().get("return", [])
            ct = [c.get("cpu-time", 0) for c in cpus]
            prev = self._last_cpu_times.get(vm_id)
            if prev and len(prev) == len(ct):
                d = sum(c - o for c, o in zip(ct, prev))
                u = max(0.0, min((d / (2e9 * (len(ct) or 1))) * 100, 100.0))
                self.vm_controls.perf_panel.add_cpu_point(u)
            else:
                self.vm_controls.perf_panel.add_cpu_point(0.0)
            self._last_cpu_times[vm_id] = ct
        except QMPError:
            self.vm_controls.perf_panel.add_cpu_point(0.0)
        try:
            balloon_resp = qmp.query_balloon().get("return", {})
            a = balloon_resp.get("actual", 0)
            self.vm_controls.perf_panel.add_ram_point(a / 1048576 if a else 0)
            if cfg and cfg.balloon_enabled:
                actual_mb = int(a / 1048576) if a else cfg.ram_mb
                self.vm_controls.balloon_panel.set_balloon_stats(cfg.ram_mb, actual_mb)
        except QMPError:
            self.vm_controls.perf_panel.add_ram_point(float(cfg.ram_mb) if cfg else 0)
        # Live overview card updates
        if cfg:
            cpu_pct = self.vm_controls.perf_panel.last_cpu if hasattr(self.vm_controls.perf_panel, 'last_cpu') else 0
            self.vm_controls.overview_tab.card_cpu.set_value(
                str(cfg.cpu_cores), "vCPU" + ("s" if cfg.cpu_cores != 1 else ""),
                f"Usage: {cpu_pct:.0f}%", secondary="KVM accelerated")
            ram_used = self.vm_controls.perf_panel.last_ram if hasattr(self.vm_controls.perf_panel, 'last_ram') else 0
            self.vm_controls.overview_tab.card_ram.set_value(
                str(cfg.ram_mb), "MB",
                f"Used: {ram_used:.0f} MB", secondary="DDR4 virtual memory")

    def _update_qmp_status(self, vm_id: str) -> None:
        qmp = self._qmp_conns.get(vm_id)
        if not qmp or not qmp.connected:
            self.vm_controls.set_buttons_for_state("stopped")
            self.vm_list.set_vm_running(vm_id, False)
            return
        try:
            st = qmp.query_status().get("return", {}).get("status", "stopped")
            self.vm_controls.set_buttons_for_state(st)
            self.vm_list.set_vm_running(vm_id, st in ("running", "paused"))
        except QMPError:
            self.vm_controls.set_buttons_for_state("stopped")
            self.vm_list.set_vm_running(vm_id, False)

    def _poll_status(self) -> None:
        if not self._current_vm:
            return
        vm_id = self._current_vm.vm_id
        proc = self._processes.get(vm_id)
        if not proc or proc.refresh_state() != ProcessState.RUNNING:
            # Check for crash (non-zero exit code) — show popup only once
            if proc and proc.exit_code is not None and proc.exit_code != 0:
                if vm_id not in self._crash_shown:
                    self._crash_shown.add(vm_id)
                    self._handle_crash(self._current_vm, proc.exit_code)
            qmp = self._qmp_conns.pop(vm_id, None)
            if qmp:
                qmp.disconnect()
            self._last_cpu_times.pop(vm_id, None)
            self.vm_controls.set_buttons_for_state("stopped")
            self.vm_controls.snapshot_panel.set_snapshots([])
            self.vm_controls.snap_dag_panel.set_snapshots([])
            self.vm_controls.perf_panel.clear()
            self.vm_list.set_vm_running(vm_id, False)
            return
        self._update_qmp_status(vm_id)
        self._poll_performance(vm_id)

    def _handle_crash(self, cfg: VMConfig, exit_code: int) -> None:
        import subprocess
        from datetime import datetime
        from app.snapshot_store import add_snapshot
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_name = f"crash_{ts}"
        audit.record("vm_crashed", cfg.vm_id, cfg.name,
                     {"exit_code": exit_code, "timestamp": ts})
        if cfg.disk_path and Path(cfg.disk_path).exists():
            try:
                subprocess.run(
                    ["qemu-img", "snapshot", "-c", snap_name, cfg.disk_path],
                    check=True, capture_output=True, timeout=30)
                log.info("Crash snapshot saved: %s for VM %s", snap_name, cfg.name)
                add_snapshot(cfg.vm_id, snap_name, tag="crash",
                             branch_name="crashes")
            except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
                log.warning("Failed to create crash snapshot: %s", exc)
        QMessageBox.warning(
            self, "VM Crashed",
            f"VM \"{cfg.name}\" crashed (exit code {exit_code}).\n\n"
            f"A disk snapshot has been saved automatically:\n  {snap_name}\n\n"
            f"Check the Snapshots tab to view crash snapshots.")

    def closeEvent(self, event) -> None:
        for qmp in self._qmp_conns.values():
            if qmp.connected:
                try:
                    qmp.quit()
                except Exception:
                    pass
            qmp.disconnect()
        self._qmp_conns.clear()
        for proc in self._processes.values():
            proc.stop()
        event.accept()
