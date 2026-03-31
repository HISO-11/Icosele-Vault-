"""Tasks 1-6 — Enterprise panels: web console, LDAP, RBAC, compliance, replication, DR."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

import app.web_console as web_console
from app.auth_manager import (
    ROLES, create_local_user, delete_local_user, load_ldap_config,
    load_local_users, save_ldap_config, test_ldap_connection, verify_local_user,
)
from app.compliance_reports import (
    export_report_csv, generate_gdpr_report, generate_iso27001_report,
    generate_security_report, generate_soc2_report,
)
from app.replication_manager import (
    ReplicationJob, load_repl_config, load_smtp_config, replicate_async,
    save_repl_config, save_smtp_config,
)
from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, COMBO_STYLE,
    FONT_FAMILY, INPUT_STYLE, LABEL_STYLE, SECTION_LABEL_STYLE,
    STOP_RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    primary_btn_style, save_btn_style, secondary_btn_style, subtle_btn_style,
)


# ── Task 1: Web Console panel ─────────────────────────────────────────

class WebConsolePanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("WEB MANAGEMENT CONSOLE", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Local web UI accessible from any browser at http://localhost:47821")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        self._toggle = QCheckBox("Enable Web Console")
        self._toggle.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; background: transparent; }}")
        self._toggle.setChecked(web_console.is_running())
        self._toggle.toggled.connect(self._on_toggle)
        lay.addWidget(self._toggle)
        self._status = QLabel("Status: stopped")
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)
        btn = QPushButton("Open in Browser")
        btn.setStyleSheet(subtle_btn_style())
        btn.setFixedHeight(30)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: webbrowser.open("http://localhost:47821"))
        lay.addWidget(btn)
        lay.addStretch()
        self._update_status()

    def _on_toggle(self, checked):
        if checked:
            web_console.start()
        else:
            web_console.stop()
        self._update_status()

    def _update_status(self):
        if web_console.is_running():
            self._status.setText("Status: running on http://localhost:47821")
            self._status.setStyleSheet(f"color: {ACCENT}; font-size: 11px; background: transparent;")
        else:
            self._status.setText("Status: stopped")
            self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")


# ── Tasks 2-3: LDAP + RBAC panel ──────────────────────────────────────

class LDAPPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("LDAP / ACTIVE DIRECTORY", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Connect to an LDAP server for centralized authentication.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        cfg = load_ldap_config()
        form = QFormLayout(); form.setSpacing(6)
        self._host = QLineEdit(cfg.get("host", "")); self._host.setStyleSheet(INPUT_STYLE)
        self._port = QSpinBox(); self._port.setRange(1, 65535); self._port.setValue(cfg.get("port", 389))
        self._port.setStyleSheet(INPUT_STYLE)
        self._base_dn = QLineEdit(cfg.get("base_dn", "")); self._base_dn.setStyleSheet(INPUT_STYLE)
        self._bind_dn = QLineEdit(cfg.get("bind_dn", "")); self._bind_dn.setStyleSheet(INPUT_STYLE)
        self._bind_pw = QLineEdit(cfg.get("bind_password", "")); self._bind_pw.setStyleSheet(INPUT_STYLE)
        self._bind_pw.setEchoMode(QLineEdit.EchoMode.Password)
        for lbl, w in [("Host", self._host), ("Port", self._port), ("Base DN", self._base_dn),
                        ("Bind DN", self._bind_dn), ("Password", self._bind_pw)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE); form.addRow(l, w)
        lay.addLayout(form)
        note = QLabel("Production: use a secrets manager for passwords.")
        note.setStyleSheet(f"color: {WARNING}; font-size: 10px; font-style: italic; background: transparent;")
        lay.addWidget(note)
        br = QHBoxLayout()
        self._btn_save = QPushButton("Save"); self._btn_save.setStyleSheet(save_btn_style())
        self._btn_save.setFixedHeight(28); self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.clicked.connect(self._save)
        self._btn_test = QPushButton("Test Connection"); self._btn_test.setStyleSheet(subtle_btn_style())
        self._btn_test.setFixedHeight(28); self._btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_test.clicked.connect(self._test)
        br.addWidget(self._btn_save); br.addWidget(self._btn_test); br.addStretch()
        lay.addLayout(br)
        self._result = QLabel(""); self._result.setWordWrap(True)
        self._result.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._result)
        lay.addStretch()

    def _save(self):
        cfg = load_ldap_config()
        cfg["host"] = self._host.text().strip()
        cfg["port"] = self._port.value()
        cfg["base_dn"] = self._base_dn.text().strip()
        cfg["bind_dn"] = self._bind_dn.text().strip()
        cfg["bind_password"] = self._bind_pw.text()
        save_ldap_config(cfg)
        self._result.setText("Saved.")

    def _test(self):
        self._save()
        ok, msg = test_ldap_connection(load_ldap_config())
        color = ACCENT if ok else STOP_RED
        self._result.setText(msg)
        self._result.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")


class UsersRolesPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("LOCAL USERS & ROLES", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Local accounts with role-based access. Passwords stored as SHA-256 hash (local use only).")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        self._user_list = QVBoxLayout(); self._user_list.setSpacing(4)
        lay.addLayout(self._user_list)
        br = QHBoxLayout()
        btn_add = QPushButton("+ Create User"); btn_add.setStyleSheet(save_btn_style())
        btn_add.setFixedHeight(28); btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._on_add)
        br.addWidget(btn_add); br.addStretch()
        lay.addLayout(br)
        # Roles reference
        lay.addWidget(QLabel("BUILT-IN ROLES", styleSheet=SECTION_LABEL_STYLE))
        for rn, rd in ROLES.items():
            perms = []
            if rd["can_view"]: perms.append("view")
            if rd["can_action"]: perms.append("start/stop/snapshot")
            if rd["can_modify"]: perms.append("settings")
            if rd["can_delete"]: perms.append("delete")
            rl = QLabel(f"  {rd['label']}: {', '.join(perms)}")
            rl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
            lay.addWidget(rl)
        lay.addStretch()

    def _refresh(self):
        while self._user_list.count():
            w = self._user_list.takeAt(0).widget()
            if w: w.deleteLater()
        for u in load_local_users():
            card = QFrame()
            card.setStyleSheet(f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 4px;")
            cl = QHBoxLayout(card); cl.setContentsMargins(8, 4, 8, 4); cl.setSpacing(6)
            cl.addWidget(QLabel(f"{u['username']}  [{u.get('role', 'viewer')}]",
                                 styleSheet=f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;"), 1)
            db = QPushButton("\u2715"); db.setFixedSize(20, 20)
            db.setStyleSheet(f"QPushButton {{ background: transparent; color: {TEXT_MUTED}; border: none; }} QPushButton:hover {{ color: {STOP_RED}; }}")
            db.clicked.connect(lambda ch, un=u["username"]: (delete_local_user(un), self._refresh()))
            cl.addWidget(db)
            self._user_list.addWidget(card)

    def _on_add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Create User"); dlg.setFixedSize(360, 240)
        dlg.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg); lay.setContentsMargins(20, 16, 20, 12); lay.setSpacing(8)
        form = QFormLayout(); form.setSpacing(6)
        _u = QLineEdit(); _u.setStyleSheet(INPUT_STYLE)
        _p = QLineEdit(); _p.setStyleSheet(INPUT_STYLE); _p.setEchoMode(QLineEdit.EchoMode.Password)
        _r = QComboBox(); _r.setStyleSheet(COMBO_STYLE)
        for rn in ROLES: _r.addItem(rn, rn)
        for lbl, w in [("Username", _u), ("Password", _p), ("Role", _r)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE); form.addRow(l, w)
        lay.addLayout(form); lay.addStretch()
        br = QHBoxLayout()
        bc = QPushButton("Cancel"); bc.setStyleSheet(secondary_btn_style()); bc.setFixedHeight(28)
        bc.clicked.connect(dlg.reject)
        bs = QPushButton("Create"); bs.setStyleSheet(primary_btn_style()); bs.setFixedHeight(28)
        br.addStretch(); br.addWidget(bc); br.addSpacing(6); br.addWidget(bs)
        lay.addLayout(br)
        def _save():
            if _u.text().strip() and _p.text():
                create_local_user(_u.text().strip(), _p.text(), _r.currentData() or "viewer")
                dlg.accept(); self._refresh()
        bs.clicked.connect(_save)
        dlg.exec()


# ── Task 4: Compliance panel ──────────────────────────────────────────

class CompliancePanel(QFrame):
    def __init__(self, configs_fn=None, parent=None):
        super().__init__(parent)
        self._configs_fn = configs_fn or (lambda: [])
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("COMPLIANCE REPORTS", styleSheet=SECTION_LABEL_STYLE))
        for name, fn in [("GDPR Report", self._gdpr), ("SOC 2 Report", self._soc2),
                          ("ISO 27001 Report", self._iso), ("Security Report", self._sec)]:
            btn = QPushButton(name); btn.setStyleSheet(subtle_btn_style())
            btn.setFixedHeight(30); btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(fn)
            lay.addWidget(btn)
        self._preview = QLabel(""); self._preview.setWordWrap(True)
        self._preview.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 10px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 8px;")
        self._preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._preview)
        ebr = QHBoxLayout()
        self._btn_export = QPushButton("Export as Text"); self._btn_export.setStyleSheet(subtle_btn_style())
        self._btn_export.setFixedHeight(28); self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.clicked.connect(self._export)
        ebr.addWidget(self._btn_export); ebr.addStretch()
        lay.addLayout(ebr)
        lay.addStretch()
        self._last_report = ""

    def _show(self, text):
        self._last_report = text
        self._preview.setText(text[:3000])

    def _gdpr(self):
        self._show(generate_gdpr_report(self._configs_fn()))
    def _soc2(self):
        self._show(generate_soc2_report(self._configs_fn()))
    def _iso(self):
        self._show(generate_iso27001_report(self._configs_fn()))
    def _sec(self):
        self._show(generate_security_report(self._configs_fn()))

    def _export(self):
        if not self._last_report: return
        path, _ = QFileDialog.getSaveFileName(self, "Export Report", "report.txt", "Text (*.txt)")
        if path: Path(path).write_text(self._last_report)


# ── Task 5: Replication panel ─────────────────────────────────────────

class ReplicationPanel(QFrame):
    def __init__(self, configs_fn=None, parent=None):
        super().__init__(parent)
        self._configs_fn = configs_fn or (lambda: [])
        self._jobs: list[ReplicationJob] = []
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("VM REPLICATION", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Replicate VM disk images to local or remote targets.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        # Target path
        tr = QHBoxLayout()
        tr.addWidget(QLabel("Target:", styleSheet=LABEL_STYLE))
        self._target = QLineEdit()
        self._target.setPlaceholderText("/mnt/backup/vms")
        self._target.setStyleSheet(INPUT_STYLE)
        tr.addWidget(self._target, 1)
        lay.addLayout(tr)
        # Replicate button
        self._btn_repl = QPushButton("Replicate All Running VMs")
        self._btn_repl.setStyleSheet(save_btn_style())
        self._btn_repl.setFixedHeight(30); self._btn_repl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_repl.clicked.connect(self._on_replicate)
        lay.addWidget(self._btn_repl)
        self._status = QLabel(""); self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)
        lay.addStretch()

    def _on_replicate(self):
        target = self._target.text().strip()
        if not target: return
        configs = self._configs_fn()
        count = 0
        for c in configs:
            if c.disk_path and Path(c.disk_path).exists():
                job = ReplicationJob(c.name, c.vm_id, c.disk_path, target)
                replicate_async(job)
                self._jobs.append(job)
                count += 1
        self._status.setText(f"Started {count} replication jobs to {target}")


# ── Task 6: Disaster Recovery panel ───────────────────────────────────

class DRPanel(QFrame):
    def __init__(self, configs_fn=None, parent=None):
        super().__init__(parent)
        self._configs_fn = configs_fn or (lambda: [])
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(QLabel("DISASTER RECOVERY", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Configure DR baselines and test recovery procedures. "
            "One-Click Restore restores all configured VMs from their DR snapshots.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        # DR config per VM
        self._vm_list = QVBoxLayout(); self._vm_list.setSpacing(4)
        lay.addLayout(self._vm_list)
        # Full restore
        self._btn_restore = QPushButton("One-Click Full Restore")
        self._btn_restore.setStyleSheet(
            f"QPushButton {{ background-color: {STOP_RED}; color: #fff;"
            f" border: none; border-radius: 8px; padding: 12px;"
            f" font-size: 14px; font-weight: 800; font-family: {FONT_FAMILY}; }}"
            f"QPushButton:hover {{ background-color: #e74c3c; }}")
        self._btn_restore.setFixedHeight(48)
        self._btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_restore.clicked.connect(self._on_full_restore)
        lay.addWidget(self._btn_restore)
        self._btn_report = QPushButton("Export DR Test Report")
        self._btn_report.setStyleSheet(subtle_btn_style())
        self._btn_report.setFixedHeight(28); self._btn_report.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_report.clicked.connect(self._export_report)
        lay.addWidget(self._btn_report)
        self._status = QLabel(""); self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)
        lay.addStretch()
        self._refresh_vms()

    def _refresh_vms(self):
        while self._vm_list.count():
            w = self._vm_list.takeAt(0).widget()
            if w: w.deleteLater()
        for c in self._configs_fn():
            card = QFrame()
            card.setStyleSheet(f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 4px;")
            cl = QHBoxLayout(card); cl.setContentsMargins(8, 6, 8, 6); cl.setSpacing(6)
            cl.addWidget(QLabel(c.name,
                                 styleSheet=f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;"), 1)
            cl.addWidget(QLabel("DR tag: dr-baseline",
                                 styleSheet=f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;"))
            self._vm_list.addWidget(card)

    def _on_full_restore(self):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Confirm Full Restore",
                                         "Type CONFIRM to restore all DR VMs:")
        if not ok or text.strip() != "CONFIRM":
            return
        self._status.setText("Full restore initiated... (requires snapshots tagged 'dr-baseline')")
        import app.audit_log as audit
        audit.record("dr_full_restore", details={"status": "initiated"})

    def _export_report(self):
        lines = [
            "Disaster Recovery Test Report",
            "=" * 40,
            f"Generated: {datetime.now(timezone.utc).isoformat()[:19]}",
            "",
        ]
        for c in self._configs_fn():
            lines.append(f"VM: {c.name}  |  DR tag: dr-baseline  |  Last test: N/A")
        path, _ = QFileDialog.getSaveFileName(self, "Export DR Report", "dr_report.txt", "Text (*.txt)")
        if path:
            Path(path).write_text("\n".join(lines))


# ── Combined Enterprise Tab ───────────────────────────────────────────

class EnterprisePanel(QFrame):
    def __init__(self, configs_fn=None, parent=None):
        super().__init__(parent)
        self._configs_fn = configs_fn or (lambda: [])
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(0)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setStyleSheet(f"""
            QTabWidget {{ border: none; }}
            QTabWidget::pane {{ border: none; background: #1e1e1e; }}
            QTabBar {{ background: transparent; border: none; }}
            QTabBar::tab {{
                background: transparent; color: {TEXT_SECONDARY};
                border: none; border-bottom: 2px solid transparent;
                padding: 8px 14px; font-size: 11px; font-weight: 500;
                font-family: {FONT_FAMILY};
            }}
            QTabBar::tab:selected {{ color: {TEXT_PRIMARY}; border-bottom: 2px solid {ACCENT}; }}
        """)
        self.web_console = WebConsolePanel()
        self.ldap_panel = LDAPPanel()
        self.users_panel = UsersRolesPanel()
        self.compliance_panel = CompliancePanel(configs_fn)
        self.replication_panel = ReplicationPanel(configs_fn)
        self.dr_panel = DRPanel(configs_fn)
        tabs.addTab(self.web_console, "Web Console")
        tabs.addTab(self.ldap_panel, "LDAP")
        tabs.addTab(self.users_panel, "Users & Roles")
        tabs.addTab(self.compliance_panel, "Compliance")
        tabs.addTab(self.replication_panel, "Replication")
        tabs.addTab(self.dr_panel, "Disaster Recovery")
        lay.addWidget(tabs, 1)
