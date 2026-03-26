from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from app.qemu.process import ProcessState, QemuProcess, kvm_available
from app.qemu.qmp import QMPConnection, QMPError
from app.ui.vm_controls import VMControlPanel, VMEditDialog
from app.ui.vm_create_dialog import VMCreateDialog
from app.ui.vm_list import VMListPanel
from app.ui.welcome_dialog import WelcomeDialog, should_show_welcome
from config.vm_config import VMConfig

log = logging.getLogger(__name__)

from app.ui.theme import BG_PANEL, FONT_FAMILY, TEXT_PRIMARY


class GradientStrip(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(4)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0.0, QColor("#4caf7d"))
        g.setColorAt(1.0, QColor("#357a55"))
        p.fillRect(self.rect(), g)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, configs: list[VMConfig]) -> None:
        super().__init__()
        self.configs = configs
        self._processes: dict[str, QemuProcess] = {}
        self._qmp_conns: dict[str, QMPConnection] = {}
        self._current_vm: VMConfig | None = None
        self._last_cpu_times: dict[str, list[int]] = {}

        self._build_ui()
        self._connect_signals()
        self._start_status_timer()

        if self.configs:
            self._on_vm_selected(0)

    def _build_ui(self) -> None:
        self.setWindowTitle("NovaMachine v0.1.0")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(
            f"* {{ font-family: {FONT_FAMILY}; }}"
            f" QMainWindow {{ background-color: {BG_PANEL}; color: {TEXT_PRIMARY}; }}"
            f" QFrame {{ background-color: {BG_PANEL}; }}"
            f" QLabel {{ color: {TEXT_PRIMARY}; background: transparent; }}"
            f" QLineEdit {{ color: {TEXT_PRIMARY}; }}"
            f" QTabBar {{ color: {TEXT_PRIMARY}; }}"
            f" QTabWidget::pane {{ background-color: {BG_PANEL}; }}")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(GradientStrip())

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self.vm_list = VMListPanel(self.configs)
        self.vm_controls = VMControlPanel()

        content.addWidget(self.vm_list)
        content.addWidget(self.vm_controls, 1)
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
        self.vm_controls.overview_tab.create_requested.connect(self._on_create_vm)
        self.vm_list.vm_rename_requested.connect(self._on_sidebar_rename)
        self.vm_list.vm_delete_requested.connect(self._on_sidebar_delete)
        self.vm_controls.vm_renamed.connect(self._on_vm_renamed)
        self.vm_controls.console_panel.get_start_button().clicked.connect(self._on_start)
        self.vm_controls.btn_start.clicked.connect(self._on_start)
        self.vm_controls.btn_stop.clicked.connect(self._on_stop)
        self.vm_controls.btn_pause.clicked.connect(self._on_pause)
        self.vm_controls.snapshot_panel.snapshot_action.connect(self._on_snapshot_action)
        self.vm_controls.network_panel.config_changed.connect(self._on_network_changed)
        self.vm_controls.usb_panel.usb_action.connect(self._on_usb_action)
        self.vm_controls.usb_panel.config_changed.connect(self._on_usb_config_changed)
        self.vm_controls.display_panel.config_changed.connect(self._on_display_changed)
        self.vm_controls.gpu_panel.config_changed.connect(self._on_gpu_changed)
        self.vm_controls.edit_requested.connect(self._on_edit_vm)
        self.vm_controls.overview_tab.card_ram.value_changed.connect(self._on_ram_changed)
        self.vm_controls.overview_tab.card_cpu.value_changed.connect(self._on_cpu_changed)

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

    def _on_vm_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.configs):
            return
        self._current_vm = self.configs[index]
        cfg = self._current_vm
        self._update_overview(cfg)
        self.vm_controls.network_panel.set_config(cfg.net_mode, cfg.net_bridge_iface)
        self.vm_controls.usb_panel.set_assigned_devices(cfg.usb_devices)
        self.vm_controls.gpu_panel.set_assigned_gpus(cfg.gpu_passthrough)
        self.vm_controls.display_panel.set_config(cfg.display_config)
        proc = self._processes.get(cfg.vm_id)
        if proc and proc.refresh_state() == ProcessState.RUNNING:
            self._update_qmp_status(cfg.vm_id)
            self._refresh_snapshots(cfg.vm_id)
        else:
            self.vm_controls.set_buttons_for_state("stopped")
            self.vm_controls.snapshot_panel.set_snapshots([])
            self.vm_controls.perf_panel.clear()

    def _on_create_vm(self) -> None:
        dialog = VMCreateDialog(self)
        if dialog.exec() and dialog.result_config is not None:
            config = dialog.result_config
            config.save()
            self.vm_list.add_vm(config)

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
        proc = self._get_or_create_process(cfg)
        if proc.state == ProcessState.STOPPED:
            proc.start()
            if proc.state != ProcessState.RUNNING:
                log.error("QEMU failed to start for VM %r — not attempting QMP", cfg.name)
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
            try:
                qmp.execute_cont()
            except QMPError:
                pass
        self.vm_controls.perf_panel.clear()
        self._last_cpu_times.pop(cfg.vm_id, None)
        self._update_qmp_status(cfg.vm_id)

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
        self.vm_controls.set_buttons_for_state("stopped")
        self.vm_controls.snapshot_panel.set_snapshots([])
        self.vm_controls.perf_panel.clear()
        self.vm_list.set_vm_running(cfg.vm_id, False)

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

    def _refresh_snapshots(self, vm_id: str) -> None:
        qmp = self._qmp_conns.get(vm_id)
        if not qmp or not qmp.connected:
            self.vm_controls.snapshot_panel.set_snapshots([])
            return
        try:
            self.vm_controls.snapshot_panel.set_snapshots(qmp.snapshot_list())
        except QMPError:
            self.vm_controls.snapshot_panel.set_snapshots([])

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
            a = qmp.query_balloon().get("return", {}).get("actual", 0)
            self.vm_controls.perf_panel.add_ram_point(a / 1048576 if a else 0)
        except QMPError:
            self.vm_controls.perf_panel.add_ram_point(float(cfg.ram_mb) if cfg else 0)

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
            qmp = self._qmp_conns.pop(vm_id, None)
            if qmp:
                qmp.disconnect()
            self._last_cpu_times.pop(vm_id, None)
            self.vm_controls.set_buttons_for_state("stopped")
            self.vm_controls.snapshot_panel.set_snapshots([])
            self.vm_controls.perf_panel.clear()
            self.vm_list.set_vm_running(vm_id, False)
            return
        self._update_qmp_status(vm_id)
        self._poll_performance(vm_id)

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
