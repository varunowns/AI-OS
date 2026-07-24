"""
Embedding Service
-----------------
Generates vector embeddings for vault notes using a pure‑numpy TF-IDF
vectorizer + cosine similarity. No heavy ML dependencies — works on any
Python version including 3.14.

The vectorizer state (vocabulary, document frequencies) is persisted to
SQLite so it survives across process boundaries: you can reindex in one
process and search in another.

For better semantic quality (when running on Python 3.10/3.11), swap
the _TfIdfVectorizer below for a sentence‑transformers model.

Usage:
    from services.embedding_service import EmbeddingIndex
    emb = EmbeddingIndex()
    emb.index_note("Career/README.md", "Career overview content...")
    results = emb.search("machine learning projects", top_k=5)
"""

import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from config import VAULT_PATH
from storage.db import get_db


# ---------------------------------------------------------------------------
# Pure‑numpy TF‑IDF vectorizer (no sklearn/sentence‑transformers needed)
# ---------------------------------------------------------------------------

class _TfIdfVectorizer:
    """A minimal TF‑IDF vectorizer using only Python stdlib + numpy.

    Vocabulary and document frequencies can be serialised to / loaded from
    a JSON blob so that index and query can run in separate processes.
    """

    def __init__(self):
        self._vocab: dict[str, int] = {}      # token -> column index
        self._doc_freq: Counter[str] = Counter()
        self._n_docs: int = 0

    # -- serialisation ------------------------------------------------

    def to_json(self) -> str:
        return json.dumps({
            "vocab": self._vocab,
            "doc_freq": dict(self._doc_freq),
            "n_docs": self._n_docs,
        })

    @classmethod
    def from_json(cls, blob: str) -> "_TfIdfVectorizer":
        obj = cls()
        data = json.loads(blob)
        obj._vocab = data["vocab"]
        obj._doc_freq = Counter(data["doc_freq"])
        obj._n_docs = data["n_docs"]
        return obj

    # -- tokenisation ------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9_\-]{2,}", text.lower())

    # -- indexing ----------------------------------------------------

    def index_document(self, text: str) -> np.ndarray:
        """Update vocabulary / df and return the TF‑IDF vector for `text`."""
        tokens = self._tokenize(text)
        if not tokens:
            return np.zeros(len(self._vocab) or 1, dtype=np.float32)

        # Add new tokens to vocabulary
        for t in set(tokens):
            if t not in self._vocab:
                self._vocab[t] = len(self._vocab)

        # Update document frequency
        for t in set(tokens):
            self._doc_freq[t] += 1
        self._n_docs += 1

        # Build vector
        dim = len(self._vocab)
        vec = np.zeros(dim, dtype=np.float32)
        tf = Counter(tokens)
        for token, count in tf.items():
            if token in self._vocab:
                idx = self._vocab[token]
                idf = math.log((self._n_docs + 1) / (self._doc_freq.get(token, 0) + 1)) + 1
                vec[idx] = (1 + math.log(count)) * idf

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def transform(self, text: str) -> np.ndarray:
        """Vectorise `text` using the **current** vocabulary (no update)."""
        tokens = self._tokenize(text)
        if not tokens or not self._vocab:
            return np.zeros(len(self._vocab) or 1, dtype=np.float32)

        dim = len(self._vocab)
        vec = np.zeros(dim, dtype=np.float32)
        tf = Counter(tokens)
        for token, count in tf.items():
            if token in self._vocab:
                idx = self._vocab[token]
                idf = math.log((self._n_docs + 1) / (self._doc_freq.get(token, 0) + 1)) + 1
                vec[idx] = (1 + math.log(count)) * idf

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


# ---------------------------------------------------------------------------
# Embedding persistence + search
# ---------------------------------------------------------------------------

_CONFIG_KEY = "tfidf_vectorizer"


class EmbeddingIndex:
    """Stores and queries note embeddings alongside the SQLite metadata."""

    def __init__(self, conn: sqlite3.Connection | None = None):
        self._conn = conn or get_db()
        self._init_schema()
        self._vectorizer = self._load_vectorizer()

    # -- schema -------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                path TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # -- vectorizer persistence ---------------------------------------

    def _load_vectorizer(self) -> _TfIdfVectorizer:
        row = self._conn.execute(
            "SELECT value FROM embedding_config WHERE key = ?", (_CONFIG_KEY,)
        ).fetchone()
        if row:
            return _TfIdfVectorizer.from_json(row[0])
        return _TfIdfVectorizer()

    def _save_vectorizer(self) -> None:
        blob = self._vectorizer.to_json()
        self._conn.execute(
            "INSERT OR REPLACE INTO embedding_config (key, value) VALUES (?, ?)",
            (_CONFIG_KEY, blob),
        )
        self._conn.commit()

    # -- public API ---------------------------------------------------

    def index_note(self, path: str, content: str) -> None:
        """Generate an embedding for `content` and store it."""
        vector = self._vectorizer.index_document(content)
        vector_bytes = vector.astype(np.float32).tobytes()

        self._conn.execute(
            """
            INSERT INTO embeddings (path, vector, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(path) DO UPDATE SET
                vector=excluded.vector,
                updated_at=excluded.updated_at
            """,
            (path, vector_bytes),
        )
        self._conn.commit()

    def save_state(self) -> None:
        """Persist the current vectorizer state to the DB.
        Call this after a batch of index_note calls."""
        self._save_vectorizer()

    def remove_note(self, path: str) -> None:
        """Delete an embedding entry when a note is removed."""
        self._conn.execute("DELETE FROM embeddings WHERE path = ?", (path,))
        self._conn.commit()

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Semantic search: embed the query, then find the top_k most similar
        notes via brute-force cosine similarity over stored vectors.
        """
        query_vec = self._vectorizer.transform(query)

        rows = self._conn.execute(
            "SELECT path, vector FROM embeddings"
        ).fetchall()

        if not rows:
            return []

        scores = []
        for path, vector_bytes in rows:
            stored_vec = np.frombuffer(vector_bytes, dtype=np.float32)
            min_dim = min(len(query_vec), len(stored_vec))
            if min_dim == 0:
                continue
            q = query_vec[:min_dim]
            s = stored_vec[:min_dim]
            q_norm = np.linalg.norm(q)
            s_norm = np.linalg.norm(s)
            if q_norm == 0 or s_norm == 0:
                sim = 0.0
            else:
                sim = float(np.dot(q / q_norm, s / s_norm))
            scores.append((path, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        top = scores[:top_k]

        results = []
        for path, score in top:
            note = self._conn.execute(
                "SELECT title, tags, plugin_source FROM notes WHERE path = ?",
                (path,),
            ).fetchone()
            results.append({
                "path": path,
                "score": round(score, 4),
                "title": note[0] if note else "",
                "tags": note[1].split(",") if note and note[1] else [],
                "plugin_source": note[2] if note else "",
            })

        return results

    def get_indexed_paths(self) -> list[str]:
        rows = self._conn.execute("SELECT path FROM embeddings").fetchall()
        return [r[0] for r in rows]