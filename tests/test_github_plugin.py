"""
Tests for the GitHub plugin.
"""

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def test_discover_finds_github():
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "github" in names


def test_github_manifest_has_permissions():
    plugins = discover_plugins()
    gh = next(p for p in plugins if p["name"] == "github")
    assert gh.get("version") == "0.1.0"
    perms = gh.get("permissions", "")
    assert "vault:read" in perms
    assert "vault:write" in perms
    assert "llm:call" in perms


def test_github_registers_event():
    bus = EventBus()
    report = load_and_register(bus)
    assert "github" in report.registered
    assert "repo.commits.summarize" in bus.registered_events()


def test_both_plugins_loaded():
    bus = EventBus()
    report = load_and_register(bus)
    assert "career" in report.registered
    assert "github" in report.registered