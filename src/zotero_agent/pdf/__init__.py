"""PDF outline (bookmark) reading, detection and writing — the `zot toc` engine.

An outline is the tree a PDF reader shows in its sidebar (`/Root/Outlines` in the
spec; "bookmarks" in Acrobat). Zotero's reader displays it, but cannot create it,
so PDFs arrive with either a good outline, a bad auto-extracted one, or none.

Layering, and why:

  pagemap  pure Python. The delicate part of this feature is arithmetic on page
           numbers, not PDF I/O, so it lives where it can be unit-tested without
           a PDF engine or a fixture file.
  scan     reads a document: text layer, page labels, printed table of contents,
           typographic heading candidates.
  outline  reads, validates and writes the outline tree itself.

PyMuPDF is reached only through `require_pymupdf()`, and only from `scan` and
`outline`. Nothing outside this subpackage imports it, so the rest of the CLI
stays importable — and testable — without the `[toc]` extra installed.
"""

from ..constants import EXIT_CONFIG
from ..term import die

INSTALL_HINT = (
    "`zot toc` needs a PDF engine. Install the extra:\n"
    "  uv tool install --force 'zotero-agent[toc]'   (or: pipx install 'zotero-agent[toc]')\n"
    "Already installed with uv? Add it in place:\n"
    "  uv tool install --force --with pymupdf zotero-agent"
)


def load_pymupdf():
    """Import PyMuPDF, or return None. Use this to *probe*; see require_pymupdf."""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        pass
    try:
        # PyMuPDF only grew the `pymupdf` module name in 1.24.3; older builds,
        # and some distro packages, still expose it as `fitz`.
        import fitz
        return fitz
    except ImportError:
        return None


def require_pymupdf():
    """Import PyMuPDF or die with the exact command that installs it."""
    mod = load_pymupdf()
    if mod is None:
        die(INSTALL_HINT, code=EXIT_CONFIG)
    return mod
