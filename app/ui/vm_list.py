from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_ELEVATED, BORDER,
    FONT_FAMILY, SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from config.vm_config import VMConfig

STATUS_DOT_ROLE = Qt.ItemDataRole.UserRole + 1
OS_LABEL_ROLE = Qt.ItemDataRole.UserRole + 2


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

    def set_hovered(self, row: int, mouse_x: int = 0) -> None:
        self._hovered_row = row
        self._mouse_x = mouse_x

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = (index.row() == self._hovered_row)

        if is_selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(BG_ELEVATED))
            painter.drawRect(rect.x(), rect.y(), rect.width(), rect.height())
            painter.setBrush(QColor(ACCENT))
            painter.drawRect(rect.x(), rect.y(), 3, rect.height())

        # VM name
        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if is_selected:
            painter.setPen(QColor(TEXT_PRIMARY))
        else:
            painter.setPen(QColor(TEXT_SECONDARY))
        painter.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        name_rect = QRect(rect.x() + 16, rect.y() + 8, rect.width() - 44, 20)
        fm = painter.fontMetrics()
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # OS/arch subtitle
        os_label = index.data(OS_LABEL_ROLE) or ""
        painter.setPen(QColor(TEXT_SECONDARY if is_selected else TEXT_MUTED))
        painter.setFont(QFont("Inter", 10))
        os_rect = QRect(rect.x() + 16, rect.y() + 28, rect.width() - 44, 16)
        painter.drawText(os_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, os_label)

        # Delete cross on hover
        if is_hovered:
            cross_x = rect.right() - 24
            cross_y = rect.center().y()
            near_cross = self._mouse_x >= rect.right() - 28
            painter.setPen(QColor("#e74c3c") if near_cross else QColor(TEXT_MUTED))
            painter.setFont(QFont("Inter", 12, QFont.Weight.Bold))
            painter.drawText(QRect(cross_x - 6, cross_y - 8, 16, 16),
                             Qt.AlignmentFlag.AlignCenter, "\u2715")

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(52)
        return hint


class VMListPanel(QFrame):
    vm_selected = Signal(int)
    create_requested = Signal()
    vm_rename_requested = Signal(int, str)   # index, new_name
    vm_delete_requested = Signal(int)        # index

    def __init__(self, configs: list[VMConfig], parent=None) -> None:
        super().__init__(parent)
        self.configs = configs
        self._running_ids: set[str] = set()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedWidth(180)
        self.setStyleSheet(f"background-color: {BG_DEEP}; border: none;")

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
        nova_label = QLabel("NOVA")
        nova_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        nova_label.setStyleSheet(
            f"font-size: 24px; font-weight: 900;"
            f" color: {ACCENT}; letter-spacing: 3px;"
            f" background: transparent;")
        machine_label = QLabel("MACHINE")
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
                border-radius: 6px;
                padding: 6px 10px;
                color: {TEXT_PRIMARY};
                font-size: 11px;
                font-family: {FONT_FAMILY};
                margin: 10px 14px 6px 14px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
        """)
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Section
        sec = QLabel("MACHINES")
        sec.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 8px; font-weight: 700;"
            f" letter-spacing: 2px; background: transparent;"
            f" padding: 8px 18px 2px 18px;")
        layout.addWidget(sec)

        count = len(self.configs)
        self._count_label = QLabel(f"{count} machine{'s' if count != 1 else ''}")
        self._count_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;"
            f" padding: 0 18px 8px 18px;")
        layout.addWidget(self._count_label)

        self._no_results = QLabel("No results")
        self._no_results.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;"
            f" padding: 12px 18px;")
        self._no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results.hide()
        layout.addWidget(self._no_results)

        # VM list
        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(180)
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
            self._add_item(cfg.name, running=False, os_label=_arch_from_binary(cfg.qemu_binary))
        if self.configs:
            self.list_widget.setCurrentRow(0)

        layout.addWidget(self.list_widget)
        layout.addStretch()

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

    def _add_item(self, name: str, running: bool = False, os_label: str = "x86_64") -> None:
        item = QListWidgetItem(name)
        item.setData(STATUS_DOT_ROLE, running)
        item.setData(OS_LABEL_ROLE, os_label)
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
            matches = not query or query in item.text().lower()
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
        delete_action = menu.addAction("\u2717  Delete")

        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == rename_action:
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
        self._add_item(config.name, running=False, os_label=_arch_from_binary(config.qemu_binary))
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
