"""
Tests for the GitHub plugin.
"""

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def test_discover_finds_github():
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "github" in names


def test_github_manifest_has_permissions():
    plugins = discover_plugins()
    gh = next(p for p in plugins if p["name"] == "github")
    assert gh.get("version") == "0.1.0"
    perms = gh.get("permissions", "")
    assert "vault:read" in perms
    assert "vault:write" in perms
    assert "llm:call" in perms


def test_github_registers_event():
    bus = EventBus()
    report = load_and_register(bus)
    assert "github" in report.registered
    assert "repo.commits.summarize" in bus.registered_events()


def test_both_plugins_loaded():
    bus = EventBus()
    report = load_and_register(bus)
    assert "career" in report.registered
    assert "github" in report.registered


class TestFormatCommits:
    """The pure commit-formatting helper."""

    def test_empty_list(self):
        from plugins.github.plugin import _format_commits
        assert _format_commits([]) == ""

    def test_single_commit(self):
        from plugins.github.plugin import _format_commits
        out = _format_commits([{"sha": "abc1234", "author": "Varun", "message": "Fix bug"}])
        assert out == "  abc1234  Varun  Fix bug"

    def test_multiple_commits_newline_separated(self):
        from plugins.github.plugin import _format_commits
        out = _format_commits([
            {"sha": "abc1234", "author": "A", "message": "First"},
            {"sha": "def5678", "author": "B", "message": "Second"},
        ])
        assert out == "  abc1234  A  First\n  def5678  B  Second"


class TestFetchCommitsParsing:
    """_fetch_commits' data extraction (network mocked)."""

    def test_parses_first_line_of_message(self, monkeypatch):
        import json
        import plugins.github.plugin as gh

        def fake_urlopen(req, timeout=15):
            class Resp:
                def read(self):
                    return json.dumps([
                        {"sha": "abcdef1234567", "commit": {
                            "message": "Header line\n\nBody line\n",
                            "author": {"name": "Varun"},
                        }},
                    ]).encode("utf-8")
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return Resp()

        monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
        commits = gh._fetch_commits("varunowns", "Nordrun", count=5)
        assert commits == [{"sha": "abcdef1", "message": "Header line", "author": "Varun"}]

    def test_http_error_raises_runtime_error(self, monkeypatch):
        import plugins.github.plugin as gh
        import urllib.error

        def raise_http(*a, **k):
            raise urllib.error.HTTPError("url", 404, "Not Found", None, None)

        monkeypatch.setattr(gh.urllib.request, "urlopen", raise_http)
        try:
            gh._fetch_commits("v4run", "missing", count=5)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "404" in str(e)