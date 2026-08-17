---
title: Make a scanned book searchable
description: Split a two-pages-at-a-time scan into single pages, OCR it, and shrink it — without the file leaving its Zotero item.
---

## The problem

Someone scanned a book on a flatbed, two facing pages at a time. What you have in
Zotero is a stack of wide landscape pages, each holding two printed pages, with a
dark valley down the middle where the binding was — and no text at all, because
the pages are photographs.

Everything downstream breaks on that. Search finds nothing. You cannot copy a
quotation. `zot toc` has no headings to read. An AI agent asked to summarize it
sees blank pages and either says so or, worse, invents something. And the file is
several times larger than it needs to be, so it is slow to open and expensive to
sync.

The usual fix is three separate tools: [Briss] to crop and split, [OCRmyPDF] to
add a text layer, something else to compress — with the file leaving Zotero and
coming back as a stranger, detached from its item, its notes and its citekey.

## What `zot pdf-prep` does

One pass: analyse, split, OCR, shrink, attach. The item never changes.

```bash
brew install ocrmypdf tesseract-lang unpaper jbig2enc   # once
# Debian/Ubuntu: sudo apt install ocrmypdf tesseract-ocr-spa unpaper
```

Splitting needs the `[toc]` extra (already there if you use `zot toc`); the text
layer needs OCRmyPDF. See [Install](/zotero-agent/getting-started/install/).

## Via the CLI

Always look first — it costs a second and changes nothing:

```bash
zot pdf-prep @bowlesIntroduccionEconomia --dry-run
```

```
147 pages, 956.2x633.2 pt, 200 dpi images, no text layer,
double-page (gutter 0.501, confidence 79%)
plan: split=True gutter=0.5011 ocr=spa+eng profile=balanced
```

Read that line before running anything: `no text layer` confirms it is a scan,
`double-page` that it is two-up, and `confidence` how sure the detector is about
where the fold is. Then:

```bash
zot pdf-prep @bowlesIntroduccionEconomia
```

```
24.7 MB -> 16.4 MB (-34%), 294 pages, OCR 167.5s
attached MI9Z5TC7 to GPHJ8CML Introducción a la economía
```

The item now has two PDFs; the new one is titled **PDF (OCR)**. A whole shelf
works the same way, and re-running skips what is already done:

```bash
zot pdf-prep --collection "Escaneos" --dry-run   # survey first: what is a scan?
zot pdf-prep --collection "Escaneos"             # ~0.5 s per page — it takes a while
```

## Via an AI agent

> "Check whether the Bowles book in my library is a scan, and if it is, prepare
> it so I can search it. Tell me what it found before doing anything slow."

The agent runs `--dry-run`, reports pages, dpi and whether there is a text layer,
and asks before starting a job measured in minutes. Afterwards it can go straight
on to the outline — `zot toc scan` now has headings to read, which on the raw
scan it did not.

## When the split needs help

The detector measures the ink profile of sampled pages and applies the **median**
cut to the whole book, which is what a human does in Briss and for the same
reason: on a nearly blank page the widest gap lands anywhere, so a per-page cut
eventually slices a chapter opening in half. Each half keeps a sliver past the
cut, so the ±2% a real binding wanders never clips a letter.

When that is not enough:

```bash
zot pdf-prep KEY --gutter 0.48        # force the cut (fraction of page width)
zot pdf-prep KEY --single "1,2,147"   # leave covers and fold-outs whole
zot pdf-prep KEY --split never        # already single pages: only OCR and shrink
zot pdf-prep KEY --split always       # two-up, but too faint to measure
zot pdf-prep KEY --rtl                # right-to-left book: right half first
zot pdf-prep KEY --ocr spa --profile quality   # force language; best text, larger file
```

`--profile quality` OCRs at 300 dpi: noticeably better text on a poor scan, but
the file grows instead of shrinking. `--no-ocr` splits and optimises with no
OCRmyPDF at all.

## The safety net

`pdf-prep` is additive. The processed PDF is attached **beside** the original and
tagged `pdf-prep`, so nothing is overwritten and a second run is a no-op. Once
you have looked at the results, reclaim the space:

```bash
zot pdf-prep --collection "Escaneos" --prune --dry-run   # what would go
zot pdf-prep --collection "Escaneos" --prune             # originals -> trash
```

Two things worth knowing:

- **Removals go to Zotero's trash**, not to oblivion — recoverable until you
  empty it.
- **Annotations do not follow the new file.** Zotero anchors highlights to the
  attachment and to page coordinates, and the prepared PDF has different pages.
  So `--replace` and `--prune` leave an annotated original alone unless you add
  `--trash-annotated`. Prepare a scan *before* you read it and this never comes
  up.

OCR output is a machine reading an image. It is good enough to search, cite and
summarize from; check long quotations against the page.

[Briss]: https://briss.sourceforge.net/
[OCRmyPDF]: https://ocrmypdf.readthedocs.io/
