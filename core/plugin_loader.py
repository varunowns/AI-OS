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

from core.plugin_registry import register_plugin

if TYPE_CHECKING:
    from core.event_bus import EventBus


def _parse_simple_yaml(path: Path) -> dict:
    """Minimal YAML reader for the tiny manifest files we use.
    Only handles top-level key: value and key: > multiline blocks.
    No dependencies needed (avoids adding PyYAML for three manifests)."""
    result: dict = {}
    current_key = None
    current_lines: list[str] = []

    for line in path.read_text("utf-8").splitlines():
        # Start of a new key
        if line and not line[0].isspace() and ":" in line:
            # Flush previous multiline value
            if current_key is not None:
                value = " ".join(current_lines).strip()
                if value:
                    result[current_key] = value
                current_lines = []

            key, _, rest = line.partition(":")
            current_key = key.strip()
            tail = rest.strip()
            if tail and tail not in ("|", ">", ">-"):
                # Strip inline YAML comments (" # ...")
                tail, *_ = tail.split(" #", maxsplit=1)
                current_lines.append(tail.strip())
        elif current_key is not None and line and not line.lstrip().startswith("#"):
            # Continuation of a multiline value (indented), but not a comment line
            clean_line, *_ = line.split(" #", maxsplit=1)
            current_lines.append(clean_line.strip())

    # Flush last key
    if current_key is not None:
        value = " ".join(current_lines).strip()
        if value:
            result[current_key] = value

    return result


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
                meta.update(_parse_simple_yaml(manifest_path))
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