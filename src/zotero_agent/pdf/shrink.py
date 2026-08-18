"""Making a PDF smaller without making it worse.

This is deliberately *not* part of `pdf-prep`. Prep exists to give a scan a text
layer, and OCR is the expensive, slow, once-per-file operation. Shrinking is the
opposite: cheap, repeatable, and useful on files that already have text. Running
them together meant `--no-ocr` promised "split and optimise only" and delivered a
byte-for-byte copy, because ocrmypdf's optimiser only runs as part of an OCR
pass.

What actually reclaims disk on a text-layer PDF is downsampling its page images.
Ghostscript does that while leaving the text layer and — crucially — the page
count alone, so Zotero's annotations still anchor where they did. 200 dpi is the
measured sweet spot for scanned books: about a fifth of the original size, still
legible down to pencil marginalia. /ebook (150 dpi) saves a little more at
visible cost; /printer (300 dpi) saves almost nothing.

Not every file gains. Anything already stored at ≤72 dpi, or already using JBIG2,
comes back the same size or larger — measured, 22 of 35 real books did. That is
why the result is only accepted when it verifies, and discarded otherwise.
"""

import os
import shutil
import subprocess

# Downsample targets. Mono (bitonal scans) keeps more resolution because text
# edges are the whole content there and JBIG2 makes it cheap anyway.
DEFAULT_DPI = 200
DEFAULT_MONO_DPI = 300

# A rewrite that saves less than a fifth is not worth the risk of touching the
# file at all.
DEFAULT_MAX_RATIO = 0.8

MISSING_GHOSTSCRIPT = (
    "Ghostscript (gs) not found — needed to shrink PDFs.\n"
    "  brew install ghostscript          (macOS)\n"
    "  sudo apt install ghostscript      (Debian/Ubuntu)"
)

MISSING_QPDF = (
    "qpdf not found — needed to verify the page count survived.\n"
    "  brew install qpdf                 (macOS)\n"
    "  sudo apt install qpdf             (Debian/Ubuntu)"
)


def have_ghostscript():
    return shutil.which("gs") is not None


def have_qpdf():
    return shutil.which("qpdf") is not None


def gs_command(src, dst, dpi=DEFAULT_DPI, mono_dpi=DEFAULT_MONO_DPI):
    """The Ghostscript invocation, as a list. Pure — tested without running it."""
    return [
        "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
        "-dNOPAUSE", "-dQUIET", "-dBATCH", "-dDetectDuplicateImages=true",
        "-dDownsampleColorImages=true", "-dColorImageResolution=%d" % dpi,
        "-dDownsampleGrayImages=true", "-dGrayImageResolution=%d" % dpi,
        "-dDownsampleMonoImages=true", "-dMonoImageResolution=%d" % mono_dpi,
        "-dColorImageDownsampleType=/Bicubic", "-dGrayImageDownsampleType=/Bicubic",
        "-sOutputFile=%s" % dst, src,
    ]


def page_count(path):
    """Pages in a PDF, or None if it cannot be read.

    Uses qpdf, not Ghostscript: `gs -dNODISPLAY` refuses to open files under its
    own sandbox (`/invalidfileaccess`), which looks exactly like a corrupt PDF.
    """
    try:
        out = subprocess.run(["qpdf", "--show-npages", path],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def verdict(size_before, size_after, pages_before, pages_after,
            max_ratio=DEFAULT_MAX_RATIO):
    """(accept, ratio, reason) for a candidate rewrite.

    Pure, so the acceptance rule is testable without Ghostscript. Rejecting is
    always safe here — it just leaves the original in place.
    """
    if not size_before or not size_after:
        return False, None, "empty output"
    if pages_before is None or pages_after is None:
        return False, None, "unreadable page count"
    if pages_before != pages_after:
        return False, None, "pages %s → %s" % (pages_before, pages_after)
    ratio = size_after / float(size_before)
    if ratio > max_ratio:
        return False, ratio, "no meaningful gain"
    return True, ratio, ""


def shrink_file(src, dst, dpi=DEFAULT_DPI, mono_dpi=DEFAULT_MONO_DPI, timeout=1800):
    """Run Ghostscript. Returns (ok, error). Never touches `src`."""
    try:
        proc = subprocess.run(gs_command(src, dst, dpi, mono_dpi),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "timed out after %ds" % timeout
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0 or not os.path.exists(dst) or not os.path.getsize(dst):
        tail = (proc.stderr or "").strip().splitlines()
        return False, tail[-1] if tail else "ghostscript failed"
    return True, ""
