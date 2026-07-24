---
title: Command reference
description: Every zot command, grouped by read, write, batch, and admin — one line each.
---

:::note
This page is maintained by hand for now and will be **auto-generated** from the
CLI in a future release. If anything here disagrees with `zot <command> --help`,
trust the CLI.
:::

All commands accept the [global flags](#global-flags) below. Writes refuse to run
non-interactively without `--yes`.

## Read

| Command | What it does |
|---------|--------------|
| `zot search <query>` | Full-text search. `--limit`, `--all`, `--tag`, `--item-type`. |
| `zot get <key\|@citekey>` | One item's fields. |
| `zot cite <citekey>` | Resolve a Better BibTeX citekey → Zotero key, title, PDF path(s). |
| `zot pdf <key\|@citekey>` | Local path(s) of the item's PDF(s). |
| `zot collections` | List collections: key, #items, name. |
| `zot tags` | List tags: #items, tag. |
| `zot author <name>` | Items by an author. |
| `zot missing <field>` | Items lacking `abstract`/`date`/`doi`/`url`. `--collection`. |
| `zot stats` | Library analytics. |
| `zot recent` | Recently added items. `--limit`. |
| `zot bib <keys…>` | Formatted bibliography. `--style`. |
| `zot related <key>` | Related items. |
| `zot notes <key>` | List an item's notes. |
| `zot annotations <key>` | PDF highlights. `--to-note` to save as a note. |
| `zot lint` | Data-quality report. |
| `zot export <collection\|name>` | Export as `json`/`csv`/`csljson`/`bibtex`/`biblatex`/`ris`. `--out`. |

## Write

| Command | What it does |
|---------|--------------|
| `zot add doi\|isbn\|arxiv <id>` | Import by identifier. `--pdf`, `--collection`. |
| `zot set <field> <value> <keys…>` | Edit a field on one or more items. |
| `zot tag add\|rm <tag> <keys…>` | Add/remove a tag on items. |
| `zot tag rename <old> --new <n>` | Rename a tag library-wide. |
| `zot tag purge` | Remove unused tags. |
| `zot tag normalize` | Fold case/space tag variants. `--map`, `--dry-run`. |
| `zot move <collection> <keys…>` | Add items to a collection. |
| `zot collection <name>` | Create a (sub)collection. `--parent`. |
| `zot note <key>` | Add a child note. `--file`, `--if-not-exists`. |

## Batch (undoable, except merges)

| Command | What it does |
|---------|--------------|
| `zot apply <file.jsonl>` | Declarative batch edit; snapshots first. `--dry-run`. |
| `zot undo last\|<op-id>\|list` | Restore a prior `apply`/`enrich`. |
| `zot enrich --field <f> --source <s>` | Fill `doi`/`date`/`abstract` from `crossref`/`openalex`. `--dry-run`. |
| `zot dedupe` | Find/merge duplicates. `--by title\|doi`, `--fuzzy`, `--merge`. |

## Admin & escape hatch

| Command | What it does |
|---------|--------------|
| `zot init` | Generate token, write config, detect userID. |
| `zot ping` | Verify local API, bridge endpoint, userID. |
| `zot backup` | Snapshot `zotero.sqlite`; print the path. |
| `zot sync` | Trigger a Zotero sync. |
| `zot mcp` | Run the MCP server (stdio). `--allow-exec` for `run_javascript`. |
| `zot exec <js\|file\|->` | Run arbitrary privileged Zotero JS. `--dry-run`. |

## Global flags

| Flag | Effect |
|------|--------|
| `--json` | Machine-readable output. |
| `-q`, `--quiet` | Suppress progress notices. |
| `--debug` | Verbose diagnostics. |
| `--yes` | Confirm writes non-interactively. |
| `--base <url>` | Override the Zotero base URL (or `ZOTERO_AGENT_BASE`). |
| `--token <tok>` | Override the bridge token (or `ZOTERO_AGENT_TOKEN`). |
| `--user-id <id>` | Override the library userID (or `ZOTERO_AGENT_USER_ID`). |

Config precedence: **flags > `ZOTERO_AGENT_*` env > `~/.config/zotero-agent/config.json`**.
For large `--json` reads, `author`/`missing` omit abstracts by default; pass
`--detail full` to include them.

## Exit codes

| Code | Meaning |
|:----:|---------|
| 0 | ok |
| 1 | error |
| 2 | connection / exec failure |
| 3 | not found |
| 4 | config |
