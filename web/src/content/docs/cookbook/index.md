---
title: Cookbook
description: Task-oriented recipes for real Zotero jobs — each shown via an AI agent and via the CLI, with a safety net.
---

Real jobs, done two ways. Each recipe states **the problem**, then shows how to
do it **via an AI agent** (the prompt to give it) and **via the CLI** (the exact
`zot` commands), and ends with the **safety net** — backup, dry-run, undo.

Many of these are things people have asked Zotero for over years of forum
threads. `zotero-agent` does them locally, on your own machine.

## Recipes

- [Clean 500 items](/zotero-agent/cookbook/clean-500-items/) — bulk metadata edits with `zot apply` + undo.
- [Summarize a PDF into a note](/zotero-agent/cookbook/summarize-pdf-to-note/) — read the PDF, write a child note.
- [Give a PDF a table of contents](/zotero-agent/cookbook/pdf-table-of-contents/) — build and embed an outline so Zotero's reader can navigate it.
- [Bulk-tag by topic](/zotero-agent/cookbook/bulk-tag-by-topic/) — classify and tag a whole collection.
- [Dedupe and merge](/zotero-agent/cookbook/dedupe-and-merge/) — find near-duplicate titles and merge safely.
- [Import by identifier](/zotero-agent/cookbook/import-by-identifier/) — add items by DOI/ISBN/arXiv, with PDFs.
- [Find missing metadata](/zotero-agent/cookbook/find-missing-metadata/) — audit gaps, then enrich from Crossref/OpenAlex.

## The universal safety net

Before any recipe that writes at scale:

```bash
zot backup            # snapshot zotero.sqlite (prints the path)
# disable auto-sync in Zotero -> Preferences -> Sync
zot <write> --dry-run # preview what would change
zot undo last         # roll back the last apply/enrich (merges excepted)
```
