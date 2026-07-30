"""
Tests for the SQLite metadata layer (storage/db.py).
"""

import sqlite3

from storage.db import NoteIndex, _init_schema


def _make_db() -> tuple[sqlite3.Connection, NoteIndex]:
    conn = sqlite3.connect(":memory:")
    _init_schema(conn)
    return conn, NoteIndex(conn)


def test_index_and_retrieve():
    _, idx = _make_db()
    idx.index_note("Test/note.md", "Test Note", ["test", "example"], "test_plugin")
    note = idx.get_note("Test/note.md")
    assert note is not None
    assert note["title"] == "Test Note"
    assert "test" in note["tags"]
    assert note["plugin_source"] == "test_plugin"


def test_get_notes_by_tag():
    _, idx = _make_db()
    idx.index_note("Note/a.md", "A", ["alpha"], "p1")
    idx.index_note("Note/b.md", "B", ["beta"], "p1")
    idx.index_note("Note/c.md", "C", ["alpha", "beta"], "p2")

    alpha = idx.get_notes_by_tag("alpha")
    assert len(alpha) == 2

    beta = idx.get_notes_by_tag("beta")
    assert len(beta) == 2


def test_index_updates_existing():
    _, idx = _make_db()
    idx.index_note("Note/a.md", "Old Title", [], "p1")
    idx.index_note("Note/a.md", "New Title", ["updated"], "p2")
    note = idx.get_note("Note/a.md")
    assert note["title"] == "New Title"
    assert "updated" in note["tags"]
    assert note["plugin_source"] == "p2"


def test_get_nonexistent_returns_none():
    _, idx = _make_db()
    assert idx.get_note("Does/not/exist.md") is None