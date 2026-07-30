"""
SQLite Metadata Layer
---------------------
Stores note metadata (path, title, tags, last_modified, plugin_source)
alongside the vault files. The vault's markdown files remain the source
of truth — this is a searchable index, not a replacement.

Usage:
    from storage.db import get_db, NoteIndex
    idx = NoteIndex(get_db())
    idx.index_note("Career/README.md", "Career Overview", ["career"], "career")
    results = idx.get_notes_by_tag("career")
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import VAULT_PATH

_DB_PATH = VAULT_PATH / ".ai-os" / "metadata.db"
_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating the DB + schema
    on first access."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(conn)
        _local.conn = conn
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            path          TEXT PRIMARY KEY,
            title         TEXT NOT NULL DEFAULT '',
            tags          TEXT NOT NULL DEFAULT '',
            last_modified TEXT NOT NULL DEFAULT '',
            plugin_source TEXT NOT NULL DEFAULT ''
        )
        """
    )


def _row_to_note(row: tuple) -> dict[str, Any]:
    """Convert a SQLite row from the notes table to a dict."""
    return {
        "path": row[0],
        "title": row[1],
        "tags": row[2].split(",") if row[2] else [],
        "last_modified": row[3],
        "plugin_source": row[4],
    }


class NoteIndex:
    """High-level interface for indexing and querying vault notes."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def index_note(
        self,
        path: str,
        title: str = "",
        tags: list[str] | None = None,
        plugin_source: str = "",
    ) -> None:
        """Insert or update metadata for a vault note."""
        now = datetime.now(timezone.utc).isoformat()
        tags_str = ",".join(tags) if tags else ""
        self._conn.execute(
            """
            INSERT INTO notes (path, title, tags, last_modified, plugin_source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                title=excluded.title,
                tags=excluded.tags,
                last_modified=excluded.last_modified,
                plugin_source=excluded.plugin_source
            """,
            (path, title, tags_str, now, plugin_source),
        )
        self._conn.commit()

    def get_notes_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Return all notes whose tags field contains `tag`."""
        cursor = self._conn.execute(
            "SELECT path, title, tags, last_modified, plugin_source FROM notes WHERE tags LIKE ?",
            (f"%{tag}%",),
        )
        return [_row_to_note(r) for r in cursor.fetchall()]

    def get_all_paths(self) -> list[str]:
        """Return all indexed note paths."""
        cursor = self._conn.execute("SELECT path FROM notes")
        return [r[0] for r in cursor.fetchall()]

    def delete_note(self, path: str) -> None:
        """Remove a note from the index by path."""
        self._conn.execute("DELETE FROM notes WHERE path = ?", (path,))
        self._conn.commit()

    def get_note(self, path: str) -> dict[str, Any] | None:
        """Look up a single note by path."""
        cursor = self._conn.execute(
            "SELECT path, title, tags, last_modified, plugin_source FROM notes WHERE path = ?",
            (path,),
        )
        row = cursor.fetchone()
        return _row_to_note(row) if row else None