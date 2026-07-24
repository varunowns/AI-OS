"""
AI-OS entrypoint (vertical slice)
----------------------------------
Wires up the event bus via auto-discovery, and exposes a
minimal CLI to trigger plugins against notes in your vault.

Usage:
    python main.py summarize "Career/README.md"
    python main.py summarize "Career/README.md" --out "Career/README-summary.md"
"""

import argparse
import sys

from core.event_bus import EventBus
from core.plugin_loader import load_and_register


def build_event_bus() -> EventBus:
    bus = EventBus()
    registered = load_and_register(bus)
    if not registered:
        print("Warning: no plugins were loaded.", file=sys.stderr)
    else:
        print(f"Loaded plugins: {', '.join(registered)}")
    return bus


def main():
    parser = argparse.ArgumentParser(description="AI-OS (vertical slice)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize_parser = subparsers.add_parser(
        "summarize", help="Summarize a note and write the result back to the vault"
    )
    summarize_parser.add_argument("note", help="Path to the note, relative to vault root")
    summarize_parser.add_argument("--out", help="Where to write the summary (optional)")

    commits_parser = subparsers.add_parser(
        "commits", help="Summarize recent commits from a GitHub repo"
    )
    commits_parser.add_argument("repo", nargs="?", default="v4run/AI-OS",
                                help="owner/repo (default: v4run/AI-OS)")
    commits_parser.add_argument("--out", help="Where to write the note (optional)")
    commits_parser.add_argument("--count", type=int, default=10,
                                help="Number of commits to fetch (default: 10)")

    review_parser = subparsers.add_parser(
        "review-resume", help="Review a resume against recent career notes"
    )
    review_parser.add_argument("note", help="Path to the resume note, relative to vault root")
    review_parser.add_argument("--out", help="Where to write the review (optional)")

    args = parser.parse_args()

    if args.command == "summarize":
        bus = build_event_bus()
        payload = {"source_note": args.note}
        if args.out:
            payload["output_note"] = args.out

        results = bus.publish("note.summarize", payload)
        if not results:
            print("No plugin handled 'note.summarize'.", file=sys.stderr)
            sys.exit(1)

        result = results[0]
        print(f"Wrote summary to: {result['output_note']}\n")
        print(result["summary"])

    elif args.command == "commits":
        bus = build_event_bus()
        payload = {"repo": args.repo, "count": args.count}
        if args.out:
            payload["output_note"] = args.out

        results = bus.publish("repo.commits.summarize", payload)
        if not results:
            print("No plugin handled 'repo.commits.summarize'.", file=sys.stderr)
            sys.exit(1)

        result = results[0]
        print(f"Wrote commits note to: {result['output_note']}\n")
        print(result["summary"])

    elif args.command == "review-resume":
        bus = build_event_bus()
        payload = {"resume_note": args.note}
        if args.out:
            payload["output_note"] = args.out

        results = bus.publish("resume.review", payload)
        if not results:
            print("No plugin handled 'resume.review'.", file=sys.stderr)
            sys.exit(1)

        result = results[0]
        print(f"Wrote review to: {result['output_note']}\n")
        print(result["review"])


if __name__ == "__main__":
    main()