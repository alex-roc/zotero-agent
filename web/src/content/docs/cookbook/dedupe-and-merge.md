---
title: Dedupe and merge
description: Find near-duplicate titles across your library and merge them — with a mandatory backup, since merges are irreversible.
---

## The problem

The same paper got imported three times — once from the browser connector, once
from a BibTeX file, once by DOI — with slightly different titles each time.
Zotero's built-in duplicate detection is conservative and its merge is manual,
one group at a time. You want to find near-duplicates across the whole library
and clear them out.

## Via an AI agent

> "Find duplicate titles in collection *Reading list*, including fuzzy matches,
> show me the groups, then merge each group keeping the oldest as the master.
> Back up first."

The agent takes a backup, finds duplicate groups (exact or fuzzy), shows them for
your approval, and merges — oldest item as master.

## Via the CLI

```bash
zot dedupe --by title --collection SS5MVVB6           # exact-title duplicates
zot dedupe --by title --fuzzy --collection SS5MVVB6   # near-duplicates (Levenshtein)
zot dedupe --by doi                                    # duplicates by DOI
```

Review the groups, then merge (oldest item becomes the master):

```bash
zot backup                          # REQUIRED — merges cannot be undone
zot dedupe --by title --merge --yes
```

Scope with `--collection` before ever running library-wide.

## Safety net

:::danger[Merges are irreversible]
Unlike `zot apply` and `zot enrich`, a **merge cannot be undone** by `zot undo`.
The only recovery is the database backup. Always run `zot backup` immediately
before `zot dedupe --merge`, and disable auto-sync so a bad merge doesn't
propagate to zotero.org.
:::

```bash
zot backup                                   # snapshot zotero.sqlite
zot dedupe --by title --fuzzy --dry-run      # inspect groups before committing
# ... verify the groups are true duplicates ...
zot dedupe --by title --merge --yes
```

If a merge went wrong, restore the `zotero.sqlite` snapshot that `zot backup`
printed the path to.
