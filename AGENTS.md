# AGENTS.md — driving Zotero with the `zot` CLI

This file gives coding/agent tools (Codex CLI, Gemini CLI, Aider, and any agent
that reads `AGENTS.md`) what they need to control a **local Zotero library**
through the `zot` command. It mirrors the Claude Code skill in `skill/SKILL.md`.

## Setup check

Run `zot ping`. It must show the local API up, the bridge endpoint answering
`1+1 == 2`, and a known userID. If it fails, the bridge plugin isn't installed —
see `docs/install.md`; do **not** work around it.

## Reading (fast, prefer these)

```bash
zot search "<query>" [--limit N] [--tag T] [--item-type book]   # full-text
zot get <KEY|@citekey>          # one item's fields
zot pdf <KEY|@citekey>          # local PDF path(s) — then read the file directly
zot collections | zot tags      # list
zot stats                       # analytics
zot missing abstract|date|doi [--collection C]
zot author "<name>"  |  zot recent  |  zot lint
```

Add `--json` to any command for machine-readable output.

## Writing (guarded — pass `--yes` for non-interactive)

```bash
zot add doi|isbn|arxiv <id> [--pdf] [--collection C]
zot set <field> <value> <KEY…> --yes
zot tag add|rm <tag> <KEY…> --yes   |   zot tag rename <old> --new <n> --yes
zot move <collection> <KEY…> --yes
zot note <KEY> --file note.html
zot dedupe [--by title|doi] [--fuzzy] [--merge --yes]
```

## Batch edits (preferred for anything at scale — undoable)

Write a JSONL file, one edit per line, then apply it:

```jsonl
{"key":"ABCD1234","set":{"abstract":"…","date":"2021"},"addTags":["review"]}
{"key":"EFGH5678","addToCollection":"To Read","removeTags":["old"]}
```

```bash
zot apply edits.jsonl --dry-run     # preview
zot apply edits.jsonl               # apply (snapshots first)
zot undo last                       # roll back the last apply/enrich
```

**You** decide the values (e.g. cleaned titles, topic tags) and write the JSONL;
`zot` performs the writes. The CLI never calls an LLM itself.

## Safety rules (follow these)

1. `zot backup` before any bulk or destructive change — always before `dedupe --merge`.
2. Prefer `--dry-run` and scope with `--collection` before touching the whole library.
3. Apply to 1–2 items and verify before the full set.
4. Deletions: prefer trash (`"trash": true` in `apply`), not permanent erase.
5. Merges are **not** reversible; everything via `zot apply`/`zot enrich` is.

Full JS recipe book: `skill/references/recipes.md`. PDF/notes workflow:
`skill/references/pdf-and-notes.md`.
