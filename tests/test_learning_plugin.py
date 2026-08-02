"""
Tests for the Learning plugin.
"""

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def test_discover_finds_learning():
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "learning" in names


def test_learning_manifest():
    plugins = discover_plugins()
    lp = next(p for p in plugins if p["name"] == "learning")
    assert lp.get("version") == "0.1.0"
    perms = lp.get("permissions", "")
    assert "vault:read" in perms
    assert "llm:call" in perms


def test_learning_registers_event():
    bus = EventBus()
    report = load_and_register(bus)
    assert "learning" in report.registered
    assert "learning.digest" in bus.registered_events()


def test_all_six_plugins_loaded():
    bus = EventBus()
    report = load_and_register(bus)
    assert "career" in report.registered
    assert "github" in report.registered
    assert "resume" in report.registered
    assert "search" in report.registered
    assert "ctx2img" in report.registered
    assert "learning" in report.registered