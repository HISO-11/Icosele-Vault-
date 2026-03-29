"""Shared Ollama client — stdlib only (urllib, json, threading)."""
from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODEL = "llama3"


def check_available() -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def query(prompt: str, system: str = "", timeout: int = 60) -> str:
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
        return data.get("response", "")


def extract_json(text: str) -> dict | None:
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL):
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None
