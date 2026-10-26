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

Calibre's `ebook-convert` builds the PDF outline from the EPUB's navigation, so
fix the EPUB first and convert the corrected copy; the nesting carries over
(verified with a part → chapter → section tree, three outline levels).

```bash
# macOS: /Applications/calibre.app/Contents/MacOS/ebook-convert
ebook-convert "book-with-toc.epub" "book.pdf" --paper-size a4
uv run --with pymupdf python -c "import pymupdf, sys
for level, title, page in pymupdf.open(sys.argv[1]).get_toc(): print('  ' * (level - 1) + title, page)" book.pdf
```

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

The helper does not upload or attach the result, replace a Zotero attachment,
convert EPUB to PDF, or decide hierarchy automatically. Those are separate tasks.
