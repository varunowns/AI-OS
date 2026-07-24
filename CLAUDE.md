# CLAUDE.md — Instructions for Claude Code

This file is read automatically at the start of every session. Follow it
before writing any code.

## What this project is

AI-OS: a personal platform that treats an Obsidian vault as permanent
memory and exposes functionality through small plugins that subscribe
to events on a shared event bus. See README.md for the current
architecture and what's deliberately not built yet.

## Rules (do not break these)

1. **One milestone at a time.** Don't build ahead of what's asked.
   If a prompt asks for a plugin, build only that plugin — don't also
   add the plugin registry, scheduler, or SQLite layer unless asked.
2. **Match the existing plugin shape.** Every plugin has a
   `manifest.yaml` + `plugin.py` with a `register(event_bus)` function
   that subscribes to events. Look at `plugins/career/` before writing
   a new plugin — copy its structure.
3. **Services stay provider-agnostic.** `services/llm_service.py` is
   the only place that talks to Claude's API. Plugins call `ask()`,
   never the Anthropic client directly.
4. **Obsidian is the source of truth.** Plugins read/write notes only
   through `services/obsidian_service.py`, never with raw file I/O.
5. **No new top-level architecture without being asked.** No event
   bus rewrites, no DI container, no permissions system, no scheduler
   — until a prompt explicitly asks for it.
6. **Update README.md** when you add a plugin or service, so it stays
   an accurate map of the project.
7. **Write a quick test** for new plugin logic where practical (a
   simple `pytest` function is enough — no test framework setup yet).
8. **Ask before assuming vault structure.** If a prompt references a
   note path you're not sure exists, ask rather than inventing folder
   names.

## Project memory lives in Obsidian, not just this repo

Official docs (`README.md`, `ARCHITECTURE.md`, `BUILD_PLAN.md`) live in
this repo — versioned, changes tracked in git history.

Design discussion lives in the vault, following the same convention as
other projects (EchoSign, Pebble): `Projects/AI-OS/` holds
`setup-and-environment.md`, `bugs-and-fixes.md`, `glossary.md`,
`Decisions/` (one ADR per architectural decision — see
`Decisions/ADR-001-python-over-typescript.md` for the format), and
dated `session-YYYY-MM-DD-handoff.md` notes.

This vault folder is separate from `AI_OS_VAULT_PATH`, which is the
vault AI-OS's *plugins* read/write at runtime (e.g. `Career/README.md`).
`Projects/AI-OS/` is about building this project; the rest of the vault
is what this project operates on.

## Workflow for each session

1. Read README.md and ARCHITECTURE.md (repo) and this file
2. Read `Projects/AI-OS/Decisions/`, `bugs-and-fixes.md`, and the most
   recent `session-YYYY-MM-DD-handoff.md` in the vault, if accessible
3. Understand the specific ask
4. Implement the smallest version that satisfies it
5. Test it runs (or write a quick test)
6. Update ARCHITECTURE.md (repo) if the architecture actually changed
7. If a real architectural decision was made, add a new ADR under
   `Projects/AI-OS/Decisions/` in the vault (don't edit past ADRs —
   write a new one that supersedes it if needed)
8. Log any bugs hit + fixes in `Projects/AI-OS/bugs-and-fixes.md`
9. Write a new `Projects/AI-OS/session-YYYY-MM-DD-handoff.md` in the
   vault summarizing what changed and what's next
10. Summarize what changed to the user
