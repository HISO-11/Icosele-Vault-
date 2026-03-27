"""Task 2 — Plugin system: load, manage, and call plugin hooks."""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugins"


class PluginInfo:
    def __init__(self, path: Path):
        self.path = path
        self.manifest: dict = {}
        self.module = None
        self.loaded = False
        self.error = ""
        self.enabled = True

    @property
    def name(self) -> str:
        return self.manifest.get("name", self.path.name)

    @property
    def version(self) -> str:
        return self.manifest.get("version", "?")

    @property
    def author(self) -> str:
        return self.manifest.get("author", "Unknown")

    @property
    def description(self) -> str:
        return self.manifest.get("description", "")

    @property
    def hooks(self) -> list[str]:
        return self.manifest.get("hooks", [])


_plugins: list[PluginInfo] = []


def discover_plugins() -> list[PluginInfo]:
    global _plugins
    _plugins = []
    if not _PLUGIN_DIR.exists():
        _PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        return _plugins
    for d in sorted(_PLUGIN_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        manifest_path = d / "plugin.json"
        entry_path = d / "main.py"
        if not manifest_path.exists() or not entry_path.exists():
            continue
        pi = PluginInfo(d)
        try:
            pi.manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            pi.error = f"Bad manifest: {exc}"
            _plugins.append(pi)
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{d.name}", str(entry_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                pi.module = mod
                pi.loaded = True
        except Exception as exc:
            pi.error = str(exc)
        _plugins.append(pi)
    return _plugins


def get_plugins() -> list[PluginInfo]:
    return _plugins


def call_hook(hook_name: str, **kwargs) -> None:
    for pi in _plugins:
        if not pi.loaded or not pi.enabled:
            continue
        if hook_name not in pi.hooks:
            continue
        fn = getattr(pi.module, hook_name, None)
        if fn and callable(fn):
            try:
                fn(**kwargs)
            except Exception as exc:
                log.warning("Plugin %s hook %s failed: %s", pi.name, hook_name, exc)


def install_plugin_zip(zip_path: str) -> str:
    """Extract a plugin zip to the plugins directory. Returns plugin name or error."""
    import zipfile
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if not any("plugin.json" in n for n in names):
                return "Error: zip does not contain plugin.json"
            zf.extractall(_PLUGIN_DIR)
            return "Plugin installed successfully"
    except Exception as exc:
        return f"Error: {exc}"
