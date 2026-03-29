"""Task 1 — Webhook configuration and log viewer panel."""
from __future__ import annotations

import json
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from app.webhook_manager import (
    load_delivery_log, load_webhooks, save_webhooks, send_test,
)
from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, COMBO_STYLE,
    FONT_FAMILY, INPUT_STYLE, LABEL_STYLE, LIST_STYLE,
    SECTION_LABEL_STYLE, STOP_RED, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WARNING,
    primary_btn_style, save_btn_style, secondary_btn_style, subtle_btn_style,
)

_ALL_EVENTS = [
    "vm_started", "vm_stopped", "vm_crashed", "snapshot_created",
    "snapshot_restored", "quarantine_enabled", "disk_warning",
    "ai_anomaly_detected",
]


class WebhookPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("WEBHOOKS", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("HTTP POST notifications sent to external services when events occur.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Webhook list
        self._hook_list = QVBoxLayout()
        self._hook_list.setSpacing(6)
        lay.addLayout(self._hook_list)

        br = QHBoxLayout()
        br.setSpacing(8)
        self._btn_add = QPushButton("+ Add Webhook")
        self._btn_add.setStyleSheet(save_btn_style())
        self._btn_add.setFixedHeight(30)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add.clicked.connect(self._on_add)
        br.addWidget(self._btn_add)
        self._btn_refresh = QPushButton("Refresh Log")
        self._btn_refresh.setStyleSheet(subtle_btn_style())
        self._btn_refresh.setFixedHeight(30)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.clicked.connect(self._refresh_log)
        br.addWidget(self._btn_refresh)
        br.addStretch()
        lay.addLayout(br)

        # Delivery log
        lay.addWidget(QLabel("DELIVERY LOG", styleSheet=SECTION_LABEL_STYLE))
        self._log_area = QScrollArea()
        self._log_area.setWidgetResizable(True)
        self._log_area.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {BORDER}; border-radius: 6px; background: {BG_DEEP}; }}")
        self._log_area.setMaximumHeight(200)
        self._log_widget = QWidget()
        self._log_layout = QVBoxLayout(self._log_widget)
        self._log_layout.setContentsMargins(8, 8, 8, 8)
        self._log_layout.setSpacing(2)
        self._log_layout.addStretch()
        self._log_area.setWidget(self._log_widget)
        lay.addWidget(self._log_area)
        lay.addStretch()

    def _refresh(self):
        while self._hook_list.count():
            w = self._hook_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        hooks = load_webhooks()
        if not hooks:
            lbl = QLabel("No webhooks configured.")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
            self._hook_list.addWidget(lbl)
            return
        for i, h in enumerate(hooks):
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(8)
            info = QVBoxLayout()
            info.setSpacing(2)
            name_lbl = QLabel(h.get("name", "Unnamed"))
            name_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600;"
                f" background: transparent; font-family: {FONT_FAMILY};")
            info.addWidget(name_lbl)
            url_lbl = QLabel(h.get("url", "")[:60])
            url_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px; background: transparent;")
            info.addWidget(url_lbl)
            evts = ", ".join(h.get("events", [])[:3])
            if len(h.get("events", [])) > 3:
                evts += f" +{len(h['events']) - 3}"
            evt_lbl = QLabel(evts)
            evt_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8px; background: transparent;")
            info.addWidget(evt_lbl)
            cl.addLayout(info, 1)
            # Toggle
            tog = QCheckBox("On")
            tog.setChecked(h.get("enabled", True))
            tog.setStyleSheet(f"QCheckBox {{ color: {TEXT_SECONDARY}; font-size: 10px; background: transparent; }}")
            tog.toggled.connect(lambda checked, idx=i: self._toggle(idx, checked))
            cl.addWidget(tog)
            # Test
            test_btn = QPushButton("Test")
            test_btn.setStyleSheet(subtle_btn_style())
            test_btn.setFixedSize(50, 24)
            test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            test_btn.clicked.connect(lambda checked, idx=i: self._test(idx))
            cl.addWidget(test_btn)
            # Delete
            del_btn = QPushButton("\u2715")
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {TEXT_MUTED}; border: none; font-size: 12px; }}"
                f"QPushButton:hover {{ color: {STOP_RED}; }}")
            del_btn.clicked.connect(lambda checked, idx=i: self._delete(idx))
            cl.addWidget(del_btn)
            self._hook_list.addWidget(card)
        self._refresh_log()

    def _refresh_log(self):
        while self._log_layout.count() > 1:
            w = self._log_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        entries = load_delivery_log()
        for e in reversed(entries[-20:]):
            ts = (e.get("timestamp") or "")[:19].replace("T", " ")
            ok = e.get("success", False)
            icon = "\u2705" if ok else "\u274c"
            color = ACCENT if ok else STOP_RED
            text = f"{icon} {ts}  {e.get('event', '')}  {e.get('webhook_name', '')}  [{e.get('status_code', '?')}]"
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 9px; background: transparent; font-family: monospace;")
            idx = self._log_layout.count() - 1
            self._log_layout.insertWidget(idx, lbl)

    def _toggle(self, idx, checked):
        hooks = load_webhooks()
        if 0 <= idx < len(hooks):
            hooks[idx]["enabled"] = checked
            save_webhooks(hooks)

    def _test(self, idx):
        hooks = load_webhooks()
        if 0 <= idx < len(hooks):
            h = hooks[idx]
            threading.Thread(
                target=lambda: send_test(h.get("url", ""), h.get("name", "")),
                daemon=True).start()

    def _delete(self, idx):
        hooks = load_webhooks()
        if 0 <= idx < len(hooks):
            hooks.pop(idx)
            save_webhooks(hooks)
            self._refresh()

    def _on_add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Webhook")
        dlg.setFixedSize(420, 380)
        dlg.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 16, 20, 12)
        lay.setSpacing(8)
        form = QFormLayout(); form.setSpacing(6)
        _name = QLineEdit(); _name.setStyleSheet(INPUT_STYLE); _name.setPlaceholderText("My Webhook")
        _url = QLineEdit(); _url.setStyleSheet(INPUT_STYLE); _url.setPlaceholderText("https://example.com/hook")
        for lbl, w in [("Name", _name), ("URL", _url)]:
            l = QLabel(lbl); l.setStyleSheet(LABEL_STYLE)
            form.addRow(l, w)
        lay.addLayout(form)
        lay.addWidget(QLabel("Events:", styleSheet=LABEL_STYLE))
        checks: dict[str, QCheckBox] = {}
        for ev in _ALL_EVENTS:
            cb = QCheckBox(ev)
            cb.setChecked(True)
            cb.setStyleSheet(f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 11px; background: transparent; }}")
            checks[ev] = cb
            lay.addWidget(cb)
        lay.addStretch()
        br = QHBoxLayout()
        bc = QPushButton("Cancel"); bc.setStyleSheet(secondary_btn_style()); bc.setFixedHeight(30)
        bc.clicked.connect(dlg.reject)
        bs = QPushButton("Save"); bs.setStyleSheet(primary_btn_style()); bs.setFixedHeight(30)
        br.addStretch(); br.addWidget(bc); br.addSpacing(6); br.addWidget(bs)
        lay.addLayout(br)

        def _save():
            name = _name.text().strip()
            url = _url.text().strip()
            if not name or not url:
                return
            events = [ev for ev, cb in checks.items() if cb.isChecked()]
            hooks = load_webhooks()
            hooks.append({"name": name, "url": url, "events": events, "enabled": True})
            save_webhooks(hooks)
            dlg.accept()
            self._refresh()

        bs.clicked.connect(_save)
        dlg.exec()
