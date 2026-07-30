"""
Tests for the SQLite metadata layer (storage/db.py).
"""

from storage.db import NoteIndex


def test_index_and_retrieve(note_index: NoteIndex):
    note_index.index_note("Test/note.md", "Test Note", ["test", "example"], "test_plugin")
    note = note_index.get_note("Test/note.md")
    assert note is not None
    assert note["title"] == "Test Note"
    assert "test" in note["tags"]
    assert note["plugin_source"] == "test_plugin"


def test_get_notes_by_tag(note_index: NoteIndex):
    note_index.index_note("Note/a.md", "A", ["alpha"], "p1")
    note_index.index_note("Note/b.md", "B", ["beta"], "p1")
    note_index.index_note("Note/c.md", "C", ["alpha", "beta"], "p2")

    alpha = note_index.get_notes_by_tag("alpha")
    assert len(alpha) == 2

    beta = note_index.get_notes_by_tag("beta")
    assert len(beta) == 2


def test_index_updates_existing(note_index: NoteIndex):
    note_index.index_note("Note/a.md", "Old Title", [], "p1")
    note_index.index_note("Note/a.md", "New Title", ["updated"], "p2")
    note = note_index.get_note("Note/a.md")
    assert note["title"] == "New Title"
    assert "updated" in note["tags"]
    assert note["plugin_source"] == "p2"


def test_get_nonexistent_returns_none(note_index: NoteIndex):
    assert note_index.get_note("Does/not/exist.md") is None
