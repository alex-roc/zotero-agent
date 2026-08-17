"""Scan preparation — the `zot pdf-prep` engine.

A book scanned on a flatbed arrives as one landscape page per *pair* of printed
pages, with no text layer and a size that makes it slow to open and impossible
to search. Fixing that by hand means Briss for the split, OCRmyPDF for the text
layer, and a third pass for the size — with the file leaving Zotero and coming
back under a new name.

The pipeline here is: analyse → split → OCR → optimise, and it keeps the item.

Layering follows `pdf/pagemap.py`: the delicate part is *deciding where the
gutter is*, which is arithmetic over an ink profile, so it lives in pure
functions that unit-test without a PDF engine or a fixture file. Only
`analyse`, `split_document` and `run_ocr` touch the outside world.

Why a global cut instead of one per page: the ink profile is only informative
where there is ink. On a nearly blank page the "widest quiet valley" lands
anywhere, and a per-page cut then slices a chapter opening in half. Sampling
many pages and taking the median of the *confident* ones is what a human does
in Briss — pick one crop and apply it to the whole run — and it degrades
gracefully, which per-page detection does not.
"""

import os
import shutil
import subprocess
from operator import add

# Fraction of the page width searched for the gutter, either side of centre.
# Wider than any real binding offset, narrow enough to never reach the text.
GUTTER_BAND = 0.18
# Pages sampled to decide the cut. The median stabilises well before this;
# more samples mostly cost rasterising time.
GUTTER_SAMPLES = 24
# Resolution the ink profile is measured at. The gutter is centimetres wide —
# there is nothing to gain from detail, and plenty of speed to lose.
PROFILE_DPI = 50
# A page below this ink fraction is too blank for its valley to mean anything.
MIN_INK = 0.03
# How much emptier than a typical column the gutter must be before it counts as
# a gutter at all. Guards against reading an evenly inked page as one wide gap.
MIN_GUTTER_CONTRAST = 0.01
# Each half reaches this fraction of the page width past the cut, so that the
# ±2% spread a real binding shows never clips a letter. Costs a sliver of the
# facing page in the margin.
DEFAULT_OVERLAP = 0.008
# Landscape enough to be a two-up scan rather than a wide single page.
DOUBLE_PAGE_RATIO = 1.25

PROFILES = {
    # clean feeds a despeckled image to the OCR engine but leaves the page
    # itself alone, so the text improves and the scan is not degraded.
    "balanced": ["--deskew", "--clean", "--optimize", "3"],
    # oversample resamples the page to 300 dpi, which is what tesseract is
    # tuned for. Best text; the file grows instead of shrinking.
    "quality": ["--deskew", "--clean", "--oversample", "300", "--optimize", "3"],
    # For bitonal scans optimize 3 already reaches for JBIG2; the quality caps
    # only bite on the colour and greyscale pages mixed in.
    "small": ["--deskew", "--clean", "--optimize", "3",
              "--jpeg-quality", "40", "--png-quality", "40"],
}

# Zotero's language field is free text, and a real library holds every spelling
# of it: "es", "es-ES", "spa", "Spanish", "español". Matched longest-first so
# that "espanol" is not decided by the "es" that starts it.
LANGUAGE_PREFIXES = tuple(sorted((
    ("spanish", "spa"), ("español", "spa"), ("espanol", "spa"), ("castellano", "spa"),
    ("english", "eng"), ("inglés", "eng"), ("ingles", "eng"),
    ("portuguese", "por"), ("português", "por"), ("portugues", "por"),
    ("french", "fra"), ("français", "fra"), ("francés", "fra"), ("frances", "fra"),
    ("german", "deu"), ("deutsch", "deu"), ("alemán", "deu"), ("aleman", "deu"),
    ("italian", "ita"), ("italiano", "ita"),
    ("catalan", "cat"), ("català", "cat"),
    ("latin", "lat"), ("latín", "lat"),
    ("quechua", "que"), ("aymara", "aym"),
    ("spa", "spa"), ("eng", "eng"), ("por", "por"), ("fra", "fra"), ("deu", "deu"),
    ("ita", "ita"), ("cat", "cat"), ("lat", "lat"), ("que", "que"), ("aym", "aym"),
    ("es", "spa"), ("en", "eng"), ("pt", "por"), ("fr", "fra"), ("de", "deu"),
    ("it", "ita"), ("ca", "cat"), ("la", "lat"), ("qu", "que"), ("ay", "aym"),
), key=lambda pair: -len(pair[0])))

OCR_INSTALL_HINT = (
    "`zot pdf-prep` needs OCRmyPDF (which brings tesseract and Ghostscript):\n"
    "  brew install ocrmypdf tesseract-lang unpaper jbig2enc   (macOS)\n"
    "  sudo apt install ocrmypdf tesseract-ocr-spa unpaper      (Debian/Ubuntu)\n"
    "Run `zot pdf-prep KEY --no-ocr` to split and optimise without a text layer."
)


# --------------------------------------------------------------------------- #
# ink profiles and the gutter — pure arithmetic, no PDF engine
# --------------------------------------------------------------------------- #
def column_ink(samples, width, height, row_step=2, threshold=None):
    """Fraction of dark pixels per column of an 8-bit greyscale raster.

    `samples` is the raw row-major buffer (PyMuPDF's `Pixmap.samples`). Rows are
    accumulated with `map(add, ...)`, which runs the inner loop in C — the naive
    per-pixel version is slow enough to be felt on a 300-page book.
    """
    if width <= 0 or height <= 0:
        return []
    if threshold is None:
        # Mid-point between the extremes. Scans are bimodal (ink and paper), so
        # this separates them as well as a histogram would, for a fraction of
        # the work.
        threshold = (min(samples) + max(samples)) // 2 if samples else 128
    table = bytes(1 if i < threshold else 0 for i in range(256))

    totals = [0] * width
    rows = 0
    for y in range(0, height, row_step):
        row = samples[y * width:(y + 1) * width]
        if len(row) != width:
            continue
        totals = list(map(add, totals, row.translate(table)))
        rows += 1
    if not rows:
        return []
    return [t / rows for t in totals]


def smooth(profile, window):
    """Moving average, to keep scanner speckle from reading as a column of ink."""
    if window <= 1 or len(profile) < window:
        return list(profile)
    out = []
    half = window // 2
    for i in range(len(profile)):
        lo, hi = max(0, i - half), min(len(profile), i + half + 1)
        out.append(sum(profile[lo:hi]) / (hi - lo))
    return out


def median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def gutter_from_profile(profile, band=GUTTER_BAND):
    """(cut fraction, valley width fraction) for the widest quiet run near centre.

    The gutter is the widest band of near-blank columns around the middle — not
    the single emptiest column, which on a two-column layout is just the space
    between columns.

    The quiet threshold is set by the *contrast* between the emptiest columns
    and the typical one, not by an absolute ink level. An absolute one calls a
    page of evenly grey ink "all gutter" and hands back the middle with full
    confidence — which is exactly the wrong answer, because that page is a
    single wide page with no binding in it at all.
    """
    width = len(profile)
    if width < 8:
        return None, 0.0
    lo, hi = int(width * (0.5 - band)), int(width * (0.5 + band))
    window = smooth(profile[lo:hi], max(3, width // 200))
    if not window:
        return None, 0.0

    floor = min(window)
    contrast = median(window) - floor
    if contrast < MIN_GUTTER_CONTRAST:
        return None, 0.0
    quiet_level = floor + contrast * 0.25
    best_start = best_len = run_start = run_len = 0
    for i, value in enumerate(window):
        if value <= quiet_level:
            if run_len == 0:
                run_start = i
            run_len += 1
            if run_len > best_len:
                best_len, best_start = run_len, run_start
        else:
            run_len = 0
    if best_len == 0:
        return None, 0.0
    return (lo + best_start + best_len / 2) / width, best_len / width


def choose_gutter(samples, min_ink=MIN_INK, tolerance=0.02):
    """Fold per-page observations into one cut.

    `samples` is a list of (cut, valley, ink) — the output of measuring pages.
    Returns (cut, confidence, used), where confidence is the share of usable
    pages agreeing with the median within `tolerance`. A low confidence is the
    signal to ask a human rather than to guess harder.
    """
    usable = [s for s in samples if s[0] is not None and s[2] >= min_ink]
    if not usable:
        return None, 0.0, 0
    cuts = sorted(s[0] for s in usable)
    mid = len(cuts) // 2
    median = cuts[mid] if len(cuts) % 2 else (cuts[mid - 1] + cuts[mid]) / 2
    agreeing = sum(1 for c in cuts if abs(c - median) <= tolerance)
    return median, agreeing / len(cuts), len(cuts)


def parse_pages(spec, total):
    """'1,4-6' → {1, 4, 5, 6}, clamped to the document. Empty spec → empty set."""
    pages = set()
    for chunk in (spec or "").replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            first, _, last = chunk.partition("-")
            try:
                start, end = int(first), int(last)
            except ValueError:
                raise ValueError("bad page range: %s" % chunk) from None
            if start > end:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            try:
                pages.add(int(chunk))
            except ValueError:
                raise ValueError("bad page number: %s" % chunk) from None
    return {p for p in pages if 1 <= p <= total}


# --------------------------------------------------------------------------- #
# reading the document
# --------------------------------------------------------------------------- #
def sample_indices(count, wanted):
    """Evenly spread page indices, skipping the covers at either end."""
    if count <= wanted:
        return list(range(count))
    # Front matter and endpapers are unrepresentative: half-title pages, plates,
    # the inside of the back cover. Sample the body.
    lo, hi = int(count * 0.1), int(count * 0.9)
    span = max(1, hi - lo)
    step = span / wanted
    return sorted({lo + int(i * step) for i in range(wanted)})


def measure_pages(doc, indices, dpi=PROFILE_DPI):
    """[(index, cut, valley, ink)] — one ink measurement per sampled page."""
    out = []
    grey = _grey(doc)
    for index in indices:
        page = doc[index]
        pix = page.get_pixmap(dpi=dpi, colorspace=grey)
        profile = column_ink(pix.samples, pix.width, pix.height)
        cut, valley = gutter_from_profile(profile)
        ink = sum(profile) / len(profile) if profile else 0.0
        out.append((index, cut, valley, ink))
    return out


def _grey(doc):
    from . import require_pymupdf
    return require_pymupdf().csGRAY


def analyse(doc, samples=GUTTER_SAMPLES):
    """What kind of document this is, and where it would be cut.

    Returns a report the caller can print, hand to `--json`, or act on.
    """
    from .scan import text_layer

    count = doc.page_count
    if not count:
        return {"pages": 0, "doublePage": False}

    sizes = []
    for index in sample_indices(count, min(count, 12)):
        rect = doc[index].rect
        sizes.append((round(rect.width, 1), round(rect.height, 1)))
    common = max(set(sizes), key=sizes.count)
    ratio = (common[0] / common[1]) if common[1] else 0.0

    has_text, chars = text_layer(doc)

    measured = measure_pages(doc, sample_indices(count, min(count, samples)))
    cut, confidence, used = choose_gutter([(c, v, i) for _n, c, v, i in measured])

    landscape = ratio >= DOUBLE_PAGE_RATIO
    double = bool(landscape and cut is not None and confidence >= 0.6)

    return {
        "pages": count,
        "pageSize": {"width": common[0], "height": common[1], "ratio": round(ratio, 3)},
        "hasText": has_text,
        "charsPerPage": chars,
        "imageDpi": _image_dpi(doc, measured),
        "doublePage": double,
        "landscape": landscape,
        "gutter": None if cut is None else round(cut, 4),
        "gutterConfidence": round(confidence, 2),
        "gutterPagesUsed": used,
        "blankish": [n + 1 for n, _c, _v, ink in measured if ink < MIN_INK],
    }


def _image_dpi(doc, measured):
    """Resolution of the page images, when the pages *are* images.

    Reported because it is what decides whether OCR can succeed at all: below
    ~200 dpi tesseract starts guessing, and the fix is a better scan, not a
    better flag.
    """
    for index, _cut, _valley, _ink in measured[:4]:
        page = doc[index]
        try:
            images = page.get_images(full=True)
        except Exception:
            return None
        if not images:
            continue
        width_px = images[0][2]
        width_pt = page.rect.width
        if width_pt:
            return round(width_px / width_pt * 72)
    return None


# --------------------------------------------------------------------------- #
# splitting
# --------------------------------------------------------------------------- #
def split_document(doc, out_path, cut, overlap=DEFAULT_OVERLAP, single=(), rtl=False):
    """Write a one-page-per-leaf copy of `doc`.

    Each half is placed with `show_pdf_page`, which re-uses the source page's
    own content stream: the scan's image data is referenced, not re-encoded, so
    nothing is lost before the OCR stage and the file does not grow.
    """
    pymupdf = _engine()
    out = pymupdf.open()
    singles = set(single or ())

    for number in range(1, doc.page_count + 1):
        source = doc[number - 1]
        rect = source.rect
        if number in singles:
            page = out.new_page(-1, width=rect.width, height=rect.height)
            page.show_pdf_page(page.rect, doc, number - 1)
            continue

        middle = rect.x0 + rect.width * cut
        pad = rect.width * overlap
        halves = [
            pymupdf.Rect(rect.x0, rect.y0, min(middle + pad, rect.x1), rect.y1),
            pymupdf.Rect(max(middle - pad, rect.x0), rect.y0, rect.x1, rect.y1),
        ]
        if rtl:
            halves.reverse()
        for clip in halves:
            page = out.new_page(-1, width=clip.width, height=clip.height)
            page.show_pdf_page(page.rect, doc, number - 1, clip=clip)

    out.save(out_path, garbage=4, deflate=True)
    pages = out.page_count
    out.close()
    return pages


def _engine():
    from . import require_pymupdf
    return require_pymupdf()


# --------------------------------------------------------------------------- #
# OCR and optimisation — OCRmyPDF does the work
# --------------------------------------------------------------------------- #
def have_ocr():
    return shutil.which("ocrmypdf") is not None


def tesseract_languages():
    """Language codes tesseract can actually load, or [] if it cannot be asked."""
    if not shutil.which("tesseract"):
        return []
    try:
        proc = subprocess.run(["tesseract", "--list-langs"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    lines = proc.stdout.splitlines()
    return [line.strip() for line in lines[1:] if line.strip()]


def pick_language(requested, item_language=None, available=None):
    """Choose tesseract languages: explicit request > the item's own field > spa+eng.

    Zotero records the work's language; using it beats defaulting to English on
    a Spanish-language library, and beats asking the user every time.
    """
    available = tesseract_languages() if available is None else available
    if requested:
        return requested
    field = (item_language or "").strip().lower()
    for prefix, code in LANGUAGE_PREFIXES:
        if field.startswith(prefix):
            # The item says what language the work is in; a second language
            # would only give tesseract a chance to disagree with itself.
            guess = [code]
            break
    else:
        # Nothing recorded: cover the two languages this library is mostly in.
        guess = ["spa", "eng"]
    usable = [code for code in guess if not available or code in available]
    return "+".join(usable) if usable else "eng"


def ocr_command(src, dst, language, profile="balanced", rotate=False, extra=()):
    """The exact OCRmyPDF invocation, as a list. Built here so tests can read it."""
    args = ["ocrmypdf", "-l", language]
    args += PROFILES.get(profile, PROFILES["balanced"])
    if rotate:
        args.append("--rotate-pages")
    # A scan has no text layer, but a mixed PDF (typed pages bound with scanned
    # plates) does, and OCRmyPDF refuses those unless told what to do.
    args += ["--skip-text", "--output-type", "pdf"]
    args += list(extra)
    args += [str(src), str(dst)]
    return args


def run_ocr(src, dst, language, profile="balanced", rotate=False, extra=(),
            timeout=None, on_line=None):
    """Run OCRmyPDF. Returns (ok, tail of its output)."""
    command = ocr_command(src, dst, language, profile, rotate, extra)
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "ocrmypdf not found"
    except subprocess.TimeoutExpired:
        return False, "ocrmypdf timed out"
    output = (proc.stderr or "") + (proc.stdout or "")
    if on_line:
        for line in output.splitlines():
            on_line(line)
    # 0 is clean; OCRmyPDF also uses low exit codes for "done, with warnings".
    ok = proc.returncode == 0 and os.path.exists(dst)
    return ok, "\n".join(output.strip().splitlines()[-12:])
