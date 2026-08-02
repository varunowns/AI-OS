"""
Tests for the embedding service (TF-IDF vectorizer + search).
"""

import numpy as np

from services.embedding_service import EmbeddingIndex, _TfIdfVectorizer


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
        v.add_document("a", "apple banana")
        v.add_document("b", "banana cherry")
        blob = v.to_json()
        v2 = _TfIdfVectorizer.from_json(blob)
        assert v2._vocab == v._vocab

    def test_add_document_replace_is_idempotent(self):
        """Re-adding a path must not double-count its terms."""
        v = _TfIdfVectorizer()
        v.add_document("a", "apple banana")
        v.add_document("b", "banana cherry")
        assert v._n_docs == 2
        assert v._doc_freq["banana"] == 2

        # Re-index "a" — its stats must be unchanged, not incremented
        v.add_document("a", "apple banana")
        assert v._n_docs == 2
        assert v._doc_freq["banana"] == 2
        assert v._doc_freq["apple"] == 1

        # Rewriting "a" with new content swaps its terms correctly
        v.add_document("a", "apple apple date")
        assert v._n_docs == 2
        assert v._doc_freq["apple"] == 1
        assert v._doc_freq["banana"] == 1
        assert v._doc_freq["date"] == 1

    def test_remove_document_decrements(self):
        v = _TfIdfVectorizer()
        v.add_document("a", "apple banana")
        v.add_document("b", "banana cherry")
        v.remove_document("a")
        assert v._n_docs == 1
        assert v._doc_freq["apple"] == 0
        assert "apple" not in v._doc_freq
        assert v._doc_freq["banana"] == 1

    def test_set_corpus_recomputes_exactly(self):
        v = _TfIdfVectorizer()
        v.add_document("a", "apple banana")
        v.add_document("b", "apple cherry")
        # Simulate a corrupt accumulated state
        v._n_docs = 99
        v._doc_freq["apple"] = 50
        v.set_corpus({"a": {"apple", "banana"}, "b": {"apple", "cherry"}})
        assert v._n_docs == 2
        assert v._doc_freq["apple"] == 2
        assert v._doc_freq["banana"] == 1

    def test_similar_docs_have_higher_score(self):
        v = _TfIdfVectorizer()
        v.index_document("machine learning deep learning")
        v.index_document("python programming web development")
        vec_a = v.transform("machine learning")
        vec_b = v.transform("web development python")
        min_dim = min(len(vec_a), len(vec_b))
        sim = float(np.dot(vec_a[:min_dim], vec_b[:min_dim]))
        assert sim < 0.8


class TestEmbeddingIndex:

    def test_index_and_search(self, embedding_index: EmbeddingIndex):
        emb = embedding_index
        emb.index_note("test/cv.md", "Computer vision with MediaPipe and OpenCV")
        emb.index_note("test/web.md", "Web development with React and TypeScript")
        emb.save_state()

        results = emb.search("computer vision", top_k=5)
        assert len(results) == 2
        assert results[0]["path"] == "test/cv.md"
        assert results[0]["score"] > 0

    def test_no_results_for_empty_index(self, embedding_index: EmbeddingIndex):
        results = embedding_index.search("anything", top_k=5)
        assert isinstance(results, list)

    def test_zero_vector_query_returns_no_results(self, embedding_index: EmbeddingIndex):
        """A query that tokenizes to nothing must not return arbitrary
        zero-score matches."""
        emb = embedding_index
        emb.index_note("test/cv.md", "Computer vision with MediaPipe")
        emb.save_state()

        for bad_query in ("", "   ", "a b c !!! ???", "@#$%^&*()"):
            assert emb.search(bad_query, top_k=5) == [], f"query {bad_query!r} returned results"

    def test_real_query_still_works(self, embedding_index: EmbeddingIndex):
        emb = embedding_index
        emb.index_note("test/cv.md", "Computer vision with MediaPipe")
        emb.save_state()
        assert len(emb.search("computer vision")) == 1

    def test_remove_note(self, embedding_index: EmbeddingIndex):
        emb = embedding_index
        emb.index_note("test/remove.md", "Will be removed")
        emb.save_state()
        assert "test/remove.md" in emb.get_indexed_paths()

        emb.remove_note("test/remove.md")
        assert "test/remove.md" not in emb.get_indexed_paths()
        # Corpus stats reflect the removal
        assert emb._vectorizer._n_docs == 0
        assert emb._vectorizer._doc_freq == {}

    def test_reindex_same_note_is_idempotent(self, embedding_index: EmbeddingIndex):
        """Re-indexing the same note must not inflate corpus stats."""
        emb = embedding_index
        emb.index_note("test/cv.md", "Computer vision with MediaPipe")
        emb.index_note("test/web.md", "Web development with React")
        n_docs_before = emb._vectorizer._n_docs
        df_before = dict(emb._vectorizer._doc_freq)

        emb.index_note("test/cv.md", "Computer vision with MediaPipe")
        assert emb._vectorizer._n_docs == n_docs_before
        assert dict(emb._vectorizer._doc_freq) == df_before

    def test_persistence_roundtrip(self, memory_db):
        """save_state/load must keep corpus stats consistent."""
        emb = EmbeddingIndex(conn=memory_db)
        emb.index_note("test/a.md", "apple banana")
        emb.index_note("test/b.md", "banana cherry")
        emb.save_state()

        emb2 = EmbeddingIndex(conn=memory_db)
        assert emb2._vectorizer._n_docs == 2
        assert emb2._vectorizer._doc_freq["banana"] == 2

    def test_rebuild_from_tokens_prunes_and_recomputes(self, memory_db):
        """rebuild_from_tokens must correct stale corpus stats and drop
        doc_tokens rows whose embedding is missing."""
        emb = EmbeddingIndex(conn=memory_db)
        emb.index_note("test/a.md", "apple banana")
        emb.index_note("test/b.md", "banana cherry")
        emb.save_state()

        # Corrupt stats + add an orphan doc_tokens row
        emb._vectorizer._n_docs = 99
        emb._vectorizer._doc_freq["apple"] = 50
        emb._conn.execute("INSERT INTO doc_tokens VALUES ('ghost.md', 'apple')")
        emb._conn.commit()

        emb.rebuild_from_tokens()
        assert emb._vectorizer._n_docs == 2
        assert emb._vectorizer._doc_freq["apple"] == 1
        assert emb._vectorizer._doc_freq["banana"] == 2
        # Orphan pruned
        assert "ghost.md" not in emb._vectorizer.all_docs()
