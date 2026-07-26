"""Read a PDF and report everything needed to build an outline for it.

`scan()` never decides anything. It gathers evidence — text layer, page labels,
the book's own printed contents pages, typographic heading candidates — and hands
it over. Deciding which lines are chapters is a judgement call, and in this
project judgement belongs to the agent (see features.py: "the CLI never calls an
LLM"). `zot toc auto` applies a deterministic default for people working without
one.

Two routes come out of a scan:

  printed-toc  the book prints its own contents. Best case by far: the hierarchy
               is the publisher's, not ours. All that is left is mapping printed
               page numbers to physical ones, which is `pagemap`'s job.
  typography   no contents page, so fall back to font size, weight and position.
               Works well on born-digital documents with consistent styling.

A scan with no text layer at all is a scanned image; report it and stop, because
no amount of heuristics will find headings in a bitmap.
"""

import re
from collections import Counter

from . import require_pymupdf
from .pagemap import (
    LEADER_CHARS as _LEADER_CHARS,
)
from .pagemap import (
    ROMAN_PAGE_CEILING,
    levels_from_indents,
    parse_toc_line,
    resolve_pages,
    roman_to_int,
)

# A page needs at least this many characters to count as having a text layer.
# Scanned pages are not empty — they carry stray marks and the odd stamp — so a
# flat "has any text" test reports false on nothing and true on junk.
MIN_CHARS_PER_PAGE = 80

# Fraction of the document searched for the printed contents pages, and the band
# at the top/bottom of a page where a printed folio lives.
FRONT_MATTER_FRACTION = 0.2
FOLIO_BAND = 0.09

DEFAULT_CANDIDATE_CAP = 400

_CONTENTS_HEADING = re.compile(
    r"\b(contents?|table\s+of\s+contents|[ií]ndice(?:\s+general)?|contenidos?|"
    r"tabla\s+de\s+contenidos?|sumario|inhalt(?:sverzeichnis)?|sommaire|"
    r"table\s+des\s+mati[eè]res|conte[uú]do|indice)\b", re.I)

# "Índice de tablas" and "List of figures" match the heading above but are not
# the table of contents — they are lists of exhibits, and every row in them
# points at a table rather than a section. Treating one as the contents page
# fills the outline with 40 entries called "Tabla".
_EXHIBIT_LIST_HEADING = re.compile(
    r"\b(?:[ií]ndice|lista|listado|tabla|table|list|relaci[oó]n)\s+(?:de\s+|of\s+|des\s+)?"
    r"(?:las\s+|los\s+|the\s+)?"
    r"(tablas?|cuadros?|mapas?|gr[aá]ficos?|figuras?|ilustraciones|im[aá]genes|"
    r"fotograf[ií]as?|recuadros?|anexos?|siglas|abreviaturas|acr[oó]nimos|"
    r"tables?|figures?|maps?|charts?|illustrations?|plates?|boxes|"
    r"abbreviations|acronyms)\b", re.I)

# The heading test only catches the first page of an exhibit list; its
# continuation pages carry a running head that just says "Índice", which reads as
# the real thing. Their *rows* give them away — every one starts "Mapa 4",
# "Tabla 12" — so count those instead of trusting the heading.
_EXHIBIT_ROW = re.compile(
    r"^(?:tablas?|cuadros?|mapas?|gr[aá]ficos?|figuras?|fig\.?|ilustraci[oó]n|"
    r"recuadros?|fotos?|im[aá]genes?|tables?|charts?|maps?|plates?|boxes?)"
    r"\s*\d", re.I)
_EXHIBIT_ROW_SHARE = 0.3
_EXHIBIT_ROW_COUNT = 4

_CAPTION = re.compile(
    r"^(figura|figure|fig\.?|tabla|table|cuadro|gr[aá]fico|graph|chart|"
    r"ilustraci[oó]n|plate|map|mapa|ecuaci[oó]n|equation)\s*\d", re.I)

_NUMBERED_HEADING = re.compile(
    r"^\s*(?:"
    r"(?:cap[ií]tulo|chapter|parte|part|secci[oó]n|section|anexo|ap[eé]ndice|"
    r"appendix|tomo|libro|book|unidad|unit|tema)\s+(?:\d{1,3}|[ivxlcdm]{1,7})\b"
    r"|\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+\S"
    r"|[IVXLCDM]{1,7}\.\s+\S"
    r")", re.I)

# PyMuPDF span flag bits (see the "dict" text extraction docs).
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4


def open_pdf(path):
    """Open a PDF, or raise the engine's own error (the caller reports it)."""
    return require_pymupdf().open(path)


# --------------------------------------------------------------------------- #
# lines, with their typography
# --------------------------------------------------------------------------- #
def iter_lines(doc, pages=None):
    """Yield one dict per visual line, carrying the style of its largest span.

    Style comes from the biggest span rather than the first because a heading
    that starts with a small drop-cap number ("1  Introduction") would otherwise
    be read as body text.
    """
    for index in (pages if pages is not None else range(doc.page_count)):
        page = doc[index]
        width, height = page.rect.width, page.rect.height
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:  # 0 = text, 1 = image
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s.get("text", "") for s in spans).strip()
                if not text:
                    continue
                biggest = max(spans, key=lambda s: s.get("size", 0))
                flags = biggest.get("flags", 0)
                font = biggest.get("font", "") or ""
                bbox = line.get("bbox", (0, 0, 0, 0))
                yield {
                    "page": index + 1,           # 1-based, as everywhere public
                    "text": text,
                    "size": round(float(biggest.get("size", 0)), 1),
                    "font": font,
                    "bold": bool(flags & _FLAG_BOLD)
                            or "bold" in font.lower() or "black" in font.lower(),
                    "italic": bool(flags & _FLAG_ITALIC),
                    "x0": round(float(bbox[0]), 1),
                    "x1": round(float(bbox[2]), 1),
                    "y": round(float(bbox[1]), 1),
                    "y1": round(float(bbox[3]), 1),
                    "pageWidth": round(float(width), 1),
                    "pageHeight": round(float(height), 1),
                    "linesInBlock": len(block.get("lines", [])),
                }


def body_font_size(lines):
    """The document's body size: the most common size weighted by how many
    characters are set in it. Weighting matters — a title page can contribute
    more distinct sizes than the body contributes lines."""
    weighted = Counter()
    for line in lines:
        weighted[line["size"]] += len(line["text"])
    return weighted.most_common(1)[0][0] if weighted else 0.0


# --------------------------------------------------------------------------- #
# text layer
# --------------------------------------------------------------------------- #
def text_layer(doc):
    """(has_text, chars_per_page). Drives the ocr-needed verdict."""
    if not doc.page_count:
        return False, 0.0
    total = sum(len(doc[i].get_text().strip()) for i in range(doc.page_count))
    per_page = total / float(doc.page_count)
    return per_page >= MIN_CHARS_PER_PAGE, round(per_page, 1)


# --------------------------------------------------------------------------- #
# printed page number -> physical page: the two evidence sources
# --------------------------------------------------------------------------- #
def page_label_map(doc):
    """{rendered label -> 1-based physical page} from /PageLabels, or {}.

    This is the publisher's own table, so when it exists nothing else is needed.
    Plenty of PDFs omit it, which is why `folio_map` exists.
    """
    labels = {}
    try:
        if not doc.get_page_labels():
            return {}
    except Exception:
        return {}
    for index in range(doc.page_count):
        try:
            label = doc[index].get_label()
        except Exception:
            continue
        if label and label not in labels:
            labels[label] = index + 1
    return labels


def folio_map(doc, band=FOLIO_BAND):
    """{("d"|"r", printed number) -> 1-based physical page}, read off the page.

    Harvests the folio actually stamped in each page's header/footer. This is
    what makes scanned books work: it discovers every numbering series in the
    document instead of assuming one offset, so roman front matter and arabic
    body resolve independently and correctly.

    First occurrence wins, because a number reappearing later is far more likely
    to be a running head or a stray digit than a renumbering.
    """
    pymupdf = require_pymupdf()
    found = {}
    for index in range(doc.page_count):
        page = doc[index]
        height, width = page.rect.height, page.rect.width
        bands = (pymupdf.Rect(0, height * (1 - band), width, height),
                 pymupdf.Rect(0, 0, width, height * band))
        for rect in bands:
            try:
                text = page.get_textbox(rect)
            except Exception:
                continue
            for token in text.split():
                token = token.strip("[]()<>{}.,;:—–-·|/\\")
                if not token or len(token) > 5:
                    continue
                if token.isdigit():
                    found.setdefault(("d", int(token)), index + 1)
                elif re.fullmatch(r"[ivxlcdm]+", token, re.I):
                    value = roman_to_int(token)
                    if 0 < value <= 200:
                        found.setdefault(("r", value), index + 1)
    return found


# --------------------------------------------------------------------------- #
# route A: the book's own printed contents pages
# --------------------------------------------------------------------------- #
def goto_links(doc, page_index):
    """[(rect, 1-based destination page)] for internal links on a page."""
    pymupdf = require_pymupdf()
    out = []
    for link in doc[page_index].get_links():
        if link.get("kind") != pymupdf.LINK_GOTO:
            continue
        dest = link.get("page")
        if dest is None or int(dest) < 0 or not link.get("from"):
            continue
        out.append((pymupdf.Rect(link["from"]), int(dest) + 1))
    return out


def find_contents_pages(doc, fraction=FRONT_MATTER_FRACTION):
    """Physical pages (1-based) that look like the book's table of contents.

    Three signals, any of which suffices: a heading that says so in one of
    several languages, a high density of "title .... number" lines, or a high
    density of internal links. That last one matters more than it sounds — a
    born-digital ebook's contents page usually prints no page numbers at all and
    is navigable purely by hyperlink, so a density test that only counts printed
    numbers scores it zero and misses the best evidence in the file.
    """
    limit = max(4, int(doc.page_count * fraction))
    candidates, titled_pages = set(), []
    for index in range(min(limit, doc.page_count)):
        text = doc[index].get_text()
        if not text.strip():
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        head = text[:400]
        if _EXHIBIT_LIST_HEADING.search(head):
            continue
        # Four rows literally named "Mapa 4" / "Tabla 12" is an exhibit list, not
        # a contents page, at any density — a real one never names four sections
        # that way. The share test catches the same thing on a short page.
        exhibits = sum(1 for ln in lines if _EXHIBIT_ROW.match(ln))
        if exhibits >= _EXHIBIT_ROW_COUNT or (
                exhibits >= 2 and exhibits / float(len(lines)) > _EXHIBIT_ROW_SHARE):
            continue
        titled = bool(_CONTENTS_HEADING.search(head))
        matched = sum(1 for ln in lines if parse_toc_line(ln))
        linked = len(goto_links(doc, index))
        if titled and matched < 4 and linked < 4:
            # Nothing text-based matched, but the page says it is the contents.
            # Check the two-column layout before giving up on it. Gated on
            # `titled` because this pass costs a full dict extraction, and
            # because a page of statistics would otherwise pair just as well.
            page_lines = list(iter_lines(doc, [index]))
            matched = len(_pair_number_columns(page_lines, _number_flags(page_lines)))
        dense = max(matched, linked) / float(len(lines))
        if max(matched, linked) >= 4 and (titled or dense > 0.4):
            candidates.add(index + 1)
            if titled:
                titled_pages.append(index + 1)
    if not candidates:
        return []

    # Density alone also fires on bibliographies, statistical tables and dense
    # footnote pages. A real contents section is a *contiguous run* starting at a
    # page that says so, so grow runs outward from the pages that announced
    # themselves and drop isolated look-alikes. With nothing titled anywhere
    # (headings set as images), fall back to the earliest run.
    anchors = titled_pages or [min(candidates)]
    keep = set()
    for anchor in anchors:
        keep.add(anchor)
        for step in (1, -1):
            page = anchor + step
            while page in candidates:
                keep.add(page)
                page += step
    return sorted(keep)


def parse_linked_contents(doc, pages):
    """Entries from a contents page whose rows are hyperlinks.

    The link's destination *is* the physical page, so there is no printed number
    to map and no offset to infer — the publisher already answered the hard
    question. Confidence is `link`, the only exact value this module produces.
    """
    pymupdf = require_pymupdf()
    rows, indents = [], []
    previous_line = None
    for page_number in pages:
        index = page_number - 1
        targets = goto_links(doc, index)
        if not targets:
            continue
        for line in iter_lines(doc, [index]):
            rect = pymupdf.Rect(line["x0"], line["y"], line["x1"], line["y1"])
            area = abs(rect)
            destination = None
            for target_rect, dest in targets:
                # A link box rarely matches a text line exactly; require it to
                # cover a third of the line before calling it that line's link.
                if area and abs(target_rect & rect) > 0.3 * area:
                    destination = dest
                    break
            if destination is None:
                previous_line = None
                continue
            # A hyperlinked contents page is usually *also* typeset the normal
            # way — leaders and a printed page number — with the link laid over
            # the top. So parse the row first and keep the printed number for
            # reference; only fall back to trimming leaders when there is no
            # number to split on. Taking the raw line would leave every title
            # ending in "........ 7".
            parsed = parse_toc_line(line["text"])
            if parsed:
                title, printed, roman = parsed["title"], parsed["printedPage"], parsed["roman"]
            else:
                title = line["text"].strip().strip(_LEADER_CHARS).strip()
                printed, roman = None, False
            # A row with no letters in it is page furniture — the contents page's
            # own folio, caught by a link box that overlaps it.
            if (len(title) < 2 or _CONTENTS_HEADING.match(title)
                    or not re.search(r"[^\W\d_]", title, re.UNICODE)):
                previous_line = None
                continue

            # A wrapped entry produces two adjacent lines linked to the *same*
            # page. Same destination alone would also merge a chapter with its
            # first section (both open on that page), so also require the second
            # line to not look like the start of an entry — real ones begin with
            # a number ("2.1.") or a capital.
            head = title[:1]
            if (rows and previous_line is not None
                    and rows[-1]["physicalPage"] == destination
                    and _follows(previous_line, line)
                    and not head.isupper() and not head.isdigit()):
                rows[-1]["title"] = _join_wrapped(rows[-1]["title"], title)
                previous_line = line
                continue

            rows.append({"title": title, "printedPage": printed, "roman": roman,
                         "physicalPage": destination, "confidence": "link"})
            indents.append(line["x0"])
            previous_line = line

    _strip_glued_page_numbers(rows)
    for row, level in zip(rows, levels_from_indents(indents), strict=True):
        row["level"] = level
    return rows


_TRAILING_DIGITS = re.compile(r"^(?P<title>.*?[^\W\d_])\s*(?P<page>\d{1,4})$", re.UNICODE)


def _strip_glued_page_numbers(rows):
    """Remove a printed page number that ran into the title with no separator.

    When leaders are missing, "…en la tecnología" and its "16" come back as one
    word, and `parse_toc_line` has nothing to split on. Guessing would be unsafe —
    plenty of real titles end in a year. But on a linked contents page the answer
    can be *checked*: the rows that did parse agree on a printed-to-physical
    delta, so trailing digits are only stripped when applying that delta lands
    exactly on the link's own destination. A title ending in "1950" survives
    unless 1950 really is this row's page.
    """
    deltas = Counter(row["physicalPage"] - row["printedPage"] for row in rows
                     if row.get("printedPage") and not row.get("roman"))
    if not deltas:
        return
    delta, agreement = deltas.most_common(1)[0]
    if agreement < 3:
        return
    for row in rows:
        if row.get("printedPage"):
            continue
        match = _TRAILING_DIGITS.match(row["title"])
        if match and int(match.group("page")) + delta == row["physicalPage"]:
            row["title"] = match.group("title").strip()
            row["printedPage"] = int(match.group("page"))


MAX_WRAPPED_LINES = 3

_BARE_PAGE = re.compile(r"^(\d{1,4}|[ivxlcdm]{1,15})$", re.I)


def _pair_number_columns(lines, is_number):
    """{title line index -> page-number line index} for a two-column contents page.

    Many books set the page number in its own right-hand column instead of
    running dot leaders up to it. PyMuPDF then emits the title and the number as
    two separate lines, nothing matches "title .... 15", and the page scores zero
    on every text-based test — which is how a real contents page gets skipped in
    favour of the list of figures two pages later.

    Geometrically it is unambiguous, though: a short numeric line sharing a
    baseline with a title line that ends to its left. Each number claims at most
    one title, so a stray figure in the margin cannot swallow the column.
    """
    pairs = {}
    for i, line in enumerate(lines):
        if not is_number[i]:
            continue
        middle = (line["y"] + line["y1"]) / 2.0
        best = None
        for j, candidate in enumerate(lines):
            if is_number[j] or j in pairs:
                continue
            if candidate["x1"] > line["x0"] + 2:      # must end left of the number
                continue
            if not (candidate["y"] - 1 <= middle <= candidate["y1"] + 1):
                continue
            if best is None or candidate["x1"] > lines[best]["x1"]:
                best = j
        if best is not None:
            pairs[best] = i
    return pairs


def _number_flags(lines):
    return [bool(_BARE_PAGE.match(line["text"].strip())) for line in lines]


def _join_wrapped(head, tail):
    """Join two halves of a wrapped title, undoing hyphenation.

    A word broken across lines leaves a trailing hyphen that is typesetting, not
    spelling ("democratiza-" + "ción"), so it goes. A hyphen the author wrote
    would be lost too, but a compound landing exactly on a line break is rare and
    "Estado-nación" surviving as "Estadonación" is a smaller error than every
    wrapped word keeping a stray "- " in the middle.
    """
    head = head.rstrip()
    if head.endswith("-") and not head.endswith("--"):
        return head[:-1] + tail.lstrip()
    return head + " " + tail.lstrip()


def _follows(first, second):
    """True when `second` is the next printed line under `first`.

    Compares the tops, not top-to-bottom: consecutive line boxes overlap by an
    ascender's worth, so a bottom-to-top gap is routinely negative and any test
    that expects a positive one never fires.
    """
    if first["page"] != second["page"]:
        return False
    height = max(first["y1"] - first["y"], 1.0)
    return 0 < second["y"] - first["y"] <= 1.8 * height


def _contiguous_runs(pages):
    """Split sorted page numbers into runs of consecutive pages."""
    runs = []
    for page in pages:
        if runs and page == runs[-1][-1] + 1:
            runs[-1].append(page)
        else:
            runs.append([page])
    return runs


def _parse_contents_run(doc, pages):
    """Parse one contiguous contents section. Levels are scoped to the run
    because indentation is only comparable within a single laid-out section —
    an anthology where every chapter prints its own contents would otherwise
    have all its scales averaged into nonsense."""
    rows, indents = [], []
    pending = []  # recent lines that carried no page number
    for line in iter_lines(doc, [p - 1 for p in pages]):
        parsed = parse_toc_line(line["text"])
        if not parsed:
            text = line["text"].strip()
            if 2 <= len(text) <= 120 and not _CONTENTS_HEADING.match(text):
                pending.append(line)
                pending[:] = pending[-MAX_WRAPPED_LINES:]
            else:
                pending = []
            continue
        if _CONTENTS_HEADING.match(parsed["title"]):
            pending = []
            continue

        indent = line["x0"]
        # Long entries wrap, and only the last line carries the page number, so a
        # line-by-line parse keeps the tail ("y la nación mestiza") and discards
        # the title. Continuations start in lower case directly under their own
        # first line; walk back up the chain until a line starts upper case,
        # which is where the entry really began.
        if pending and parsed["title"][:1].islower():
            chain, following = [], line
            for candidate in reversed(pending):
                if not _follows(candidate, following):
                    break
                chain.insert(0, candidate)
                following = candidate
                if not candidate["text"].strip()[:1].islower():
                    break
            if chain:
                title = chain[0]["text"].strip()
                for part in chain[1:]:
                    title = _join_wrapped(title, part["text"].strip())
                parsed["title"] = _join_wrapped(title, parsed["title"])
                indent = chain[0]["x0"]
        pending = []
        rows.append(parsed)
        indents.append(indent)

    # strict=True: both lists are appended together, so a mismatch is a bug.
    for row, level in zip(rows, levels_from_indents(indents), strict=True):
        row["level"] = level
    return rows


def _parse_columnar_run(doc, pages):
    """Parse a contents section whose page numbers sit in a separate column."""
    rows, indents = [], []
    for page_number in pages:
        lines = list(iter_lines(doc, [page_number - 1]))
        is_number = _number_flags(lines)
        pairs = _pair_number_columns(lines, is_number)
        if len(pairs) < 4:
            continue
        for title_index in sorted(pairs):
            raw = lines[pairs[title_index]]["text"].strip()
            if raw.isdigit():
                printed, roman = int(raw), False
            else:
                printed, roman = roman_to_int(raw), True
                if printed > ROMAN_PAGE_CEILING:
                    continue
            if printed <= 0:
                continue
            title_line = lines[title_index]
            title = title_line["text"].strip()
            if len(title) < 2 or _CONTENTS_HEADING.match(title):
                continue
            indent = title_line["x0"]

            # In this layout the number sits on the *last* line of a wrapped
            # entry, and the continuation is often indented further rather than
            # starting lower case — so pair by geometry, not by capitalisation:
            # walk back over title lines directly above that no number claimed.
            chain, following, k = [], title_line, title_index - 1
            while k >= 0 and len(chain) < MAX_WRAPPED_LINES:
                previous = lines[k]
                if is_number[k] or k in pairs or not _follows(previous, following):
                    break
                chain.insert(0, previous)
                following = previous
                k -= 1
            if chain:
                joined = chain[0]["text"].strip()
                for part in chain[1:]:
                    joined = _join_wrapped(joined, part["text"].strip())
                title = _join_wrapped(joined, title)
                indent = chain[0]["x0"]

            rows.append({"title": title, "printedPage": printed, "roman": roman})
            indents.append(indent)

    for row, level in zip(rows, levels_from_indents(indents), strict=True):
        row["level"] = level
    return rows


def parse_printed_contents(doc, pages):
    """Entries from the printed contents pages, with levels from indentation.

    Tries dot-leader rows first and falls back to the two-column layout, per
    contiguous section — a book uses one convention or the other, not both.
    """
    rows = []
    for run in _contiguous_runs(sorted(pages)):
        parsed = _parse_contents_run(doc, run)
        if len(parsed) < 4:
            parsed = _parse_columnar_run(doc, run) or parsed
        rows.extend(parsed)
    return rows


def verify_pages(doc, entries, radius=2):
    """Nudge each resolved page by searching for the title nearby.

    Mapping gets a document-wide answer; this checks it entry by entry. Scanners
    drop a page, publishers slip a plate in, and OCR shifts a folio — a title
    found one page over is the cheapest possible correction, and finding it also
    upgrades the entry's confidence to something earned rather than inferred.
    """
    for entry in entries:
        needle = (entry.get("title") or "")[:40].strip()
        if len(needle) < 8:
            continue
        base = entry.get("physicalPage")
        if not base:
            continue
        for delta in [0] + [d for r in range(1, radius + 1) for d in (r, -r)]:
            index = base + delta - 1
            if not (0 <= index < doc.page_count):
                continue
            try:
                if doc[index].search_for(needle, quads=False):
                    entry["physicalPage"] = index + 1
                    entry["confidence"] = "verified" if delta == 0 else "verified-shifted"
                    break
            except Exception:
                break
    return entries


def repair_unverified(doc, entries):
    """Re-place entries the title search could not confirm, using the delta the
    confirmed ones agree on.

    A printed folio is good evidence until it isn't: a footnote marker or a year
    in a running head can register as a page number and strand one entry hundreds
    of pages from where it belongs. The entries whose titles *were* found are a
    trustworthy sample, and within one numbering series they share a delta — so
    their median is a far better guess for an outlier than the outlier's own
    lookup. Each numbering series is repaired separately, which is the whole
    reason this works on books with roman front matter.
    """
    import statistics
    for roman_series in (False, True):
        confirmed = [e for e in entries
                     if bool(e.get("roman", False)) == roman_series
                     and str(e.get("confidence", "")).startswith("verified")
                     and e.get("printedPage")]
        if len(confirmed) < 3:
            continue
        delta = int(statistics.median(e["physicalPage"] - e["printedPage"]
                                      for e in confirmed))
        moved = []
        for entry in entries:
            if bool(entry.get("roman", False)) != roman_series:
                continue
            if str(entry.get("confidence", "")).startswith("verified"):
                continue
            if not entry.get("printedPage"):
                continue
            target = entry["printedPage"] + delta
            if 1 <= target <= doc.page_count and target != entry["physicalPage"]:
                entry["physicalPage"] = target
                entry["confidence"] = "consensus"
                moved.append(entry)
        if moved:
            verify_pages(doc, moved)
    return entries


# --------------------------------------------------------------------------- #
# route B: typography
# --------------------------------------------------------------------------- #
HEADING_MAX_CHARS = 110
HEADING_MAX_WORDS = 20
RUNNING_HEAD_PAGES = 3
LEVEL_MIN_PAGES = 3
FULL_MEASURE_SHARE = 0.85

# A sentence boundary inside the line — punctuation followed by a lower-case
# word or an opening quote. Headings do not contain them; prose does.
_PROSE = re.compile(r"[.;:!?]\s+[a-záéíóúüñ¿¡“\"'(\[]")


def text_measure(lines, body_size=0.0):
    """The width of a full line of running text, in points.

    Used to tell a heading from a line of prose. Measured over lines set at body
    size only — headings are exactly what this is meant to exclude, so letting
    them into the sample raises the bar they then have to clear. Taken as a high
    percentile of observed widths rather than from the page, because margins,
    columns and indentation all sit in between.
    """
    widths = sorted(line["x1"] - line["x0"] for line in lines
                    if not body_size or abs(line["size"] - body_size) < 0.5)
    if not widths:
        return 0.0
    return widths[min(int(len(widths) * 0.9), len(widths) - 1)]


def score_line(line, body_size, measure=0.0):
    """How much this line looks like a heading, or 0 if it cannot be one.

    The gates come first and matter more than the score. Two do most of the work:

    - the size floor. Footnotes are the biggest single source of false headings —
      numbered, short, first in their block, so they score exactly like a section
      — and what actually separates them is being set *smaller* than the body.
    - the measure. A book with no bold anywhere that sets block quotes two points
      up from the body makes every quoted line look like a heading; what gives it
      away is that it runs the full width of the text block, and a title does not.
    """
    text = line["text"]
    height = line["pageHeight"] or 1.0

    # Running heads and folios are not headings, whatever their font.
    if line["y"] < 0.06 * height or line["y"] > 0.93 * height:
        return 0
    if not (3 <= len(text) <= HEADING_MAX_CHARS):
        return 0
    if len(text.split()) > HEADING_MAX_WORDS:
        return 0
    if _CAPTION.match(text):
        return 0
    if body_size and line["size"] < body_size - 0.4:
        return 0                      # footnotes, marginalia, captions, credits
    if _PROSE.search(text):
        return 0                      # a sentence, not a title
    if (measure and body_size and line["size"] < body_size * 1.35
            and (line["x1"] - line["x0"]) > FULL_MEASURE_SHARE * measure):
        return 0                      # fills the column: running text

    score = 0
    if body_size:
        if line["size"] > body_size * 1.12:
            score += 3
        if line["size"] > body_size * 1.35:
            score += 2
        if line["bold"] and line["size"] >= body_size:
            score += 2
    elif line["bold"]:
        score += 2
    if _NUMBERED_HEADING.match(text):
        score += 3
    if text.isupper() and len(text) > 4:
        score += 1
    if line["linesInBlock"] <= 2:
        score += 1
    if not text.endswith((".", ",", ";", ":")):
        score += 1
    width = line["pageWidth"] or 1.0
    if abs((line["x0"] + line["x1"]) / 2.0 - width / 2.0) < 0.04 * width:
        score += 1
    return score


def _merge_wrapped_headings(scored):
    """Join a heading that spans two or three lines back into one entry.

    A chapter title set over two lines arrives as two candidates ("Sociología
    de" / "la imagen"), which would become two sibling outline rows pointing at
    the same page. Same page, same style, directly underneath: one heading.
    """
    merged = []
    for candidate in scored:
        previous = merged[-1] if merged else None
        if (previous
                and previous["page"] == candidate["page"]
                and previous["size"] == candidate["size"]
                and previous["bold"] == candidate["bold"]
                and previous.get("_lines", 1) < MAX_WRAPPED_LINES
                and 0 < candidate["y"] - previous["y"]
                <= 1.8 * max(previous["y1"] - previous["y"], 1.0)):
            previous["text"] = _join_wrapped(previous["text"], candidate["text"])
            previous["y1"] = candidate["y1"]
            previous["score"] = max(previous["score"], candidate["score"])
            previous["_lines"] = previous.get("_lines", 1) + 1
            continue
        merged.append(dict(candidate, _lines=1))
    for candidate in merged:
        candidate.pop("_lines", None)
    return merged


def _drop_running_heads(candidates):
    """Discard text repeated across many pages — a running head that happens to
    sit inside the text area, or a recurring section label."""
    pages_seen = {}
    for candidate in candidates:
        pages_seen.setdefault(candidate["text"].strip().lower(), set()).add(candidate["page"])
    return [c for c in candidates
            if len(pages_seen[c["text"].strip().lower()]) < RUNNING_HEAD_PAGES]


def heading_candidates(lines, body_size, threshold=5, cap=DEFAULT_CANDIDATE_CAP):
    """(candidates, truncated). Candidates keep their raw typography so the
    agent can regroup them; `cap` bounds the JSON handed to a model."""
    measure = text_measure(lines, body_size)
    scored = []
    for line in lines:
        score = score_line(line, body_size, measure)
        if score >= threshold:
            scored.append({"page": line["page"], "text": line["text"],
                           "size": line["size"], "bold": line["bold"],
                           "font": line["font"], "y": line["y"], "y1": line["y1"],
                           "x0": line["x0"], "score": score})
    scored = _drop_running_heads(_merge_wrapped_headings(scored))
    truncated = len(scored) > cap
    if truncated:
        # Keep the strongest, then restore reading order: an arbitrary prefix of
        # the document would silently hide the whole second half.
        scored = sorted(sorted(scored, key=lambda c: -c["score"])[:cap],
                        key=lambda c: (c["page"], c["y"]))
    return scored, truncated


_SECTION_NUMBER = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+\S")


def numbering_depth(text):
    """1 for "3. Title", 2 for "3.1. Title", 3 for "3.1.2. Title"; 0 if unnumbered."""
    match = _SECTION_NUMBER.match(text or "")
    return match.group(1).count(".") + 1 if match else 0


def levels_from_typography(candidates, max_level=4):
    """Assign levels to typographic candidates.

    Two sources, and the order matters. When the document numbers its sections,
    "3.1.2." states its own depth — that beats any inference. Ranking every
    distinct (size, bold, font) tuple, as this used to do, invents a level per
    style variation and produces four levels of nesting out of what is really
    two.

    Falling back to size, sizes alone are ranked: bold and font are style
    variation *within* a level far more often than they mark a new one.
    """
    if not candidates:
        return []
    numbered = sum(1 for c in candidates if numbering_depth(c["text"]))
    use_numbering = numbered >= max(3, 0.4 * len(candidates))

    # Rank only sizes the book actually uses as a level. A size that appears on
    # two pages of a 350-page book is the cover, not a tier — and letting it take
    # level 1 pushes every real chapter down to level 3.
    pages_per_size = {}
    for candidate in candidates:
        pages_per_size.setdefault(candidate["size"], set()).add(candidate["page"])
    common = sorted((size for size, pages in pages_per_size.items()
                     if len(pages) >= LEVEL_MIN_PAGES), reverse=True)
    if not common:
        common = sorted(pages_per_size, reverse=True)
    by_size = {size: min(i + 1, max_level) for i, size in enumerate(common)}

    def level_for(size):
        if size in by_size:
            return by_size[size]
        return by_size[min(common, key=lambda s: abs(s - size))]

    out = []
    for candidate in candidates:
        depth = numbering_depth(candidate["text"]) if use_numbering else 0
        level = depth or level_for(candidate["size"])
        out.append({"level": min(level, max_level),
                    "title": candidate["text"], "page": candidate["page"]})
    return out


# --------------------------------------------------------------------------- #
# the whole scan
# --------------------------------------------------------------------------- #
def scan(doc, offset=None, cap=DEFAULT_CANDIDATE_CAP):
    """Gather every signal about this document's structure. Decides nothing."""
    from .outline import read_outline

    has_text, chars = text_layer(doc)
    report = {
        "pages": doc.page_count,
        "textLayer": has_text,
        "charsPerPage": chars,
        "existingOutline": read_outline(doc),
        "pageLabels": False,
        "contentsToc": {"pages": [], "source": None, "entries": []},
        "headingCandidates": [],
        "bodyFontSize": 0.0,
        "truncated": False,
        "suggestion": "ocr-needed",
    }
    if not has_text:
        return report

    labels = page_label_map(doc)
    report["pageLabels"] = bool(labels)

    contents_pages = find_contents_pages(doc)
    if contents_pages:
        # Links first: an exact destination beats a printed number that still has
        # to be mapped onto a physical page.
        rows = parse_linked_contents(doc, contents_pages)
        source = "links"
        if not rows:
            rows = parse_printed_contents(doc, contents_pages)
            source = "printed-numbers"
            if rows:
                rows = repair_unverified(doc, verify_pages(doc, resolve_pages(
                    rows, label_map=labels, folio_map=folio_map(doc),
                    offset=offset, page_count=doc.page_count)))
        if rows:
            report["contentsToc"] = {"pages": contents_pages, "source": source,
                                     "entries": rows}

    lines = list(iter_lines(doc))
    report["bodyFontSize"] = body_font_size(lines)
    candidates, truncated = heading_candidates(lines, report["bodyFontSize"], cap=cap)
    report["headingCandidates"] = candidates
    report["truncated"] = truncated

    if report["contentsToc"]["entries"]:
        report["suggestion"] = "contents-" + report["contentsToc"]["source"]
    elif candidates:
        report["suggestion"] = "typography"
    else:
        report["suggestion"] = "nothing-found"
    return report


def auto_entries(report, max_level=4):
    """The deterministic pick `zot toc auto` writes, from a scan report.

    Prefers the book's own contents page every time it exists: those titles and
    that nesting are the publisher's, and no font heuristic beats them.
    """
    contents = report.get("contentsToc", {}).get("entries") or []
    if contents:
        return [{"level": min(e.get("level", 1), max_level),
                 "title": e["title"], "page": e["physicalPage"]} for e in contents]
    return levels_from_typography(report.get("headingCandidates") or [],
                                  max_level=max_level)
