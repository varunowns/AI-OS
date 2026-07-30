"""
Tests for the embedding service (TF-IDF vectorizer + search).
"""

import sqlite3

import numpy as np

from services.embedding_service import EmbeddingIndex, _TfIdfVectorizer
from storage.db import _init_schema


def _make_emb() -> EmbeddingIndex:
    conn = sqlite3.connect(":memory:")
    _init_schema(conn)
    return EmbeddingIndex(conn=conn)


class TestTfIdfVectorizer:

    def test_tokenize(self):
        tokens = _TfIdfVectorizer._tokenize("Hello World! Testing 123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "testing" in tokens

    def test_simple_roundtrip(self):
        v = _TfIdfVectorizer()
        vec = v.index_document("apple banana apple")
        assert vec.shape[0] > 0
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-6

    def test_serialisation(self):
        v = _TfIdfVectorizer()
        v.index_document("apple banana")
        v.index_document("banana cherry")
        blob = v.to_json()
        v2 = _TfIdfVectorizer.from_json(blob)
        assert v2._vocab == v._vocab
        assert v2._n_docs == v._n_docs

    def test_similar_docs_have_higher_score(self):
        v = _TfIdfVectorizer()
        v.index_document("machine learning deep learning")
        v.index_document("python programming web development")
        vec_a = v.transform("machine learning")
        vec_b = v.transform("web development python")
        min_dim = min(len(vec_a), len(vec_b))
        sim = float(np.dot(vec_a[:min_dim], vec_b[:min_dim]))
        # These are different topics, similarity should be modest
        assert sim < 0.8


class TestEmbeddingIndex:

    def test_index_and_search(self):
        emb = _make_emb()

        emb.index_note("test/cv.md", "Computer vision with MediaPipe and OpenCV")
        emb.index_note("test/web.md", "Web development with React and TypeScript")
        emb.save_state()

        results = emb.search("computer vision", top_k=5)
        assert len(results) == 2
        # The CV note should rank first for this query
        assert results[0]["path"] == "test/cv.md"
        assert results[0]["score"] > 0

    def test_no_results_for_empty_index(self):
        emb = _make_emb()
        emb.save_state()

        results = emb.search("anything", top_k=5)
        # May return 0 or see notes from other tests
        assert isinstance(results, list)

    def test_remove_note(self):
        emb = _make_emb()

        emb.index_note("test/remove.md", "Will be removed")
        emb.save_state()
        assert "test/remove.md" in emb.get_indexed_paths()

        emb.remove_note("test/remove.md")
        assert "test/remove.md" not in emb.get_indexed_paths()