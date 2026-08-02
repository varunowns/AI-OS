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


def test_get_notes_by_tag_matches_whole_tag_only(note_index: NoteIndex):
    """A tag lookup must match whole comma-delimited tags, not substrings.

    Otherwise `learning` would match a note tagged `machine-learning` and
    `career` a note tagged `non-career`.
    """
    note_index.index_note("Note/ml.md", "ML", ["machine-learning"], "p1")
    note_index.index_note("Note/learn.md", "Learn", ["learning"], "p1")
    note_index.index_note("Note/career.md", "Career", ["career"], "p1")
    note_index.index_note("Note/other.md", "Other", ["non-career"], "p1")

    learning = {n["path"] for n in note_index.get_notes_by_tag("learning")}
    assert learning == {"Note/learn.md"}

    career = {n["path"] for n in note_index.get_notes_by_tag("career")}
    assert career == {"Note/career.md"}


def test_get_notes_by_tag_handles_leading_trailing_tags(note_index: NoteIndex):
    """Tags at the start/end of the comma list must still match."""
    note_index.index_note("Note/first.md", "First", ["alpha", "beta"], "p1")
    note_index.index_note("Note/last.md", "Last", ["beta", "gamma"], "p1")

    alpha = {n["path"] for n in note_index.get_notes_by_tag("alpha")}
    assert alpha == {"Note/first.md"}

    gamma = {n["path"] for n in note_index.get_notes_by_tag("gamma")}
    assert gamma == {"Note/last.md"}


def test_index_updates_existing(note_index: NoteIndex):
    note_index.index_note("Note/a.md", "Old Title", [], "p1")
    note_index.index_note("Note/a.md", "New Title", ["updated"], "p2")
    note = note_index.get_note("Note/a.md")
    assert note["title"] == "New Title"
    assert "updated" in note["tags"]
    assert note["plugin_source"] == "p2"


def test_get_nonexistent_returns_none(note_index: NoteIndex):
    assert note_index.get_note("Does/not/exist.md") is None
