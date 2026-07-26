"""Read, validate, exchange and write a PDF's outline tree.

The exchange format is a plain text file, and that is a deliberate choice
borrowed from pdf.tocgen: detection is never perfect, so the pipeline has to have
a place where a human (or an agent) reads the proposed tree, fixes the two wrong
rows, and only then writes it. A tab-separated, indentation-is-hierarchy file is
that place — editable in any editor, diffable, and round-trips exactly.

    Chapter 1. Introduction<TAB>15
      1.1 Background<TAB>17
    Chapter 2. Method<TAB>48

Pages are 1-based physical pages throughout, which is what set_toc() wants.
`normalize()` and the text codec are pure; only `write_outline`/`save_pdf` need
the engine.
"""

import json
import os
import re

from . import require_pymupdf

INDENT = "  "  # two spaces per level when rendering

# Accepts either the rendered form (title TAB page) or a hand-typed line whose
# page number is separated by spaces. Two spaces minimum for the latter, so a
# stray "Chapter 1" with no page raises instead of silently becoming page 1.
_ROW_TAB = re.compile(r"^(?P<title>.*\S)\t+(?P<page>\d{1,6})\s*$")
_ROW_SPACE = re.compile(r"^(?P<title>.*\S)\s{2,}(?P<page>\d{1,6})\s*$")


# --------------------------------------------------------------------------- #
# read
# --------------------------------------------------------------------------- #
def read_outline(doc):
    """The document's current outline as [{level, title, page}] (page 1-based)."""
    out = []
    for row in doc.get_toc(simple=True) or []:
        level, title, page = row[0], row[1], row[2]
        out.append({"level": int(level), "title": title, "page": int(page)})
    return out


# --------------------------------------------------------------------------- #
# validate  (pure)
# --------------------------------------------------------------------------- #
def normalize(entries, page_count=None, max_level=None):
    """Return (entries, warnings): a tree PyMuPDF will accept, plus what changed.

    set_toc() rejects a level that jumps by more than one (1 -> 3), and a page
    outside the document, by raising — which for the user is an opaque traceback
    halfway through a batch. Fixing both here, and *reporting* each fix, turns a
    hard failure into a visible, reviewable one.
    """
    clean, warnings = [], []
    previous_level = 0
    previous_page = None
    for raw in entries:
        title = (raw.get("title") or "").strip()
        if not title:
            warnings.append("dropped an entry with an empty title")
            continue
        try:
            page = int(raw.get("page"))
        except (TypeError, ValueError):
            warnings.append("dropped %r: page is not a number" % title[:60])
            continue

        if page < 1:
            warnings.append("%r: page %d clamped to 1" % (title[:60], page))
            page = 1
        if page_count and page > page_count:
            warnings.append("%r: page %d is past the end (%d pages), clamped"
                            % (title[:60], page, page_count))
            page = page_count

        level = max(1, int(raw.get("level") or 1))
        if max_level:
            level = min(level, max_level)
        if level > previous_level + 1:
            warnings.append("%r: level %d follows level %d, lowered to %d"
                            % (title[:60], level, previous_level, previous_level + 1))
            level = previous_level + 1

        if clean and clean[-1]["title"] == title and clean[-1]["page"] == page:
            warnings.append("dropped a duplicate of %r" % title[:60])
            continue
        if previous_page is not None and page < previous_page:
            warnings.append("%r: page %d goes backwards (previous was %d)"
                            % (title[:60], page, previous_page))

        clean.append({"level": level, "title": title, "page": page})
        previous_level, previous_page = level, page
    return clean, warnings


# --------------------------------------------------------------------------- #
# text / JSON exchange  (pure)
# --------------------------------------------------------------------------- #
def render_toc_text(entries):
    """Render entries as the editable exchange format."""
    lines = []
    for e in entries:
        level = max(1, int(e.get("level") or 1))
        lines.append("%s%s\t%d" % (INDENT * (level - 1), e["title"], int(e["page"])))
    return "\n".join(lines) + ("\n" if lines else "")


def parse_toc_text(text):
    """Parse the exchange format back into entries.

    Indentation sets the level: a tab is one level, and every `INDENT` worth of
    spaces is one level, so files typed by hand with either convention work.
    """
    entries = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip(" \t")
        prefix = line[: len(line) - len(stripped)]
        level = 1 + prefix.count("\t") + len(prefix.replace("\t", "")) // len(INDENT)

        match = _ROW_TAB.match(stripped) or _ROW_SPACE.match(stripped)
        if not match:
            raise ValueError("line %d is not 'title<TAB>page': %s"
                             % (lineno, stripped[:80]))
        entries.append({"level": level,
                        "title": match.group("title").strip(),
                        "page": int(match.group("page"))})
    return entries


def load_entries(raw):
    """Parse either exchange format. JSON is what the agent and `--json` emit;
    text is what a human edits. Sniffing beats a --format flag nobody remembers."""
    text = raw.strip()
    if not text:
        return []
    if text[0] in "[{":
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("entries") or data.get("outline") or data.get("toc") or []
        return [{"level": int(e.get("level") or 1),
                 "title": (e.get("title") or "").strip(),
                 "page": int(e.get("page") or e.get("physicalPage") or 0)}
                for e in data]
    return parse_toc_text(raw)


# --------------------------------------------------------------------------- #
# write
# --------------------------------------------------------------------------- #
def save_pdf(doc, path):
    """Persist `doc` back to `path`. Returns "incremental" or "rewrite".

    Incremental is the whole point: it appends the new objects to the end of the
    file and leaves every existing byte alone, so scanned page images are never
    recompressed and existing signatures/xref stay intact. It is not always
    possible (a linearised or damaged file will refuse), hence the full-rewrite
    fallback — still with no garbage collection or recompression, and staged
    through a temp file so an interrupted write cannot destroy the original.
    """
    pymupdf = require_pymupdf()
    try:
        doc.save(path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        return "incremental"
    except Exception:
        tmp = path + ".zot-toc-tmp"
        doc.save(tmp, garbage=0, deflate=False)
        doc.close()
        os.replace(tmp, path)
        return "rewrite"


def write_outline(doc, entries, path):
    """Replace the document's outline and save. Entries must already be
    normalized — set_toc raises on a bad level, and by here that is a bug."""
    doc.set_toc([[e["level"], e["title"], int(e["page"])] for e in entries], collapse=1)
    return save_pdf(doc, path)


def clear_outline(doc, path):
    doc.set_toc([])
    return save_pdf(doc, path)
