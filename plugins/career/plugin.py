"""
Career Plugin
-------------
The first real AI-OS plugin. Deliberately does one thing:

  1. Read a note from the vault
  2. Ask Claude to summarize it + extract action items
  3. Write the result back as a new note

This is the reference implementation every future plugin (resume, github,
learning, ...) will copy the shape of: subscribe to an event, call a
service, publish a result event.
"""

from pathlib import Path

from core.event_bus import EventBus
from config import VAULT_PATH
from services import llm_service
from services.context_service import get_context

SUMMARY_PROMPT = (
    "Summarize the following note in 3-5 bullet points, then list any "
    "clear action items as a separate checklist. Keep it concise.\n\n"
    "---\n\n{content}"
)


def _note_to_wikilink(relative_path: str) -> str:
    """Turn 'Career/README.md' into '[[Career/README]]'."""
    stem = relative_path.replace(".md", "")
    return f"[[{stem}]]"


def handle_summarize(payload: dict) -> dict:
    """
    payload:
      source_note: str  - path to the note to summarize, relative to vault root
      output_note: str  - path to write the summary to, relative to vault root
    """
    source_note = payload["source_note"]
    output_note = payload.get(
        "output_note", source_note.replace(".md", "-summary.md")
    )

    # 1. Read source & generate summary
    ctx = get_context()
    content = ctx.read_note(source_note)
    summary = llm_service.ask(SUMMARY_PROMPT.format(content=content))

    # 2. Write summary note with a backlink header, tagged for search
    summary_header = f"Summary of {_note_to_wikilink(source_note)}\n\n"
    ctx.write_note(
        output_note,
        summary_header + summary,
        title=f"Summary of {source_note}",
        tags=["summary", "career"],
        plugin_source="career",
    )

    # 3. Update source note with a "Related" section (only add once)
    related_link = f"- {_note_to_wikilink(output_note)}"
    if "## Related" not in content:
        source_update = content.rstrip() + f"\n\n## Related\n\n{related_link}\n"
        ctx.write_note(
            source_note,
            source_update,
            plugin_source="career",
        )

    return {
        "source_note": source_note,
        "output_note": str(VAULT_PATH / output_note),
        "summary": summary,
    }


def register(event_bus: EventBus, plugin_name: str = "", config: dict | None = None) -> None:
    """Called once at startup to wire this plugin into the event bus."""
    event_bus.subscribe("note.summarize", handle_summarize, plugin_name=plugin_name)