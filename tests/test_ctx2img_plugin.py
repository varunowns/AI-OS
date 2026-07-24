"""
Tests for the ctx2img plugin.
"""

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def test_discover_finds_ctx2img():
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "ctx2img" in names


def test_ctx2img_registers_event():
    bus = EventBus()
    registered = load_and_register(bus)
    assert "ctx2img" in registered
    assert "note.toimage" in bus.registered_events()


def test_sanitise_filename():
    from plugins.ctx2img.plugin import _sanitise_filename
    assert _sanitise_filename("Career/README.md") == "Career-README"
    assert _sanitise_filename("Dev/some-notes.md") == "Dev-some-notes"


def test_all_plugins_loaded():
    bus = EventBus()
    registered = load_and_register(bus)
    assert len(registered) >= 5
    assert "ctx2img" in registered