"""
Tests that vault I/O cannot escape the vault root via path traversal.

A plugin event payload is untrusted input: a path like '../../evil.md'
must never resolve to a file outside the vault. Both obsidian_service
(read/write) and ContextService (delete/exists) validate containment.
"""

import pytest

from services import obsidian_service
from services.context_service import ContextService
from services.obsidian_service import _resolve_vault_path


class TestResolveVaultPath:

    def test_plain_path_stays_inside(self, test_vault):
        target = _resolve_vault_path("Career/README.md", test_vault)
        assert target == (test_vault / "Career" / "README.md").resolve()

    def test_nested_path_stays_inside(self, test_vault):
        target = _resolve_vault_path("a/b/c.md", test_vault)
        assert target == (test_vault / "a" / "b" / "c.md").resolve()

    def test_dotdot_escape_rejected(self, test_vault):
        with pytest.raises(ValueError):
            _resolve_vault_path("../../evil.md", test_vault)

    def test_absolute_path_escape_rejected(self, test_vault):
        with pytest.raises(ValueError):
            _resolve_vault_path(str(test_vault.parent / "secret.md"), test_vault)

    def test_traversal_then_back_inside_allowed(self, test_vault):
        # 'a/../b.md' resolves inside the vault — must be allowed
        target = _resolve_vault_path("a/../b.md", test_vault)
        assert target == (test_vault / "b.md").resolve()


class TestReadWriteTraversalBlocked:

    def test_write_cannot_escape_vault(self, test_vault):
        with pytest.raises(ValueError):
            obsidian_service.write_note(
                "../../evil.md", "pwnd", plugin_source="test_plugin"
            )

    def test_read_cannot_escape_vault(self, test_vault):
        with pytest.raises(ValueError):
            obsidian_service.read_note("../../secret.txt")

    def test_legitimate_write_still_works(self, test_vault):
        path = obsidian_service.write_note(
            "Career/OK.md", "fine", plugin_source="test_plugin"
        )
        assert path == (test_vault / "Career" / "OK.md").resolve()
        assert (test_vault / "Career" / "OK.md").exists()


class TestContextServiceTraversalBlocked:

    def _ctx(self, test_db, test_vault) -> ContextService:
        return ContextService(conn=test_db, vault_path=test_vault)

    def test_delete_cannot_escape_vault(self, test_db, test_vault):
        ctx = self._ctx(test_db, test_vault)
        with pytest.raises(ValueError):
            ctx.delete_note("../../victim.md")

    def test_note_exists_false_for_escape(self, test_db, test_vault):
        ctx = self._ctx(test_db, test_vault)
        # note_exists is non-destructive: it returns False for escapes
        assert ctx.note_exists("../../victim.md") is False

    def test_delete_in_vault_works(self, test_db, test_vault):
        ctx = self._ctx(test_db, test_vault)
        ctx.write_note("Test/DeleteMe.md", "content", plugin_source="test_plugin")
        assert ctx.delete_note("Test/DeleteMe.md") is True
        assert not ctx.note_exists("Test/DeleteMe.md")
