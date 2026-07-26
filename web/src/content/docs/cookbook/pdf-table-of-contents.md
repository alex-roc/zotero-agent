---
title: Give a PDF a table of contents
description: Build and embed a real outline (bookmarks) into a Zotero PDF so the reader's Outline tab can navigate it.
---

## The problem

You open a 400-page book in Zotero and the **Outline** tab is empty, so there is
no way to jump to chapter 7 except by dragging the scrollbar. Zotero's reader can
only display bookmarks that are already in the file, and it cannot create them —
[zotero#3396](https://github.com/zotero/zotero/issues/3396) has been open since
2023. Zotero 7 added its own automatic extraction, but the team calls it
experimental and it tends to surface stray sentences, equations and the printed
index itself as if they were chapters.

Doing it by hand in Acrobat works and takes an afternoon per book.

## What `zot toc` does

It writes a real outline into the PDF. That fixes the sidebar permanently, in
Zotero and in every other reader, and it survives sync because the outline lives
in the file.

```bash
uv tool install --force "zotero-agent[toc]"
```

The PDF engine is an optional extra — see [Install](/zotero-agent/getting-started/install/).

## The quick way

```bash
zot toc show ABCD1234            # does it already have one?
zot toc scan ABCD1234            # what can be detected, and from what
zot toc auto ABCD1234 --dry-run  # build one deterministically, preview it
zot toc auto ABCD1234 --yes      # write it
zot undo last                    # changed your mind
```

`auto` is right often enough to be worth trying first. Always `--dry-run`: it
prints the tree it would write and touches nothing.

## How pages are worked out

This is the part that makes or breaks the result, and it is why `zot toc` leans
on the book's own contents page instead of guessing from fonts.

**If the contents page hyperlinks to its chapters** (most born-digital ebooks),
the link destinations *are* the physical pages. Nothing to infer; confidence is
`link`.

**If the contents page prints page numbers** (most scanned books), they have to
be mapped. A printed "15" is almost never page 15 of the file, because the front
matter comes first and is numbered i, ii, iii before the body restarts at 1 — so
**a single offset is wrong for half the document**. `zot toc` builds the whole
map instead, from best evidence to worst:

1. `/PageLabels`, the publisher's own printed-to-physical table, when present.
2. The folio actually printed in each page's header or footer, harvested page by
   page. This discovers every numbering series in the book independently.
3. A voted offset, as a last resort.

Then it searches for each title near where it landed. Rows found that way are
marked `verified`; rows that are not get re-placed using the delta the verified
ones agree on (`consensus`) — which is what rescues an entry that a footnote
marker in a running head sent 100 pages away.

Every row carries its `confidence`, so you can see which ones were earned and
which were inferred.

## When the book has no contents page

Plenty don't. `zot toc` then finds headings by their typography — size, weight,
position, numbering — which is a draft rather than an answer, but a useful one.

Getting that to be useful is mostly about what it *rejects*, and each filter is
there because a real book needed it:

- **Smaller than the body text** → a footnote. This is the big one: footnotes are
  numbered, short and start their own block, so they score exactly like sections.
- **Fills the column** → running text. A book with no bold anywhere that sets
  block quotes two points above body size otherwise turns every quoted line into
  a heading.
- **A sentence, a figure caption, a running head, a line of twenty-plus words** →
  not a title.

Headings split across two lines are rejoined, and de-hyphenated. Levels come from
section numbering when the book numbers its sections ("3.1.2." states its own
depth); otherwise from font size, ignoring sizes that appear on only a page or
two — a 24pt title page is a cover, not an outline level.

Expect to prune the front matter, and expect an agent to do better than `auto`
here than on a book that prints its own contents.

## The agent way

`auto` applies one fixed rule. An agent can do better on a messy book, and the
CLI is built for that: it gathers evidence and performs the write, and the model
supplies the judgement in between.

```bash
zot toc scan ABCD1234 --json > scan.json
# the agent reads scan.json, decides the hierarchy, writes toc.json
zot toc set ABCD1234 --from toc.json --dry-run
zot toc set ABCD1234 --from toc.json --yes
```

`scan --json` reports a `suggestion` and the evidence behind it:

| suggestion | meaning |
|---|---|
| `contents-links` | contents page links to chapters; pages are exact |
| `contents-printed-numbers` | contents page prints numbers, already mapped |
| `typography` | no contents page; heading candidates with size/bold/score |
| `ocr-needed` | page images only — it prints the `ocrmypdf` command to run |
| `nothing-found` | text, but no detectable structure |

If you are using Claude Code, the bundled skill already knows this procedure —
prefer the contents page over typography, never invent page numbers, dry-run
before writing.

## Editing by hand

The exchange format is deliberately plain text: indentation is hierarchy, a tab
separates the title from its page.

```
Capítulo 1. Introducción	15
  1.1 Antecedentes	17
  1.2 Objetivos	22
Capítulo 2. Método	48
```

So the natural workflow is to generate, fix the two wrong rows in your editor,
and write:

```bash
zot toc auto ABCD1234 --dry-run > toc.txt   # then edit toc.txt
zot toc set  ABCD1234 --from toc.txt --yes
```

JSON is accepted too, so a `scan` result can be fed straight back.

## Scanned books

A PDF that is pure page images has nothing to read. `zot toc scan` says so and
prints the command:

```bash
ocrmypdf --skip-text --rotate-pages --deskew -l spa+eng in.pdf out.pdf
```

`zot toc` does not run OCR itself — it is a minutes-long operation that rewrites
the whole file, and it is better done deliberately.

## Safety

- Writes refuse to run non-interactively without `--yes`, and `--dry-run`
  previews without touching the file.
- The previous outline is snapshotted before every write, so `zot undo last`
  restores it exactly.
- The save is **incremental**: new objects are appended and existing bytes are
  left alone, so scanned page images are never recompressed. `--backup` keeps a
  full copy of the original under `~/.local/state/zotero-agent/pdf-backups/` —
  deliberately outside Zotero's `storage/<KEY>/`, where a stray second file would
  only confuse it.
- Your highlights are safe. Zotero stores annotations in `zotero.sqlite`, not in
  the PDF, and the outline does not move any page.
- The file's bytes do change, so Zotero re-uploads it on the next sync. Pass
  `--mark-for-sync` to make that happen promptly; leave it off if you are working
  through many large books and watching a storage quota.
