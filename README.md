# AI-OS — Vertical Slice

This is the smallest end-to-end version of AI-OS: enough to prove the
core loop works before any of the bigger architecture (scheduler, DI
container, knowledge graph, 19 plugins) gets built.

## What it does

Run the `career` plugin against a note in your Obsidian vault:

1. Reads the note
2. Sends it to Claude with a summarize + extract-action-items prompt
3. Writes the result back to your vault as a new note

That single loop exercises the four building blocks every future
plugin will reuse:

- **Event bus** (`core/event_bus.py`) — plugins subscribe/publish, nothing else
- **Obsidian service** (`services/obsidian_service.py`) — vault read/write
- **LLM service** (`services/llm_service.py`) — provider-agnostic seam for Claude/GPT/Gemini later
- **Plugin shape** (`plugins/career/`) — manifest + `register(event_bus)` pattern

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env: set AI_OS_VAULT_PATH to your vault, and ANTHROPIC_API_KEY
```

## Run it

```bash
python main.py summarize "Career/README.md"
```

Optionally specify where the summary goes:

```bash
python main.py summarize "Career/README.md" --out "Career/README-summary.md"
```

## Folder structure

```
ai-os/
├── config.py                    # env-based settings
├── main.py                      # CLI entrypoint, wires everything together
├── core/
│   └── event_bus.py             # pub/sub dispatcher
├── services/
│   ├── obsidian_service.py      # vault read/write
│   └── llm_service.py           # Claude API wrapper
└── plugins/
    └── career/
        ├── manifest.yaml        # what the plugin declares/subscribes to
        └── plugin.py            # the actual logic
```

## What's deliberately NOT here yet

- Plugin registry / auto-discovery (plugins are registered by hand in `main.py`)
- Scheduler, background jobs, Hermes automation
- SQLite metadata layer
- Permissions/sandboxing
- The other 18 plugins from the original plan

The idea: get this loop solid and actually useful first, then add the
next piece of architecture only when a real plugin needs it — not
before. Once you've used this for a week and know what's annoying
about it, that's the signal for what to build next (a plugin registry,
if adding plugins by hand gets old; SQLite, if you need to query
across notes; a scheduler, if you want this running automatically).

## Next candidates, in likely order

1. **Plugin auto-discovery** — scan `plugins/` and call `register()` on
   each automatically, instead of hand-editing `main.py`
2. **A second plugin** (e.g. `github` — pull recent commits, summarize
   into a vault note) to prove the plugin shape generalizes
3. **SQLite metadata layer** — once you want to query/relate notes
   rather than just read/write them one at a time
