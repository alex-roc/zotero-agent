---
title: Quickstart — CLI
description: The core zot commands for reading, editing, and batch-processing your local Zotero library.
---

This walks through `zot` as a plain command-line tool. If you want to drive it
from an AI agent instead, see [Quickstart: AI agent](/zotero-agent/getting-started/quickstart-agent/).
Make sure `zot ping` is green first — see [Install](/zotero-agent/getting-started/install/).

## Read your library

Reads hit Zotero's fast local HTTP API.

```bash
zot search "bolivia" --limit 10          # full-text search
zot search "x" --tag "#digitalización"   # filter by tag
zot search "x" --item-type book          # filter by type
zot get ABCD1234                          # one item (Zotero key or BBT citekey)
zot pdf ABCD1234                          # local path(s) of the item's PDF(s)
zot collections                           # key, #items, name
zot tags                                  # #items, tag
zot stats                                 # library analytics
```

Add `--json` to any command for machine-readable output. Listing commands stop
at `--limit` and print `showing N of M` on stderr — pass `--all` to paginate
through everything.

## Find and fill gaps

```bash
zot missing abstract --collection SS5MVVB6   # items lacking a field
zot missing doi                              # library-wide
zot enrich --field doi --source crossref --dry-run   # preview filling DOIs
zot enrich --field doi --source crossref             # apply (undoable)
zot lint                                     # data-quality report
```

`zot missing` uses a reliable `getField` check rather than Zotero's empty-string
search condition (which silently returns zero — see the
[JS recipes](/zotero-agent/reference/zot-exec-js/)).

## Import, dedupe, edit

```bash
zot add doi 10.1371/journal.pmed.0020124 --pdf   # import by identifier (+ OA PDF)
zot dedupe --by title --fuzzy                    # find near-duplicate titles
zot dedupe --merge --yes                         # merge (oldest = master)
zot set date 2021 ABCD1234 --yes                 # edit a field
zot tag add review ABCD1234 EFGH5678 --yes       # add a tag to items
zot tag normalize --dry-run                      # fold case/space tag variants
zot export "My Collection" --format bibtex --out refs.bib
```

Writes are **safe-by-default**: they refuse to run non-interactively without
`--yes`, and prompt on a TTY.

## Batch edits, undoably

`zot apply` is the batch primitive. Each line of a JSONL file describes one
item's edit:

```jsonl
{"key":"ABCD1234","set":{"date":"2021"},"addTags":["ml"],"addToCollection":"To Read"}
{"key":"EFGH5678","removeTags":["old"],"trash":false}
```

```bash
zot apply edits.jsonl --dry-run     # preview
zot apply edits.jsonl               # apply — snapshots the affected items first
zot undo last                       # roll it back
zot undo list                       # see prior operations
```

Because `apply` snapshots before writing, `zot undo` can restore it. (Merges are
the exception — they are **not** reversible; take a `zot backup` first.)

## The escape hatch

For anything the commands above don't cover, `zot exec` runs arbitrary
privileged Zotero JavaScript:

```bash
zot exec 'return Zotero.version;'                # inline
zot exec script.js                                # from a file
echo 'return 1+1;' | zot exec -                   # from stdin
zot exec script.js --dry-run                      # intercept writes, report only
```

See the [JS recipe book](/zotero-agent/reference/zot-exec-js/) for ready-made snippets.

## Global flags & exit codes

| Flag | Effect |
|------|--------|
| `--json` | machine-readable output |
| `-q`, `--quiet` | suppress progress notices |
| `--yes` | confirm writes non-interactively |
| `--base` / `--token` / `--user-id` | override config (or `ZOTERO_AGENT_*` env) |

Exit codes: **0** ok, **1** error, **2** connection/exec, **3** not-found,
**4** config. Full details in the [command reference](/zotero-agent/reference/commands/).
