"""Settings store for accessibility and user preferences (Task 8)."""
from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "settings.json"

_DEFAULTS = {
    "high_contrast": False,
    "reduced_motion": False,
}


def load_settings() -> dict:
    if _SETTINGS_PATH.exists():
        try:
            d = json.loads(_SETTINGS_PATH.read_text())
            merged = dict(_DEFAULTS)
            merged.update(d)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def save_settings(settings: dict) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
