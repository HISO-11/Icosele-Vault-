from __future__ import annotations

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.ui.ai_assistant_panel import AIAssistantPanel
from app.ui.ai_snapshot_pruner import SnapshotPrunerPanel
from app.ui.archaeology_panel import ArchaeologyPanel
from app.ui.apparmor_panel import AppArmorPanel
from app.ui.audio_panel import AudioPanel
from app.ui.audit_panel import AuditPanel
from app.ui.balloon_panel import BalloonPanel
from app.ui.clipboard_panel import ClipboardPanel
from app.ui.cloud_panel import CloudPanel
from app.ui.console_panel import ConsolePanel
from app.ui.disk_perf_panel import DiskPerfPanel
from app.ui.display_panel import DisplayPanel
from app.ui.dns_filter_panel import DNSFilterPanel
from app.ui.dns_panel import DNSPanel
from app.ui.ecosystem_panel import GitHubActionsPanel, TerraformPanel
from app.ui.encryption_panel import EncryptionPanel
from app.ui.enterprise_panel import EnterprisePanel
from app.ui.fake_internet_panel import FakeInternetPanel
from app.ui.firewall_panel import FirewallPanel
from app.ui.gpu_panel import GPUPanel
from app.ui.iommu_panel import IOMMUPanel
from app.ui.webcam_panel import WebcamPanel
from app.ui.hugepages_panel import HugepagesPanel
from app.ui.instant_boot_panel import InstantBootPanel
from app.ui.ksm_panel import KSMPanel
from app.ui.netsim_panel import NetSimPanel
from app.ui.network_panel import NetworkPanel
from app.ui.plugin_panel import PluginPanel
from app.ui.quarantine_panel import QuarantinePanel
from app.ui.recording_panel import RecordingPanel
from app.ui.team_library_panel import TeamLibraryPanel
from app.ui.vm_handoff_panel import HandoffPanel
from app.ui.vm_share_panel import VMSharePanel
from app.ui.sandbox_panel import SandboxPanel
from app.ui.streaming_panel import StreamingPanel
from app.ui.webhook_panel import WebhookPanel
from app.ui.perf_graph import PerformancePanel
from app.ui.shared_folders_panel import SharedFoldersPanel
from app.ui.snapshot_dag_panel import SnapshotDAGPanel
from app.ui.snapshot_panel import SnapshotPanel
from app.ui.timeline_panel import TimelinePanel
from app.ui.spice_panel import SpicePanel
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
                 show_separator: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        self._editable = editable
        self._show_separator = show_separator
        self._step = step
        self._min_val = min_val
        self._max_val = max_val
        self._current_int: int = 0

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("""
            InfoCard {
                background-color: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(0)

        self._label = QLabel(label.upper())
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._label.setStyleSheet(
            f"color: #F47B1F; font-size: 11px; font-weight: 700;"
            f" letter-spacing: 1.5px; background: transparent;"
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

        self._secondary = QLabel("")
        self._secondary.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._secondary.setStyleSheet(
            f"color: rgba(255,255,255,0.45); font-size: 9px; background: transparent;"
            f" font-family: {FONT_FAMILY};")

        layout.addWidget(self._label)
        layout.addSpacing(2)
        layout.addLayout(value_row)
        layout.addSpacing(2)
        layout.addWidget(self._subtitle)
        layout.addSpacing(0)
        layout.addWidget(self._secondary)

        if show_separator:
            sep_row = QHBoxLayout()
            sep_row.setContentsMargins(0, 6, 0, 0)
            sep_row.addStretch(2)
            sep_line = QFrame()
            sep_line.setFixedHeight(1)
            sep_line.setStyleSheet("background-color: #2a3545; border: none;")
            sep_line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            sep_row.addWidget(sep_line, 3)
            sep_row.addStretch(2)
            layout.addLayout(sep_row)

        self.setLayout(layout)

        if not editable:
            self._btn_minus.hide()
            self._btn_plus.hide()

    def set_value(self, text: str, unit: str = "", subtitle: str = "",
                  secondary: str = "") -> None:
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
                f'<span style="font-size:28px; font-weight:900">{display_text}</span>'
                f' <span style="font-size:13px; font-weight:500; color:{TEXT_SECONDARY}">{unit}</span>')
        else:
            self._value.setText(
                f'<span style="font-size:28px; font-weight:900">{display_text}</span>')
        self._subtitle.setText(subtitle)
        self._secondary.setText(secondary)

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
        self.setObjectName("StatusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(26)
        print(f"[StatusBadge] objectName={self.objectName()!r} class={type(self).__name__}")
        self.set_status("stopped")

    def set_status(self, status: str) -> None:
        if status == "running":
            label = "RUNNING"
            bg, fg, border = "rgba(29,158,117,0.15)", "#1D9E75", "#1D9E75"
        elif status == "paused":
            label = "PAUSED"
            bg, fg, border = "rgba(249,226,175,0.15)", "#f9e2af", "rgba(249,226,175,0.40)"
        else:
            label = "STOPPED"
            bg, fg, border = "rgba(100,100,100,0.15)", "#666", "#666"
        self.setText(label)
        self.setStyleSheet(
            f"QLabel#StatusBadge {{"
            f" color: {fg};"
            f" background-color: {bg};"
            f" border: 1px solid {border};"
            f" border-radius: 10px;"
            f" font-weight: 700;"
            f" padding: 4px 16px;"
            f" font-size: 11px;"
            f" letter-spacing: 1px;"
            f" font-family: {FONT_FAMILY};"
            f"}}")
        self.setFixedHeight(26)
        self.setFixedWidth(self.fontMetrics().horizontalAdvance(label) + 40)


class OverviewTab(QWidget):
    create_requested = Signal()
    fullscreen_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        # 2x2 card grid — compact, dense
        card_w = QWidget()
        card_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid = QGridLayout(card_w)
        grid.setSpacing(8)
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

        # Action buttons — translucent frosted glass, pill-shaped
        btn_row = QWidget()
        btn_row.setStyleSheet(
            "QWidget { background: rgba(255,255,255,0.03);"
            " border-top: 1px solid rgba(255,255,255,0.06); }")
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 10, 0, 0)
        btn_row_layout.setSpacing(10)

        self.btn_new = QPushButton("+ NEW MACHINE")
        self.btn_start = QPushButton("\u25b6 START")
        self.btn_stop = QPushButton("\u25a0 STOP")
        self.btn_pause = QPushButton("\u23f8 PAUSE")

        # Frosted glass base style shared by all buttons — pill shape
        _glass_base = (
            f"border-radius: 12px; font-size: 13px; font-weight: 800;"
            f" min-height: 44px; font-family: {FONT_FAMILY};"
        )

        self.btn_new.setStyleSheet(
            f"QPushButton {{ background-color: rgba(31,184,244,0.15); color: #1FB8F4;"
            f" border: 1px solid rgba(31,184,244,0.30); {_glass_base} }}"
            f"QPushButton:hover {{ background-color: rgba(31,184,244,0.28);"
            f" border: 1px solid rgba(31,184,244,0.50); }}")
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: rgba(76,175,125,0.18); color: #a6e3a1;"
            f" border: 1px solid rgba(76,175,125,0.30); {_glass_base} }}"
            f"QPushButton:hover {{ background-color: rgba(76,175,125,0.30);"
            f" border: 1px solid rgba(76,175,125,0.45); }}")
        self.btn_stop.setStyleSheet(
            f"QPushButton {{ background-color: rgba(255,59,48,0.18); color: #f38ba8;"
            f" border: 1px solid rgba(255,59,48,0.30); {_glass_base} }}"
            f"QPushButton:hover {{ background-color: rgba(255,59,48,0.30);"
            f" border: 1px solid rgba(255,59,48,0.45); }}")
        self.btn_pause.setStyleSheet(
            f"QPushButton {{ background-color: rgba(244,123,31,0.18); color: #fab387;"
            f" border: 1px solid rgba(244,123,31,0.30); {_glass_base} }}"
            f"QPushButton:hover {{ background-color: rgba(244,123,31,0.30);"
            f" border: 1px solid rgba(244,123,31,0.45); }}")

        for btn in [self.btn_new, self.btn_start, self.btn_stop, self.btn_pause]:
            btn.setFixedHeight(48)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_new.clicked.connect(self.create_requested.emit)

        btn_row_layout.addWidget(self.btn_new)
        btn_row_layout.addWidget(self.btn_start)
        btn_row_layout.addWidget(self.btn_stop)
        btn_row_layout.addWidget(self.btn_pause)

        layout.addWidget(btn_row)



class DisplayPreviewTab(QWidget):
    """Tab showing the live VM display preview."""

    # Simple monitor icon as SVG — rectangle with a stand, no fonts/images
    _MONITOR_SVG = (
        '<svg width="64" height="56" viewBox="0 0 64 56" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="4" y="2" width="56" height="38" rx="4" fill="none" '
        'stroke="#585b70" stroke-width="2"/>'
        '<rect x="8" y="6" width="48" height="30" rx="2" fill="#1a1d1c"/>'
        '<rect x="26" y="42" width="12" height="6" fill="#585b70"/>'
        '<rect x="20" y="48" width="24" height="3" rx="1.5" fill="#585b70"/>'
        '</svg>'
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Live display image — fills the tab when active
        self._thumb_label = QLabel()
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background-color: rgba(255,255,255,0.02); border: none;")
        layout.addWidget(self._thumb_label, 1)

        # Inactive placeholder — centred icon + text, shown when VM is off
        self._placeholder = QWidget()
        self._placeholder.setStyleSheet("background: transparent;")
        ph_lay = QVBoxLayout(self._placeholder)
        ph_lay.setContentsMargins(0, 0, 0, 0)
        ph_lay.setSpacing(12)
        ph_lay.addStretch(1)

        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPixmap, QPainter as _QPainter
        renderer = QSvgRenderer(bytearray(self._MONITOR_SVG.encode()))
        icon_pix = QPixmap(64, 56)
        icon_pix.fill(QColor(0, 0, 0, 0))
        p = _QPainter(icon_pix)
        renderer.render(p)
        p.end()
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setPixmap(icon_pix)
        icon_label.setStyleSheet("background: transparent;")
        ph_lay.addWidget(icon_label)

        text_label = QLabel("Display inactive")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 18px; font-weight: 400;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        ph_lay.addWidget(text_label)

        hint_label = QLabel("Start the VM to view display output")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet(
            f"color: #45475a; font-size: 11px; background: transparent;"
            f" font-family: {FONT_FAMILY};")
        ph_lay.addWidget(hint_label)

        ph_lay.addStretch(1)
        layout.addWidget(self._placeholder, 1)

        self.set_thumbnail(None)

    def set_thumbnail(self, pixmap) -> None:
        """Update the live thumbnail preview. None = stopped/inactive."""
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                max(self._thumb_label.width(), 200),
                max(self._thumb_label.height(), 200),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._thumb_label.setPixmap(scaled)
            self._thumb_label.show()
            self._placeholder.hide()
        else:
            self._thumb_label.clear()
            self._thumb_label.hide()
            self._placeholder.show()


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
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 28, 40, 24)
        outer.setSpacing(0)

        # Header — VM name + badges
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.name_label = ClickableLabel("No VM selected")
        self.name_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 32px; font-weight: 200;"
            f" letter-spacing: -0.5px; background: transparent;"
            f" font-family: {FONT_FAMILY};")
        self.name_label.double_clicked.connect(self.edit_requested.emit)

        header.addWidget(self.name_label)
        header.addStretch()

        # Hidden branch badge (kept for signal compatibility but not shown)
        self.branch_badge = QLabel("main")
        self.branch_badge.hide()

        self.status_badge = StatusBadge()
        header.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(header)

        outer.addSpacing(4)

        self.subtitle_label = QLabel("KVM \u00b7 x86_64")
        self.subtitle_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
            f" font-family: {FONT_FAMILY};")
        outer.addWidget(self.subtitle_label)

        outer.addSpacing(10)

        # ── Main 5 tabs: Overview | Console | Snapshots | AI Assistant | cog ──
        # 32px gap between tabs achieved via generous padding
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(f"""
            QTabWidget {{ border: none; background: transparent; }}
            QTabWidget::pane {{
                border: none; margin: 0; padding: 0; background: #1e1e1e;
            }}
            QTabBar {{ border: none; background: transparent; }}
            QTabBar::tab {{
                background: transparent; color: #888888;
                border: none; border-bottom: 2px solid transparent;
                padding: 8px 16px; font-size: 13px; font-weight: 500;
                font-family: {FONT_FAMILY}; margin: 0;
            }}
            QTabBar::tab:selected {{
                background: transparent;
                color: #ffffff; font-weight: 600;
                border: none; border-bottom: 2px solid #F47B1F;
            }}
            QTabBar::tab:hover {{
                background: transparent;
                border: none; border-bottom: 2px solid rgba(244,123,31,0.3);
                color: #cccccc;
            }}
        """)

        # Create all panels (keep references for signal wiring)
        self.overview_tab = OverviewTab()
        self.display_preview_tab = DisplayPreviewTab()
        self.console_panel = ConsolePanel()
        self.perf_panel = PerformancePanel()
        self.network_panel = NetworkPanel()
        self.snapshot_panel = SnapshotPanel()
        self.usb_panel = USBPanel()
        self.gpu_panel = GPUPanel()
        self.display_panel = DisplayPanel()
        self.disk_perf_panel = DiskPerfPanel()
        self.ksm_panel = KSMPanel()
        self.balloon_panel = BalloonPanel()
        self.hugepages_panel = HugepagesPanel()
        self.instant_boot_panel = InstantBootPanel()
        self.audio_panel = AudioPanel()
        self.clipboard_panel = ClipboardPanel()
        self.shared_folders_panel = SharedFoldersPanel()
        self.spice_panel = SpicePanel()
        self.netsim_panel = NetSimPanel()
        self.dns_panel = DNSPanel()
        self.snap_dag_panel = SnapshotDAGPanel()
        self.encryption_panel = EncryptionPanel()
        self.audit_panel = AuditPanel()
        self.firewall_panel = FirewallPanel()
        self.dns_filter_panel = DNSFilterPanel()
        self.quarantine_panel = QuarantinePanel()
        self.apparmor_panel = AppArmorPanel()
        self.timeline_panel = TimelinePanel()
        self.ai_assistant = AIAssistantPanel()
        self.ai_pruner = SnapshotPrunerPanel()
        self.iommu_panel = IOMMUPanel()
        self.webcam_panel = WebcamPanel()
        self.sandbox_panel = SandboxPanel()
        self.fake_internet_panel = FakeInternetPanel()
        self.archaeology_panel = ArchaeologyPanel()
        self.streaming_panel = StreamingPanel()
        self.webhook_panel = WebhookPanel()
        self.plugin_panel = PluginPanel()
        self.gh_actions_panel = GitHubActionsPanel()
        self.terraform_panel = TerraformPanel()
        self.enterprise_panel = EnterprisePanel()
        self.vm_share_panel = VMSharePanel()
        self.handoff_panel = HandoffPanel()
        self.team_library_panel = TeamLibraryPanel()
        self.recording_panel = RecordingPanel()
        self.cloud_panel = CloudPanel()

        # Settings items list
        self._settings_items: list[tuple[str, QWidget]] = [
            ("Performance", self.perf_panel),
            ("Disk I/O", self.disk_perf_panel),
            ("Balloon", self.balloon_panel),
            ("Audio", self.audio_panel),
            ("Network", self.network_panel),
            ("Net Sim", self.netsim_panel),
            ("DNS", self.dns_panel),
            ("USB", self.usb_panel),
            ("Webcam", self.webcam_panel),
            ("GPU", self.gpu_panel),
            ("Display", self.display_panel),
            ("Firewall", self.firewall_panel),
            ("Encryption", self.encryption_panel),
            ("AppArmor", self.apparmor_panel),
            ("Cloud", self.cloud_panel),
            ("Streaming", self.streaming_panel),
            ("Developer", self.enterprise_panel),
            ("RBAC", self.enterprise_panel),
            ("Audit Log", self.audit_panel),
            ("Webhooks", self.webhook_panel),
            ("Plugins", self.plugin_panel),
        ]

        # Settings page: grid of category cards + stacked panels
        from PySide6.QtWidgets import QStackedWidget, QScrollArea
        self._settings_page = QFrame()
        self._settings_page.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        sp_outer = QVBoxLayout(self._settings_page)
        sp_outer.setContentsMargins(0, 0, 0, 0)
        sp_outer.setSpacing(0)

        self._settings_stack = QStackedWidget()

        # Page 0: the grid of cards
        grid_page = QWidget()
        grid_page.setStyleSheet(f"background-color: {BG_PANEL};")
        gp_lay = QVBoxLayout(grid_page)
        gp_lay.setContentsMargins(20, 16, 20, 16)
        gp_lay.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BG_PANEL}; }}")
        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_container)
        grid.setSpacing(20)
        _LINK = (f"QPushButton {{ background: transparent; color: #6c7086;"
                 f" border: none;"
                 f" font-size: 14px; font-weight: 500; font-family: {FONT_FAMILY};"
                 f" padding: 12px 0; }}"
                 f"QPushButton:hover {{ color: {TEXT_PRIMARY}; }}")
        for i, (name, _) in enumerate(self._settings_items):
            btn = QPushButton(name)
            btn.setStyleSheet(_LINK)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda ch, idx=i: self._open_settings_panel(idx))
            grid.addWidget(btn, i // 3, i % 3)
        scroll.setWidget(grid_container)
        gp_lay.addWidget(scroll, 1)
        self._settings_stack.addWidget(grid_page)  # index 0

        # Pages 1..N: individual settings panels with back button
        for _, panel in self._settings_items:
            wrapper = QWidget()
            wrapper.setStyleSheet(f"background-color: {BG_PANEL};")
            wl = QVBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(0)
            back = QPushButton("\u2190 Back")
            back.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY};"
                f" border: none; padding: 10px 16px; font-size: 13px;"
                f" font-family: {FONT_FAMILY}; }}"
                f"QPushButton:hover {{ color: {TEXT_PRIMARY}; }}")
            back.setCursor(Qt.CursorShape.PointingHandCursor)
            back.setFixedHeight(40)
            back.clicked.connect(lambda: self._settings_stack.setCurrentIndex(0))
            wl.addWidget(back)
            wl.addWidget(panel, 1)
            self._settings_stack.addWidget(wrapper)

        sp_outer.addWidget(self._settings_stack, 1)

        # Main tabs
        self.tabs.addTab(self.overview_tab, "Overview")
        self.tabs.addTab(self.console_panel, "Console")
        self.tabs.addTab(self.display_preview_tab, "Display")
        self.tabs.addTab(self.snap_dag_panel, "Snapshots")
        self.tabs.addTab(self.ai_assistant, "AI Assistant")
        self.tabs.addTab(self._settings_page, "\u2699")

        # Reset settings grid when entering cog tab
        self.tabs.currentChanged.connect(self._on_main_tab_changed)

        outer.addWidget(self.tabs, 1)
        self.set_buttons_for_state("stopped")

    def _on_main_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) == "\u2699":
            self._settings_stack.setCurrentIndex(0)

    def _open_settings_panel(self, idx: int) -> None:
        self._settings_stack.setCurrentIndex(idx + 1)  # +1 because grid is at index 0

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
        title_name = " ".join("VM" if w.lower() == "vm" else w.capitalize() for w in name.split()) if name else name
        self.name_label.setText(title_name)
        # Keep window title static
        w = self.window()
        if w:
            w.setWindowTitle("Icosele Vault")
        self.overview_tab.card_cpu.set_value(
            str(cpus), "vCPU" + ("s" if cpus != 1 else ""), "KVM accelerated",
            secondary="x86_64 architecture")
        self.overview_tab.card_ram.set_value(
            str(ram), "MB", "Allocated RAM",
            secondary="DDR4 virtual memory")

        if disk:
            import subprocess, json as _json
            fmt = "qcow2"
            size_sub = ""
            try:
                out = subprocess.check_output(
                    ["qemu-img", "info", "--output=json", disk],
                    timeout=5, stderr=subprocess.DEVNULL)
                info = _json.loads(out)
                fmt = info.get("format", "qcow2")
                vsize = info.get("virtual-size", 0)
                if vsize:
                    size_sub = f"{vsize / (1024**3):.1f} GB"
            except Exception:
                pass
            disk_filename = os.path.basename(disk)[:24]
            self.overview_tab.card_disk.set_value(
                fmt, "", size_sub or disk_filename,
                secondary=disk_filename if size_sub else "")
        else:
            self.overview_tab.card_disk.set_value(
                "No disk", "", "Edit VM to attach a disk")

        net_label = {"nat": "NAT", "bridge": "Bridged", "hostonly": "Host-only"}.get(net_mode, "NAT")
        self.overview_tab.card_net.set_value(
            net_label, "", "virtio-net",
            secondary=f"{net_mode or 'nat'} mode")
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
        if is_stopped:
            self.display_preview_tab.set_thumbnail(None)

        self.status_badge.set_status(status if status else "stopped")
        self.console_panel.set_status(status if status else "stopped")
        self.snapshot_panel.set_enabled(is_running or is_paused)
        self.snap_dag_panel.set_enabled(is_running or is_paused)
        self.usb_panel.set_vm_running(is_running or is_paused)
