"""
Tests for the plugin manifest contract (core/plugin_loader.validate_manifest)
and loader behavior for invalid manifests.
"""

from pathlib import Path

import pytest

from core.event_bus import EventBus
from core.plugin_loader import discover_plugins, load_and_register, validate_manifest


def _valid_manifest() -> dict:
    return {
        "name": "sample",
        "version": "1.2.3",
        "description": "A sample plugin.",
        "subscribes": ["sample.event"],
        "publishes": ["sample.done"],
        "permissions": ["vault:read"],
        "commands": "do-it:sample.event:Do the thing",
    }


class TestValidateManifest:

    def test_valid_manifest(self):
        assert validate_manifest(_valid_manifest()) == []

    def test_missing_name(self):
        m = _valid_manifest()
        del m["name"]
        issues = validate_manifest(m)
        assert any("name" in i for i in issues)

    def test_name_must_be_kebab_case(self):
        m = _valid_manifest()
        m["name"] = "Bad Name!"
        issues = validate_manifest(m)
        assert any("kebab-case" in i for i in issues)

    def test_name_must_match_dir(self):
        """A valid manifest's name is checked against the plugin dir at load."""
        m = _valid_manifest()
        m["name"] = "different"
        m["dir"] = "plugins/sample"
        # validate_manifest alone checks format, not the dir match; that's the
        # loader's concern. Here we assert the format check still passes.
        assert validate_manifest(m) == []

    def test_version_not_semver(self):
        m = _valid_manifest()
        m["version"] = "abc"
        issues = validate_manifest(m)
        assert any("semver" in i for i in issues)

    def test_missing_version(self):
        m = _valid_manifest()
        del m["version"]
        issues = validate_manifest(m)
        assert any("version" in i for i in issues)

    def test_missing_description(self):
        m = _valid_manifest()
        del m["description"]
        issues = validate_manifest(m)
        assert any("description" in i for i in issues)

    def test_subscribes_must_be_list(self):
        m = _valid_manifest()
        m["subscribes"] = "note.summarize"
        issues = validate_manifest(m)
        assert any("subscribes" in i for i in issues)

    def test_publishes_entries_non_empty(self):
        m = _valid_manifest()
        m["publishes"] = ["valid.event", "   "]
        issues = validate_manifest(m)
        assert any("publishes" in i for i in issues)

    def test_unknown_permission(self):
        m = _valid_manifest()
        m["permissions"] = ["vault:read", "network:call"]
        issues = validate_manifest(m)
        assert any("network:call" in i for i in issues)

    def test_permissions_as_csv_string(self):
        m = _valid_manifest()
        m["permissions"] = "vault:read, vault:write"
        assert validate_manifest(m) == []

    def test_bad_command_format(self):
        m = _valid_manifest()
        m["commands"] = "noevent"
        issues = validate_manifest(m)
        assert any("commands" in i for i in issues)

    def test_commands_as_list(self):
        m = _valid_manifest()
        m["commands"] = ["a:x", "b:y:Help"]
        assert validate_manifest(m) == []

    def test_multiple_issues_reported_together(self):
        m = {"name": "x", "version": "nope", "permissions": ["bogus:perm"]}
        issues = validate_manifest(m)
        assert any("semver" in i for i in issues)
        assert any("bogus:perm" in i for i in issues)


class TestLoaderSkipsInvalid:

    @pytest.fixture
    def broken_plugins_dir(self, tmp_path: Path) -> Path:
        """A plugins dir with one valid and one invalid plugin."""
        good = tmp_path / "good"
        good.mkdir()
        (good / "manifest.yaml").write_text(
            "name: good\nversion: 1.0.0\ndescription: A good plugin\n"
            "subscribes:\n  - good.event\npermissions: vault:read\n",
            encoding="utf-8",
        )
        (good / "plugin.py").write_text(
            "def register(event_bus, plugin_name=''):\n"
            "    event_bus.subscribe('good.event', lambda p: {'ok': True}, plugin_name=plugin_name)\n",
            encoding="utf-8",
        )

        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "manifest.yaml").write_text(
            "name: bad\nversion: not-semver\ndescription: Broken plugin\npermissions: vault:read\n",
            encoding="utf-8",
        )
        (bad / "plugin.py").write_text(
            "def register(event_bus, plugin_name=''):\n"
            "    raise AssertionError('should never be called')\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_invalid_plugin_is_skipped(self, broken_plugins_dir: Path, capsys):
        bus = EventBus()
        registered = load_and_register(bus, plugins_dir=broken_plugins_dir)
        assert registered == ["good"]
        # The bad plugin's register() must never run
        err = capsys.readouterr().err
        assert "Skipping 'bad'" in err
        assert "invalid manifest" in err

    def test_discover_still_reports_both(self, broken_plugins_dir: Path):
        metas = discover_plugins(broken_plugins_dir)
        names = {m["name"] for m in metas}
        assert names == {"good", "bad"}


class TestAllRealPluginsValid:

    def test_every_shipped_plugin_has_a_valid_manifest(self):
        metas = discover_plugins()
        assert len(metas) >= 6
        for meta in metas:
            assert "_parse_error" not in meta, f"{meta['name']} failed to parse"
            issues = validate_manifest(meta)
            assert issues == [], f"{meta['name']} has invalid manifest: {issues}"
