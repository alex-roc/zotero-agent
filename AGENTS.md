# AGENTS.md — driving Zotero with the `zot` CLI

This file gives coding/agent tools (Codex CLI, Gemini CLI, Aider, and any agent
that reads `AGENTS.md`) what they need to control a **local Zotero library**
through the `zot` command. It mirrors the Claude Code skill in `skill/SKILL.md`.

## Setup check

Run `zot ping`. It must show the local API up, the bridge endpoint answering
`1+1 == 2`, and a known userID. If it fails, the bridge plugin isn't installed —
see `docs/install.md`; do **not** work around it.

If Zotero is closed, or the plugin wants the restart Zotero keeps asking for,
`zot restart --yes` handles it (`--plugin` reloads only the bridge, leaving
Zotero open) and waits for the endpoint to answer again. Ask the user first: a
restart can lose unsaved work in Zotero.

## Reading (fast, prefer these)

```bash
zot search "<query>" [--limit N] [--tag T] [--item-type book]   # full-text
zot get <KEY|@citekey>          # one item's fields
zot pdf <KEY|@citekey>          # local PDF path(s) — then read the file directly
zot collections | zot tags      # list
zot stats                       # analytics
zot missing abstract|date|doi [--collection C]
zot author "<name>"  |  zot recent  |  zot lint
zot toc show|scan <KEY>         # a PDF's table of contents (needs the [toc] extra)
zot export <COLLECTION> --recursive   # collections do NOT include subcollections by default
```

Add `--json` to any command for machine-readable output. Items always come back
in one flat shape (`key, citekey, type, title, date, year, creators, venue, doi,
url, tags, abstract`); `get`/`search`/`recent` take `--raw` for Zotero's own
`{data:{itemType, DOI, citationKey}}` format. For bibliographies prefer
`zot export --format biblatex` (native exporter) over anything that goes through
Better BibTeX's export cache, which can serve stale citekeys.

## Writing (guarded — pass `--yes` for non-interactive)

```bash
zot add doi|isbn|arxiv <id> [--pdf] [--collection C] [--check-duplicate]
zot attach <KEY> --file <PATH> | --url <URL> [--link]   # attach to an existing item
zot pdf-fetch <KEY…> | --collection C                   # open-access PDF lookup
zot set <field> <value> <KEY…> --yes
zot tag add|rm <tag> <KEY…> --yes   |   zot tag rename <old> --new <n> --yes
zot move <collection> <KEY…> --yes
zot note <KEY> --file note.html
zot dedupe [--by title|doi] [--fuzzy] [--merge --yes]
zot toc set|auto|clear <KEY> [--from f] --dry-run   # write a PDF's outline
```

`zot toc` is the one command that modifies the **PDF file** rather than the
library. `scan --json` gives you the evidence (the book's own contents page, or
typographic heading candidates); you decide the hierarchy; `set --from -` writes
it. Prefer `contentsToc` over `headingCandidates`, pass `physicalPage` through
unchanged instead of computing pages yourself, and `zot undo last` restores the
previous outline.

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
