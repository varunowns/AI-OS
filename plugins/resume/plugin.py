"""
Resume Plugin
-------------
Reads a resume note from the vault and, using recent career summaries
from the SQLite index, suggests concrete edits or additions.

Usage:
    python main.py review-resume "Career/Resume.md"
"""

from config import VAULT_PATH
from core.event_bus import EventBus
from services import llm_service
from services.context_service import get_context

REVIEW_PROMPT = (
    "You are a career coach reviewing a resume. Below is the resume "
    "content followed by recent career notes (summaries, achievements, "
    "projects). Suggest 3-5 concrete edits or additions to the resume "
    "based on this new material.\n\n"
    "--- RESUME ---\n{resume}\n\n"
    "--- RECENT CAREER NOTES ---\n{career_notes}\n"
)


def handle_review(payload: dict) -> dict:
    """
    payload:
      resume_note: str  - path to the resume note in the vault
      output_note: str   - where to write the review (optional)
    """
    resume_note = payload["resume_note"]
    output_note = payload.get("output_note", resume_note.replace(".md", "-review.md"))

    ctx = get_context()

    # Read the resume
    resume = ctx.read_note(resume_note)

    # Query recent career summaries from the context service
    career_notes = ctx.find_by_tag("career")
    summary_notes = ctx.find_by_tag("summary")

    # Combine and deduplicate by path
    seen = set()
    recent_notes = []
    for note in career_notes + summary_notes:
        if note["path"] not in seen and note["path"] != resume_note:
            seen.add(note["path"])
            recent_notes.append(note)

    # Fetch content for recent career notes
    snippets = []
    for note in recent_notes[:5]:  # limit to 5 to keep prompt size manageable
        try:
            content = ctx.read_note(note["path"])
            first_para = content.strip().split("\n\n")[0] if content.strip() else ""
            snippets.append(f"=== {note['path']} ===\n{first_para}")
        except FileNotFoundError:
            snippets.append(f"=== {note['path']} ===\n(file not found)")

    career_context = "\n\n".join(snippets) if snippets else "(no recent career notes found)"

    # Ask LLM for suggestions
    review = llm_service.ask(REVIEW_PROMPT.format(resume=resume, career_notes=career_context))

    # Write the review note
    ctx.write_note(
        output_note,
        review,
        title=f"Resume Review — {resume_note}",
        tags=["resume", "review"],
        plugin_source="resume",
    )

    return {
        "resume_note": resume_note,
        "output_note": str(VAULT_PATH / output_note),
        "review": review,
    }


def register(event_bus: EventBus, plugin_name: str = "") -> None:
    """Called once at startup to wire this plugin into the event bus."""
    event_bus.subscribe("resume.review", handle_review, plugin_name=plugin_name)