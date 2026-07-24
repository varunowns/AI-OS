"""
Tests for the SQLite metadata layer (storage/db.py).
"""

from storage.db import NoteIndex, get_db


def _clean_db():
    """Drop all tables so each test starts fresh."""
    conn = get_db()
    conn.execute("DROP TABLE IF EXISTS notes")
    conn.commit()
    # Re-init schema
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notes (path TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', last_modified TEXT NOT NULL DEFAULT '', plugin_source TEXT NOT NULL DEFAULT '')"
    )
    conn.commit()


def test_index_and_retrieve():
    _clean_db()
    idx = NoteIndex(get_db())
    idx.index_note("Test/note.md", "Test Note", ["test", "example"], "test_plugin")
    note = idx.get_note("Test/note.md")
    assert note is not None
    assert note["title"] == "Test Note"
    assert "test" in note["tags"]
    assert note["plugin_source"] == "test_plugin"


def test_get_notes_by_tag():
    _clean_db()
    idx = NoteIndex(get_db())
    idx.index_note("Note/a.md", "A", ["alpha"], "p1")
    idx.index_note("Note/b.md", "B", ["beta"], "p1")
    idx.index_note("Note/c.md", "C", ["alpha", "beta"], "p2")

    alpha = idx.get_notes_by_tag("alpha")
    assert len(alpha) == 2

    beta = idx.get_notes_by_tag("beta")
    assert len(beta) == 2


def test_index_updates_existing():
    _clean_db()
    idx = NoteIndex(get_db())
    idx.index_note("Note/a.md", "Old Title", [], "p1")
    idx.index_note("Note/a.md", "New Title", ["updated"], "p2")
    note = idx.get_note("Note/a.md")
    assert note["title"] == "New Title"
    assert "updated" in note["tags"]
    assert note["plugin_source"] == "p2"


def test_get_nonexistent_returns_none():
    _clean_db()
    idx = NoteIndex(get_db())
    assert idx.get_note("Does/not/exist.md") is None