"""Task 5 — Anomalous network detection monitor."""
from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict, deque

from PySide6.QtCore import QObject, QTimer, Signal

from app.ollama_client import check_available, query, extract_json

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a network security monitor for a VM named {vm_name}. Here "
    "are the last 20 network readings taken every 30 seconds — each has "
    "bytes_sent, bytes_recv, packets_sent, packets_recv: {readings_json}. "
    "Is there anything anomalous in this pattern? Look for: sudden spikes "
    "in outbound data, unusual packet rates, sustained high outbound "
    "traffic. Respond with JSON only: "
    '{"anomaly_detected": true|false, "severity": "none|low|medium|high", '
    '"description": "one sentence or null", "recommend_quarantine": true|false}.'
)

_OUTBOUND_THRESHOLD = 50 * 1024 * 1024  # 50MB per 30s window


class _Signals(QObject):
    anomaly = Signal(str, dict)  # vm_id, result dict


class NetworkMonitor:
    """Collects network stats every 30s and checks for anomalies."""

    def __init__(self):
        self._sigs = _Signals()
        self.anomaly = self._sigs.anomaly
        self._windows: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
        self._last_bytes: dict[str, tuple[int, int]] = {}
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(30000)
        self._qmp_fn = None  # set by main window
        self._vm_names: dict[str, str] = {}

    def set_qmp_provider(self, fn):
        """fn(vm_id) -> QMPConnection | None"""
        self._qmp_fn = fn

    def set_vm_names(self, names: dict[str, str]):
        self._vm_names = names

    def _tick(self):
        if not self._qmp_fn:
            return
        for vm_id in list(self._vm_names.keys()):
            qmp = self._qmp_fn(vm_id)
            if not qmp or not qmp.connected:
                continue
            try:
                resp = qmp.execute("query-net")
                devs = resp.get("return", [])
                total_sent = sum(d.get("tx-bytes", 0) for d in devs)
                total_recv = sum(d.get("rx-bytes", 0) for d in devs)
                total_pkts_s = sum(d.get("tx-packets", 0) for d in devs)
                total_pkts_r = sum(d.get("rx-packets", 0) for d in devs)

                prev = self._last_bytes.get(vm_id)
                if prev:
                    delta_sent = total_sent - prev[0]
                    delta_recv = total_recv - prev[1]
                else:
                    delta_sent = 0
                    delta_recv = 0
                self._last_bytes[vm_id] = (total_sent, total_recv)

                reading = {
                    "bytes_sent": delta_sent,
                    "bytes_recv": delta_recv,
                    "packets_sent": total_pkts_s,
                    "packets_recv": total_pkts_r,
                }
                self._windows[vm_id].append(reading)

                if len(self._windows[vm_id]) >= 5:
                    self._analyze(vm_id)
            except Exception:
                pass

    def _analyze(self, vm_id: str):
        readings = list(self._windows[vm_id])
        vm_name = self._vm_names.get(vm_id, vm_id)

        # Fallback threshold check
        latest = readings[-1] if readings else {}
        if latest.get("bytes_sent", 0) > _OUTBOUND_THRESHOLD:
            result = {
                "anomaly_detected": True,
                "severity": "high",
                "description": f"Outbound burst: {latest['bytes_sent'] / (1024*1024):.0f}MB in 30s",
                "recommend_quarantine": True,
            }
            self._sigs.anomaly.emit(vm_id, result)
            return

        if not check_available():
            return

        threading.Thread(
            target=self._ai_analyze,
            args=(vm_id, vm_name, readings),
            daemon=True,
        ).start()

    def _ai_analyze(self, vm_id, vm_name, readings):
        try:
            system = _SYSTEM_PROMPT.replace(
                "{vm_name}", vm_name
            ).replace("{readings_json}", json.dumps(readings))
            raw = query("Check for anomalies.", system=system, timeout=20)
            parsed = extract_json(raw)
            if parsed and parsed.get("anomaly_detected"):
                self._sigs.anomaly.emit(vm_id, parsed)
                import app.audit_log as audit
                audit.record("network_anomaly", vm_id, vm_name, {
                    "severity": parsed.get("severity", "unknown"),
                    "description": parsed.get("description", ""),
                })
        except Exception as exc:
            log.debug("Network monitor AI error: %s", exc)
