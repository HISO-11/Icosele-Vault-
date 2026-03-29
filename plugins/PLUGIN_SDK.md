# Icosele Vault Plugin SDK

## Plugin Structure

Each plugin lives in a subdirectory of `plugins/`:

```
plugins/
  my_plugin/
    plugin.json     # manifest (required)
    main.py         # entry point (required)
```

## Manifest (plugin.json)

```json
{
  "name": "My Plugin",
  "version": "1.0",
  "author": "Your Name",
  "description": "What this plugin does",
  "entry": "main.py",
  "hooks": ["on_vm_start", "on_vm_stop", "on_snapshot_created"]
}
```

## Available Hooks

Implement these as functions in `main.py`:

| Hook | Arguments | Called When |
|------|-----------|------------|
| `on_vm_start` | `vm_id`, `vm_name` | A VM starts |
| `on_vm_stop` | `vm_id`, `vm_name` | A VM stops |
| `on_snapshot_created` | `vm_id`, `snapshot_name` | Snapshot taken |
| `on_dashboard_widget` | (none) | Dashboard loads — return a QWidget |

All hooks are called inside try/except — a broken plugin will never crash the app.

## Example Plugin

See `plugins/example_plugin/` for a complete working example that logs VM events to a text file.

## Installation

1. Create your plugin directory under `plugins/`
2. Add `plugin.json` and `main.py`
3. Restart Icosele Vault — plugins are loaded on startup
4. Or use the Install Plugin button in Settings > Plugins to install from a zip file
