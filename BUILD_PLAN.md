# Nordrun — Full Build Plan (Claude Code Prompt Playbook)

Run these prompts **in order**, one at a time, inside Claude Code at the
repo root. Each one builds on working code from the last — don't skip
ahead even if it feels slow. This is what "fully functional" actually
requires: every phase depends on the one before it being real and tested,
not just scaffolded.

Check off each phase as Claude Code completes and you've verified it
works before moving to the next prompt.

---

## ✅ Phase 0-2 — DONE (already built)
Core event bus, Obsidian read/write service, LLM service, career plugin.

---

## Phase 3 — Plugin auto-discovery
> "Scan the plugins/ folder, read each manifest.yaml, and call
> register(event_bus) on every plugin automatically instead of
> hand-wiring imports in main.py. Keep the career plugin working
> exactly as before. Add a test that confirms auto-discovery finds it."

## Phase 4 — SQLite metadata layer
> "Add storage/db.py using SQLite. Create a `notes` table (path, title,
> tags, last_modified, plugin_source). Update obsidian_service.write_note
> to also index the note into SQLite. Add a query function
> get_notes_by_tag(tag). Write tests."

## Phase 5 — Plugin registry + permissions (minimal)
> "Add core/plugin_registry.py that tracks which plugins are loaded and
> what events/permissions each declares in its manifest.yaml (e.g.
> vault:read, vault:write, llm:call). Enforce that a plugin can only call
> obsidian_service or llm_service if its manifest declares the matching
> permission. Update career's manifest.yaml accordingly."

## Phase 6 — Second plugin: GitHub
> "Add a github plugin (same shape as career) that pulls recent commits
> from a repo via the GitHub CLI or REST API and writes a summary note
> to the vault. This proves the plugin pattern generalizes beyond one
> plugin. Write tests."

## Phase 7 — Third plugin: Resume
> "Add a resume plugin that reads a resume note from the vault, and
> using the career plugin's recent summaries (query via SQLite from
> Phase 4), suggests concrete edits or additions. Write tests."

## Phase 8 — Knowledge graph / semantic search
> "Add services/embeddings_service.py using sentence-transformers (or
> the Claude API) to embed notes and store vectors alongside the SQLite
> metadata. Add a query function semantic_search(query, top_k) that
> returns the most relevant notes. Wire a new 'search' plugin that uses
> it."

> **Why this moved earlier:** Semantic search needs real content from
> multiple plugins (career + github + resume) to be worth testing, and
> every later phase (scheduler, ctx2img, learning digest) benefits from
> search existing rather than adding more isolated, unsearchable notes
> first. See ADR-004.

## Phase 9 — CLI polish + config validation
> "Improve main.py: auto-generate subcommands from loaded plugins'
> manifests instead of hardcoding 'summarize'. Validate .env config on
> startup and give a clear error if NORDRUN_VAULT_PATH or
> ANTHROPIC_API_KEY is missing or invalid."

## Phase 10 — Scheduler / automation (Hermes)
> "Add automation/scheduler.py using APScheduler (or a simple loop) that
> can run a plugin event on a schedule (e.g. 'run github plugin daily at
> 9am'). Store schedule config in a schedules.yaml. Add a CLI command
> `python main.py serve` that keeps the scheduler running."

## Phase 11 — ctx2img (context-to-image)
> "Add a ctx2img plugin: given a note or set of notes, build a text
> summary via llm_service, then generate an image (via an image
> generation API of your choice) that visually represents the content.
> Save the image into workspace/ctx2img/ and link it from the source
> note."

## Phase 12 — Learning plugin
> "Add a learning plugin that reads notes tagged #learning (via the
> Phase 4 SQLite query), summarizes concepts learned this week, and
> writes a weekly digest note with spaced-repetition style follow-up
> questions."

---

## Rules that apply to every phase (already in CLAUDE.md)

- One phase per prompt — don't let Claude Code build ahead
- New plugins must copy the existing plugin shape (manifest.yaml + plugin.py + register())
- All vault I/O goes through obsidian_service — never raw file access
- All LLM calls go through llm_service — never a provider SDK directly
- Update README.md whenever structure changes
- Write tests for new logic, however minimal

## After Phase 12

At this point you'll have a genuinely functional Nordrun: plugins,
permissions, scheduling, semantic search, and multiple real workflows.
Further plugins (linkedin, portfolio, interview, jobs, docker, terminal,
git, calendar, email, notifications) all now follow the exact same
one-prompt-per-plugin pattern — copy Phase 6 or 7's prompt shape and
swap in the new plugin's purpose.
