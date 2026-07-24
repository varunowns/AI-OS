"""
Event Bus
---------
The simplest thing that could work: an in-memory pub/sub dispatcher.

Plugins subscribe to named events ("note.summarize", "note.created", ...)
and the core (or other plugins) publish events with a payload dict.

No persistence, no async, no scheduler yet — those get added later,
once a real need for them shows up. This is intentionally small so it's
easy to reason about and easy to extend.
"""

from collections import defaultdict
from typing import Any, Callable

from core.plugin_registry import set_active_plugin


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, Callable[[dict], Any]]]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable[[dict], Any], plugin_name: str = "") -> None:
        """Register a handler to run when `event_name` is published."""
        self._subscribers[event_name].append((plugin_name, handler))

    def publish(self, event_name: str, payload: dict | None = None) -> list[Any]:
        """
        Fire an event. Every subscribed handler runs synchronously in
        registration order. Returns the list of handler return values
        (useful for the CLI to print results).
        """
        payload = payload or {}
        results = []
        for plugin_name, handler in self._subscribers.get(event_name, []):
            set_active_plugin(plugin_name)
            try:
                results.append(handler(payload))
            finally:
                set_active_plugin(None)
        return results

    def registered_events(self) -> list[str]:
        return list(self._subscribers.keys())