"""
Tests for the Context Service.

All vault I/O lands in the tmp test_vault and DB access uses the
in-memory test_db — the real Obsidian vault is never touched.
"""

from services.context_service import ContextService, get_context


def _ctx(test_db, test_vault) -> ContextService:
    """Build a ContextService pointed at the isolated test vault/DB."""
    return ContextService(conn=test_db, vault_path=test_vault)


def test_context_service_singleton():
    """Test that get_context returns the same instance."""
    ctx1 = get_context()
    ctx2 = get_context()
    assert ctx1 is ctx2


def test_read_write_note(test_db, test_vault):
    """Test reading and writing notes through context service."""
    ctx = _ctx(test_db, test_vault)

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


def test_find_by_tag(test_db, test_vault):
    """Test finding notes by tag."""
    ctx = _ctx(test_db, test_vault)

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


def test_search(test_db, test_vault):
    """Test semantic search."""
    ctx = _ctx(test_db, test_vault)

    ctx.write_note("Test/cv.md", "Computer vision with MediaPipe and OpenCV", tags=["cv"])
    ctx.write_note("Test/web.md", "Web development with React and TypeScript", tags=["web"])

    results = ctx.search("computer vision", top_k=5)
    assert len(results) >= 1
    assert results[0]["path"] == "Test/cv.md"
    assert results[0]["score"] > 0


def test_get_all_tags(test_db, test_vault):
    """Test getting all unique tags."""
    ctx = _ctx(test_db, test_vault)

    ctx.write_note("Test/A.md", "A", tags=["alpha", "beta"])
    ctx.write_note("Test/B.md", "B", tags=["beta", "gamma"])

    tags = ctx.get_all_tags()
    assert "alpha" in tags
    assert "beta" in tags
    assert "gamma" in tags
    assert len(tags) == 3


def test_get_notes_by_plugin(test_db, test_vault):
    """Test getting notes by plugin source."""
    ctx = _ctx(test_db, test_vault)

    ctx.write_note("Test/A.md", "A", plugin_source="career")
    ctx.write_note("Test/B.md", "B", plugin_source="github")
    ctx.write_note("Test/C.md", "C", plugin_source="career")

    career_notes = ctx.get_notes_by_plugin("career")
    assert len(career_notes) == 2
    paths = {n["path"] for n in career_notes}
    assert "Test/A.md" in paths
    assert "Test/C.md" in paths


def test_get_recent_notes(test_db, test_vault):
    """Test getting recently modified notes."""
    ctx = _ctx(test_db, test_vault)

    ctx.write_note("Test/A.md", "A", plugin_source="career")
    ctx.write_note("Test/B.md", "B", plugin_source="github")
    ctx.write_note("Test/C.md", "C", plugin_source="career")

    recent = ctx.get_recent_notes(limit=2)
    assert len(recent) == 2
    # Most recent first
    assert recent[0]["path"] == "Test/C.md"


def test_append_to_note(test_db, test_vault):
    """Test appending to an existing note."""
    ctx = _ctx(test_db, test_vault)

    ctx.write_note("Test/Append.md", "Original content", plugin_source="test")
    ctx.append_to_note("Test/Append.md", "\n\nAppended content")

    content = ctx.read_note("Test/Append.md")
    assert "Original content" in content
    assert "Appended content" in content


def test_add_section(test_db, test_vault):
    """Test adding a new section to a note."""
    ctx = _ctx(test_db, test_vault)

    ctx.write_note("Test/Section.md", "# Title\n\nBody", plugin_source="test")
    ctx.add_section("Test/Section.md", "New Section", "Section content")

    content = ctx.read_note("Test/Section.md")
    assert "## New Section" in content
    assert "Section content" in content


def test_note_exists_and_delete(test_db, test_vault):
    """Test note_exists and delete_note."""
    ctx = _ctx(test_db, test_vault)

    assert not ctx.note_exists("Test/DeleteMe.md")

    ctx.write_note("Test/DeleteMe.md", "To be deleted", plugin_source="test")
    assert ctx.note_exists("Test/DeleteMe.md")

    deleted = ctx.delete_note("Test/DeleteMe.md")
    assert deleted
    assert not ctx.note_exists("Test/DeleteMe.md")

    # Deleting non-existent returns False
    deleted = ctx.delete_note("Test/DeleteMe.md")
    assert not deleted


def test_reindex_note(test_db, test_vault):
    """Test re-indexing a single note."""
    ctx = _ctx(test_db, test_vault)

    ctx.write_note("Test/Reindex.md", "Machine learning content", tags=["ml"])

    # Search should find it
    results = ctx.search("machine learning", top_k=1)
    assert len(results) == 1
    assert results[0]["path"] == "Test/Reindex.md"

    # Re-index should work
    success = ctx.reindex_note("Test/Reindex.md")
    assert success
