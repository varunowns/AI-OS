"""
AI-OS entrypoint (vertical slice)
----------------------------------
Wires up the event bus via auto-discovery, and auto-generates CLI
subcommands from each plugin's CLI_COMMANDS metadata — no more
hardcoding commands in main.py.

Usage:
    python main.py --help
    python main.py summarize "Career/README.md"
    python main.py commits "varunowns/EchoSign"
"""

import argparse
import os
import sys

# Load .env early so validate_config() sees the variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def validate_config() -> list[str]:
    """Check critical config values and return a list of issues."""
    issues = []
    vault = os.environ.get("AI_OS_VAULT_PATH", "")
    vault = os.environ.get("AI_OS_VAULT_PATH", "")
    if not vault:
        issues.append("AI_OS_VAULT_PATH is not set. Add it to your .env file "
                       "(e.g. AI_OS_VAULT_PATH=V:/Obsidian/Obsidian Vault)")
    else:
        from pathlib import Path
        if not Path(vault).is_dir():
            issues.append(f"AI_OS_VAULT_PATH={vault} does not exist or is not a directory")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    proxy_key = os.environ.get("AI_OS_LLM_API_KEY", "")
    proxy_url = os.environ.get("AI_OS_LLM_BASE_URL", "")
    if not api_key and not proxy_key:
        issues.append("No LLM API key configured. Set ANTHROPIC_API_KEY or "
                       "AI_OS_LLM_API_KEY in your .env file")
    if proxy_url and not proxy_key:
        issues.append("AI_OS_LLM_BASE_URL is set but AI_OS_LLM_API_KEY is missing")
    if not proxy_url and not api_key:
        # No proxy and no key — that's already caught above
        pass

    return issues


def build_event_bus() -> EventBus:
    bus = EventBus()
    registered = load_and_register(bus)
    if not registered:
        print("Warning: no plugins were loaded.", file=sys.stderr)
    else:
        print(f"Loaded plugins: {', '.join(registered)}")
    return bus


def main():
    issues = validate_config()
    if issues:
        print("Configuration errors:", file=sys.stderr)
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}", file=sys.stderr)
        print("\nFix these in your .env file and try again.", file=sys.stderr)
        sys.exit(1)

    # Discover plugins *before* building the bus, so we know the CLI shape
    plugins = discover_plugins()

    parser = argparse.ArgumentParser(
        description="AI-OS — personal AI platform over your Obsidian vault"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Map command names to (event_name, plugin_name, cli_meta)
    command_map: dict[str, tuple[str, str, dict]] = {}

    for meta in plugins:
        plugin_name = meta["name"]
        commands_raw = meta.get("commands", "")
        if commands_raw:
            # Parse commands from manifest: "summarize:note.summarize"
            for entry in commands_raw.split(";"):
                entry = entry.strip()
                if not entry:
                    continue
                parts = entry.split(":", 2)
                cmd_name = parts[0].strip()
                event_name = parts[1].strip() if len(parts) > 1 else ""
                cmd_help = parts[2].strip() if len(parts) > 2 else ""
                if cmd_name and event_name:
                    command_map[cmd_name] = (event_name, plugin_name, {"help": cmd_help})

    # Build subparsers from the command map
    for cmd_name, (event_name, plugin_name, cmd_meta) in sorted(command_map.items()):
        help_text = cmd_meta.get("help") or f"Trigger {event_name} event"

        # Determine if this command takes a positional "note" arg
        sp = subparsers.add_parser(cmd_name, help=help_text)

        # Most commands take a note/repo path
        if event_name in ("note.summarize", "note.review", "resume.review"):
            sp.add_argument("note", help="Path to the note, relative to vault root")
        elif event_name == "repo.commits.summarize":
            sp.add_argument("repo", nargs="?", default="varunowns/AI-OS",
                            help="owner/repo (default: varunowns/AI-OS)")
            sp.add_argument("--count", type=int, default=10,
                            help="Number of commits to fetch (default: 10)")
        elif event_name == "note.toimage":
            sp.add_argument("note", help="Path to the note, relative to vault root")
        elif event_name == "note.search":
            sp.add_argument("query", help="Search query")
        # Many commands support --out
        sp.add_argument("--out", help="Where to write the result (optional)")

        # search also has --top-k
        if event_name == "note.search":
            sp.add_argument("--top-k", type=int, default=5,
                            help="Number of results (default: 5)")

    # Add built-in commands not driven by plugins
    subparsers.add_parser("reindex", help="Re-index all vault notes for semantic search")
    subparsers.add_parser("serve", help="Start the background scheduler (Hermes)")

    args = parser.parse_args()
    bus = build_event_bus()

    # --- Route to the right event ---
    if args.command in command_map:
        event_name, _, _ = command_map[args.command]
        payload = {}

        if event_name == "note.summarize":
            payload["source_note"] = args.note
            if args.out:
                payload["output_note"] = args.out
        elif event_name == "note.toimage":
            payload["source_note"] = args.note
        elif event_name == "repo.commits.summarize":
            payload["repo"] = args.repo
            payload["count"] = args.count
            if args.out:
                payload["output_note"] = args.out
        elif event_name == "resume.review":
            payload["resume_note"] = args.note
            if args.out:
                payload["output_note"] = args.out
        elif event_name == "note.search":
            payload["query"] = args.query
            payload["top_k"] = args.top_k
        else:
            # Generic fallback: pass args as payload
            payload = vars(args)

        results = bus.publish(event_name, payload)
        if not results:
            print(f"No plugin handled '{event_name}'.", file=sys.stderr)
            sys.exit(1)

        result = results[0]

        if event_name == "note.search":
            if result.get("error"):
                print(f"Error: {result['error']}", file=sys.stderr)
                sys.exit(1)
            print(f"Search results for: \"{result['query']}\" ({result['result_count']} found)\n")
            for i, r in enumerate(result["results"], 1):
                print(f"  {i}. {r['path']}  (score: {r['score']})")
                if r["title"]:
                    print(f"     Title: {r['title']}")
                if r["tags"]:
                    print(f"     Tags: {', '.join(r['tags'])}")
                if r["plugin_source"]:
                    print(f"     Source: {r['plugin_source']}")
                print()
        else:
            output_key = "output_note" if "output_note" in result else None
            if output_key:
                print(f"Wrote to: {result[output_key]}\n")
            summary = result.get("summary") or result.get("review") or ""
            if summary:
                print(summary)

    elif args.command == "reindex":
        result = bus.publish("note.reindex", {})
        if not result:
            print("No plugin handled 'note.reindex'.", file=sys.stderr)
            sys.exit(1)

        r = result[0]
        print(f"Re-indexed {r['indexed']}/{r['total_requested']} notes")
        if r["errors"]:
            for e in r["errors"]:
                print(f"  [X] {e['path']}: {e['error']}")

    elif args.command == "serve":
        import signal
        from automation.scheduler import start_scheduler

        stop = start_scheduler(bus, interval_seconds=60)
        print("[scheduler] Running. Press Ctrl+C to stop.")

        def _handle_sig(*_):
            print("\n[scheduler] Shutting down...")
            stop.set()

        signal.signal(signal.SIGINT, _handle_sig)
        signal.signal(signal.SIGTERM, _handle_sig)

        try:
            stop.wait()
        except KeyboardInterrupt:
            stop.set()


if __name__ == "__main__":
    main()