# EPUB table of contents

Use this workflow for creating, repairing or organizing EPUB navigation, including
before EPUB → PDF conversion. `zot toc` itself accepts Zotero PDF items, not EPUBs.
The bundled **`epub_toc.py`** works on local files without Zotero, Calibre, a PDF
engine or third-party Python packages. Resolve its path relative to this skill.

## Inspect → decide → validate → write a copy

```bash
# Set this to the directory of the loaded Zotero skill.
SKILL_DIR="/path/to/zotero/skill"
python3 "$SKILL_DIR/references/epub_toc.py" "book.epub" > toc.json
python3 "$SKILL_DIR/references/epub_toc.py" "book.epub" --from toc.json --dry-run
python3 "$SKILL_DIR/references/epub_toc.py" "book.epub" --from toc.json -o "book-with-toc.epub"
```

The first command reads EPUB 3's `nav` document, or EPUB 2's `toc.ncx` as fallback.
Edit the JSON tree based on the publisher's contents and actual section headings.
For an EPUB without navigation, author the same JSON directly; the writer creates
a new navigation document and registers it in the package. If both NCX and EPUB 3
nav exist, writing updates **both from the same tree**. Other nav elements such as
landmarks and page lists are preserved. Existing book content is not rewritten.

```json
[
  {"title": "Introduction", "href": "Text/introduction.xhtml", "children": [
    {"title": "Background", "href": "Text/introduction.xhtml#background"}
  ]},
  {"title": "Part I", "href": "Text/part1.xhtml", "children": [
    {"title": "Chapter 1. The problem", "href": "Text/chapter1.xhtml", "children": [
      {"title": "Evidence", "href": "Text/chapter1.xhtml#evidence"}
    ]}
  ]},
  {"title": "References", "href": "Text/references.xhtml"}
]
```

`href` is relative to the **OPF directory**, independent of where the nav/NCX lives.
Targets must be local files; fragments must name real `id`/`xml:id` attributes.
There are no page numbers in this format: EPUB pagination is reflowable.
`--dry-run` validates every file and fragment and prints the proposed tree.
The output path must not exist and must differ from the input. The original stays
intact. `mimetype` stays first and uncompressed in the new EPUB ZIP.

## Decide the hierarchy, not just the indentation

- Keep an existing meaningful hierarchy. Prefer publisher navigation and headings
  over font guessing or filename numbers.
- A flat source is evidence to review, not permission to guess an entire tree.
  Typical hierarchy: part → chapter → section. Introduction subsections belong to
  the introduction. Bibliography, indexes and author information normally return
  to the root rather than becoming children of the last chapter.
- When a chapter number and its title are separate navigation entries for the same
  chapter, combine their labels and target the actual chapter heading/content.
  Do not drop any unique section or silently rename its content.
- Use the same reviewed tree for EPUB 2 NCX, EPUB 3 nav, a separate visible contents
  page if present, and the PDF outline after conversion. Formatting a visible list
  does **not** fix navigation metadata.

The helper updates the EPUB 3 navigation contents itself, but **does not rewrite a
separate legacy visible contents page in the spine**. Inspect and update that page
from the same plan when the user requests a visible index, preserving its other
content and links. This separation is explicit so a helper cannot accidentally
delete front matter bundled into the same XHTML as the index.

## Convert to PDF

Use the bundled **`epub_to_pdf.py`** (stdlib plus Calibre's `ebook-convert`; on
macOS it finds `/Applications/calibre.app` by itself). Give it the **same reviewed
tree** you would write with `epub_toc.py`: it becomes the PDF outline, rebuilds a
visible contents page made of one-link paragraphs, and decides where pages start.

```bash
python3 "$SKILL_DIR/references/epub_toc.py" "book.epub" > toc.json   # then review it
python3 "$SKILL_DIR/references/epub_to_pdf.py" "book.epub" --toc toc.json -o "book.pdf"
python3 "$SKILL_DIR/references/epub_to_pdf.py" "book.epub" --toc toc.json --profile tablet --language es -o "book.pdf"
uv run --with pymupdf python -c "import pymupdf, sys
for level, title, page in pymupdf.open(sys.argv[1]).get_toc(): print('  ' * (level - 1) + title, page)" book.pdf
```

Profiles: `a4` (default: A4, 14.4 pt, 72 pt margins) and `tablet` (A5, 12 pt, 32 pt);
`--width/--height` (mm), `--font-size` and `--margin` (pt) override them. The
font defaults to Liberation Serif, embedded from Calibre. The footer reads
"Página N" or "Page N" by the book's language. **Pass `--language` when the
metadata is wrong**: it often is in converted EPUBs (a Spanish book declaring
`en-US`). `--prepare-only out.epub` writes the EPUB Calibre would see, without
converting, for inspection.

What the preparation fixes, and why a correct outline alone does not:

- **Page breaks inside chapters.** Calibre starts **every spine file on a new
  page**; `--page-breaks-before /` only drops its extra break before each `h1`/`h2`.
  Books that keep each section, or just the "CAPÍTULO N" label, in its own file
  break after every section. The helper merges each chapter's files. A page starts
  at every top-level entry, at every entry with children and at their siblings, so
  a chapter without sections still starts one. A short label page that no entry
  points to joins the chapter it announces. Links, ids and the tree follow the
  merge, and the forced `page-break-before: always` that such files end with is
  removed.
- **Notes as plain text.** Scanned-and-OCRed EPUBs keep the call as a digit glued
  to the word (`análisis8.`, `previos.17 De`) and the notes as `<p>8. …</p>` closing
  the chapter, unlinked. Only a consecutive run that closes a chapter and starts at 1
  or continues the previous run counts, because numbered lists in the body look the
  same. Calls are matched in order and never after a digit (`1.7` and `5,25` are not
  calls). They become superscripts linked to the note, and the note number links
  back. A chapter where fewer than half the calls are found is left alone. The
  report line says how many notes were linked; the missing ones are usually calls
  the source lost. Look before guessing.

On the book this was built for (88 spine files, 155 notes), the PDF went from 450
to 323 pages and 151 notes were linked both ways. The other four calls are missing
or mistyped in the source.

Verify in the PDF, not in the EPUB: count internal links and check that each page
pair has as many links back as forward. Confirm that the pages still left short
end a chapter or precede a figure that did not fit.

## Validate the deliverable

1. Re-read the output with the helper and compare the nested tree and destinations
   with the reviewed plan (omitted `children` and `children: []` are equivalent).
2. Check expected parents and children, not only total link counts: e.g. every
   chapter under its correct part, sections under chapters, back matter at root.
3. Open the EPUB reader's contents panel and inspect nesting and representative
   jumps. If updating a visible index, inspect wrapping and page transitions too.
4. After PDF conversion, inspect the embedded outline as well as the visible
   contents. Confirm actual PDF destination pages; do not reuse printed page
   numbers or EPUB offsets. See `pdf-and-notes.md` §6 for `zot toc` on catalogued PDFs.

If Calibre shrinks all the front matter or the contents to tiny text, check for an
oversized object in the **same XHTML**, especially a table with `white-space:
nowrap`. Fix that overflow rather than compensating with a larger base font.
Avoid splitting a long contents entry across pages (`break-inside: avoid`).

Neither helper uploads or attaches the result, replaces a Zotero attachment, or
decides the hierarchy for you. Those are separate tasks.
