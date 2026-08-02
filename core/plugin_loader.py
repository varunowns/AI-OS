"""
Plugin Loader
-------------
Auto-discovers plugins in the plugins/ folder by scanning for
manifest.yaml + plugin.py pairs, then calls register(event_bus)
on each one — no more hand-wiring imports in main.py.

Each plugin directory must contain:
  - manifest.yaml    — metadata (name, version, description, permissions)
  - plugin.py        — module that exports a register(event_bus) function

Manifest validation: a plugin whose manifest does not satisfy
validate_manifest() is skipped loudly (never half-loaded). This keeps
the plugin contract a real contract rather than a suggestion.
"""

import importlib
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from core.plugin_registry import register_plugin

if TYPE_CHECKING:
    from core.event_bus import EventBus

# Root directory the default plugin set lives under.
PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"

# Permissions the platform currently understands.
_KNOWN_PERMISSIONS = {"vault:read", "vault:write", "llm:call"}

# Commands declared in a manifest look like "name:event:help".
_COMMAND_ENTRY_SEPARATOR = ";"


@dataclass
class PluginLoadReport:
    """
    Structured result of load_and_register, so callers can surface why
    a plugin is missing rather than guessing from stderr.
    """

    registered: list[str] = field(default_factory=list)
    skipped: dict[str, list[str]] = field(default_factory=dict)  # name -> manifest issues
    failed: dict[str, str] = field(default_factory=dict)  # name -> error string

    @property
    def ok(self) -> bool:
        """True when every discovered plugin loaded successfully."""
        return not self.skipped and not self.failed

    def summary(self) -> str:
        """One-line summary for CLI output, e.g. '5 loaded, 1 skipped, 0 failed'."""
        parts = [f"{len(self.registered)} loaded"]
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts)


def validate_manifest(meta: dict) -> list[str]:
    """
    Validate a plugin manifest against the plugin contract.

    Returns a list of issue strings; an empty list means the manifest
    is valid. Issues are human-readable and prefixed with 'name: field'
    so a plugin with multiple problems can be fixed in one pass.

    Required:
      name         — non-empty string, kebab-case, matches the plugin dir
      version      — valid semver (x.y.z)
      description  — non-empty string

    Optional but validated when present:
      subscribes   — list of non-empty event names
      publishes    — list of non-empty event names
      permissions  — string or list of strings, each a known permission
      commands     — 'cmd:event:help' entries (cmd and event non-empty)
    """
    issues: list[str] = []

    name = meta.get("name", "")
    if not isinstance(name, str) or not name.strip():
        issues.append("name: missing or not a string")
    else:
        name = name.strip()
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
            issues.append(f"name: '{name}' is not kebab-case")

    version = meta.get("version", "")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version.strip()):
        issues.append(f"version: '{version}' is not semver (expected x.y.z)")

    description = meta.get("description", "")
    if not isinstance(description, str) or not description.strip():
        issues.append("description: missing or empty")

    for field in ("subscribes", "publishes"):
        value = meta.get(field, [])
        if not isinstance(value, list):
            issues.append(f"{field}: expected a list of event names")
        elif not all(isinstance(e, str) and e.strip() for e in value):
            issues.append(f"{field}: entries must be non-empty strings")

    permissions = meta.get("permissions", [])
    if isinstance(permissions, str):
        permissions = [p.strip() for p in permissions.split(",") if p.strip()]
    if not isinstance(permissions, list):
        issues.append("permissions: expected a string or list of strings")
    else:
        unknown = [p for p in permissions if p not in _KNOWN_PERMISSIONS]
        if unknown:
            issues.append(f"permissions: unknown permissions: {', '.join(sorted(unknown))}")

    commands = meta.get("commands", "")
    if isinstance(commands, str):
        commands = [c.strip() for c in commands.split(_COMMAND_ENTRY_SEPARATOR) if c.strip()]
    if not isinstance(commands, list):
        issues.append("commands: expected a string or list of strings")
    else:
        for cmd in commands:
            if not isinstance(cmd, str):
                issues.append("commands: entries must be strings")
                continue
            parts = cmd.split(":")
            if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
                issues.append(f"commands: '{cmd}' must be 'cmd:event[:help]'")

    return issues


def _read_manifest(manifest_path: Path, entry_name: str) -> dict:
    """Read a manifest.yaml into a metadata dict, preserving load errors."""
    meta = {"name": entry_name, "dir": str(manifest_path.parent)}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            meta.update(yaml.safe_load(f) or {})
    except Exception as exc:
        meta["_parse_error"] = str(exc)
    return meta


def discover_plugins(plugins_dir: Path | None = None) -> list[dict]:
    """Scan the plugins/ directory and return metadata dicts for each
    plugin found. A plugin needs both manifest.yaml and plugin.py.

    Metadata is returned unvalidated — callers decide whether to
    enforce the contract (load_and_register skips invalid plugins).
    Load errors are stored under '_parse_error' so they stay visible.
    """
    base_dir = plugins_dir or PLUGINS_DIR
    discovered = []

    if not base_dir.is_dir():
        return discovered

    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_") or entry.name.startswith("."):
            continue

        manifest_path = entry / "manifest.yaml"
        plugin_path = entry / "plugin.py"
        if manifest_path.is_file() and plugin_path.is_file():
            meta = _read_manifest(manifest_path, entry.name)
            discovered.append(meta)

    return discovered


def load_and_register(event_bus: "EventBus", plugins_dir: Path | None = None) -> PluginLoadReport:
    """
    Discover all plugins, import their plugin.py module, and call
    register(event_bus). Returns a PluginLoadReport describing what
    happened for every discovered plugin.

    Failure isolation: a plugin whose manifest fails validation (or
    failed to parse) is skipped, and a plugin whose import or register()
    raises is recorded as failed — either way it is never half-loaded and
    one bad plugin does not block the others. plugins_dir can be
    overridden for testing.
    """
    base_dir = plugins_dir or PLUGINS_DIR
    plugins = discover_plugins(base_dir)
    report = PluginLoadReport()

    for meta in plugins:
        plugin_name = meta["name"]

        if "_parse_error" in meta:
            print(
                f"[plugin_loader] Skipping '{plugin_name}': manifest failed to parse: {meta['_parse_error']}",
                file=sys.stderr,
            )
            report.skipped[plugin_name] = [f"manifest failed to parse: {meta['_parse_error']}"]
            continue

        validation_issues = validate_manifest(meta)
        if validation_issues:
            print(
                f"[plugin_loader] Skipping '{plugin_name}': invalid manifest:",
                file=sys.stderr,
            )
            for issue in validation_issues:
                print(f"  - {issue}", file=sys.stderr)
            meta["_validation_errors"] = validation_issues
            report.skipped[plugin_name] = validation_issues
            continue

        try:
            # Import the plugin module from the directory that was scanned,
            # so the plugins_dir seam is honest and testable.
            plugin_module_path = base_dir / plugin_name / "plugin.py"
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}.plugin", plugin_module_path
            )
            if spec is None or spec.loader is None:
                raise ImportError("cannot build a module spec from the plugin.py path")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "register"):
                raise AttributeError("plugin.py has no register(event_bus) function")

            # Register permissions from manifest before calling register()
            permissions = meta.get("permissions", "")
            perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
            register_plugin(plugin_name, perm_list)

            module.register(event_bus, plugin_name=plugin_name)
            report.registered.append(plugin_name)
        except Exception as exc:
            print(f"[plugin_loader] Failed to load plugin '{plugin_name}': {exc}", file=sys.stderr)
            report.failed[plugin_name] = str(exc)

    return report