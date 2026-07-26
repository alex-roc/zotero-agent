# Reading PDFs, summarizing, and saving notes

This covers three things users often want: **answer questions** about an item's
PDF, **summarize** it at several levels (whole → chapter → section), and
**save** the result back into Zotero as a note. The key idea: Zotero stores the
PDF as a normal file on disk, so once you have its path you read it with your
own PDF-reading tool — no OCR pipeline, no extraction step.

## Contents
- [1. Locate the PDF](#1-locate-the-pdf)
- [2. Answer questions about it](#2-answer-questions)
- [3. Multi-level summaries (roll-up)](#3-multi-level-summaries)
- [4. Use the user's existing annotations](#4-existing-annotations)
- [5. Save the result as a note](#5-save-as-note)
- [6. Build the PDF's table of contents](#6-table-of-contents)

## 1. Locate the PDF

Fastest — the CLI prints the path(s):

```bash
zot pdf <ITEMKEY>            # one path per line
zot pdf <ITEMKEY> --json     # {itemKey, title, pdfs:[{attachmentKey, path, title}]}
zot pdf <CITEKEY>            # also accepts a Better BibTeX citekey (auto-detected)
```

If the user gives a **Better BibTeX citekey** (e.g.
`ojedaDigitalizacionSocietalTeorias2025`), `zot pdf`/`zot get` resolve it
automatically; `zot cite <CITEKEY>` returns the Zotero key + PDF path(s).

Equivalent via `zot exec` if you need more control (e.g. non-PDF attachments):

```javascript
var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, 'ITEMKEY');
var atts = it.isAttachment() ? [it.id] : it.getAttachments();
return atts.map(id => Zotero.Items.get(id))
           .filter(a => a.attachmentContentType === 'application/pdf')
           .map(a => ({ key: a.key, path: a.getFilePath() }));
```

<a id="2-answer-questions"></a>
## 2. Answer questions about it

Get the path, then **read the PDF directly with your Read tool** and answer.
Your Read tool accepts a page range, so for a large document read only the
pages you need rather than the whole file at once.

```
zot pdf 7H6RD32M          → /Users/.../Politica_e_Internet_en_Bolivia.pdf
Read that path (optionally pages="12-18") and answer the user's question.
```

Prefer reading the actual pages over relying on the item's `abstractNote` — the
abstract is often empty or partial (see recipes.md).

<a id="3-multi-level-summaries"></a>
## 3. Multi-level summaries (roll-up)

Big documents don't fit in one read, and a flat summary loses structure. Work
**bottom-up** so each level stays within a comfortable context window:

1. **Find the structure.** Read the first pages to get the table of contents /
   outline (chapter and section titles with their page numbers). Many PDFs have
   an outline; if not, infer boundaries from headings as you read.
2. **Summarize each section** by reading its page range (your Read tool caps at
   ~20 pages per call, so split longer sections). Keep each section summary
   short and faithful — a few sentences plus key claims.
3. **Roll up:** combine a chapter's section summaries into a chapter summary,
   then the chapter summaries into a whole-document summary. Because each step
   summarizes summaries, even a 400-page book collapses cleanly.
4. Keep page references (e.g. "§3.2, pp. 45–52") so the user can jump back.

Produce a single hierarchical result:

```
# <title> — summary
## Overview        (3–5 sentences)
## Chapter 1: ...
   - §1.1 ... (pp. x–y): ...
   - §1.2 ...
## Chapter 2: ...
```

This is a reading/reasoning task, not a Zotero API task — the only Zotero calls
are step 1 (locate) and step 5 (save).

<a id="4-existing-annotations"></a>
## 4. Use the user's existing annotations

If the user already highlighted the PDF in Zotero, fold those into the summary —
they mark what *they* found important. Read them from the attachment:

```javascript
var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, 'ITEMKEY');
var pdf = it.getAttachments().map(id => Zotero.Items.get(id))
            .find(a => a.attachmentContentType === 'application/pdf');
var anns = pdf.getAnnotations();   // annotation items
return anns.map(a => ({
  type: a.annotationType,          // 'highlight', 'note', 'underline', ...
  page: a.annotationPageLabel,
  text: a.annotationText,          // highlighted text
  comment: a.annotationComment,    // user's comment, if any
}));
```

> Writing new highlight annotations programmatically is fragile (it needs exact
> text-rectangle coordinates in PDF points). Save AI-generated content as a
> **note** (below) instead — that's the reliable, reviewable path.

<a id="5-save-as-note"></a>
## 5. Save the result as a note

Store the summary as a **child note** on the item. The easy path is the CLI —
write the HTML to a file and add it (works with a key or citekey):

```bash
zot note <ITEMKEY|@citekey> --file summary.html   # add a child note
zot note <ITEMKEY> --file summary.html --dry-run   # preview, don't write
zot notes <ITEMKEY>                                 # list existing notes
```

Notes are HTML; use headings and lists so they render well in Zotero's note
pane. Keep a marker line at the top so it's clear the note was AI-generated and
can be found/removed later. The equivalent via `zot exec` if you need more
control:

```javascript
var parent = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, 'ITEMKEY');
var html = `<h1>Resumen (AI)</h1>
<p><em>Generado automáticamente — revisar.</em></p>
<h2>Panorama</h2><p>...</p>
<h2>Capítulo 1</h2><ul><li>§1.1 (pp. 3–10): ...</li></ul>`;
var note = new Zotero.Item('note');
note.setNote(html);
note.parentID = parent.id;
var noteID = await note.saveTx();
return { noteKey: Zotero.Items.get(noteID).key };
```

Pass the HTML from a file to avoid quoting problems: write the JS (with the note
body) to a file and run `zot exec file.js`.

**Reversible by design:** to remove AI notes later, find child notes whose text
contains your marker and trash them:

```javascript
var parent = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, 'ITEMKEY');
var notes = parent.getNotes().map(id => Zotero.Items.get(id))
                  .filter(n => n.getNote().includes('Resumen (AI)'));
for (var n of notes) { n.deleted = true; await n.saveTx(); }
return notes.length + ' nota(s) enviadas a la papelera';
```

<a id="6-table-of-contents"></a>
## 6. Build the PDF's table of contents

Zotero's reader has an **Outline** tab that shows the bookmarks embedded in the
PDF, but it cannot create them, and its own auto-extraction is experimental and
noisy. `zot toc` writes a real outline into the file, which fixes the sidebar
permanently and in every other reader too. Needs the `[toc]` extra
(`uv tool install --force "zotero-agent[toc]"`).

**You are the judgement step.** The CLI gathers evidence and writes the result;
deciding which lines are chapters and how they nest is your job.

```bash
zot toc show <ITEMKEY>                 # what the file already has
zot toc scan <ITEMKEY> --json          # the evidence, for you to reason over
zot toc set  <ITEMKEY> --from toc.txt --dry-run   # review
zot toc set  <ITEMKEY> --from toc.txt --yes       # write
zot undo last                          # restore the previous outline
```

### Reading a scan

`suggestion` tells you which route the file supports:

| suggestion | what it means | what to do |
|---|---|---|
| `contents-links` | the contents page hyperlinks to each chapter | use `contentsToc.entries` as-is — the pages are **exact** |
| `contents-printed-numbers` | the contents page prints page numbers | use `contentsToc.entries`; check each `confidence` |
| `typography` | no contents page — headings detected by their type | build from `headingCandidates` |
| `ocr-needed` | page images, no text layer | stop; tell the user to run the `ocrmypdf` command `scan` prints |
| `nothing-found` | text layer, but no structure | say so; don't invent one |

**Always prefer `contentsToc` over `headingCandidates` when it is non-empty** —
that hierarchy and those titles are the publisher's, and no font heuristic beats
them.

### When there is no contents page

Plenty of books have none, so `scan` falls back to finding headings by their
type. `headingCandidates` gives you each surviving line with its `size`, `bold`,
`font`, `page` and a `score`. The obvious noise is already gone — the scan drops
anything smaller than body text (footnotes), anything that fills the column
(running text), sentences, figure captions, running heads, and it rejoins
headings that were split across two lines. `bodyFontSize` tells you the baseline
to compare `size` against.

What is left for you:

- **Cut the front matter.** Cover and half-title pages have the largest type in
  the book and are not sections. They cluster in the first few pages, often
  repeated once.
- **Decide the levels.** If the book numbers its sections, "3.1.2." states its
  own depth and you should use it. Otherwise group by `size`: one distinct size
  is usually one level, and a size that appears on only two pages is a cover, not
  a tier.
- **Drop what is clearly not a section** — epigraph attributions, author names
  under a chapter title, dedications.
- **Say how confident you are.** This route is a draft, unlike the contents-page
  routes. Show the user the tree before writing it.

Each `contentsToc` entry carries a `confidence`:

- `link` — the destination came from a hyperlink. Exact.
- `verified` / `verified-shifted` — the title was found on that page. Trust it.
- `labels` / `folio` — mapped from `/PageLabels` or a printed folio, unconfirmed.
- `consensus` — re-placed using the delta the verified entries agree on.
- `voted` / `offset` / `none` — a guess. Say so if you pass it through.

### Two rules that matter

1. **Never invent or adjust page numbers.** `printedPage` is what the book
   prints; `physicalPage` is the page in the file. The CLI already did that
   mapping — and it is harder than it looks, because front matter is numbered in
   roman numerals and the body restarts at 1, so a single offset is wrong for
   half the document. Pass `physicalPage` through unchanged.
2. **Always `--dry-run` first**, and show the user the tree before writing.

### Writing it back

The format is one `title<TAB>page` per line, two spaces of indent per level:

```
Capítulo 1. Introducción	15
  1.1 Antecedentes	17
Capítulo 2. Método	48
```

JSON works too, so a `scan` result can go straight back in:
`[{"level":1,"title":"…","page":15}]` (or with `physicalPage` instead of
`page`). Write it to a file and pass `--from file`, or pipe it with `--from -`.

`zot toc auto <ITEMKEY>` does scan → decide → write in one deterministic step,
with no judgement from you. It is right often enough to be worth trying with
`--dry-run`, but review the output: a collective volume where every chapter
prints its own contents will come out in contents order rather than page order,
and `normalize` will warn that pages go backwards.

## Safe-workflow reminder

Reading is free. The notes you create are small and reversible (trash, not
erase). `zot toc` is the one thing here that **modifies the PDF file itself** —
it appends the new outline without touching existing bytes, and Zotero's
annotations live in the database rather than the file, so they survive; still,
use `--dry-run`, and `--backup` if the file is irreplaceable. For a batch, test
on 1–2 first and confirm the format with the user before the full run — see
SKILL.md.
