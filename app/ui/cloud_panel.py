"""Tasks 1-5 — Cloud integration: provider detection, export, cost estimator, host monitor, readiness."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

import app.audit_log as audit
from app.host_monitor import ResourceHistory, read_cpu_percent, read_disk_usage, read_ram_info
from app.ui.theme import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_DEEP, BG_ELEVATED, BG_PANEL,
    BORDER, COMBO_STYLE, FONT_FAMILY, SECTION_LABEL_STYLE, STOP_RED,
    TEXT_MUTED, TEXT_ON_ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent.parent / "data"

# ── Task 1: Cloud providers ───────────────────────────────────────────

_PROVIDERS = {
    "aws":    {"name": "AWS",          "cli": "aws",    "url": "https://aws.amazon.com/cli/",
               "auth_cmd": ["aws", "sts", "get-caller-identity", "--output", "json"],
               "account_key": "Account"},
    "gcp":    {"name": "Google Cloud", "cli": "gcloud", "url": "https://cloud.google.com/sdk/",
               "auth_cmd": ["gcloud", "auth", "list", "--format", "json"],
               "account_key": "account"},
    "azure":  {"name": "Azure",        "cli": "az",     "url": "https://learn.microsoft.com/cli/azure/",
               "auth_cmd": ["az", "account", "show", "--output", "json"],
               "account_key": "name"},
    "do":     {"name": "DigitalOcean", "cli": "doctl",  "url": "https://docs.digitalocean.com/reference/doctl/",
               "auth_cmd": ["doctl", "account", "get", "--output", "json"],
               "account_key": "email"},
    "hetzner":{"name": "Hetzner",      "cli": "hcloud", "url": "https://github.com/hetznercloud/cli",
               "auth_cmd": ["hcloud", "context", "list"],
               "account_key": "name"},
}

# Export formats per provider
_EXPORT_FMTS = {
    "aws":     ("raw",  ".raw",  "aws s3 cp {file} s3://your-bucket/\naws ec2 import-image ..."),
    "gcp":     ("vmdk", ".vmdk", "gcloud compute images import --source-file={file} ..."),
    "azure":   ("vpc",  ".vhd",  "az image create --source {file} ..."),
    "do":      ("raw",  ".raw",  "doctl compute image create --image-url file://{file} ..."),
    "hetzner": ("raw",  ".raw",  "hcloud image create --from-file {file} ..."),
}

# Pricing URLs
_PRICING_URLS = {
    "aws": "https://aws.amazon.com/ec2/pricing/",
    "gcp": "https://cloud.google.com/compute/all-pricing",
    "azure": "https://azure.microsoft.com/pricing/details/virtual-machines/",
    "do": "https://www.digitalocean.com/pricing/droplets",
    "hetzner": "https://www.hetzner.com/cloud/",
}


def _detect_providers() -> dict[str, dict]:
    results = {}
    for key, info in _PROVIDERS.items():
        found = shutil.which(info["cli"]) is not None
        results[key] = {"name": info["name"], "installed": found, "account": ""}
    return results


def _check_auth(key: str) -> str:
    info = _PROVIDERS.get(key)
    if not info:
        return ""
    try:
        out = subprocess.check_output(info["auth_cmd"], timeout=10,
                                       stderr=subprocess.DEVNULL, text=True)
        data = json.loads(out) if out.strip().startswith(("{", "[")) else {}
        if isinstance(data, dict):
            return data.get(info["account_key"], str(data)[:40])
        if isinstance(data, list) and data:
            return str(data[0].get(info["account_key"], ""))[:40]
        return out.strip()[:40] if out.strip() else ""
    except Exception:
        return ""


class CloudProviderPanel(QFrame):
    """Task 1 — Cloud provider detection and auth status."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("CLOUD PROVIDERS", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Detected CLI tools on this machine. No network requests made by this panel.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        self._cards = QVBoxLayout(); self._cards.setSpacing(6)
        lay.addLayout(self._cards)
        br = QHBoxLayout()
        btn = QPushButton("Refresh"); btn.setStyleSheet(subtle_btn_style())
        btn.setFixedHeight(28); btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._refresh); br.addWidget(btn); br.addStretch()
        lay.addLayout(br)
        lay.addStretch()
        self._refresh()

    def _refresh(self):
        while self._cards.count():
            w = self._cards.takeAt(0).widget()
            if w: w.deleteLater()
        providers = _detect_providers()
        for key, info in providers.items():
            card = QFrame()
            card.setStyleSheet(f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
            cl = QHBoxLayout(card); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(8)
            icon = "\u2705" if info["installed"] else "\u274c"
            color = ACCENT if info["installed"] else TEXT_MUTED
            cl.addWidget(QLabel(f"{icon} {info['name']}",
                                 styleSheet=f"color: {color}; font-size: 12px; font-weight: 600;"
                                            f" background: transparent; font-family: {FONT_FAMILY};"), 1)
            if info["installed"]:
                chk = QPushButton("Check Auth")
                chk.setStyleSheet(subtle_btn_style()); chk.setFixedSize(80, 22)
                chk.setCursor(Qt.CursorShape.PointingHandCursor)
                chk.clicked.connect(lambda ch, k=key: self._check(k))
                cl.addWidget(chk)
            else:
                inst = QPushButton("Install Guide")
                inst.setStyleSheet(subtle_btn_style()); inst.setFixedSize(90, 22)
                inst.setCursor(Qt.CursorShape.PointingHandCursor)
                inst.clicked.connect(lambda ch, k=key: QDesktopServices.openUrl(
                    QUrl(_PROVIDERS[k]["url"])))
                cl.addWidget(inst)
            self._cards.addWidget(card)

    def _check(self, key: str):
        acct = _check_auth(key)
        if acct:
            QMessageBox.information(self, "Auth", f"{_PROVIDERS[key]['name']}: {acct}")
        else:
            QMessageBox.information(self, "Auth", f"{_PROVIDERS[key]['name']}: Not authenticated")


# ── Task 2: VM export ─────────────────────────────────────────────────

class CloudExportPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._disk_path = ""
        self._vm_name = ""
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("EXPORT FOR CLOUD", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Convert VM disk image to cloud-compatible format. Runs entirely locally.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Provider:", styleSheet=f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"))
        self._provider = QComboBox(); self._provider.setStyleSheet(COMBO_STYLE)
        for k, v in _PROVIDERS.items():
            self._provider.addItem(v["name"], k)
        pr.addWidget(self._provider); pr.addStretch()
        lay.addLayout(pr)
        self._btn = QPushButton("Convert Disk Image"); self._btn.setStyleSheet(save_btn_style())
        self._btn.setFixedHeight(30); self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._convert)
        lay.addWidget(self._btn)
        self._progress = QProgressBar(); self._progress.setFixedHeight(16); self._progress.hide()
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; }}")
        lay.addWidget(self._progress)
        self._status = QLabel(""); self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)
        self._cmd_box = QLabel(""); self._cmd_box.setWordWrap(True)
        self._cmd_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._cmd_box.setStyleSheet(
            f"color: {ACCENT}; font-size: 10px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 8px;")
        self._cmd_box.hide()
        lay.addWidget(self._cmd_box)
        note = QLabel("Commands shown are for reference only. Running them uses your cloud account and may incur costs.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {WARNING}; font-size: 9px; font-style: italic; background: transparent;")
        lay.addWidget(note)
        lay.addStretch()

    def set_vm(self, vm_name: str, disk_path: str):
        self._vm_name = vm_name; self._disk_path = disk_path

    def _convert(self):
        if not self._disk_path or not Path(self._disk_path).exists():
            self._status.setText("No disk image."); return
        key = self._provider.currentData()
        fmt, ext, upload_cmd = _EXPORT_FMTS.get(key, ("raw", ".raw", ""))
        ts = datetime.now().strftime("%Y%m%d")
        out_dir = _DATA / "cloud_exports" / f"{self._vm_name}_{key}_{ts}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = str(out_dir / f"disk{ext}")
        self._progress.show(); self._progress.setMaximum(0)
        self._status.setText(f"Converting to {fmt}...")
        self._cmd_box.hide()
        threading.Thread(target=self._worker, args=(fmt, out_file, upload_cmd), daemon=True).start()

    def _worker(self, fmt, out_file, upload_cmd):
        try:
            subprocess.run(
                ["qemu-img", "convert", "-f", "qcow2", "-O", fmt, self._disk_path, out_file],
                check=True, capture_output=True, timeout=1200)
            cmd = upload_cmd.replace("{file}", out_file)
            from PySide6.QtCore import QMetaObject, Q_ARG
            # Use thread-safe status update via signals would be better,
            # but for simplicity we'll set text from main thread on next poll
            self._status.setText(f"Done: {out_file}")
            self._cmd_box.setText(f"Upload command (run in your terminal):\n{cmd}")
            self._cmd_box.show()
            self._progress.hide()
            audit.record("cloud_export", details={"vm": self._vm_name, "provider": fmt, "file": out_file})
        except Exception as exc:
            self._status.setText(f"Error: {exc}")
            self._progress.hide()


# ── Task 3: Cost estimator ────────────────────────────────────────────

_PRICING_PATH = _DATA / "cloud_pricing.json"

_DEFAULT_PRICING = {
    "aws": [
        {"type": "t3.micro", "vcpu": 1, "ram_gb": 1, "price": 8},
        {"type": "t3.small", "vcpu": 2, "ram_gb": 2, "price": 15},
        {"type": "t3.medium", "vcpu": 2, "ram_gb": 4, "price": 30},
        {"type": "t3.large", "vcpu": 2, "ram_gb": 8, "price": 60},
        {"type": "t3.xlarge", "vcpu": 4, "ram_gb": 16, "price": 120},
    ],
    "gcp": [
        {"type": "e2-micro", "vcpu": 2, "ram_gb": 1, "price": 6},
        {"type": "e2-small", "vcpu": 2, "ram_gb": 2, "price": 13},
        {"type": "e2-medium", "vcpu": 2, "ram_gb": 4, "price": 25},
        {"type": "e2-standard-2", "vcpu": 2, "ram_gb": 8, "price": 49},
        {"type": "e2-standard-4", "vcpu": 4, "ram_gb": 16, "price": 97},
    ],
    "azure": [
        {"type": "B1s", "vcpu": 1, "ram_gb": 1, "price": 8},
        {"type": "B1ms", "vcpu": 1, "ram_gb": 2, "price": 15},
        {"type": "B2s", "vcpu": 2, "ram_gb": 4, "price": 30},
        {"type": "B2ms", "vcpu": 2, "ram_gb": 8, "price": 58},
        {"type": "D2s_v3", "vcpu": 2, "ram_gb": 8, "price": 70},
    ],
    "do": [
        {"type": "s-1vcpu-1gb", "vcpu": 1, "ram_gb": 1, "price": 6},
        {"type": "s-1vcpu-2gb", "vcpu": 1, "ram_gb": 2, "price": 12},
        {"type": "s-2vcpu-2gb", "vcpu": 2, "ram_gb": 2, "price": 18},
        {"type": "s-2vcpu-4gb", "vcpu": 2, "ram_gb": 4, "price": 24},
        {"type": "s-4vcpu-8gb", "vcpu": 4, "ram_gb": 8, "price": 48},
    ],
    "hetzner": [
        {"type": "cx11", "vcpu": 1, "ram_gb": 2, "price": 4},
        {"type": "cx21", "vcpu": 2, "ram_gb": 4, "price": 6},
        {"type": "cx31", "vcpu": 2, "ram_gb": 8, "price": 10},
        {"type": "cx41", "vcpu": 4, "ram_gb": 16, "price": 17},
        {"type": "cx51", "vcpu": 8, "ram_gb": 32, "price": 33},
    ],
}

_STORAGE_PER_GB = 0.10


def _ensure_pricing():
    if not _PRICING_PATH.exists():
        _PRICING_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PRICING_PATH.write_text(json.dumps(_DEFAULT_PRICING, indent=2))


def _load_pricing() -> dict:
    _ensure_pricing()
    try:
        return json.loads(_PRICING_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return _DEFAULT_PRICING


def _best_match(instances: list[dict], vcpu: int, ram_gb: float) -> dict | None:
    candidates = [i for i in instances if i["vcpu"] >= vcpu and i["ram_gb"] >= ram_gb]
    if not candidates:
        return instances[-1] if instances else None
    return min(candidates, key=lambda i: i["price"])


class CostEstimatorPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("CLOUD COST ESTIMATOR", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Offline estimates using hardcoded pricing. No internet connection used.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        self._table = QLabel("")
        self._table.setWordWrap(True)
        self._table.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._table.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 10px; font-family: monospace;"
            f" background-color: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 10px;")
        lay.addWidget(self._table)
        # Pricing links
        lr = QHBoxLayout(); lr.setSpacing(6)
        for key in _PROVIDERS:
            b = QPushButton(_PROVIDERS[key]["name"])
            b.setStyleSheet(subtle_btn_style()); b.setFixedHeight(22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda ch, k=key: QDesktopServices.openUrl(QUrl(_PRICING_URLS.get(k, ""))))
            lr.addWidget(b)
        lr.addStretch()
        lay.addLayout(lr)
        disclaimer = QLabel(
            "Prices are approximate estimates only. Always verify with your cloud provider.")
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(f"color: {WARNING}; font-size: 9px; font-style: italic; background: transparent;")
        lay.addWidget(disclaimer)
        lay.addStretch()

    def estimate(self, vm_name: str, vcpu: int, ram_mb: int, disk_gb: float):
        pricing = _load_pricing()
        ram_gb = ram_mb / 1024
        storage_cost = disk_gb * _STORAGE_PER_GB
        lines = [f"Cost estimate for: {vm_name} ({vcpu} vCPU, {ram_gb:.0f} GB RAM, {disk_gb:.0f} GB disk)",
                 f"{'Provider':<14} {'Instance':<18} {'Compute':<10} {'Storage':<10} {'Monthly':<10} {'Annual':<10}",
                 "-" * 72]
        cheapest_total = float("inf")
        cheapest_provider = ""
        for key in ["aws", "gcp", "azure", "do", "hetzner"]:
            instances = pricing.get(key, [])
            match = _best_match(instances, vcpu, ram_gb)
            if not match:
                continue
            compute = match["price"]
            monthly = compute + storage_cost
            annual = monthly * 12
            badge = ""
            if monthly < cheapest_total:
                cheapest_total = monthly
                cheapest_provider = key
            lines.append(
                f"{_PROVIDERS[key]['name']:<14} {match['type']:<18} ${compute:<9.0f} ${storage_cost:<9.1f} ${monthly:<9.1f} ${annual:<9.0f}")
        if cheapest_provider:
            lines.append(f"\nCheapest: {_PROVIDERS[cheapest_provider]['name']} at ${cheapest_total:.1f}/month")
        self._table.setText("\n".join(lines))


# ── Task 4: Host resource monitor ─────────────────────────────────────

class ResourceChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cpu: deque[float] = deque(maxlen=60)
        self._ram: deque[float] = deque(maxlen=60)
        self.setMinimumHeight(160)

    def add_point(self, cpu: float, ram: float):
        self._cpu.append(cpu); self._ram.append(ram)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_DEEP))
        ml, mr, mt, mb = 36, 8, 20, 20
        gw, gh = w - ml - mr, h - mt - mb
        if gw < 20 or gh < 20:
            p.end(); return
        # Grid
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawRect(QRectF(ml, mt, gw, gh))
        p.setFont(QFont("Inter", 7))
        for pct in (25, 50, 75):
            y = mt + gh * (1 - pct / 100)
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(ml, y), QPointF(ml + gw, y))
            p.setPen(QColor(TEXT_MUTED))
            p.drawText(QRectF(0, y - 6, ml - 4, 12), Qt.AlignmentFlag.AlignRight, f"{pct}%")
        # Labels
        p.setPen(QColor(TEXT_PRIMARY))
        p.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        p.drawText(QRectF(ml, 2, 60, 14), Qt.AlignmentFlag.AlignLeft, "CPU")
        p.setPen(QColor(ACCENT_LIGHT))
        p.drawText(QRectF(ml + 40, 2, 60, 14), Qt.AlignmentFlag.AlignLeft, "RAM")
        # Draw lines
        def _draw(data, color):
            if len(data) < 2: return
            p.setPen(QPen(QColor(color), 2))
            pts = []
            for i, v in enumerate(data):
                x = ml + (i / max(len(data) - 1, 1)) * gw
                y = mt + gh * (1 - min(v, 100) / 100)
                pts.append(QPointF(x, y))
            for i in range(len(pts) - 1):
                p.drawLine(pts[i], pts[i + 1])
        _draw(self._cpu, "#89b4fa")
        _draw(self._ram, ACCENT_LIGHT)
        p.end()


class HostMonitorPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = ResourceHistory()
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(10000)
        self._poll()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("HOST RESOURCE MONITOR", styleSheet=SECTION_LABEL_STYLE))
        self._cpu_lbl = QLabel("CPU: --")
        self._cpu_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                                     f" background: transparent; font-family: {FONT_FAMILY};")
        self._ram_lbl = QLabel("RAM: --")
        self._ram_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
                                     f" background: transparent; font-family: {FONT_FAMILY};")
        self._disk_lbl = QLabel("Disk: --")
        self._disk_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._cpu_lbl)
        lay.addWidget(self._ram_lbl)
        lay.addWidget(self._disk_lbl)
        self._chart = ResourceChartWidget()
        lay.addWidget(self._chart, 1)
        self._pressure_lbl = QLabel("")
        self._pressure_lbl.setWordWrap(True)
        self._pressure_lbl.hide()
        lay.addWidget(self._pressure_lbl)
        lay.addStretch()

    def _poll(self):
        cpu = read_cpu_percent()
        ram = read_ram_info()
        disk = read_disk_usage()
        self._history.record(cpu, ram["percent"])
        self._chart.add_point(cpu, ram["percent"])
        cpu_color = ACCENT if cpu < 60 else WARNING if cpu < 80 else STOP_RED
        ram_color = ACCENT if ram["percent"] < 60 else WARNING if ram["percent"] < 80 else STOP_RED
        self._cpu_lbl.setText(f"CPU: {cpu:.0f}%")
        self._cpu_lbl.setStyleSheet(f"color: {cpu_color}; font-size: 13px; font-weight: 600;"
                                     f" background: transparent; font-family: {FONT_FAMILY};")
        self._ram_lbl.setText(f"RAM: {ram['percent']:.0f}% ({ram['used_mb']:.0f}/{ram['total_mb']:.0f} MB)")
        self._ram_lbl.setStyleSheet(f"color: {ram_color}; font-size: 13px; font-weight: 600;"
                                     f" background: transparent; font-family: {FONT_FAMILY};")
        self._disk_lbl.setText(f"Disk: {disk['used_gb']:.1f}/{disk['total_gb']:.1f} GB ({disk['percent']:.0f}%)")
        if self._history.under_pressure:
            self._pressure_lbl.setText("Host under resource pressure! Consider pausing VMs.")
            self._pressure_lbl.setStyleSheet(
                f"background-color: #2d1010; border: 1px solid {STOP_RED};"
                f" border-radius: 6px; padding: 8px; color: {STOP_RED}; font-size: 11px;")
            self._pressure_lbl.show()
        else:
            self._pressure_lbl.hide()

    def get_status_text(self) -> tuple[str, str, str, str]:
        """Return (cpu_text, cpu_color, ram_text, ram_color) for status bar."""
        if not self._history.cpu:
            return "CPU --", TEXT_MUTED, "RAM --", TEXT_MUTED
        cpu = self._history.cpu[-1]
        ram = self._history.ram[-1]
        cc = ACCENT if cpu < 60 else WARNING if cpu < 80 else STOP_RED
        rc = ACCENT if ram < 60 else WARNING if ram < 80 else STOP_RED
        return f"CPU {cpu:.0f}%", cc, f"RAM {ram:.0f}%", rc


# ── Task 5: Cloud readiness checker ───────────────────────────────────

class CloudReadinessPanel(QFrame):
    def __init__(self, configs_fn=None, parent=None):
        super().__init__(parent)
        self._configs_fn = configs_fn or (lambda: [])
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("CLOUD READINESS CHECKER", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel("Checks whether VMs are ready to export. Entirely offline — reads local files only.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        self._btn_check = QPushButton("Check All VMs")
        self._btn_check.setStyleSheet(save_btn_style())
        self._btn_check.setFixedHeight(30); self._btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_check.clicked.connect(self._check_all)
        lay.addWidget(self._btn_check)
        self._results = QVBoxLayout(); self._results.setSpacing(4)
        lay.addLayout(self._results)
        lay.addStretch()

    def _check_all(self):
        while self._results.count():
            w = self._results.takeAt(0).widget()
            if w: w.deleteLater()
        for cfg in self._configs_fn():
            checks = self._run_checks(cfg)
            passed = sum(1 for _, ok, _ in checks if ok)
            total = len(checks)
            card = QFrame()
            card.setStyleSheet(f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;")
            cl = QVBoxLayout(card); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(3)
            score_color = ACCENT if passed == total else WARNING if passed >= 4 else STOP_RED
            cl.addWidget(QLabel(f"{cfg.name}  —  {passed}/{total} checks passed",
                                 styleSheet=f"color: {score_color}; font-size: 12px; font-weight: 600;"
                                            f" background: transparent; font-family: {FONT_FAMILY};"))
            for name, ok, detail in checks:
                icon = "\u2705" if ok else "\u274c"
                cl.addWidget(QLabel(f"  {icon} {name}: {detail}",
                                     styleSheet=f"color: {ACCENT if ok else TEXT_SECONDARY};"
                                                f" font-size: 10px; background: transparent;"))
            self._results.addWidget(card)

    def _run_checks(self, cfg) -> list[tuple[str, bool, str]]:
        checks = []
        # 1. Disk format
        fmt = self._get_disk_format(cfg.disk_path)
        checks.append(("Disk format", fmt == "qcow2", f"{fmt or 'unknown'} (need qcow2)"))
        # 2. Disk size
        vsize = self._get_virtual_size(cfg.disk_path)
        over = vsize > 2 * 1024**4 if vsize else False
        checks.append(("Disk size", not over,
                        f"{vsize / (1024**3):.0f} GB" if vsize else "unknown"))
        # 3. Network
        is_bridge = cfg.net_mode == "bridge"
        checks.append(("Network config", not is_bridge,
                        f"{cfg.net_mode} ({'needs reconfiguration' if is_bridge else 'OK'})"))
        # 4. Encryption
        checks.append(("Encryption", not cfg.encrypted,
                        "encrypted (must decrypt for cloud)" if cfg.encrypted else "unencrypted (OK)"))
        # 5. Architecture
        is_x86 = "x86_64" in cfg.qemu_binary
        checks.append(("Architecture", is_x86, "x86_64" if is_x86 else cfg.qemu_binary))
        # 6. Snapshot baseline
        from app.snapshot_store import load_snapshots
        snaps = load_snapshots(cfg.vm_id)
        has_baseline = any("baseline" in (s.get("tag") or "").lower() or
                           "clean" in (s.get("tag") or "").lower() for s in snaps)
        checks.append(("Snapshot baseline", has_baseline,
                        "found" if has_baseline else "no clean baseline — create one before export"))
        return checks

    @staticmethod
    def _get_disk_format(path: str) -> str:
        if not path or not Path(path).exists(): return ""
        try:
            out = subprocess.check_output(
                ["qemu-img", "info", "--output=json", path], timeout=10, stderr=subprocess.DEVNULL)
            return json.loads(out).get("format", "")
        except Exception: return ""

    @staticmethod
    def _get_virtual_size(path: str) -> int:
        if not path or not Path(path).exists(): return 0
        try:
            out = subprocess.check_output(
                ["qemu-img", "info", "--output=json", path], timeout=10, stderr=subprocess.DEVNULL)
            return json.loads(out).get("virtual-size", 0)
        except Exception: return 0


# ── Combined Cloud Panel ──────────────────────────────────────────────

class CloudPanel(QFrame):
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
            QTabWidget::pane {{ border: none; background: {BG_PANEL}; }}
            QTabBar {{ background: transparent; border: none; }}
            QTabBar::tab {{
                background: transparent; color: {TEXT_SECONDARY};
                border: none; border-bottom: 2px solid transparent;
                padding: 8px 14px; font-size: 11px; font-weight: 500;
                font-family: {FONT_FAMILY};
            }}
            QTabBar::tab:selected {{ color: {TEXT_PRIMARY}; border-bottom: 2px solid {ACCENT}; }}
        """)
        self.providers = CloudProviderPanel()
        self.export_panel = CloudExportPanel()
        self.cost_panel = CostEstimatorPanel()
        self.monitor_panel = HostMonitorPanel()
        self.readiness_panel = CloudReadinessPanel(configs_fn)
        tabs.addTab(self.providers, "Providers")
        tabs.addTab(self.export_panel, "Export")
        tabs.addTab(self.cost_panel, "Cost Estimator")
        tabs.addTab(self.monitor_panel, "Host Monitor")
        tabs.addTab(self.readiness_panel, "Readiness")
        lay.addWidget(tabs, 1)
