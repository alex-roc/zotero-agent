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

Store the summary as a **child note** on the item. Notes are HTML; use headings
and lists so it renders well in Zotero's note pane. Keep a marker line at the
top so it's clear the note was AI-generated and can be found/removed later.

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

## Safe-workflow reminder

Reading is free; the only writes here are the notes you create, which are small
and reversible (trash, not erase). For a batch (summarize many items at once),
still test on 1–2 first and confirm the note format with the user before the
full run — see SKILL.md.
