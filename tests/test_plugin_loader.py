"""
Test that plugin auto-discovery finds the career plugin.
"""

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def test_discover_finds_career():
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "career" in names


def test_discover_returns_metadata():
    plugins = discover_plugins()
    career = next(p for p in plugins if p["name"] == "career")
    assert career.get("version") == "0.2.0"
    assert career.get("description", "").startswith("Reads a note")


def test_load_and_register():
    bus = EventBus()
    registered = load_and_register(bus)
    assert "career" in registered
    assert "note.summarize" in bus.registered_events()