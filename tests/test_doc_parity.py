"""Guard against docs/ ↔ website drift.

Three docs exist twice: as plain Markdown for the repo and as a Starlight page for
the site. They are *not* copies — the web versions carry frontmatter, site-relative
links, asides, and extra material — so neither can be generated from the other the
way `docs/commands.md` is generated from argparse.

What must never diverge is the *facts*: install routes, the update mechanism, the
security guarantees. Every entry below is a fact that has to hold in both copies;
if you add one to a page, add it here so the other copy cannot be forgotten. This
is the class of bug that shipped a stale `install.sh` instruction on the site while
the repo's copy was correct.
"""

import os
import re
import unittest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# label -> (repo copy, website copy)
PAIRS = {
    "architecture": ("docs/architecture.md",
                     "web/src/content/docs/architecture.md"),
    "security": ("docs/security.md",
                 "web/src/content/docs/security.md"),
    "install": ("docs/install.md",
                "web/src/content/docs/getting-started/install.md"),
}

# label -> [(regex, what the fact is)] — must appear in BOTH copies.
SHARED_FACTS = {
    "architecture": [
        (r"release asset", "the XPI's single distribution channel"),
        (r"updates\.json", "Zotero auto-update manifest"),
        (r"zot skill install", "how the skill is installed"),
        (r"[Hh]omebrew", "the tap as a generated mirror of the PyPI sdist"),
    ],
    "security": [
        (r"X-Zotero-Agent-Token", "the required token header"),
        (r"update_hash", "sha256-verified plugin updates"),
        (r"loopback", "loopback-only binding"),
        (r"extensions\.zotero-agent\.token", "the pref that overrides the token"),
        (r"--require-hashes", "what the Homebrew route pins"),
        (r"pdf-prep", "the one command that runs an external program"),
        (r"--trash-annotated", "annotations do not follow the processed file"),
    ],
    "install": [
        (r"releases/latest/download/zotero-agent-bridge\.xpi", "permanent XPI link"),
        (r"zot skill install", "installing the bundled skill"),
        (r"24 hours|once a day", "Zotero's plugin-update interval"),
        (r"--refresh", "uv's cached-index gotcha"),
        (r"extensions\.zotero-agent\.token", "the token pref"),
        (r"~/\.local/state/zotero-agent", "the state dir an uninstall must remove"),
        (r"uv tool uninstall", "how to uninstall the CLI"),
        (r"zotero-agent\[toc\]", "the extra that enables zot toc"),
        (r"pymupdf", "what the toc extra pulls in"),
        (r"ocrmypdf", "the external program zot pdf-prep needs for OCR"),
        (r"tesseract-lang|tesseract-ocr-", "the language packs OCR needs to be correct"),
        (r"--no-ocr", "how to run pdf-prep without OCRmyPDF installed"),
        (r"brew install alex-roc/tap/zotero-agent", "the Homebrew route"),
        (r"brew upgrade zotero-agent", "how the Homebrew install is updated"),
        (r"command -v zot", "which install wins when two routes are present"),
        (r"zot source", "the ping line that names the answering install"),
        (r"zot restart --plugin", "the CLI way out of a manual Zotero restart"),
        (r"both extras|extras included|everything", "that brew ships the extras, "
                                                    "since a keg cannot gain them later"),
    ],
}

# Retired wording that must not resurface in either copy (any doc, any site page).
FORBIDDEN = [
    (r"zot plugin build", "the removed plugin-build command"),
    (r"skill/scripts", "the XPI bundling that no longer happens"),
    (r"self-built plugin", "the XPI is built in CI, not by users"),
]


def _read(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _flat(text):
    """Collapse whitespace: prose is hard-wrapped at 80 columns, so a fact can be
    split across lines in one copy and not the other."""
    return re.sub(r"\s+", " ", text)


class TestDocParity(unittest.TestCase):
    def test_shared_facts_appear_in_both_copies(self):
        for label, (repo_doc, web_doc) in PAIRS.items():
            for path in (repo_doc, web_doc):
                text = _flat(_read(path))
                for pattern, what in SHARED_FACTS[label]:
                    self.assertTrue(
                        re.search(pattern, text, re.I),
                        "%s is missing %s (/%s/) — the other copy has it, so they "
                        "have drifted" % (path, what, pattern))

    def test_retired_wording_is_gone_everywhere(self):
        roots = [os.path.join(_ROOT, "docs"), os.path.join(_ROOT, "web", "src", "content", "docs"),
                 os.path.join(_ROOT, "skill")]
        # install.sh is scanned too: its header comment described `zot plugin build`
        # and bundling into skill/scripts/ for two releases after both were removed,
        # precisely because it sat outside this sweep.
        pages = [os.path.join(_ROOT, "README.md"), os.path.join(_ROOT, "install.sh")]
        for root in roots:
            for dirpath, _dirs, files in os.walk(root):
                pages += [os.path.join(dirpath, f) for f in files if f.endswith((".md", ".mdx"))]
        for page in pages:
            if os.path.basename(page) == "commands.md":
                continue  # generated from the CLI; it cannot name a retired command
            with open(page, encoding="utf-8") as fh:
                text = fh.read()
            for pattern, why in FORBIDDEN:
                self.assertNotRegex(
                    text, pattern,
                    "%s still mentions %s (%s)" % (os.path.relpath(page, _ROOT), pattern, why))


if __name__ == "__main__":
    unittest.main()
