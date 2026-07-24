"""
Search Plugin
-------------
Semantic search over vault notes using the embedding service.
Supports searching the index and re-indexing all vault notes.

Usage:
    python main.py search "machine learning projects"
    python main.py reindex
"""

from core.event_bus import EventBus
from services import obsidian_service
from services.embedding_service import EmbeddingIndex
from storage.db import NoteIndex, get_db


def handle_search(payload: dict) -> dict:
    """
    payload:
      query: str        - search query
      top_k: int        - number of results (default 5)
    """
    query = payload.get("query", "")
    top_k = payload.get("top_k", 5)

    if not query.strip():
        return {"query": query, "results": [], "error": "Empty query"}

    emb = EmbeddingIndex()
    results = emb.search(query, top_k=top_k)

    return {
        "query": query,
        "top_k": top_k,
        "results": results,
        "result_count": len(results),
    }


def handle_reindex(payload: dict) -> dict:
    """
    Re-index all vault notes that have metadata in the SQLite notes table.
    payload:
      paths: list[str]  - optional: only re-index these specific paths
    """
    emb = EmbeddingIndex()
    note_idx = NoteIndex(get_db())

    specific_paths = payload.get("paths", None)
    if specific_paths:
        paths = specific_paths
    else:
        # Get all notes from the notes table
        conn = get_db()
        rows = conn.execute("SELECT path FROM notes").fetchall()
        paths = [r[0] for r in rows]

    indexed = 0
    errors = []
    for path in paths:
        try:
            content = obsidian_service.read_note(path)
            emb.index_note(path, content)
            indexed += 1
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})

    emb.save_state()

    return {
        "action": "reindex",
        "indexed": indexed,
        "errors": errors,
        "total_requested": len(paths),
    }


def register(event_bus: EventBus, plugin_name: str = "") -> None:
    """Called once at startup to wire this plugin into the event bus."""
    event_bus.subscribe("note.search", handle_search, plugin_name=plugin_name)
    event_bus.subscribe("note.reindex", handle_reindex, plugin_name=plugin_name)