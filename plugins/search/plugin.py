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
from services.context_service import ContextService


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

    ctx = ContextService()
    results = ctx.search(query, top_k=top_k)

    return {
        "query": query,
        "top_k": top_k,
        "results": results,
        "result_count": len(results),
    }


def handle_reindex(payload: dict) -> dict:
    """
    Re-index all vault notes that have metadata in the SQLite notes table.
    Delegates to the ContextService to avoid service-to-plugin coupling.

    payload:
      scan_vault: bool  - when True, scans the vault for new notes first
    """
    ctx = ContextService()
    return ctx.reindex_all(scan_vault=payload.get("scan_vault", False))


def register(event_bus: EventBus, plugin_name: str = "") -> None:
    """Called once at startup to wire this plugin into the event bus."""
    event_bus.subscribe("note.search", handle_search, plugin_name=plugin_name)
    event_bus.subscribe("note.reindex", handle_reindex, plugin_name=plugin_name)
