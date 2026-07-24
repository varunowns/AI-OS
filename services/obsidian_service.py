"""
Obsidian Service
----------------
Treats your existing Obsidian vault as AI-OS's permanent memory,
per the constitution rule "Obsidian is source of truth."

Only two operations for the vertical slice: read a note, write a note.
Everything else (frontmatter parsing, backlinks, the knowledge graph)
comes later once more than one plugin needs it.
"""

from pathlib import Path

from config import VAULT_PATH
from core.plugin_registry import require
from storage.db import NoteIndex, get_db

# Lazy-init index so we don't force SQLite setup at import time.
_index: NoteIndex | None = None


def _get_index() -> NoteIndex:
    global _index
    if _index is None:
        _index = NoteIndex(get_db())
    return _index


@require("vault:read")
def read_note(relative_path: str) -> str:
    """
    Read a note's raw markdown content.
    relative_path is relative to the vault root, e.g. "Career/README.md"
    """
    note_path = VAULT_PATH / relative_path
    if not note_path.exists():
        raise FileNotFoundError(f"No note found at {note_path}")
    return note_path.read_text(encoding="utf-8")


@require("vault:write")
def write_note(
    relative_path: str,
    content: str,
    title: str = "",
    tags: list[str] | None = None,
    plugin_source: str = "",
) -> Path:
    """
    Write (or overwrite) a note. Creates parent folders if needed.
    Also indexes the note in the SQLite metadata layer.
    Returns the full path written to.
    """
    note_path = VAULT_PATH / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")

    # Index metadata
    _get_index().index_note(
        path=relative_path,
        title=title or _extract_title(content),
        tags=tags or [],
        plugin_source=plugin_source,
    )

    return note_path


def _extract_title(content: str) -> str:
    """Extract the first H1 heading from markdown content."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return ""