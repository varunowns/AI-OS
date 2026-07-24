# Architecture

## Current (vertical slice)

```
ai-os/
├── config.py
├── main.py
├── core/
│   └── event_bus.py
├── services/
│   ├── obsidian_service.py
│   └── llm_service.py
└── plugins/
    └── career/
        ├── manifest.yaml
        └── plugin.py
```

- **Event bus**: in-memory pub/sub, plugins subscribe/publish
- **Obsidian service**: only sanctioned way to read/write vault notes
- **LLM service**: only sanctioned way to call Claude — provider-agnostic seam
- **Plugin shape**: `manifest.yaml` + `plugin.py` with `register(event_bus)`

## Not yet built
Plugin auto-discovery, SQLite metadata layer, permissions, scheduler,
semantic search, additional plugins. See BUILD_PLAN.md for order.

## Why this lives here, not in the vault
This is the official, versioned description of the system — it should
change in lockstep with the code and show up in git history/diffs.
Design *discussion* (why a decision was made, alternatives considered)
lives in the vault as ADRs under `Projects/AI-OS/Decisions/`, linked
back here. Update this file only when the architecture actually
changes — not when it's planned to.
