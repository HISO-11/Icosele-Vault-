from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    LIST_STYLE, SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING, save_btn_style, subtle_btn_style,
)


class SharedFoldersPanel(QFrame):
    config_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_id = ""
        self._ram_mb = 2048
        self._folders: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(QLabel("SHARED FOLDERS (VIRTIO-FS)", styleSheet=SECTION_LABEL_STYLE))

        desc = QLabel(
            "Share host directories with the guest using virtio-fs. "
            "Requires virtiofsd on the host and shared memory support."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        # Folder list
        self._folder_list = QListWidget()
        self._folder_list.setStyleSheet(LIST_STYLE)
        self._folder_list.setMinimumHeight(120)
        self._folder_list.setMaximumHeight(200)
        layout.addWidget(self._folder_list)

        # Add/Remove buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_add = QPushButton("+ Add Folder")
        self._btn_add.setStyleSheet(save_btn_style())
        self._btn_add.setFixedHeight(32)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_remove = QPushButton("- Remove")
        self._btn_remove.setStyleSheet(subtle_btn_style())
        self._btn_remove.setFixedHeight(32)
        self._btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Add folder form (inline)
        self._add_form = QWidget()
        self._add_form.setStyleSheet("background: transparent;")
        af_layout = QVBoxLayout(self._add_form)
        af_layout.setContentsMargins(0, 0, 0, 0)
        af_layout.setSpacing(8)

        path_row = QHBoxLayout()
        path_lbl = QLabel("Host Path")
        path_lbl.setFixedWidth(80)
        path_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("/home/user/shared")
        self._path_input.setStyleSheet(INPUT_STYLE)
        self._path_browse = QPushButton("Browse")
        self._path_browse.setFixedWidth(70)
        self._path_browse.setStyleSheet(subtle_btn_style())
        self._path_browse.setFixedHeight(30)
        self._path_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        path_row.addWidget(path_lbl)
        path_row.addWidget(self._path_input, 1)
        path_row.addWidget(self._path_browse)
        af_layout.addLayout(path_row)

        tag_row = QHBoxLayout()
        tag_lbl = QLabel("Mount Tag")
        tag_lbl.setFixedWidth(80)
        tag_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("shared")
        self._tag_input.setStyleSheet(INPUT_STYLE)
        self._readonly_check = QCheckBox("Read-only")
        self._readonly_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 12px; spacing: 6px;"
            f" background: transparent; }}")
        tag_row.addWidget(tag_lbl)
        tag_row.addWidget(self._tag_input, 1)
        tag_row.addWidget(self._readonly_check)
        af_layout.addLayout(tag_row)

        confirm_row = QHBoxLayout()
        confirm_row.addStretch()
        self._btn_confirm_add = QPushButton("Add")
        self._btn_confirm_add.setStyleSheet(save_btn_style())
        self._btn_confirm_add.setFixedHeight(28)
        self._btn_confirm_add.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_row.addWidget(self._btn_confirm_add)
        af_layout.addLayout(confirm_row)

        self._add_form.hide()
        layout.addWidget(self._add_form)

        # Mount instructions
        mount_note = QLabel("Mount inside the guest VM:")
        mount_note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f" background: transparent;")
        layout.addWidget(mount_note)

        self._mount_cmd = QLabel("mount -t virtiofs <tag> /mnt/shared")
        self._mount_cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._mount_cmd.setWordWrap(True)
        self._mount_cmd.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self._mount_cmd)

        # QEMU args preview
        layout.addWidget(QLabel("QEMU ARGS", styleSheet=SECTION_LABEL_STYLE))
        self._args_preview = QLabel()
        self._args_preview.setWordWrap(True)
        self._args_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px 12px;")
        layout.addWidget(self._args_preview)

        layout.addStretch()

        # Connections
        self._btn_add.clicked.connect(self._show_add_form)
        self._btn_remove.clicked.connect(self._on_remove)
        self._path_browse.clicked.connect(self._browse_path)
        self._btn_confirm_add.clicked.connect(self._on_confirm_add)
        self._update_ui()

    def set_config(self, folders: list[dict], vm_id: str = "", ram_mb: int = 2048) -> None:
        self._vm_id = vm_id
        self._ram_mb = ram_mb
        self._folders = list(folders)
        self._update_ui()

    def _show_add_form(self) -> None:
        self._path_input.clear()
        self._tag_input.clear()
        self._readonly_check.setChecked(False)
        self._add_form.show()

    def _browse_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Host Directory")
        if path:
            self._path_input.setText(path)
            if not self._tag_input.text():
                import os
                self._tag_input.setText(os.path.basename(path) or "shared")

    def _on_confirm_add(self) -> None:
        host_path = self._path_input.text().strip()
        mount_tag = self._tag_input.text().strip()
        if not host_path or not mount_tag:
            return
        self._folders.append({
            "host_path": host_path,
            "mount_tag": mount_tag,
            "readonly": self._readonly_check.isChecked(),
        })
        self._add_form.hide()
        self._update_ui()
        self.config_changed.emit(self._folders)

    def _on_remove(self) -> None:
        row = self._folder_list.currentRow()
        if 0 <= row < len(self._folders):
            self._folders.pop(row)
            self._update_ui()
            self.config_changed.emit(self._folders)

    def _update_ui(self) -> None:
        self._folder_list.clear()
        for f in self._folders:
            ro = " (read-only)" if f.get("readonly") else ""
            text = f"{f['host_path']}  ->  {f['mount_tag']}{ro}"
            self._folder_list.addItem(QListWidgetItem(text))

        if self._folders:
            first_tag = self._folders[0]["mount_tag"]
            self._mount_cmd.setText(f"mount -t virtiofs {first_tag} /mnt/shared")
        else:
            self._mount_cmd.setText("mount -t virtiofs <tag> /mnt/shared")

        if not self._folders:
            self._args_preview.setText("(no shared folders configured)")
            return

        lines = []
        vm_id = self._vm_id or "<vm>"
        for i, f in enumerate(self._folders):
            sock = f"/tmp/icosele-vault/{vm_id}/virtiofs{i}.sock"
            lines.append(
                f"-chardev socket,id=char{i},path={sock}")
            lines.append(
                f"-device vhost-user-fs-pci,queue-size=1024,"
                f"chardev=char{i},tag={f['mount_tag']}")
        lines.append(
            f"-object memory-backend-file,id=mem,"
            f"size={self._ram_mb}M,mem-path=/dev/hugepages,share=on")
        lines.append("-numa node,memdev=mem")
        self._args_preview.setText("\n".join(lines))
