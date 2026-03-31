from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_DEEP, BG_ELEVATED, BORDER,
    FONT_FAMILY, STOP_RED, SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
)

def export_vm(vm_config: VMConfig, output_path: str) -> None:
    """Package VM config JSON + disk into .ivault zip file."""
    from dataclasses import asdict
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('config.json', json.dumps(asdict(vm_config), indent=2))
        disk = vm_config.disk_path
        if disk and os.path.exists(disk):
            zf.write(disk, 'disk.qcow2')


def import_vm(archive_path: str) -> VMConfig:
    """Extract .ivault file, restore config and disk."""
    with zipfile.ZipFile(archive_path, 'r') as zf:
        data = json.loads(zf.read('config.json'))
        cfg = VMConfig(**{k: v for k, v in data.items()
                         if k in {f.name for f in __import__('dataclasses').fields(VMConfig)}})
        if 'disk.qcow2' in zf.namelist():
            vm_dir = Path.home() / ".icosele-vault" / "vms" / cfg.vm_id
            vm_dir.mkdir(parents=True, exist_ok=True)
            disk_dest = vm_dir / f"{cfg.vm_id}.qcow2"
            with zf.open('disk.qcow2') as src, open(disk_dest, 'wb') as dst:
                import shutil
                shutil.copyfileobj(src, dst)
            cfg.disk_path = str(disk_dest)
    return cfg


_ICOSELE_ORANGE = "#f47b1f"
_AVATAR_COLORS = ["#a6e3a1", "#89b4fa", "#cba6f7", "#f9e2af", "#fab387", "#f38ba8", "#94e2d5", "#74c7ec"]

def _name_color(name: str) -> str:
    h = sum(ord(c) for c in name)
    return _AVATAR_COLORS[h % len(_AVATAR_COLORS)]
from config.vm_config import VMConfig

STATUS_DOT_ROLE = Qt.ItemDataRole.UserRole + 1
OS_LABEL_ROLE = Qt.ItemDataRole.UserRole + 2
THUMB_ROLE = Qt.ItemDataRole.UserRole + 4
CPU_BAR_ROLE = Qt.ItemDataRole.UserRole + 5
RAM_BAR_ROLE = Qt.ItemDataRole.UserRole + 6
NET_BAR_ROLE = Qt.ItemDataRole.UserRole + 7
ENCRYPTED_ROLE = Qt.ItemDataRole.UserRole + 8


def _arch_from_binary(qemu_binary: str) -> str:
    name = qemu_binary.rsplit("/", 1)[-1]
    if "x86_64" in name:
        return "x86_64"
    if "aarch64" in name:
        return "aarch64"
    if "arm" in name:
        return "ARM"
    return "QEMU"


CROSS_ROLE = Qt.ItemDataRole.UserRole + 3  # True if mouse near cross


class VMItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hovered_row: int = -1
        self._mouse_x: int = 0
        self._pulse_phase: int = 0

    def set_hovered(self, row: int, mouse_x: int = 0) -> None:
        self._hovered_row = row
        self._mouse_x = mouse_x

    def advance_pulse(self) -> None:
        self._pulse_phase = (self._pulse_phase + 1) % 20

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = (index.row() == self._hovered_row)
        is_running = bool(index.data(STATUS_DOT_ROLE))
        name = index.data(Qt.ItemDataRole.DisplayRole) or ""

        # Card background
        card = QRectF(rect.x() + 4, rect.y() + 2, rect.width() - 8, rect.height() - 4)
        if is_selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(244, 123, 31, 20))  # rgba(244,123,31,0.08)
            painter.drawRoundedRect(card, 6, 6)
            # Orange left border accent — 3px solid
            painter.setBrush(QColor("#F47B1F"))
            painter.drawRoundedRect(QRectF(card.x(), card.y() + 3, 3, card.height() - 6), 1.5, 1.5)
        elif is_hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 8))
            painter.drawRoundedRect(card, 6, 6)

        # Lock icon for encrypted VMs
        is_encrypted = bool(index.data(ENCRYPTED_ROLE))
        lx = card.x() + 12
        if is_encrypted:
            painter.setPen(QColor(ACCENT))
            painter.setFont(QFont("Inter", 9))
            painter.drawText(QRectF(lx, card.y(), 14, card.height()),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             "\U0001f512")
            lx += 16

        # VM name — 12px, weight 400, left aligned, vertically centred
        name_w = card.right() - lx - 24
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont("Inter", 12))
        fm = painter.fontMetrics()
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, int(name_w))
        painter.drawText(QRectF(lx, card.y(), name_w, card.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # Status dot — small coloured circle
        dot_r = 4
        dot_color = "#a6e3a1" if is_running else "#f38ba8"
        dot_x = card.right() - dot_r * 2 - 10
        dot_y = card.y() + (card.height() - dot_r * 2) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(dot_color))
        painter.drawEllipse(QRectF(dot_x, dot_y, dot_r * 2, dot_r * 2))

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(40)
        return hint


class VMListPanel(QFrame):
    vm_selected = Signal(int)
    create_requested = Signal()
    ai_create_requested = Signal()
    clone_requested = Signal(int)            # index
    vm_rename_requested = Signal(int, str)   # index, new_name
    vm_delete_requested = Signal(int)        # index
    vm_imported = Signal(object)             # VMConfig

    def __init__(self, configs: list[VMConfig], parent=None) -> None:
        super().__init__(parent)
        self.configs = configs
        self._running_ids: set[str] = set()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedWidth(200)
        self.setStyleSheet(
            "background-color: #1a1a1a;"
            " border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(0)

        # Logo — crisp text, centered
        logo_widget = QWidget()
        logo_widget.setFixedHeight(70)
        logo_widget.setStyleSheet("background: transparent;")
        logo_layout = QVBoxLayout(logo_widget)
        logo_layout.setContentsMargins(16, 14, 16, 4)
        logo_layout.setSpacing(4)
        nova_label = QLabel("ICOSELE")
        nova_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        nova_label.setStyleSheet(
            f"font-size: 22px; font-weight: 900;"
            f" color: {ACCENT}; letter-spacing: 3px;"
            f" background: transparent;")
        machine_label = QLabel("VAULT")
        machine_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        machine_label.setStyleSheet(
            f"font-size: 8px; font-weight: 500;"
            f" color: {TEXT_SECONDARY}; letter-spacing: 6px;"
            f" background: transparent;")
        logo_layout.addWidget(nova_label)
        logo_layout.addWidget(machine_label)
        layout.addWidget(logo_widget)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BG_ELEVATED}; margin: 0 18px;")
        layout.addWidget(sep)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search machines...")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_DEEP};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                color: {TEXT_PRIMARY};
                font-size: 12px;
                font-family: {FONT_FAMILY};
                margin: 10px 14px 6px 14px;
            }}
            QLineEdit:focus {{ border-color: #45475a; }}
        """)
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Section
        sec = QLabel("MACHINES")
        sec.setStyleSheet(
            f"color: #4a5568; font-size: 10px; font-weight: 600;"
            f" letter-spacing: 1.5px; background: transparent;"
            f" padding: 8px 18px 2px 18px;")
        layout.addWidget(sec)

        count = len(self.configs)
        self._count_label = QLabel(f"{count} machine{'s' if count != 1 else ''}")
        self._count_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;"
            f" padding: 0 18px 8px 18px;")
        layout.addWidget(self._count_label)

        _div2 = QFrame()
        _div2.setFixedHeight(1)
        _div2.setStyleSheet("background-color: #313244; border: none; margin: 4px 14px;")
        layout.addWidget(_div2)

        self._no_results = QLabel("No results")
        self._no_results.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;"
            f" padding: 12px 18px;")
        self._no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results.hide()
        layout.addWidget(self._no_results)

        # VM list
        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(200)
        self.list_widget.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list_widget.setWordWrap(False)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._delegate = VMItemDelegate(self.list_widget)
        self.list_widget.setItemDelegate(self._delegate)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item { border: none; }
        """)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)

        # Hook mouse events for hover cross
        self.list_widget.viewport().installEventFilter(self)

        for cfg in self.configs:
            self._add_item(cfg.name, running=False,
                           os_label=_arch_from_binary(cfg.qemu_binary),
                           encrypted=getattr(cfg, 'encrypted', False))
        if self.configs:
            self.list_widget.setCurrentRow(0)

        layout.addWidget(self.list_widget)
        layout.addStretch()

        # Import/Export buttons
        ie_row = QHBoxLayout()
        ie_row.setContentsMargins(14, 0, 14, 0)
        ie_row.setSpacing(6)
        self._btn_import = QPushButton("Import")
        self._btn_import.setFixedHeight(28)
        self._btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_import.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY};"
            f" border: 1px solid {BORDER}; border-radius: 4px;"
            f" font-size: 11px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {TEXT_SECONDARY}; }}")
        self._btn_import.clicked.connect(self._on_import)
        self._btn_export = QPushButton("Export")
        self._btn_export.setFixedHeight(28)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY};"
            f" border: 1px solid {BORDER}; border-radius: 4px;"
            f" font-size: 11px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {TEXT_SECONDARY}; }}")
        self._btn_export.clicked.connect(self._on_export)
        self._btn_remote = QPushButton("Remote")
        self._btn_remote.setFixedHeight(28)
        self._btn_remote.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_remote.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY};"
            f" border: 1px solid {BORDER}; border-radius: 4px;"
            f" font-size: 11px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {TEXT_SECONDARY}; }}")
        self._btn_remote.clicked.connect(self._on_remote)
        ie_row.addWidget(self._btn_import)
        ie_row.addWidget(self._btn_export)
        ie_row.addWidget(self._btn_remote)
        ie_row.addStretch()
        layout.addLayout(ie_row)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.list_widget.viewport():
            if event.type() == QEvent.Type.MouseMove:
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                item = self.list_widget.itemAt(pos)
                if item:
                    row = self.list_widget.row(item)
                    self._delegate.set_hovered(row, pos.x())
                else:
                    self._delegate.set_hovered(-1)
                self.list_widget.viewport().update()
            elif event.type() == QEvent.Type.Leave:
                self._delegate.set_hovered(-1)
                self.list_widget.viewport().update()
            elif event.type() == QEvent.Type.MouseButtonPress:
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                item = self.list_widget.itemAt(pos)
                if item:
                    rect = self.list_widget.visualItemRect(item)
                    if pos.x() >= rect.right() - 28:
                        name = item.text()
                        idx = self._config_index_for_name(name)
                        if idx >= 0:
                            reply = QMessageBox.question(
                                self, "Delete Machine",
                                f"Delete \"{name}\"?\nThis cannot be undone.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                            if reply == QMessageBox.StandardButton.Yes:
                                self.vm_delete_requested.emit(idx)
                            return True
        return super().eventFilter(obj, event)

    def _add_item(self, name: str, running: bool = False, os_label: str = "x86_64",
                  encrypted: bool = False) -> None:
        item = QListWidgetItem(name)
        item.setData(STATUS_DOT_ROLE, running)
        item.setData(OS_LABEL_ROLE, os_label)
        item.setData(ENCRYPTED_ROLE, encrypted)
        self.list_widget.addItem(item)

    def _update_count_label(self) -> None:
        c = len(self.configs)
        self._count_label.setText(f"{c} machine{'s' if c != 1 else ''}")

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self.list_widget.item(row)
        if item is None:
            return
        name = item.text()
        for i, cfg in enumerate(self.configs):
            if cfg.name == name:
                self.vm_selected.emit(i)
                return

    def _on_search(self, text: str) -> None:
        query = text.strip().lower()
        visible = 0
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is None:
                continue
            name_match = not query or query in item.text().lower()
            tag_match = False
            if query and i < len(self.configs):
                tags = getattr(self.configs[i], 'tags', []) or []
                tag_match = any(query in t.lower() for t in tags)
            matches = name_match or tag_match
            item.setHidden(not matches)
            if matches:
                visible += 1
        self._no_results.setVisible(visible == 0 and bool(query))

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        name = item.text()
        idx = self._config_index_for_name(name)
        if idx < 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_CARD}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER}; border-radius: 4px;
                padding: 4px 0;
            }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{ background-color: {BG_ELEVATED}; }}
        """)
        rename_action = menu.addAction("\u270e  Rename")
        clone_action = menu.addAction("\u2398  Clone")
        delete_action = menu.addAction("\u2717  Delete")

        # Group submenu
        group_menu = menu.addMenu("\U0001f4c1  Group")
        no_group_action = group_menu.addAction("(No group)")
        group_actions = {}
        existing_groups = sorted({c.group for c in self.configs if c.group})
        for g in existing_groups:
            group_actions[group_menu.addAction(g)] = g
        new_group_action = group_menu.addAction("+ New Group...")

        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == clone_action:
            self.clone_requested.emit(idx)
        elif action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "Rename Machine", "New name:", text=name)
            if ok and new_name.strip() and new_name.strip() != name:
                self.vm_rename_requested.emit(idx, new_name.strip())
        elif action == delete_action:
            reply = QMessageBox.question(
                self, "Delete Machine",
                f"Are you sure you want to delete \"{name}\"?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.vm_delete_requested.emit(idx)
        elif action == no_group_action:
            self.configs[idx].group = ""
            self.configs[idx].save()
            self._rebuild_list()
        elif action == new_group_action:
            gname, ok = QInputDialog.getText(self, "New Group", "Group name:")
            if ok and gname.strip():
                self.configs[idx].group = gname.strip()
                self.configs[idx].save()
                self._rebuild_list()
        elif action in group_actions:
            self.configs[idx].group = group_actions[action]
            self.configs[idx].save()
            self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Rebuild list widget to reflect group changes."""
        current_name = None
        item = self.list_widget.currentItem()
        if item:
            current_name = item.text()
        self.list_widget.clear()
        # Sort by group then name
        grouped = sorted(enumerate(self.configs), key=lambda x: (x[1].group or "zzz", x[1].name))
        last_group = None
        for _, cfg in grouped:
            group = cfg.group or ""
            if group and group != last_group:
                header = QListWidgetItem(f"\U0001f4c1 {group}")
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setData(STATUS_DOT_ROLE, False)
                self.list_widget.addItem(header)
                last_group = group
            elif not group and last_group:
                last_group = None
            self._add_item(cfg.name, running=cfg.vm_id in self._running_ids,
                           os_label=_arch_from_binary(cfg.qemu_binary),
                           encrypted=getattr(cfg, 'encrypted', False))
        if current_name:
            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                if it and it.text() == current_name:
                    self.list_widget.setCurrentRow(i)
                    break

    def _config_index_for_name(self, name: str) -> int:
        for i, cfg in enumerate(self.configs):
            if cfg.name == name:
                return i
        return -1

    def remove_vm(self, index: int) -> None:
        if 0 <= index < len(self.configs):
            self.configs.pop(index)
            self.list_widget.takeItem(index)
            self._update_count_label()

    def add_vm(self, config: VMConfig) -> None:
        self.configs.append(config)
        self._add_item(config.name, running=False,
                       os_label=_arch_from_binary(config.qemu_binary),
                       encrypted=getattr(config, 'encrypted', False))
        self._update_count_label()
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)

    def set_vm_running(self, vm_id: str, running: bool) -> None:
        if running:
            self._running_ids.add(vm_id)
        else:
            self._running_ids.discard(vm_id)
        for i, cfg in enumerate(self.configs):
            item = self.list_widget.item(i)
            if item is not None:
                item.setData(STATUS_DOT_ROLE, cfg.vm_id in self._running_ids)
        self.list_widget.viewport().update()

    def update_thumbnail(self, vm_id: str, pixmap: QPixmap | None) -> None:
        for i, cfg in enumerate(self.configs):
            if cfg.vm_id == vm_id:
                item = self.list_widget.item(i)
                if item is not None:
                    item.setData(THUMB_ROLE, pixmap)
                break
        self.list_widget.viewport().update()

    def update_activity(self, vm_id: str, cpu: float, ram: float, net: float) -> None:
        for i, cfg in enumerate(self.configs):
            if cfg.vm_id == vm_id:
                item = self.list_widget.item(i)
                if item is not None:
                    item.setData(CPU_BAR_ROLE, cpu)
                    item.setData(RAM_BAR_ROLE, ram)
                    item.setData(NET_BAR_ROLE, net)
                break
        self.list_widget.viewport().update()

    def _on_remote(self) -> None:
        from app.ui.remote_host_dialog import RemoteHostDialog
        dlg = RemoteHostDialog(self)
        dlg.exec()

    def _on_export(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.configs):
            return
        cfg = self.configs[row]
        default_name = f"{cfg.vm_id}.ivault"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export VM", str(Path.home() / default_name),
            "Icosele Vault Archive (*.ivault);;All Files (*)")
        if not path:
            return
        try:
            export_vm(cfg, path)
            QMessageBox.information(self, "Export Complete",
                                    f"VM exported to:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import VM", str(Path.home()),
            "Icosele Vault Archive (*.ivault);;Zip Files (*.zip);;All Files (*)")
        if not path:
            return
        try:
            cfg = import_vm(path)
            cfg.save()
            self.vm_imported.emit(cfg)
            QMessageBox.information(self, "Import Complete",
                                    f"VM \"{cfg.name}\" imported successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Import Failed", str(exc))

    def pulse_animation(self) -> None:
        self._delegate.advance_pulse()
        if self._running_ids:
            self.list_widget.viewport().update()
