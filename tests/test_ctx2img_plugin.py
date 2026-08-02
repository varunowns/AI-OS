"""
Tests for the ctx2img plugin.
"""

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register


def test_discover_finds_ctx2img():
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "ctx2img" in names


def test_ctx2img_registers_event():
    bus = EventBus()
    report = load_and_register(bus)
    assert "ctx2img" in report.registered
    assert "note.toimage" in bus.registered_events()


def test_sanitise_filename():
    from plugins.ctx2img.plugin import _sanitise_filename
    assert _sanitise_filename("Career/README.md") == "Career-README"
    assert _sanitise_filename("Dev/some-notes.md") == "Dev-some-notes"


class TestGenerateSvgPlaceholder:
    """The pure SVG placeholder generator."""

    def test_returns_valid_svg_bytes(self):
        from plugins.ctx2img.plugin import _generate_svg_placeholder
        data = _generate_svg_placeholder("A vivid summary", "line art")
        assert isinstance(data, bytes)
        text = data.decode("utf-8")
        assert text.startswith("<svg")
        assert text.endswith("</svg>")
        assert "A vivid summary" in text

    def test_long_summary_truncated(self):
        from plugins.ctx2img.plugin import _generate_svg_placeholder
        data = _generate_svg_placeholder("word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11", "")
        text = data.decode("utf-8")
        # Only the first 6 words + "..." should be in the label
        assert "word1" in text
        assert "..." in text
        assert "word11" not in text

    def test_empty_summary_still_valid(self):
        from plugins.ctx2img.plugin import _generate_svg_placeholder
        data = _generate_svg_placeholder("", "style")
        text = data.decode("utf-8")
        assert text.startswith("<svg")
        assert text.endswith("</svg>")


def test_all_plugins_loaded():
    bus = EventBus()
    report = load_and_register(bus)
    assert len(report.registered) >= 5
    assert "ctx2img" in report.registered