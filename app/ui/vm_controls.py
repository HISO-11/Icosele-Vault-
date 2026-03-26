from __future__ import annotations

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.ui.console_panel import ConsolePanel
from app.ui.display_panel import DisplayPanel
from app.ui.gpu_panel import GPUPanel
from app.ui.network_panel import NetworkPanel
from app.ui.perf_graph import PerformancePanel
from app.ui.snapshot_panel import SnapshotPanel
from app.ui.theme import (
    ACCENT, BG_CARD, BG_ELEVATED, BG_PANEL, BORDER, FONT_FAMILY,
    TAB_STYLE, TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY,
)
from app.ui.usb_panel import USBPanel

_SUBLABEL = "#8a9ab0"

# Naked +/- style: no background, no border, just the character
_NAKED_BTN = (
    f"QPushButton {{"
    f" background: transparent; color: #ffffff;"
    f" border: none; font-size: 18px; font-weight: 400;"
    f" font-family: {FONT_FAMILY};"
    f"}}"
    f"QPushButton:hover {{ color: {ACCENT}; }}"
)


class ClickableLabel(QLabel):
    double_clicked = Signal()

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()


class InfoCard(QFrame):
    value_changed = Signal(int)

    def __init__(self, label: str, editable: bool = False,
                 step: int = 1, min_val: int = 1, max_val: int = 999999,
                 parent=None) -> None:
        super().__init__(parent)
        self._editable = editable
        self._step = step
        self._min_val = min_val
        self._max_val = max_val
        self._current_int: int = 0

        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setStyleSheet(f"""
            InfoCard {{
                background-color: {BG_CARD};
                border: none;
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(0)

        layout.addStretch(1)

        self._label = QLabel(label.upper())
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 2px; background: transparent;"
            f" font-family: {FONT_FAMILY};")

        # Value row: optional [-] value [+]
        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(6)

        self._btn_minus = QPushButton("\u2212")
        self._btn_minus.setFixedSize(28, 28)
        self._btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_minus.setStyleSheet(_NAKED_BTN)
        self._btn_minus.clicked.connect(self._on_minus)

        self._btn_plus = QPushButton("+")
        self._btn_plus.setFixedSize(28, 28)
        self._btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_plus.setStyleSheet(_NAKED_BTN)
        self._btn_plus.clicked.connect(self._on_plus)

        self._value = QLabel("--")
        self._value.setTextFormat(Qt.TextFormat.RichText)
        self._value.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._value.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent;"
            f" font-family: {FONT_FAMILY};")
        self._value.setWordWrap(False)

        value_row.addStretch()
        if editable:
            value_row.addWidget(self._btn_minus, 0, Qt.AlignmentFlag.AlignVCenter)
        value_row.addWidget(self._value, 0, Qt.AlignmentFlag.AlignVCenter)
        if editable:
            value_row.addWidget(self._btn_plus, 0, Qt.AlignmentFlag.AlignVCenter)
        value_row.addStretch()

        self._subtitle = QLabel("")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._subtitle.setStyleSheet(
            f"color: {_SUBLABEL}; font-size: 10px; background: transparent;"
            f" font-family: {FONT_FAMILY};")

        layout.addWidget(self._label)
        layout.addSpacing(4)
        layout.addLayout(value_row)
        layout.addSpacing(3)
        layout.addWidget(self._subtitle)

        layout.addStretch(1)

        self.setLayout(layout)

        if not editable:
            self._btn_minus.hide()
            self._btn_plus.hide()

    def set_value(self, text: str, unit: str = "", subtitle: str = "") -> None:
        try:
            self._current_int = int(text)
        except (ValueError, TypeError):
            self._current_int = 0

        # Elide text if too long
        display_text = text
        fm = self._value.fontMetrics()
        max_width = max(self.width() - 80, 120)
        if fm.horizontalAdvance(text) > max_width and len(text) > 15:
            while fm.horizontalAdvance(display_text + "\u2026") > max_width and len(display_text) > 5:
                display_text = display_text[:-1]
            display_text = display_text + "\u2026"

        if unit:
            self._value.setText(
                f'<span style="font-size:36px; font-weight:900">{display_text}</span>'
                f' <span style="font-size:16px; font-weight:500; color:{TEXT_SECONDARY}">{unit}</span>')
        else:
            self._value.setText(
                f'<span style="font-size:36px; font-weight:900">{display_text}</span>')
        self._subtitle.setText(subtitle)

    def set_editable_visible(self, visible: bool) -> None:
        if not self._editable:
            return
        self._btn_minus.setVisible(visible)
        self._btn_plus.setVisible(visible)

    def _on_minus(self) -> None:
        new_val = max(self._min_val, self._current_int - self._step)
        if new_val != self._current_int:
            self._current_int = new_val
            self.value_changed.emit(new_val)

    def _on_plus(self) -> None:
        new_val = min(self._max_val, self._current_int + self._step)
        if new_val != self._current_int:
            self._current_int = new_val
            self.value_changed.emit(new_val)


class StatusBadge(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status("stopped")

    def set_status(self, status: str) -> None:
        if status == "running":
            label = "RUNNING"
            s = (f"color: {TEXT_ON_ACCENT}; background-color: {ACCENT};"
                 f" border: none; border-radius: 12px; font-weight: 700;")
        elif status == "paused":
            label = "PAUSED"
            s = (f"color: {TEXT_ON_ACCENT}; background-color: {ACCENT};"
                 f" border: none; border-radius: 12px; font-weight: 700;")
        else:
            label = "STOPPED"
            s = (f"color: {TEXT_SECONDARY}; background-color: transparent;"
                 f" border: 1px solid {TEXT_MUTED}; border-radius: 12px;"
                 f" font-weight: 700;")

        self.setText(label)
        self.setStyleSheet(f"""
            {s}
            padding: 6px 16px;
            font-size: 11px;
            letter-spacing: 1px;
            font-family: {FONT_FAMILY};
        """)
        self.setFixedHeight(30)
        self.setFixedWidth(self.fontMetrics().horizontalAdvance(label) + 40)


class OverviewTab(QWidget):
    create_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(0)

        card_w = QWidget()
        card_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid = QGridLayout(card_w)
        grid.setSpacing(3)
        grid.setContentsMargins(0, 0, 0, 0)

        self.card_cpu = InfoCard("CPU Cores", editable=True, step=1, min_val=1, max_val=32)
        self.card_ram = InfoCard("Memory", editable=True, step=1024, min_val=1024, max_val=32768)
        self.card_disk = InfoCard("Storage")
        self.card_net = InfoCard("Network")

        grid.addWidget(self.card_cpu, 0, 0)
        grid.addWidget(self.card_ram, 0, 1)
        grid.addWidget(self.card_disk, 1, 0)
        grid.addWidget(self.card_net, 1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        layout.addWidget(card_w, 1)
        layout.addSpacing(16)

        # Bottom action bar: + NEW | START | STOP | PAUSE
        btn_row = QWidget()
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 0, 0, 0)
        btn_row_layout.setSpacing(12)

        self.btn_new = QPushButton("+ NEW MACHINE")
        self.btn_start = QPushButton("\u25b6 START")
        self.btn_stop = QPushButton("\u25a0 STOP")
        self.btn_pause = QPushButton("\u23f8 PAUSE")

        # Permanent styles — hardcoded, never overridden
        self.btn_new.setStyleSheet(
            f"QPushButton {{ background-color: #2a3040; color: #ffffff; border: none;"
            f" border-radius: 8px; font-size: 14px; font-weight: 800;"
            f" min-height: 52px; font-family: {FONT_FAMILY}; }}"
            f"QPushButton:hover {{ background-color: #343e52; }}")
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: #4caf7d; color: #ffffff; border: none;"
            f" border-radius: 8px; font-size: 14px; font-weight: 800;"
            f" min-height: 52px; font-family: {FONT_FAMILY}; }}")
        self.btn_stop.setStyleSheet(
            f"QPushButton {{ background-color: #ff3b30; color: #ffffff; border: none;"
            f" border-radius: 8px; font-size: 14px; font-weight: 800;"
            f" min-height: 52px; font-family: {FONT_FAMILY}; }}")
        self.btn_pause.setStyleSheet(
            f"QPushButton {{ background-color: #ff9500; color: #ffffff; border: none;"
            f" border-radius: 8px; font-size: 14px; font-weight: 800;"
            f" min-height: 52px; font-family: {FONT_FAMILY}; }}")

        for btn in [self.btn_new, self.btn_start, self.btn_stop, self.btn_pause]:
            btn.setFixedHeight(56)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_new.clicked.connect(self.create_requested.emit)

        btn_row_layout.addWidget(self.btn_new)
        btn_row_layout.addWidget(self.btn_start)
        btn_row_layout.addWidget(self.btn_stop)
        btn_row_layout.addWidget(self.btn_pause)

        btn_row.setContentsMargins(0, 0, 0, 16)
        layout.addWidget(btn_row)


class VMEditDialog(QDialog):
    """Dialog for editing an existing VM's settings."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.accepted_changes = False
        self._build_ui()

    def _build_ui(self) -> None:
        from app.ui.theme import (
            BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY, INPUT_STYLE,
            LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY, WARNING,
            primary_btn_style, secondary_btn_style,
        )
        from config.vm_config import NET_MODE_NAT, NET_MODE_BRIDGE, NET_MODE_HOSTONLY

        self.setWindowTitle(f"Edit \u2014 {self.config.name}")
        self.setFixedSize(500, 480)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = QLabel("Edit VM Settings")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name = QLineEdit(self.config.name)
        self._name.setStyleSheet(INPUT_STYLE)

        self._ram = QSpinBox()
        self._ram.setRange(128, 131072)
        self._ram.setValue(self.config.ram_mb)
        self._ram.setSuffix(" MB")
        self._ram.setSingleStep(256)
        self._ram.setStyleSheet(INPUT_STYLE)

        self._cpu = QSpinBox()
        self._cpu.setRange(1, 128)
        self._cpu.setValue(self.config.cpu_cores)
        self._cpu.setStyleSheet(INPUT_STYLE)

        self._iso = QLineEdit(self.config.iso_path)
        self._iso.setPlaceholderText("(none)")
        self._iso.setStyleSheet(INPUT_STYLE)

        self._disk = QLineEdit(self.config.disk_path)
        self._disk.setPlaceholderText("(none)")
        self._disk.setStyleSheet(INPUT_STYLE)

        self._qemu = QLineEdit(self.config.qemu_binary)
        self._qemu.setStyleSheet(INPUT_STYLE)

        self._net = QComboBox()
        self._net.setStyleSheet(COMBO_STYLE)
        modes = [
            ("NAT (User mode)", NET_MODE_NAT),
            ("Bridged", NET_MODE_BRIDGE),
            ("Host-only", NET_MODE_HOSTONLY),
        ]
        for label, key in modes:
            self._net.addItem(label, key)
        idx = next((i for i, (_, k) in enumerate(modes) if k == self.config.net_mode), 0)
        self._net.setCurrentIndex(idx)

        for lbl_text, widget in [
            ("Name", self._name), ("RAM", self._ram), ("CPU Cores", self._cpu),
            ("ISO Path", self._iso), ("Disk Path", self._disk),
            ("QEMU Binary", self._qemu), ("Network", self._net),
        ]:
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(LABEL_STYLE)
            form.addRow(lbl, widget)

        layout.addLayout(form)

        info = QLabel("RAM and CPU changes take effect on next VM start.")
        info.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(info)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(secondary_btn_style())
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save")
        btn_save.setStyleSheet(primary_btn_style())
        btn_save.setFixedHeight(34)
        btn_save.setMinimumWidth(80)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._on_save)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(8)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        self.config.name = self._name.text().strip() or self.config.name
        self.config.ram_mb = self._ram.value()
        self.config.cpu_cores = self._cpu.value()
        self.config.iso_path = self._iso.text().strip()
        self.config.disk_path = self._disk.text().strip()
        self.config.qemu_binary = self._qemu.text().strip()
        self.config.net_mode = self._net.currentData()
        self.accepted_changes = True
        self.accept()


class VMControlPanel(QFrame):
    vm_renamed = Signal(str, str)
    edit_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 28, 40, 24)
        outer.setSpacing(0)

        # Header — VM name + badge (no pencil, no edit button)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.name_label = ClickableLabel("No VM selected")
        self.name_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 42px; font-weight: 900;"
            f" letter-spacing: -1px; background: transparent;"
            f" font-family: {FONT_FAMILY};")
        self.name_label.double_clicked.connect(self.edit_requested.emit)

        header.addWidget(self.name_label)
        header.addStretch()

        self.status_badge = StatusBadge()
        header.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(header)

        outer.addSpacing(4)

        self.subtitle_label = QLabel("KVM \u00b7 x86_64")
        self.subtitle_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
            f" font-family: {FONT_FAMILY};")
        outer.addWidget(self.subtitle_label)

        outer.addSpacing(16)
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {BG_ELEVATED};")
        outer.addWidget(div)
        outer.addSpacing(16)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)
        self.tabs.setDocumentMode(True)

        self.overview_tab = OverviewTab()
        self.console_panel = ConsolePanel()
        self.perf_panel = PerformancePanel()
        self.network_panel = NetworkPanel()
        self.snapshot_panel = SnapshotPanel()
        self.usb_panel = USBPanel()
        self.gpu_panel = GPUPanel()
        self.display_panel = DisplayPanel()

        self.tabs.addTab(self.overview_tab, "Overview")
        self.tabs.addTab(self.console_panel, "Console")
        self.tabs.addTab(self.perf_panel, "Performance")
        self.tabs.addTab(self.network_panel, "Network")
        self.tabs.addTab(self.usb_panel, "USB")
        self.tabs.addTab(self.gpu_panel, "GPU")
        self.tabs.addTab(self.display_panel, "Display")
        self.tabs.addTab(self.snapshot_panel, "Snapshots")

        outer.addWidget(self.tabs, 1)
        self.set_buttons_for_state("stopped")

    @property
    def btn_start(self) -> QPushButton:
        return self.overview_tab.btn_start

    @property
    def btn_stop(self) -> QPushButton:
        return self.overview_tab.btn_stop

    @property
    def btn_pause(self) -> QPushButton:
        return self.overview_tab.btn_pause

    def set_vm_info(self, name, ram, cpus, disk, net_mode="",
                    display_backend="gtk", vga_type="virtio",
                    usb_count=0, gpu_count=0) -> None:
        self.name_label.setText(name)
        self.overview_tab.card_cpu.set_value(
            str(cpus), "vCPU" + ("s" if cpus != 1 else ""), "KVM accelerated")
        self.overview_tab.card_ram.set_value(
            str(ram), "MB", "Allocated RAM")

        if disk:
            disk_name = os.path.basename(disk)
            ext = os.path.splitext(disk_name)[1].lstrip(".").lower()
            disk_type = ext if ext else "disk"
            self.overview_tab.card_disk.set_value(disk_name, "", disk_type)
        else:
            self.overview_tab.card_disk.set_value(
                "No disk", "", "Edit VM to attach a disk")

        net_label = {"nat": "NAT", "bridge": "Bridged", "hostonly": "Host-only"}.get(net_mode, "NAT")
        self.overview_tab.card_net.set_value(net_label, "", "virtio-net")
        self.perf_panel.set_ram_max(float(ram))

    def set_buttons_for_state(self, status: str) -> None:
        is_running = status == "running"
        is_paused = status == "paused"
        is_stopped = status in ("stopped", "")

        if is_paused:
            self.btn_pause.setText("\u25b6 RESUME")
        else:
            self.btn_pause.setText("\u23f8 PAUSE")

        self.overview_tab.card_ram.set_editable_visible(is_stopped)
        self.overview_tab.card_cpu.set_editable_visible(is_stopped)

        self.status_badge.set_status(status if status else "stopped")
        self.console_panel.set_status(status if status else "stopped")
        self.snapshot_panel.set_enabled(is_running or is_paused)
        self.usb_panel.set_vm_running(is_running or is_paused)
