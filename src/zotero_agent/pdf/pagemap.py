"""Printed page numbers -> physical page numbers. Pure Python, no PDF engine.

This is the part every other "auto-bookmark a PDF" tool gets wrong, so it is
worth stating plainly. A book's printed table of contents says "Chapter 1 ... 15",
but page 15 of the *file* is almost never the page printed with a 15 on it: the
front matter comes first, and it is usually numbered i, ii, iii... restarting at
arabic 1 where the body begins.

A single global offset therefore cannot be right for the whole document — it is
off by the length of the front matter for every roman-numbered entry. What works
is building the *full* map, from best evidence to worst:

  1. /PageLabels    the publisher's own printed-number -> physical-index table.
                    Exact when present, which is often for born-digital PDFs.
  2. printed folios the page number actually stamped in the header or footer of
                    each physical page, harvested page by page. Handles scans,
                    multiple numbering series, and unnumbered plates.
  3. a voted offset last resort: locate a few titles by text search, and take the
                    most common (physical - printed) delta.

Every page number crossing this module's boundary is **1-based**, matching what a
reader displays and what PyMuPDF's set_toc() expects. Callers that work with
0-based PyMuPDF page indices convert at the edge.
"""

import re
from collections import Counter

# --------------------------------------------------------------------------- #
# roman numerals
# --------------------------------------------------------------------------- #
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_ROMAN_RE = re.compile(r"^[ivxlcdm]{1,15}$", re.I)


def is_roman(s):
    """True for a plausible roman numeral. Deliberately loose on validity: OCR
    produces `iiv` and `xxxx`, and a wrong-but-parseable numeral still beats
    dropping the entry."""
    return bool(s) and bool(_ROMAN_RE.match(s))


def roman_to_int(s):
    """Parse a roman numeral (case-insensitive). Returns 0 for unparseable input."""
    s = (s or "").strip().lower()
    if not is_roman(s):
        return 0
    total = 0
    for i, ch in enumerate(s):
        val = _ROMAN_VALUES[ch]
        nxt = _ROMAN_VALUES[s[i + 1]] if i + 1 < len(s) else 0
        total += -val if val < nxt else val
    return total


_ROMAN_STEPS = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
    (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]


def int_to_roman(n):
    """Render a lowercase roman numeral. Needed to look a printed roman page up
    in a /PageLabels map, which is keyed by the rendered label string."""
    if n <= 0:
        return ""
    out = []
    for value, glyph in _ROMAN_STEPS:
        while n >= value:
            out.append(glyph)
            n -= value
    return "".join(out)


# --------------------------------------------------------------------------- #
# parsing a line of a printed table of contents
# --------------------------------------------------------------------------- #
# Leader characters that publishers put between a title and its page number.
_LEADERS = r"\.·•․‥…‧_\-–—\s"

_LINE_WITH_LEADER = re.compile(
    r"^(?P<title>.+?\S)[" + _LEADERS + r"]{2,}(?P<page>\d{1,4}|[ivxlcdm]{1,15})$", re.I)
_LINE_PLAIN = re.compile(r"^(?P<title>.+?\S)\s+(?P<page>\d{1,4})$")

# The same leaders as a strippable set, so callers that get a title without going
# through `parse_toc_line` — the hyperlinked-contents route, where the link
# replaces the page number but the typeset dots stay — can clean it the same way.
LEADER_CHARS = " \t .·•․‥…‧_-–—"

# Two families, same failure mode. Structural words are chapter openers
# ("Chapter 1"), and without this guard `_LINE_PLAIN` turns every one of them
# into an entry pointing at page 1, 2, 3... Caption words head a list of tables
# or figures, where every row reads "Tabla 12 ..... 255" and the naive parse
# records the title as "Tabla".
_STRUCTURAL_ONLY = re.compile(
    r"^(?:cap[ií]tulo|chapter|parte|part|secci[oó]n|section|tomo|volumen|volume|"
    r"book|libro|anexo|ap[eé]ndice|appendix|unidad|unit|tema|lecci[oó]n|lesson|"
    r"cap|ch"
    r"|tabla|table|cuadro|mapa|map|gr[aá]fico|graph|chart|figura|figure|fig|"
    r"ilustraci[oó]n|illustration|plate|imagen|image|foto(?:graf[ií]a)?|"
    r"ecuaci[oó]n|equation|recuadro|box)$", re.I)

# Largest value accepted from a roman-numeral page number. Front matter does not
# run to page 1000; a bigger result means letters from a word were parsed.
ROMAN_PAGE_CEILING = 200


def parse_toc_line(text):
    """Parse one line of a printed contents page.

    Returns {"title", "printedPage", "roman"} or None. Handles dot leaders
    (`Title......15`), unicode leaders (`Title······ix`), and plain spacing
    (`Bibliography   201`).
    """
    if not text:
        return None
    # The literal below is U+00A0: typesetters use non-breaking spaces between a
    # title and its leader dots, and str.split() does not treat them as space.
    line = " ".join(text.replace(" ", " ").split())
    if not line:
        return None

    match = _LINE_WITH_LEADER.match(line) or _LINE_PLAIN.match(line)
    if not match:
        return None

    title = match.group("title").strip(LEADER_CHARS)
    raw = match.group("page")
    if len(title) < 2 or _STRUCTURAL_ONLY.match(title):
        return None
    # A title that is itself only digits or punctuation is page-furniture, not a
    # heading (a stray folio picked up from the contents page's own footer).
    if not re.search(r"[^\W\d_]", title, re.UNICODE):
        return None

    if raw.isdigit():
        page, roman = int(raw), False
        if page > 9999:
            return None
    else:
        page, roman = roman_to_int(raw), True
        # Front matter runs to maybe lx; anything larger means the "numeral" is
        # really the tail of a word ("Index — mix" parses as 1009).
        if page > ROMAN_PAGE_CEILING:
            return None
    if page <= 0:
        return None
    return {"title": title, "printedPage": page, "roman": roman}


# --------------------------------------------------------------------------- #
# hierarchy from indentation
# --------------------------------------------------------------------------- #
def levels_from_indents(indents, tolerance=4.0, max_level=6):
    """Turn a column of left-edge x positions into 1-based outline levels.

    A printed contents page already encodes its own hierarchy as indentation, so
    the levels come free — no font analysis, no guessing. Values within
    `tolerance` points are one level (justification jitters by a point or two).
    """
    if not indents:
        return []
    ordered = sorted(set(round(float(x), 1) for x in indents))
    clusters = [ordered[0]]
    for x in ordered[1:]:
        if x - clusters[-1] > tolerance:
            clusters.append(x)
    levels = []
    for x in indents:
        rank = 0
        for i, base in enumerate(clusters):
            if float(x) >= base - tolerance:
                rank = i
        levels.append(min(rank + 1, max_level))
    return levels


# --------------------------------------------------------------------------- #
# resolving printed -> physical
# --------------------------------------------------------------------------- #
def vote_offset(pairs):
    """Most common (physical - printed) delta over (printedPage, physicalPage)
    samples, both 1-based. Returns None when there is nothing to vote on."""
    votes = Counter(physical - printed for printed, physical in pairs
                    if printed and physical)
    if not votes:
        return None
    return votes.most_common(1)[0][0]


def label_key(printed_page, roman):
    """The /PageLabels key a printed page number would be rendered as."""
    return int_to_roman(printed_page) if roman else str(printed_page)


def folio_key(printed_page, roman):
    """The key `folio_map` uses: numbering series + value, so a roman iv and an
    arabic 4 never collide."""
    return ("r" if roman else "d", printed_page)


def resolve_pages(entries, label_map=None, folio_map=None, offset=None, page_count=None):
    """Attach a 1-based `physicalPage` and a `confidence` to each entry.

    `entries` carry `printedPage` and `roman` (as produced by parse_toc_line).
    `label_map` maps a rendered label string to a 1-based physical page;
    `folio_map` maps folio_key() to a 1-based physical page. `offset` forces a
    fixed delta and wins over the voted one but not over real evidence.

    Confidence is `labels` > `folio` > `offset` > `voted` > `none`, so callers
    can decide how much to trust each row, and users can see which entries were
    guessed.
    """
    label_map = label_map or {}
    folio_map = folio_map or {}
    out = []
    voted = None
    if offset is None:
        # Vote using only the entries real evidence already placed — that is the
        # only sample where both the printed and the physical number are known.
        samples = []
        for e in entries:
            physical = (label_map.get(label_key(e["printedPage"], e.get("roman", False)))
                        or folio_map.get(folio_key(e["printedPage"], e.get("roman", False))))
            if physical:
                samples.append((e["printedPage"], physical))
        voted = vote_offset(samples)

    for entry in entries:
        e = dict(entry)
        printed, roman = e["printedPage"], e.get("roman", False)
        physical = label_map.get(label_key(printed, roman))
        confidence = "labels"
        if not physical:
            physical = folio_map.get(folio_key(printed, roman))
            confidence = "folio"
        if not physical and offset is not None:
            physical, confidence = printed + offset, "offset"
        if not physical and voted is not None:
            physical, confidence = printed + voted, "voted"
        if not physical:
            physical, confidence = printed, "none"
        if page_count:
            physical = max(1, min(int(physical), int(page_count)))
        else:
            physical = max(1, int(physical))
        e["physicalPage"] = physical
        e["confidence"] = confidence
        out.append(e)
    return out
