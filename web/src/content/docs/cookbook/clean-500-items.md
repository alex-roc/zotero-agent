---
title: Clean 500 items
description: Bulk-edit metadata across hundreds of items with zot apply — snapshotted and undoable.
---

## The problem

You imported a few hundred references and the metadata is a mess: inconsistent
dates, missing publishers, `TITLE IN ALL CAPS`, junk left over from a PDF
scrape. Editing them one at a time in the Zotero UI is hopeless, and true
**batch editing of metadata for multiple items** is one of the longest-standing
Zotero feature requests — [open on the forums since 2016](https://forums.zotero.org/discussion/111815/feature-batch-editing-metadata-for-multiple-items).
`zotero-agent` does it locally, and undoably.

## Via an AI agent

> "In collection *Imports 2024*, normalize titles to sentence case, set any
> missing publisher on the book items to the value I gave you, and tag everything
> `#cleaned`. Dry-run first, show me a sample of before/after, then apply."

The agent reads the collection, proposes the JSONL edit, previews it, and applies
it with a snapshot so you can undo. **You** approve the values; the CLI does the
writing.

## Via the CLI

The batch primitive is `zot apply`, fed a JSONL file — one edit per line:

```jsonl
{"key":"ABCD1234","set":{"title":"Digitalization and society","date":"2021"},"addTags":["cleaned"]}
{"key":"EFGH5678","set":{"publisher":"MIT Press"},"addTags":["cleaned"]}
{"key":"IJKL9012","set":{"date":"2019"},"addTags":["cleaned"],"removeTags":["raw-import"]}
```

Each line may carry `set`, `addTags`, `removeTags`, `addToCollection`, and
`trash`. Then:

```bash
zot apply edits.jsonl --dry-run    # preview every change, no writes
zot apply edits.jsonl              # apply — snapshots affected items first
```

To build `edits.jsonl` at scale, export the collection, decide the values
(by hand, a script, or an agent), and emit one line per item:

```bash
zot export "Imports 2024" --format json --out imports.json
# ... produce edits.jsonl from imports.json ...
```

## Safety net

```bash
zot backup                          # snapshot zotero.sqlite before a big run
zot apply edits.jsonl --dry-run     # confirm the diff
zot apply edits.jsonl               # snapshots automatically
zot undo last                       # full rollback if anything looks wrong
```

`zot apply` snapshots the affected items before writing, so `zot undo last`
restores them exactly. Disable auto-sync during the run so a mistake doesn't
propagate to zotero.org.
