"""
Scheduler / Automation (Hermes)
--------------------------------
Runs plugin events on a schedule using a simple background loop (no
external scheduler dependency). Schedule config is stored in
schedules.yaml in the vault's .ai-os/ directory.

Usage:
    python main.py serve

The scheduler thread wakes every 60 seconds, checks which schedules
are due, and publishes the corresponding event on the event bus.
"""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from config import VAULT_PATH
from core.event_bus import EventBus

_SCHEDULES_PATH = VAULT_PATH / ".ai-os" / "schedules.yaml"

# Default schedules — created as a template on first run
_DEFAULT_SCHEDULES = {
    "schedules": [
        {
            "id": "daily-github-commits",
            "label": "Daily GitHub commits summary",
            "event": "repo.commits.summarize",
            "payload": {"repo": "varunowns/AI-OS", "count": 5},
            "interval_hours": 24,
            "enabled": True,
        },
    ]
}


def load_schedules() -> dict[str, Any]:
    """Load schedules from schedules.yaml, creating defaults if missing."""
    if not _SCHEDULES_PATH.exists():
        _SCHEDULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SCHEDULES_PATH.write_text(
            yaml.dump(_DEFAULT_SCHEDULES, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        # Return a fresh copy so callers never share the template's dict.
        return yaml.safe_load(
            yaml.dump(_DEFAULT_SCHEDULES, default_flow_style=False, sort_keys=False)
        )

    with open(_SCHEDULES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"schedules": []}


def save_schedules(data: dict[str, Any]) -> None:
    """Write schedules back to schedules.yaml."""
    _SCHEDULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SCHEDULES_PATH.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _run_schedule(schedule: dict, bus: EventBus) -> None:
    """Publish the event for one schedule entry."""
    event = schedule["event"]
    payload = schedule.get("payload", {})
    print(f"[scheduler] Running '{schedule.get('label', event)}'...")
    try:
        bus.publish(event, payload)
    except Exception as exc:
        print(f"[scheduler] Error running '{event}': {exc}")


def _run_cycle(data: dict, bus: EventBus, now: float) -> bool:
    """Run every due schedule in `data`, stamping last_run in place.

    Returns True when any schedule fired (and thus should be persisted).
    A schedule with no last_run has never run and fires on its first
    cycle. Per-schedule errors are handled inside _run_schedule.
    """
    changed = False
    for schedule in data.get("schedules", []):
        if not schedule.get("enabled", True):
            continue

        interval_h = schedule.get("interval_hours", 24)
        interval_s = interval_h * 3600
        last = schedule.get("last_run", 0)
        if now - last >= interval_s:
            _run_schedule(schedule, bus)
            schedule["last_run"] = now
            changed = True
    return changed


def serve(bus: EventBus, interval_seconds: int = 60, stop_event: threading.Event | None = None) -> None:
    """
    Main scheduler loop. Runs in a background thread, waking every
    `interval_seconds` to check and fire due schedules.

    Each schedule's last-run time is persisted in schedules.yaml, so a
    restart does not re-fire every enabled schedule immediately.
    """
    if stop_event is None:
        stop_event = threading.Event()

    print(f"[scheduler] Started (check interval: {interval_seconds}s)")

    while not stop_event.is_set():
        now = time.time()
        try:
            data = load_schedules()
            if _run_cycle(data, bus, now):
                save_schedules(data)
        except Exception as exc:
            print(f"[scheduler] Error in check cycle: {exc}")

        stop_event.wait(timeout=interval_seconds)

    print("[scheduler] Stopped.")


def start_scheduler(bus: EventBus, interval_seconds: int = 60) -> threading.Event:
    """Start the scheduler in a daemon thread. Returns the stop event."""
    stop_event = threading.Event()
    t = threading.Thread(
        target=serve,
        args=(bus, interval_seconds, stop_event),
        daemon=True,
    )
    t.start()
    return stop_event