# Architecture

## Current

```
ai-os/
├── config.py                  # Environment-based settings
├── main.py                    # CLI entrypoint, auto-discovers plugins
├── core/
│   ├── event_bus.py           # In-memory pub/sub dispatcher
│   ├── plugin_loader.py       # Auto-discovery + registration
│   └── plugin_registry.py     # Permission declarations and enforcement
├── services/
│   ├── obsidian_service.py    # Vault read/write (enforces vault:read, vault:write)
│   ├── llm_service.py         # Anthropic API wrapper (enforces llm:call)
│   ├── embedding_service.py   # TF-IDF vectorizer + cosine similarity search
│   └── context_service.py     # Unified plugin-facing API (aggregates all services)
├── storage/
│   └── db.py                  # SQLite metadata index (notes table)
├── automation/
│   └── scheduler.py           # Background job loop with YAML schedule config
└── plugins/
    ├── career/                # note.summarize
    ├── github/                # repo.commits.summarize
    ├── resume/                # resume.review
    ├── search/                # note.search, note.reindex
    ├── ctx2img/               # note.toimage
    └── learning/              # learning.digest
```

## Key relationships

- **Event bus**: in-memory pub/sub. Plugins subscribe to events; CLI commands
  or the scheduler publish events. Handlers run synchronously in registration order.
- **Plugin permissions**: Each `manifest.yaml` declares permissions
  (`vault:read`, `vault:write`, `llm:call`). Services check these at runtime
  via the `@require()` decorator. A plugin can only call a service if it
  declared the matching permission.
- **Vault containment**: every vault-relative path is resolved through
  `_resolve_vault_path` and rejected with `ValueError` if it escapes the
  vault root. Plugin event payloads are untrusted, so `../../` traversal
  can never read, write, or delete files outside the vault.
- **ContextService**: The unified interface plugins should use. Aggregates
  `obsidian_service` (read/write), `NoteIndex` (tag queries, metadata),
  and `EmbeddingIndex` (semantic search). New plugins should prefer
  `from services.context_service import get_context` over importing
  individual services.
- **Storage**: SQLite database lives at `VAULT_PATH/.ai-os/metadata.db`.
  The vault's markdown files remain the source of truth — SQLite is a
  searchable index, not a replacement.
- **Search index is idempotent**: `EmbeddingIndex` tracks each note's
  tokens in a `doc_tokens` table, so re-indexing an existing note replaces
  its terms instead of double-counting them (which previously inflated
  IDF statistics and degraded ranking over time). Corpus stats are
  reconciled from `doc_tokens` on load, so the in-memory vectorizer always
  matches the persisted corpus. `reindex` is self-healing: notes that no
  longer exist on disk are pruned from both the metadata and embedding
  tables.

## Event catalog

| Event | Publisher | Plugin handler(s) | Payload |
|-------|-----------|-------------------|---------|
| `note.summarize` | CLI | career | source_note, output_note |
| `repo.commits.summarize` | CLI, scheduler | github | repo, count, output_note |
| `resume.review` | CLI | resume | resume_note, output_note |
| `note.search` | CLI | search | query, top_k |
| `note.reindex` | CLI | search | (none) |
| `note.toimage` | CLI | ctx2img | source_note, style |
| `learning.digest` | CLI | learning | tag, output_note |

## Scheduler (Hermes)

The scheduler runs plugin events on a timer. Schedule config is stored in
`VAULT_PATH/.ai-os/schedules.yaml`. Run with `python main.py serve`.

Each schedule's `last_run` timestamp is persisted in `schedules.yaml`,
so restarting the daemon does not immediately re-fire every enabled
schedule — only schedules whose interval has elapsed since their last
run execute.

Default schedule: daily GitHub commits summary for `varunowns/AI-OS`.

## Plugin contract

A plugin is a folder under `plugins/` with `manifest.yaml` + `plugin.py`
that exports `register(event_bus, plugin_name="", config=None)`. The
loader passes the plugin's manifest `config` dict to `register()` so a
plugin's defaults live in its manifest, not hardcoded in code. The
manifest declares the plugin's contract, enforced at load time by
`validate_manifest()` in `core/plugin_loader.py`:

| Field | Required | Shape |
|-------|----------|-------|
| `name` | yes | kebab-case string, matches the plugin dir |
| `version` | yes | semver `x.y.z` |
| `description` | yes | non-empty string |
| `subscribes` / `publishes` | no | list of non-empty event names |
| `permissions` | no | string or list of known permissions (`vault:read`, `vault:write`, `llm:call`) |
| `commands` | no | `cmd:event[:help]` entries (semicolon- or list-separated) |
| `config` | no | free-form plugin config |

Invalid or unparseable manifests are skipped loudly at load — a plugin is
never half-loaded, and one bad plugin never blocks the others.
`load_and_register(bus, plugins_dir=...)` returns a `PluginLoadReport`
(registered / skipped / failed) so callers can surface *why* a plugin is
missing; `discover_plugins(plugins_dir=...)` returns unvalidated metadata.
Both accept a custom directory for testing.

## Design decisions

- **One milestone at a time**: No speculative architecture. Each piece is
  built only when a real plugin needs it.
- **Plugin contract over convention**: manifests are validated at load time
  (see `Projects/AI-OS/Decisions/ADR-005` in the vault). Invalid contracts
  are skipped loudly, never half-loaded.
- **Python over TypeScript**: Best library fit for markdown/SQLite/LLM SDKs.
  See `Projects/AI-OS/Decisions/ADR-001` in the vault.
- **Vertical slice first**: One working plugin before full architecture.
  See ADR-002.
- **Semantic search before CLI polish**: Real content from multiple plugins
  needed a search layer before quality-of-life CLI improvements.
  See ADR-004.

## Not yet built

- Plugin sandboxing/isolation
- Multi-user
- Web UI
- Real image generation
- Additional plugins (linkedin, portfolio, calendar, email, etc.)
