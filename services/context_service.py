"""
Context Service
---------------
Unified interface for plugins to access vault context without knowing
the underlying services (obsidian_service, storage.db, embedding_service).

This is the single point of access for:
- Reading/writing notes with metadata
- Tag-based queries
- Semantic search
- Note indexing

Plugins should use this instead of calling services directly.
"""

from pathlib import Path
from typing import Any

from config import VAULT_PATH
from services import obsidian_service
from services.embedding_service import EmbeddingIndex
from storage.db import NoteIndex, get_db, _row_to_note


class ContextService:
    """
    High-level context access for plugins.

    Usage:
        ctx = ContextService()
        content = ctx.read_note("Career/README.md")
        notes = ctx.find_by_tag("career")
        results = ctx.search("machine learning")
        ctx.write_note("New/Note.md", "Content", tags=["tag1"], plugin_source="my_plugin")
    """

    def __init__(self):
        self._note_index: NoteIndex | None = None
        self._embedding_index: EmbeddingIndex | None = None

    @property
    def _notes(self) -> NoteIndex:
        if self._note_index is None:
            self._note_index = NoteIndex(get_db())
        return self._note_index

    @property
    def _embeddings(self) -> EmbeddingIndex:
        if self._embedding_index is None:
            self._embedding_index = EmbeddingIndex()
        return self._embedding_index

    # -------------------------------------------------------------------------
    # Note read/write
    # -------------------------------------------------------------------------

    def read_note(self, relative_path: str) -> str:
        """Read a note's raw markdown content."""
        return obsidian_service.read_note(relative_path)

    def write_note(
        self,
        relative_path: str,
        content: str,
        title: str = "",
        tags: list[str] | None = None,
        plugin_source: str = "",
    ) -> Path:
        """
        Write a note and index it in metadata + embeddings.
        Returns the full path written to.
        """
        # Write to vault
        note_path = obsidian_service.write_note(
            relative_path=relative_path,
            content=content,
            title=title,
            tags=tags,
            plugin_source=plugin_source,
        )

        # Also index in embeddings for semantic search
        self._embeddings.index_note(relative_path, content)
        self._embeddings.save_state()

        return note_path

    def note_exists(self, relative_path: str) -> bool:
        """Check if a note exists in the vault."""
        return (VAULT_PATH / relative_path).exists()

    def delete_note(self, relative_path: str) -> bool:
        """Delete a note from vault and indexes."""
        note_path = VAULT_PATH / relative_path
        if not note_path.exists():
            return False

        note_path.unlink()
        self._notes.delete_note(relative_path)
        self._embeddings.remove_note(relative_path)
        self._embeddings.save_state()
        return True

    # -------------------------------------------------------------------------
    # Tag-based queries
    # -------------------------------------------------------------------------

    def find_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """
        Find all notes with a given tag.
        Returns list of dicts with: path, title, tags, last_modified, plugin_source
        """
        return self._notes.get_notes_by_tag(tag)

    def get_note_metadata(self, relative_path: str) -> dict[str, Any] | None:
        """Get metadata for a single note (title, tags, last_modified, plugin_source)."""
        return self._notes.get_note(relative_path)

    def get_all_tags(self) -> list[str]:
        """Get all unique tags across all indexed notes."""
        conn = get_db()
        rows = conn.execute("SELECT tags FROM notes WHERE tags != ''").fetchall()
        tags = set()
        for row in rows:
            if row[0]:
                tags.update(t.strip() for t in row[0].split(",") if t.strip())
        return sorted(tags)

    def get_notes_by_plugin(self, plugin_source: str) -> list[dict[str, Any]]:
        """Get all notes written by a specific plugin."""
        conn = get_db()
        cursor = conn.execute(
            "SELECT path, title, tags, last_modified, plugin_source FROM notes WHERE plugin_source = ?",
            (plugin_source,),
        )
        return [_row_to_note(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Semantic search
    # -------------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Semantic search over vault notes.
        Returns list of dicts with: path, score, title, tags, plugin_source
        """
        return self._embeddings.search(query, top_k=top_k)

    def reindex_all(self, scan_vault: bool = False) -> dict[str, Any]:
        """Re-index all vault notes.

        When scan_vault is True, first discovers all .md files in the
        vault and indexes them in SQLite metadata + embeddings, including
        notes not created by AI-OS. When False, only re-indexes notes
        already present in the SQLite notes table.
        """
        if scan_vault:
            vault_notes = obsidian_service.scan_vault()
            for note in vault_notes:
                self._notes.index_note(
                    path=note["path"],
                    title=note["title"],
                    tags=note["tags"],
                    plugin_source="",
                )

        paths = self._notes.get_all_paths()
        indexed = 0
        errors = []
        for path in paths:
            try:
                content = self.read_note(path)
                self._embeddings.index_note(path, content)
                indexed += 1
            except Exception as exc:
                errors.append({"path": path, "error": str(exc)})

        self._embeddings.save_state()

        return {
            "action": "reindex",
            "indexed": indexed,
            "errors": errors,
            "total_requested": len(paths),
        }

    def reindex_note(self, relative_path: str) -> bool:
        """Re-index a single note in the embedding store."""
        try:
            content = self.read_note(relative_path)
            self._embeddings.index_note(relative_path, content)
            self._embeddings.save_state()
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Convenience methods for common plugin patterns
    # -------------------------------------------------------------------------

    def read_and_index(self, relative_path: str) -> str:
        """Read a note and ensure it's indexed in embeddings."""
        content = self.read_note(relative_path)
        self._embeddings.index_note(relative_path, content)
        self._embeddings.save_state()
        return content

    def append_to_note(self, relative_path: str, addition: str) -> Path:
        """Append content to an existing note and re-index."""
        existing = self.read_note(relative_path)
        updated = existing.rstrip() + "\n\n" + addition
        meta = self._notes.get_note(relative_path)
        plugin_source = meta.get("plugin_source", "") if meta else ""
        return self.write_note(relative_path, updated, plugin_source=plugin_source)

    def add_section(self, relative_path: str, heading: str, content: str) -> Path:
        """Add a new section (heading + content) to a note."""
        addition = f"## {heading}\n\n{content}"
        return self.append_to_note(relative_path, addition)

    def get_recent_notes(self, limit: int = 10, plugin_source: str | None = None) -> list[dict[str, Any]]:
        """Get recently modified notes, optionally filtered by plugin."""
        conn = get_db()
        if plugin_source:
            cursor = conn.execute(
                "SELECT path, title, tags, last_modified, plugin_source FROM notes WHERE plugin_source = ? ORDER BY last_modified DESC LIMIT ?",
                (plugin_source, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT path, title, tags, last_modified, plugin_source FROM notes ORDER BY last_modified DESC LIMIT ?",
                (limit,),
            )
        return [_row_to_note(r) for r in cursor.fetchall()]


# Singleton instance for easy import
_context_service: ContextService | None = None


def get_context() -> ContextService:
    """Get the global ContextService instance."""
    global _context_service
    if _context_service is None:
        _context_service = ContextService()
    return _context_service