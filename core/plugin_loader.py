"""
Plugin Loader
-------------
Auto-discovers plugins in the plugins/ folder by scanning for
manifest.yaml + plugin.py pairs, then calls register(event_bus)
on each one — no more hand-wiring imports in main.py.

Each plugin directory must contain:
  - manifest.yaml    — metadata (name, version, description, permissions)
  - plugin.py        — module that exports a register(event_bus) function
"""

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from core.plugin_registry import register_plugin

if TYPE_CHECKING:
    from core.event_bus import EventBus


def discover_plugins() -> list[dict]:
    """Scan the plugins/ directory and return metadata dicts for each
    valid plugin found. A valid plugin has both manifest.yaml and plugin.py."""
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    discovered = []

    if not plugins_dir.is_dir():
        return discovered

    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_") or entry.name.startswith("."):
            continue

        manifest_path = entry / "manifest.yaml"
        plugin_path = entry / "plugin.py"
        if manifest_path.is_file() and plugin_path.is_file():
            meta = {"name": entry.name, "dir": str(entry)}
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    meta.update(yaml.safe_load(f) or {})
            except Exception as exc:
                meta["_parse_error"] = str(exc)
            discovered.append(meta)

    return discovered


def load_and_register(event_bus: "EventBus") -> list[str]:
    """
    Discover all plugins, import their plugin.py module, and call
    register(event_bus). Returns the list of registered plugin names.
    """
    plugins = discover_plugins()
    registered = []

    for meta in plugins:
        plugin_name = meta["name"]
        try:
            # Import the plugin module
            module = importlib.import_module(f"plugins.{plugin_name}.plugin")
            # Call its register function
            # Register permissions from manifest before calling register()
            permissions = meta.get("permissions", "")
            perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
            register_plugin(plugin_name, perm_list)

            if hasattr(module, "register"):
                module.register(event_bus, plugin_name=plugin_name)
                registered.append(plugin_name)
            else:
                print(f"[plugin_loader] Warning: {plugin_name}/plugin.py has no register() function", file=sys.stderr)
        except Exception as exc:
            print(f"[plugin_loader] Error loading plugin '{plugin_name}': {exc}", file=sys.stderr)

    return registered