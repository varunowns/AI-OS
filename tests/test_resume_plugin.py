"""
Tests for the Resume plugin.
"""

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def test_discover_finds_resume():
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "resume" in names


def test_resume_manifest_has_permissions():
    plugins = discover_plugins()
    rp = next(p for p in plugins if p["name"] == "resume")
    assert rp.get("version") == "0.1.0"
    perms = rp.get("permissions", "")
    assert "vault:read" in perms
    assert "vault:write" in perms
    assert "llm:call" in perms


def test_resume_registers_event():
    bus = EventBus()
    report = load_and_register(bus)
    assert "resume" in report.registered
    assert "resume.review" in bus.registered_events()


def test_all_plugins_loaded():
    bus = EventBus()
    report = load_and_register(bus)
    assert "career" in report.registered
    assert "github" in report.registered
    assert "resume" in report.registered