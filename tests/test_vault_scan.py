"""
Tests for vault scanning and frontmatter parsing.
"""

from services.obsidian_service import parse_frontmatter, extract_tags_from_frontmatter, scan_vault


class TestFrontmatterParsing:

    def test_no_frontmatter(self):
        content = "# Hello\n\nJust a note."
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_simple_frontmatter(self):
        content = """---
title: Test Note
tags: ai learning
---

# Body here"""
        fm, body = parse_frontmatter(content)
        assert fm["title"] == "Test Note"
        assert fm["tags"] == "ai learning"
        assert "Body here" in body

    def test_list_tags(self):
        content = """---
title: List Tags
tags:
  - alpha
  - beta
---

Content"""
        fm, body = parse_frontmatter(content)
        assert fm["title"] == "List Tags"
        assert fm["tags"] == ["alpha", "beta"]

    def test_unclosed_frontmatter(self):
        """A single '---' without a closing one should be treated as body."""
        content = "---\ntitle: Broken"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content


class TestTagExtraction:

    def test_string_tags(self):
        tags = extract_tags_from_frontmatter({"tags": "ai learning paper"})
        assert "ai" in tags
        assert "learning" in tags
        assert "paper" in tags

    def test_list_tags(self):
        tags = extract_tags_from_frontmatter({"tags": ["ai", "learning"]})
        assert tags == ["ai", "learning"]

    def test_no_tags_key(self):
        tags = extract_tags_from_frontmatter({"title": "Test"})
        assert tags == []


class TestVaultScanning:

    def test_scan_returns_list(self):
        """At minimum, the vault should exist and return a list."""
        notes = scan_vault()
        assert isinstance(notes, list)

    def test_scan_finds_markdown(self):
        notes = scan_vault()
        if notes:
            assert all("path" in n for n in notes)
            assert all(n["path"].endswith(".md") for n in notes)
            assert all("title" in n for n in notes)
