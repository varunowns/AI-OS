"""
Learning Plugin
---------------
Reads notes tagged #learning from the SQLite index, summarizes concepts
learned this week, and writes a weekly digest note with spaced-repetition
style follow-up questions.

Usage:
    python main.py digest
    python main.py digest --tag learning --out "Learning/Weekly-Digest.md"
"""

from datetime import datetime, timezone

from config import VAULT_PATH
from core.event_bus import EventBus
from services import llm_service
from services.context_service import get_context

DIGEST_PROMPT = (
    "You are creating a weekly learning digest. Below are notes tagged "
    "#learning. For each note, extract 2-3 key concepts. Then produce:\n\n"
    "1. **Summary** (2-3 sentences on the overall theme)\n"
    "2. **Key Concepts** (bullet list of what was learned)\n"
    "3. **Review Questions** (3-5 spaced-repetition style questions to "
    "test understanding next week)\n\n"
    "---\n\n{notes_content}"
)

# Defaults drawn from the manifest's config; populated by register().
_DEFAULT_TAG = "learning"
_DEFAULT_DIGEST_FOLDER = "Learning/Digests"


def handle_digest(payload: dict) -> dict:
    """
    payload:
      tag: str          - tag to search for (default: learning)
      output_note: str  - where to write the digest (optional)
    """
    tag = payload.get("tag", _DEFAULT_TAG)
    output_note = payload.get(
        "output_note",
        f"{_DEFAULT_DIGEST_FOLDER}/weekly-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md",
    )

    ctx = get_context()

    # Query SQLite for notes with this tag
    tagged = ctx.find_by_tag(tag)

    if not tagged:
        # Create an empty digest explaining nothing was found
        content = (
            f"# Weekly Learning Digest\n\n"
            f"_No notes tagged #{tag} found this week._\n\n"
            f"Tag a note with #{tag} and re-run `python main.py digest` to "
            f"generate a digest.\n"
        )
        ctx.write_note(
            output_note, content,
            title=f"Weekly Digest ({tag})",
            tags=["digest", tag],
            plugin_source="learning",
        )
        return {
            "output_note": str(VAULT_PATH / output_note),
            "digest": content,
            "notes_count": 0,
        }

    # Read each tagged note's content
    notes_content = []
    for note in tagged[:10]:  # limit to 10 notes to keep prompt reasonable
        try:
            content = ctx.read_note(note["path"])
            notes_content.append(f"=== {note['path']} ===\n{content}")
        except FileNotFoundError:
            notes_content.append(f"=== {note['path']} ===\n(file not found)")

    full_notes = "\n\n".join(notes_content)

    # Generate digest
    digest_text = llm_service.ask(DIGEST_PROMPT.format(notes_content=full_notes))

    # Write digest note
    header = f"# Weekly Learning Digest\n\n*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n\n"
    ctx.write_note(
        output_note, header + digest_text,
        title=f"Weekly Digest ({tag})",
        tags=["digest", tag],
        plugin_source="learning",
    )

    return {
        "output_note": str(VAULT_PATH / output_note),
        "digest": digest_text,
        "notes_count": len(tagged),
    }


def register(event_bus: EventBus, plugin_name: str = "", config: dict | None = None) -> None:
    """Called once at startup to wire this plugin into the event bus.

    config (from the manifest) may provide:
      learning_tag   — tag to search for
      digest_folder  — where to write digests
    """
    global _DEFAULT_TAG, _DEFAULT_DIGEST_FOLDER
    cfg = config or {}
    if "learning_tag" in cfg:
        _DEFAULT_TAG = str(cfg["learning_tag"])
    if "digest_folder" in cfg:
        _DEFAULT_DIGEST_FOLDER = str(cfg["digest_folder"])

    event_bus.subscribe("learning.digest", handle_digest, plugin_name=plugin_name)