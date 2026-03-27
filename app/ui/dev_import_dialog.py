"""Tasks 1 & 2 — Git repo detection + devcontainer.json import dialog."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, FONT_FAMILY, INPUT_STYLE,
    LABEL_STYLE, SECTION_LABEL_STYLE, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING,
    primary_btn_style, secondary_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

# Indicator files → template configs
_INDICATORS: list[tuple[list[str], str, int, int]] = [
    # (files, stack_name, ram_mb, cpu_cores)
    (["package.json"], "Node.js", 4096, 2),
    (["requirements.txt", "pyproject.toml"], "Python", 4096, 2),
    (["Cargo.toml"], "Rust", 8192, 4),
    (["go.mod"], "Go", 4096, 2),
    (["pom.xml", "build.gradle"], "Java", 8192, 4),
    (["docker-compose.yml", "docker-compose.yaml"], "Docker Compose", 16384, 4),
    (["Dockerfile"], "Docker", 8192, 4),
    ([".ruby-version", "Gemfile"], "Ruby", 4096, 2),
]


def scan_repo(repo_path: str) -> dict:
    """Scan a directory for developer indicator files.

    Returns {stacks: [...], ram_mb, cpu_cores, name, repo_path}.
    """
    p = Path(repo_path)
    if not p.is_dir():
        return {}
    stacks: list[str] = []
    ram = 2048
    cpus = 2
    for files, stack, s_ram, s_cpus in _INDICATORS:
        for f in files:
            if (p / f).exists():
                stacks.append(stack)
                ram = max(ram, s_ram)
                cpus = max(cpus, s_cpus)
                break
    name = p.name or "dev-vm"
    return {
        "stacks": stacks,
        "ram_mb": ram,
        "cpu_cores": cpus,
        "name": f"{name}-dev",
        "repo_path": str(p),
    }


def parse_devcontainer(repo_path: str) -> dict | None:
    """Parse .devcontainer/devcontainer.json if it exists."""
    for candidate in [
        Path(repo_path) / ".devcontainer" / "devcontainer.json",
        Path(repo_path) / ".devcontainer.json",
    ]:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text())
                result: dict = {}
                if "image" in data:
                    result["image"] = data["image"]
                if "forwardPorts" in data:
                    result["forward_ports"] = [
                        int(p) for p in data["forwardPorts"] if isinstance(p, (int, str))]
                if "postCreateCommand" in data:
                    cmd = data["postCreateCommand"]
                    result["post_create_command"] = cmd if isinstance(cmd, str) else " && ".join(cmd)
                if "customizations" in data:
                    exts = []
                    vscode = data["customizations"].get("vscode", {})
                    exts = vscode.get("extensions", [])
                    result["extensions"] = exts
                elif "extensions" in data:
                    result["extensions"] = data["extensions"]
                if "mounts" in data:
                    mounts = []
                    for m in data["mounts"]:
                        if isinstance(m, str):
                            parts = m.split(",")
                            src = tgt = ""
                            for part in parts:
                                if part.startswith("source="):
                                    src = part.split("=", 1)[1]
                                elif part.startswith("target="):
                                    tgt = part.split("=", 1)[1]
                            if src and tgt:
                                mounts.append({"host_path": src, "mount_tag": Path(tgt).name,
                                               "readonly": "readonly" in m})
                        elif isinstance(m, dict):
                            mounts.append({
                                "host_path": m.get("source", ""),
                                "mount_tag": Path(m.get("target", "share")).name,
                                "readonly": m.get("readOnly", False),
                            })
                    result["mounts"] = mounts
                return result
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                log.warning("Failed to parse devcontainer.json: %s", exc)
    return None


class DevImportDialog(QDialog):
    """Dialog shown after scanning a git repo — lets user review and adjust."""

    def __init__(self, scan_result: dict, devcontainer: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.scan = scan_result
        self.devc = devcontainer or {}
        self.accepted_config: dict | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Import from Git Repository")
        self.setFixedSize(520, 600)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        title = QLabel("Detected Developer Stack")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
            f" background: transparent; font-family: {FONT_FAMILY};")
        root.addWidget(title)

        repo = self.scan.get("repo_path", "")
        root.addWidget(QLabel(f"Repository: {repo}",
                               styleSheet=f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;"))

        # Stacks detected
        stacks = self.scan.get("stacks", [])
        if stacks:
            pill_row = QHBoxLayout()
            pill_row.setSpacing(6)
            for s in stacks:
                pill = QLabel(f"  {s}  ")
                pill.setStyleSheet(
                    f"background-color: #1a3328; color: {ACCENT}; border: 1px solid {ACCENT};"
                    f" border-radius: 10px; font-size: 11px; font-weight: 700;"
                    f" padding: 2px 8px; font-family: {FONT_FAMILY};")
                pill_row.addWidget(pill)
            pill_row.addStretch()
            root.addLayout(pill_row)
        else:
            root.addWidget(QLabel("No specific stack detected — using default config.",
                                   styleSheet=f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"))

        root.addSpacing(8)

        # Editable config form
        root.addWidget(QLabel("PROPOSED CONFIGURATION", styleSheet=SECTION_LABEL_STYLE))
        form = QFormLayout()
        form.setSpacing(8)

        self._name_input = QLineEdit(self.scan.get("name", "dev-vm"))
        self._name_input.setStyleSheet(INPUT_STYLE)

        self._ram_input = QSpinBox()
        self._ram_input.setRange(512, 131072)
        self._ram_input.setValue(self.scan.get("ram_mb", 4096))
        self._ram_input.setSuffix(" MB")
        self._ram_input.setSingleStep(1024)
        self._ram_input.setStyleSheet(INPUT_STYLE)

        self._cpu_input = QSpinBox()
        self._cpu_input.setRange(1, 32)
        self._cpu_input.setValue(self.scan.get("cpu_cores", 2))
        self._cpu_input.setStyleSheet(INPUT_STYLE)

        for lbl, w in [("Name", self._name_input), ("RAM", self._ram_input),
                        ("CPU Cores", self._cpu_input)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE)
            form.addRow(l, w)
        root.addLayout(form)

        # Repo path note
        root.addWidget(QLabel(
            f"The repo folder will be auto-mounted as a virtio-fs shared folder.",
            styleSheet=f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic; background: transparent;"))

        # devcontainer.json summary (Task 2)
        if self.devc:
            root.addSpacing(8)
            root.addWidget(QLabel("DEVCONTAINER.JSON", styleSheet=SECTION_LABEL_STYLE))

            dc_card = QWidget()
            dc_card.setStyleSheet(
                f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
            dc_lay = QVBoxLayout(dc_card)
            dc_lay.setContentsMargins(12, 10, 12, 10)
            dc_lay.setSpacing(4)
            _ds = f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;"
            _vs = f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;"

            if "image" in self.devc:
                dc_lay.addWidget(QLabel(f"Image: {self.devc['image']} (note — QEMU boots from disk, not Docker)",
                                         styleSheet=_ds))
            if "forward_ports" in self.devc:
                ports_str = ", ".join(str(p) for p in self.devc["forward_ports"])
                dc_lay.addWidget(QLabel(f"Port forwards: {ports_str}", styleSheet=_vs))
            if "post_create_command" in self.devc:
                dc_lay.addWidget(QLabel(f"Post-create: {self.devc['post_create_command'][:120]}",
                                         styleSheet=_ds))
            if "extensions" in self.devc and self.devc["extensions"]:
                ext_str = ", ".join(self.devc["extensions"][:8])
                if len(self.devc["extensions"]) > 8:
                    ext_str += f" (+{len(self.devc['extensions']) - 8} more)"
                dc_lay.addWidget(QLabel(f"VSCode extensions: {ext_str}", styleSheet=_ds))
            if "mounts" in self.devc and self.devc["mounts"]:
                for mt in self.devc["mounts"][:4]:
                    dc_lay.addWidget(QLabel(
                        f"Mount: {mt.get('host_path', '?')} -> {mt.get('mount_tag', '?')}",
                        styleSheet=_ds))
            root.addWidget(dc_card)

        root.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(secondary_btn_style())
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_accept = QPushButton("Create VM")
        btn_accept.setStyleSheet(primary_btn_style())
        btn_accept.setFixedHeight(34)
        btn_accept.setMinimumWidth(100)
        btn_accept.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_accept.clicked.connect(self._on_accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(8)
        btn_row.addWidget(btn_accept)
        root.addLayout(btn_row)

    def _on_accept(self) -> None:
        self.accepted_config = {
            "name": self._name_input.text().strip() or "dev-vm",
            "ram_mb": self._ram_input.value(),
            "cpu_cores": self._cpu_input.value(),
            "repo_path": self.scan.get("repo_path", ""),
            "devcontainer_config": self.devc,
            "port_forwards": self.devc.get("forward_ports", []),
            "shared_folders": [],
        }
        # Add repo as shared folder
        rp = self.scan.get("repo_path", "")
        if rp:
            self.accepted_config["shared_folders"].append({
                "host_path": rp,
                "mount_tag": Path(rp).name or "repo",
                "readonly": False,
            })
        # Add devcontainer mounts
        if self.devc.get("mounts"):
            for m in self.devc["mounts"]:
                self.accepted_config["shared_folders"].append(m)
        self.accept()
