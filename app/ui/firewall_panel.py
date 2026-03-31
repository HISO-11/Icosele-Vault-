"""Task 3 — Per-VM firewall rule builder."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    ACCENT, BG_CARD, BG_PANEL, BORDER, COMBO_STYLE, FONT_FAMILY,
    INPUT_STYLE, LABEL_STYLE, LIST_STYLE, SECTION_LABEL_STYLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    primary_btn_style, save_btn_style, secondary_btn_style, subtle_btn_style,
)

DEFAULT_RULES = [
    {"direction": "out", "protocol": "any", "port": "", "cidr": "", "action": "allow"},
    {"direction": "in", "protocol": "any", "port": "", "cidr": "",
     "action": "deny", "note": "except established"},
]


def _rule_text(r: dict) -> str:
    d = r.get("direction", "in").upper()
    p = r.get("protocol", "any")
    port = r.get("port", "") or "*"
    cidr = r.get("cidr", "") or "any"
    act = r.get("action", "deny").upper()
    note = r.get("note", "")
    s = f"{d} {p} port={port} src={cidr} -> {act}"
    if note:
        s += f" ({note})"
    return s


def generate_nft_script(vm_id: str, rules: list[dict]) -> str:
    lines = [
        "#!/usr/sbin/nft -f",
        f"table inet icosele_{vm_id} {{",
        f"  chain input {{",
        f"    type filter hook input priority 0; policy drop;",
        f"    ct state established,related accept",
    ]
    for r in rules:
        if r.get("direction") != "in":
            continue
        act = "accept" if r.get("action") == "allow" else "drop"
        proto = r.get("protocol", "any")
        port = r.get("port", "")
        cidr = r.get("cidr", "")
        parts = []
        if cidr:
            parts.append(f"ip saddr {cidr}")
        if proto not in ("any", ""):
            parts.append(proto)
            if port:
                parts.append(f"dport {port}")
        parts.append(act)
        lines.append(f"    {' '.join(parts)}")
    lines += [
        f"  }}",
        f"  chain output {{",
        f"    type filter hook output priority 0; policy accept;",
    ]
    for r in rules:
        if r.get("direction") != "out":
            continue
        act = "accept" if r.get("action") == "allow" else "drop"
        proto = r.get("protocol", "any")
        port = r.get("port", "")
        cidr = r.get("cidr", "")
        parts = []
        if cidr:
            parts.append(f"ip daddr {cidr}")
        if proto not in ("any", ""):
            parts.append(proto)
            if port:
                parts.append(f"dport {port}")
        parts.append(act)
        lines.append(f"    {' '.join(parts)}")
    lines += [f"  }}", f"}}"]
    return "\n".join(lines)


class RuleEditDialog(QDialog):
    def __init__(self, rule: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.result: dict | None = None
        self.setWindowTitle("Firewall Rule")
        self.setFixedSize(400, 300)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(8)
        self._dir = QComboBox(); self._dir.setStyleSheet(COMBO_STYLE)
        self._dir.addItem("Inbound", "in"); self._dir.addItem("Outbound", "out")
        self._proto = QComboBox(); self._proto.setStyleSheet(COMBO_STYLE)
        for p in ("any", "tcp", "udp", "icmp"):
            self._proto.addItem(p, p)
        self._port = QLineEdit(); self._port.setStyleSheet(INPUT_STYLE)
        self._port.setPlaceholderText("e.g. 80 or 8000-9000")
        self._cidr = QLineEdit(); self._cidr.setStyleSheet(INPUT_STYLE)
        self._cidr.setPlaceholderText("e.g. 10.0.0.0/8")
        self._action = QComboBox(); self._action.setStyleSheet(COMBO_STYLE)
        self._action.addItem("Allow", "allow"); self._action.addItem("Deny", "deny")
        for lbl, w in [("Direction", self._dir), ("Protocol", self._proto),
                       ("Port", self._port), ("Source/Dest", self._cidr),
                       ("Action", self._action)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE)
            form.addRow(l, w)
        lay.addLayout(form)
        if rule:
            idx = self._dir.findData(rule.get("direction", "in"))
            if idx >= 0: self._dir.setCurrentIndex(idx)
            idx2 = self._proto.findData(rule.get("protocol", "any"))
            if idx2 >= 0: self._proto.setCurrentIndex(idx2)
            self._port.setText(rule.get("port", ""))
            self._cidr.setText(rule.get("cidr", ""))
            idx3 = self._action.findData(rule.get("action", "deny"))
            if idx3 >= 0: self._action.setCurrentIndex(idx3)
        lay.addStretch()
        br = QHBoxLayout()
        bc = QPushButton("Cancel"); bc.setStyleSheet(secondary_btn_style())
        bc.setFixedHeight(30); bc.clicked.connect(self.reject)
        bs = QPushButton("Save"); bs.setStyleSheet(primary_btn_style())
        bs.setFixedHeight(30); bs.clicked.connect(self._save)
        br.addStretch(); br.addWidget(bc); br.addSpacing(8); br.addWidget(bs)
        lay.addLayout(br)

    def _save(self) -> None:
        self.result = {
            "direction": self._dir.currentData(),
            "protocol": self._proto.currentData(),
            "port": self._port.text().strip(),
            "cidr": self._cidr.text().strip(),
            "action": self._action.currentData(),
        }
        self.accept()


class FirewallPanel(QFrame):
    config_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm_id = ""
        self._rules: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(QLabel("FIREWALL RULES", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Define per-VM firewall rules. Rules are applied via nftables "
            "when the VM starts (requires root via pkexec).")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(desc)

        self._rule_list = QListWidget()
        self._rule_list.setStyleSheet(LIST_STYLE)
        self._rule_list.setMinimumHeight(140)
        layout.addWidget(self._rule_list)

        br = QHBoxLayout()
        br.setSpacing(8)
        self._btn_add = QPushButton("Add Rule")
        self._btn_add.setStyleSheet(save_btn_style()); self._btn_add.setFixedHeight(30)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setStyleSheet(subtle_btn_style()); self._btn_edit.setFixedHeight(30)
        self._btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_del = QPushButton("Delete")
        self._btn_del.setStyleSheet(subtle_btn_style()); self._btn_del.setFixedHeight(30)
        self._btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset = QPushButton("Reset to Default")
        self._btn_reset.setStyleSheet(subtle_btn_style()); self._btn_reset.setFixedHeight(30)
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_apply = QPushButton("Apply Rules")
        self._btn_apply.setStyleSheet(subtle_btn_style()); self._btn_apply.setFixedHeight(30)
        self._btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        for b in (self._btn_add, self._btn_edit, self._btn_del, self._btn_reset, self._btn_apply):
            br.addWidget(b)
        br.addStretch()
        layout.addLayout(br)

        self._no_rules_warn = QLabel("No firewall rules defined. The VM has unrestricted network access.")
        self._no_rules_warn.setWordWrap(True)
        self._no_rules_warn.setStyleSheet(
            f"background-color: #2d2010; border: 1px solid {WARNING};"
            f" border-radius: 6px; padding: 8px; color: {WARNING}; font-size: 11px;")
        layout.addWidget(self._no_rules_warn)

        # nft script preview
        layout.addWidget(QLabel("NFT SCRIPT PREVIEW", styleSheet=SECTION_LABEL_STYLE))
        self._nft_preview = QLabel("")
        self._nft_preview.setWordWrap(True)
        self._nft_preview.setStyleSheet(
            f"color: {ACCENT}; font-size: 10px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 8px;")
        layout.addWidget(self._nft_preview)
        layout.addStretch()

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_del.clicked.connect(self._on_del)
        self._btn_reset.clicked.connect(self._on_reset)
        self._btn_apply.clicked.connect(self._on_apply)

    def set_config(self, rules: list[dict], vm_id: str = "") -> None:
        self._vm_id = vm_id
        self._rules = list(rules)
        self._refresh()

    def _refresh(self) -> None:
        self._rule_list.clear()
        for r in self._rules:
            self._rule_list.addItem(QListWidgetItem(_rule_text(r)))
        self._no_rules_warn.setVisible(len(self._rules) == 0)
        self._nft_preview.setText(generate_nft_script(self._vm_id or "vm", self._rules))

    def _on_add(self) -> None:
        dlg = RuleEditDialog(parent=self)
        if dlg.exec() and dlg.result:
            self._rules.append(dlg.result)
            self._refresh()
            self.config_changed.emit(self._rules)

    def _on_edit(self) -> None:
        row = self._rule_list.currentRow()
        if row < 0 or row >= len(self._rules):
            return
        dlg = RuleEditDialog(self._rules[row], parent=self)
        if dlg.exec() and dlg.result:
            self._rules[row] = dlg.result
            self._refresh()
            self.config_changed.emit(self._rules)

    def _on_del(self) -> None:
        row = self._rule_list.currentRow()
        if 0 <= row < len(self._rules):
            self._rules.pop(row)
            self._refresh()
            self.config_changed.emit(self._rules)

    def _on_reset(self) -> None:
        self._rules = [dict(r) for r in DEFAULT_RULES]
        self._refresh()
        self.config_changed.emit(self._rules)

    def _on_apply(self) -> None:
        if not self._vm_id:
            return
        script = generate_nft_script(self._vm_id, self._rules)
        run_dir = Path(f"/tmp/icosele-vm/{self._vm_id}")
        run_dir.mkdir(parents=True, exist_ok=True)
        script_path = run_dir / "firewall.nft"
        script_path.write_text(script)
        try:
            subprocess.run(
                ["pkexec", "nft", "-f", str(script_path)],
                check=True, capture_output=True, timeout=15)
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "Firewall", f"Failed to apply rules:\n{exc}")
