---
title: Find missing metadata
description: Audit which items lack an abstract, date, DOI, or URL — then enrich them from Crossref or OpenAlex.
---

## The problem

Half your library is missing abstracts, a chunk has no DOI, and some items have
no date at all — which breaks sorting, citation, and search. Zotero has no
built-in "show me everything missing field X," and its own empty-field search is
unreliable (Zotero doesn't store an unset field as an empty string, so the
obvious search returns zero).

## Via an AI agent

> "Which items in *To Read* are missing a DOI or an abstract? Fill in the DOIs
> from Crossref, dry-run first."

The agent audits the collection, reports the gaps, previews the enrichment, and
applies it undoably.

## Via the CLI

Audit first — `zot missing` uses a reliable `getField` check, not the
empty-string search condition:

```bash
zot missing abstract --collection SS5MVVB6   # items with no abstract
zot missing doi                              # library-wide
zot missing date
zot lint                                     # full data-quality report
```

Then enrich from an external source:

```bash
zot enrich --field doi --source crossref --dry-run    # preview
zot enrich --field doi --source crossref              # apply (undoable)
zot enrich --field abstract --source openalex
zot enrich --field date --source crossref
```

## Safety net

```bash
zot backup
zot enrich --field doi --source crossref --dry-run    # see exactly what would fill
zot enrich --field doi --source crossref              # snapshots first
zot undo last                                          # roll back if a match was wrong
```

`zot enrich` snapshots the affected items before writing, so `zot undo` fully
reverses it — useful when an external source returns a wrong match. Scope with
`--collection` and dry-run before running across the whole library.
