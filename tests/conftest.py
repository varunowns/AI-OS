"""
Shared test fixtures.

Usage in tests:
    def test_something(memory_db, test_plugin, note_index):
        note_index.index_note("Test/a.md", "Title", ["tag1"], "plugin")
        results = note_index.get_notes_by_tag("tag1")
        assert len(results) == 1

Available fixtures:
    - memory_db: in-memory SQLite connection with the notes schema
    - note_index: NoteIndex backed by memory_db
    - embedding_index: EmbeddingIndex backed by memory_db
    - test_plugin: registers "test_plugin" with vault:read, vault:write, llm:call permissions
"""

import sqlite3

import pytest

from core.plugin_registry import register_plugin, set_active_plugin
from services.embedding_service import EmbeddingIndex
from storage.db import NoteIndex, _init_schema


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Create a clean in-memory SQLite database with the notes schema."""
    conn = sqlite3.connect(":memory:")
    _init_schema(conn)
    return conn


@pytest.fixture
def note_index(memory_db: sqlite3.Connection) -> NoteIndex:
    """NoteIndex backed by an in-memory SQLite database."""
    return NoteIndex(memory_db)


@pytest.fixture
def embedding_index(memory_db: sqlite3.Connection) -> EmbeddingIndex:
    """EmbeddingIndex backed by an in-memory SQLite database."""
    return EmbeddingIndex(conn=memory_db)


@pytest.fixture(autouse=True)
def test_context() -> None:
    """Automatically set up test plugin context for permission checks.
    Clears and re-registers the plugin to ensure a clean state per test."""
    register_plugin("test_plugin", ["vault:read", "vault:write", "llm:call"])
    set_active_plugin("test_plugin")
    yield
    set_active_plugin(None)
