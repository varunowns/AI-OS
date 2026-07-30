"""
Tests for the event bus.
"""

import sys

from core.event_bus import EventBus


def test_isolated_failure():
    """A failing handler should not prevent other handlers from running."""
    bus = EventBus()
    results = []

    def handler_a(payload):
        results.append("a")
        raise ValueError("handler a failed")

    def handler_b(payload):
        results.append("b")
        return "b-result"

    bus.subscribe("test.event", handler_a, plugin_name="failing_plugin")
    bus.subscribe("test.event", handler_b, plugin_name="good_plugin")

    # Both handlers should have run
    bus.publish("test.event", {})
    assert results == ["a", "b"], f"Expected ['a', 'b'], got {results}"
