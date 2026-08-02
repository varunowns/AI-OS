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

    Tracks per-document tokens so that rewriting or removing a note updates
    the corpus statistics correctly — re-indexing an existing note must not
    double-count its terms in the document frequencies (which previously
    inflated IDF and degraded search ranking over time).

    The vocabulary grows monotonically: once a token is seen its column is
    kept forever, so stored embedding vectors never change dimension. The
    corpus (per-doc tokens) is persisted separately in the doc_tokens table;
    the vectorizer's JSON blob carries only the vocabulary.
    """

    def __init__(self):
        self._vocab: dict[str, int] = {}        # token -> column index
        self._doc_freq: Counter[str] = Counter()  # token -> # docs containing it
        self._n_docs: int = 0
        self._docs: dict[str, set[str]] = {}    # path -> set of tokens

    # -- serialisation (vocabulary only; corpus lives in doc_tokens) -----

    def to_json(self) -> str:
        return json.dumps({"vocab": self._vocab})

    @classmethod
    def from_json(cls, blob: str) -> "_TfIdfVectorizer":
        obj = cls()
        data = json.loads(blob)
        obj._vocab = data.get("vocab", {})
        # Legacy blobs also carried doc_freq/n_docs. Keep them as a
        # best-effort starting point; they are superseded by the per-doc
        # token corpus on the next save or set_corpus call.
        obj._doc_freq = Counter(data.get("doc_freq", {}))
        obj._n_docs = data.get("n_docs", 0)
        return obj

    # -- tokenisation ------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9_\-]{2,}", text.lower())

    # -- corpus management -------------------------------------------

    def index_document(self, text: str) -> np.ndarray:
        """Register a new pathless document and return its vector.

        Kept for direct vectorizer use (and the pure-vectorizer tests).
        EmbeddingIndex uses add_document(path, ...) instead so that
        re-indexing an existing note does not double-count its terms.
        """
        tokens = set(self._tokenize(text))
        for t in tokens:
            if t not in self._vocab:
                self._vocab[t] = len(self._vocab)
            self._doc_freq[t] += 1
        self._n_docs += 1
        return self._compute_vector(tokens)

    def add_document(self, path: str, text: str) -> np.ndarray:
        """Index `path`'s content, replacing any prior version of it.

        Returns the TF‑IDF vector. If the path was already indexed, its
        old terms are first removed from the document frequencies, so
        rewriting a note keeps the corpus statistics exact.
        """
        tokens = set(self._tokenize(text))
        old = self._docs.get(path)
        if old is not None:
            for t in old:
                self._decrement(t)
        else:
            self._n_docs += 1
        for t in tokens:
            if t not in self._vocab:
                self._vocab[t] = len(self._vocab)
            self._doc_freq[t] += 1
        self._docs[path] = tokens
        return self._compute_vector(tokens)

    def remove_document(self, path: str) -> None:
        """Drop a document from the corpus, decrementing its counts."""
        old = self._docs.pop(path, None)
        if old is None:
            return
        for t in old:
            self._decrement(t)
        self._n_docs = max(0, self._n_docs - 1)

    def set_corpus(self, docs: dict[str, set[str]]) -> None:
        """Replace the corpus and recompute statistics exactly.

        Used at load time (from doc_tokens) and for a full resync. The
        vocabulary never shrinks, so stored vector dimensions are stable.
        """
        for tokens in docs.values():
            for t in tokens:
                if t not in self._vocab:
                    self._vocab[t] = len(self._vocab)
        self._docs = {p: set(tokens) for p, tokens in docs.items()}
        self._n_docs = len(self._docs)
        self._doc_freq = Counter(
            t for tokens in self._docs.values() for t in tokens
        )

    def all_docs(self) -> dict[str, set[str]]:
        """Return a copy of the corpus: path -> set of tokens."""
        return {p: set(t) for p, t in self._docs.items()}

    def vector_for_tokens(self, tokens: set[str]) -> np.ndarray:
        """Compute a TF‑IDF vector for already-tokenised text without
        updating the corpus. Used to rebuild cached embeddings at load."""
        return self._compute_vector(tokens)

    def _decrement(self, token: str) -> None:
        self._doc_freq[token] -= 1
        if self._doc_freq[token] <= 0:
            del self._doc_freq[token]

    # -- vectorisation -----------------------------------------------

    def transform(self, text: str) -> np.ndarray:
        """Vectorise `text` using the **current** vocabulary (no update)."""
        tokens = self._tokenize(text)
        if not tokens or not self._vocab:
            return np.zeros(len(self._vocab) or 1, dtype=np.float32)
        return self._compute_vector(tokens)

    def _compute_vector(self, tokens: set[str] | list[str]) -> np.ndarray:
        """Build a normalised TF‑IDF vector from token counts."""
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
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_tokens (
                path   TEXT PRIMARY KEY,
                tokens TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # -- vectorizer persistence ---------------------------------------

    def _load_vectorizer(self) -> _TfIdfVectorizer:
        row = self._conn.execute(
            "SELECT value FROM embedding_config WHERE key = ?", (_CONFIG_KEY,)
        ).fetchone()
        vectorizer = (
            _TfIdfVectorizer.from_json(row[0]) if row else _TfIdfVectorizer()
        )
        # Reconcile the corpus statistics from the per-doc token table.
        # doc_tokens is authoritative: it is updated together with every
        # embedding write, so a stale legacy doc_freq/n_docs blob is
        # superseded here.
        docs = {
            path: set(tokens.split(",")) if tokens else set()
            for path, tokens in self._conn.execute(
                "SELECT path, tokens FROM doc_tokens"
            ).fetchall()
        }
        vectorizer.set_corpus(docs)
        return vectorizer

    def _save_vectorizer(self) -> None:
        """Persist vocabulary + per-doc token corpus to SQLite.

        Writing the whole corpus keeps doc_tokens authoritative even
        after load-time reconciliation or a set_corpus resync.
        """
        blob = self._vectorizer.to_json()
        self._conn.execute(
            "INSERT OR REPLACE INTO embedding_config (key, value) VALUES (?, ?)",
            (_CONFIG_KEY, blob),
        )
        self._conn.execute("DELETE FROM doc_tokens")
        self._conn.executemany(
            "INSERT INTO doc_tokens (path, tokens) VALUES (?, ?)",
            [
                (path, ",".join(sorted(tokens)))
                for path, tokens in self._vectorizer.all_docs().items()
            ],
        )
        self._conn.commit()

    # -- public API ---------------------------------------------------

    def index_note(self, path: str, content: str) -> None:
        """Generate an embedding for `content` and store it.

        Re-indexing an existing path replaces its prior tokens in the
        corpus (see _TfIdfVectorizer.add_document), so rewriting a note
        does not inflate its document frequency. The doc_tokens row is
        kept in sync with the embeddings row.
        """
        vector = self._vectorizer.add_document(path, content)
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
        self._write_tokens(path)
        self._conn.commit()

    def save_state(self) -> None:
        """Persist the current vectorizer state to the DB.
        Call this after a batch of index_note calls."""
        self._save_vectorizer()

    def remove_note(self, path: str) -> None:
        """Delete an embedding entry when a note is removed."""
        self._vectorizer.remove_document(path)
        self._conn.execute("DELETE FROM embeddings WHERE path = ?", (path,))
        self._conn.execute("DELETE FROM doc_tokens WHERE path = ?", (path,))
        self._conn.commit()

    def _write_tokens(self, path: str) -> None:
        """Store one path's tokens in doc_tokens (used by index_note)."""
        tokens = self._vectorizer.all_docs().get(path, set())
        self._conn.execute(
            "INSERT OR REPLACE INTO doc_tokens (path, tokens) VALUES (?, ?)",
            (path, ",".join(sorted(tokens))),
        )

    def rebuild_from_tokens(self) -> None:
        """Recompute corpus statistics + cached embedding vectors from
        the doc_tokens table.

        Corrects any drift introduced by older index code (which
        double-counted document frequencies) and prunes doc_tokens rows
        whose embeddings row is missing.
        """
        docs = {
            path: set(tokens.split(",")) if tokens else set()
            for path, tokens in self._conn.execute(
                "SELECT path, tokens FROM doc_tokens"
            ).fetchall()
        }
        indexed_paths = set(self.get_indexed_paths())
        for stale in set(docs) - indexed_paths:
            del docs[stale]
        self._vectorizer.set_corpus(docs)
        for path, tokens in docs.items():
            vector = self._vectorizer.vector_for_tokens(tokens)
            self._conn.execute(
                "UPDATE embeddings SET vector = ? WHERE path = ?",
                (vector.astype(np.float32).tobytes(), path),
            )
        self._conn.commit()

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Semantic search: embed the query, then find the top_k most similar
        notes via brute-force cosine similarity over stored vectors.

        A query that tokenizes to nothing (empty, whitespace, or only
        single-char/symbol tokens) has no meaning, so it returns no
        results rather than an arbitrary zero-score match.
        """
        query_vec = self._vectorizer.transform(query)
        if not np.any(query_vec):
            return []

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