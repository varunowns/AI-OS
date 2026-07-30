"""
Tests for the Context Service.
"""

import pytest
from services.context_service import ContextService, get_context
from storage.db import get_db
from core.plugin_registry import register_plugin, set_active_plugin


def _clean_db():
    """Drop all tables so each test starts fresh."""
    conn = get_db()
    conn.execute("DROP TABLE IF EXISTS notes")
    conn.execute("DROP TABLE IF EXISTS embeddings")
    conn.execute("DROP TABLE IF EXISTS embedding_config")
    conn.commit()
    # Re-init schema
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notes (path TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', last_modified TEXT NOT NULL DEFAULT '', plugin_source TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS embeddings (path TEXT PRIMARY KEY, vector BLOB NOT NULL, updated_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS embedding_config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()


def _setup_test_plugin():
    """Register a test plugin and set it as active for permission checks."""
    register_plugin("test_plugin", ["vault:read", "vault:write", "llm:call"])
    set_active_plugin("test_plugin")


def test_context_service_singleton():
    """Test that get_context returns the same instance."""
    _setup_test_plugin()
    ctx1 = get_context()
    ctx2 = get_context()
    assert ctx1 is ctx2


def test_read_write_note():
    """Test reading and writing notes through context service."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    # Write a note
    path = ctx.write_note(
        "Test/ContextTest.md",
        "# Test Note\n\nContent here.",
        title="Test Note",
        tags=["test", "context"],
        plugin_source="test_plugin",
    )

    assert path.exists()
    assert path.name == "ContextTest.md"

    # Read it back
    content = ctx.read_note("Test/ContextTest.md")
    assert "# Test Note" in content
    assert "Content here." in content


def test_find_by_tag():
    """Test finding notes by tag."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    ctx.write_note("Test/A.md", "A", tags=["alpha"], plugin_source="p1")
    ctx.write_note("Test/B.md", "B", tags=["beta"], plugin_source="p1")
    ctx.write_note("Test/C.md", "C", tags=["alpha", "beta"], plugin_source="p2")

    alpha = ctx.find_by_tag("alpha")
    assert len(alpha) == 2
    paths = {n["path"] for n in alpha}
    assert "Test/A.md" in paths
    assert "Test/C.md" in paths

    beta = ctx.find_by_tag("beta")
    assert len(beta) == 2


def test_search():
    """Test semantic search."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    ctx.write_note("Test/cv.md", "Computer vision with MediaPipe and OpenCV", tags=["cv"])
    ctx.write_note("Test/web.md", "Web development with React and TypeScript", tags=["web"])

    results = ctx.search("computer vision", top_k=5)
    assert len(results) >= 1
    assert results[0]["path"] == "Test/cv.md"
    assert results[0]["score"] > 0


def test_get_all_tags():
    """Test getting all unique tags."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    ctx.write_note("Test/A.md", "A", tags=["alpha", "beta"])
    ctx.write_note("Test/B.md", "B", tags=["beta", "gamma"])

    tags = ctx.get_all_tags()
    assert "alpha" in tags
    assert "beta" in tags
    assert "gamma" in tags
    assert len(tags) == 3


def test_get_notes_by_plugin():
    """Test getting notes by plugin source."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    ctx.write_note("Test/A.md", "A", plugin_source="career")
    ctx.write_note("Test/B.md", "B", plugin_source="github")
    ctx.write_note("Test/C.md", "C", plugin_source="career")

    career_notes = ctx.get_notes_by_plugin("career")
    assert len(career_notes) == 2
    paths = {n["path"] for n in career_notes}
    assert "Test/A.md" in paths
    assert "Test/C.md" in paths


def test_get_recent_notes():
    """Test getting recently modified notes."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    ctx.write_note("Test/A.md", "A", plugin_source="career")
    ctx.write_note("Test/B.md", "B", plugin_source="github")
    ctx.write_note("Test/C.md", "C", plugin_source="career")

    recent = ctx.get_recent_notes(limit=2)
    assert len(recent) == 2
    # Most recent first
    assert recent[0]["path"] == "Test/C.md"


def test_append_to_note():
    """Test appending to an existing note."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    ctx.write_note("Test/Append.md", "Original content", plugin_source="test")
    ctx.append_to_note("Test/Append.md", "\n\nAppended content")

    content = ctx.read_note("Test/Append.md")
    assert "Original content" in content
    assert "Appended content" in content


def test_add_section():
    """Test adding a new section to a note."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    ctx.write_note("Test/Section.md", "# Title\n\nBody", plugin_source="test")
    ctx.add_section("Test/Section.md", "New Section", "Section content")

    content = ctx.read_note("Test/Section.md")
    assert "## New Section" in content
    assert "Section content" in content


def test_note_exists_and_delete():
    """Test note_exists and delete_note."""
    _clean_db()
    _setup_test_plugin()
    ctx = ContextService()

    assert not ctx.note_exists("Test/DeleteMe.md")

    ctx.write_note("Test/DeleteMe.md", "To be deleted", plugin_source="test")
    assert ctx.note_exists("Test/DeleteMe.md")

    deleted = ctx.delete_note("Test/DeleteMe.md")
    assert deleted
    assert not ctx.note_exists("Test/DeleteMe.md")

    # Deleting non-existent returns False
    deleted = ctx.delete_note("Test/DeleteMe.md")
    assert not deleted


def test_reindex_note():
    """Test re-indexing a single note."""
    _clean_db()
    ctx = ContextService()

    ctx.write_note("Test/Reindex.md", "Machine learning content", tags=["ml"])

    # Search should find it
    results = ctx.search("machine learning", top_k=1)
    assert len(results) == 1
    assert results[0]["path"] == "Test/Reindex.md"

    # Re-index should work
    success = ctx.reindex_note("Test/Reindex.md")
    assert success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])