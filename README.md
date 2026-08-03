# Nordrun — Personal AI Platform

Nordrun is an autonomous AI operating system: a personal platform that
treats an Obsidian vault as permanent memory and exposes functionality
through small plugins that subscribe to events on a shared event bus.

## What it does

Six plugins running over your Obsidian vault:

| Plugin | Command | What it does |
|--------|---------|-------------|
| **career** | `summarize` | Reads a note, summarizes it via Claude, extracts action items |
| **github** | `commits` | Pulls recent GitHub commits and writes a summary note |
| **resume** | `review-resume` | Reviews a resume against recent career notes |
| **search** | `search` | Semantic search over vault notes |
| **ctx2img** | `toimage` | Generates a visual representation from a note's content |
| **learning** | `digest` | Weekly learning digest with review questions |

```bash
# List all available commands
python main.py --help

# Summarize a note
python main.py summarize "Career/README.md"

# Search vault content
python main.py search "machine learning"

# Generate a learning digest
python main.py digest

# Run the background scheduler
python main.py serve
```

All plugins share the same shape: `manifest.yaml` + `plugin.py` with a
`register(event_bus)` function. See `plugins/career/` for the reference
implementation.

## Architecture

```
nordrun/
├── config.py                  # Environment-based settings
├── main.py                    # CLI entrypoint, auto-discovers plugins
├── core/
│   ├── event_bus.py           # Pub/sub dispatcher
│   ├── plugin_loader.py       # Auto-discovers and registers plugins
│   └── plugin_registry.py     # Plugin permissions and tracking
├── services/
│   ├── obsidian_service.py    # Vault read/write
│   ├── llm_service.py         # LLM provider wrapper
│   ├── embedding_service.py   # TF-IDF semantic search
│   └── context_service.py     # Unified plugin-facing API
├── storage/
│   └── db.py                  # SQLite metadata index
├── automation/
│   └── scheduler.py           # Background job scheduler (Hermes)
└── plugins/
    ├── career/                # Note summarization
    ├── github/                # GitHub commits
    ├── resume/                # Resume review
    ├── search/                # Semantic search + reindex
    ├── ctx2img/               # Context-to-image
    └── learning/              # Weekly learning digest
```

**Design principles:**

- **Event-driven**: plugins subscribe/publish events, nothing else
- **Obsidian is source of truth**: all vault I/O goes through the Obsidian service, never raw file access
- **Provider-agnostic LLM**: only `services/llm_service.py` talks to the API
- **Plugin permissions**: services enforce declared permissions from `manifest.yaml`
- **ContextService**: plugins access vault content through a unified API, not raw imports

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env: set NORDRUN_VAULT_PATH to your vault, and ANTHROPIC_API_KEY
```

## Built-in commands

| Command | Description |
|---------|-------------|
| `reindex` | Re-index all vault notes for semantic search |
| `serve` | Start the background scheduler (Hermes) |

## What's deliberately not here yet

- Plugin sandboxing/isolation enforcement
- Multi-user support
- Web UI (this is a CLI app)
- Real image generation (ctx2img generates SVG placeholders)
