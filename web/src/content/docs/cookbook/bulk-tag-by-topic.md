---
title: Bulk-tag by topic
description: Classify a whole collection and apply topic tags in one undoable batch.
---

## The problem

You want to tag a large collection by topic — `#method`, `#theory`,
`#case-study` — but Zotero only lets you drag tags onto items one at a time.
There's no "classify these 300 items and tag them" button, and doing it by hand
is exactly the tedium people automate away.

## Via an AI agent

> "Read every item in *Literature review*, classify each as theory, method, or
> case study from its title and abstract, and tag it accordingly. Show me the
> proposed tags for the first 5, then apply to all — undoably."

The agent reads titles and abstracts, decides a tag per item, previews a sample,
and applies the tags in a snapshotted batch. **You** confirm the scheme; the CLI
writes it.

## Via the CLI

For a known set of items, `zot tag add` is direct:

```bash
zot tag add method ABCD1234 EFGH5678 IJKL9012 --yes
zot tag rename "case study" --new case-study --yes   # tidy an existing tag
zot tag normalize --dry-run                           # fold case/space variants
```

For classification at scale, drive it through `zot apply` so it's one undoable
operation. Export the collection, decide a tag per item, and emit JSONL:

```bash
zot export "Literature review" --format json --out lit.json
```

```jsonl
{"key":"ABCD1234","addTags":["theory"]}
{"key":"EFGH5678","addTags":["method"]}
{"key":"IJKL9012","addTags":["case-study"]}
```

```bash
zot apply tags.jsonl --dry-run
zot apply tags.jsonl
```

## Safety net

```bash
zot backup
zot apply tags.jsonl --dry-run     # preview the tag assignments
zot apply tags.jsonl               # snapshots first
zot undo last                      # remove them all if the scheme was off
```

Tagging is additive and fully reversible via `zot undo`. Run `zot tag normalize`
afterward to catch any near-duplicate tags (`Case Study` vs `case-study`) before
they proliferate.
