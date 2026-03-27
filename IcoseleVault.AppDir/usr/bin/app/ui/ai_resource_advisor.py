"""Task 2 — Intelligent resource reallocation advisor (background)."""
from __future__ import annotations

import json
import logging
import os
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from app.ollama_client import check_available, query, extract_json

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a VM resource advisor. Here are the current resource stats "
    "for running VMs: {stats_json}. The host has {host_ram}GB total RAM "
    "and {host_cores} CPU cores. Identify any VMs that are over-allocated "
    "(using less than 30% of their allocation) or under-allocated (using "
    "more than 85% consistently). Respond with JSON only: "
    '{"recommendations": [{"vm_name": "...", "issue": "over|under", '
    '"resource": "ram|cpu", "current": "...", "suggested": "...", '
    '"reason": "..."}]}. Return empty list if no issues.'
)


class _Signals(QObject):
    recommendations = Signal(list)


class AIResourceAdvisor:
    """Runs in background every 60s when Ollama is available."""

    def __init__(self, get_stats_fn, parent_obj=None):
        self._get_stats = get_stats_fn
        self._sigs = _Signals()
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(60000)
        self.recommendations = self._sigs.recommendations

    def _poll(self):
        if not check_available():
            return
        stats = self._get_stats()
        if not stats:
            return
        threading.Thread(target=self._worker, args=(stats,), daemon=True).start()

    def _worker(self, stats):
        try:
            host_cores = os.cpu_count() or 4
            try:
                import psutil
                host_ram = round(psutil.virtual_memory().total / (1024**3), 1)
            except ImportError:
                host_ram = 16
            system = _SYSTEM_PROMPT.replace(
                "{stats_json}", json.dumps(stats)
            ).replace(
                "{host_ram}", str(host_ram)
            ).replace(
                "{host_cores}", str(host_cores)
            )
            raw = query("Analyze these VM resource stats.", system=system, timeout=30)
            parsed = extract_json(raw)
            if parsed and "recommendations" in parsed:
                recs = parsed["recommendations"]
                if isinstance(recs, list) and recs:
                    self._sigs.recommendations.emit(recs)
        except Exception as exc:
            log.debug("Resource advisor error: %s", exc)
