"""Model Context Protocol server exposing zotero-agent to any MCP client.

This is the strategic surface: a skill only reaches Claude Code, but an MCP
server reaches Claude Desktop, Codex CLI, Gemini CLI, Cursor and more — with
full *local* read-write, no zotero.org account or API key.

Needs the optional `[mcp]` extra (`uv tool install "zotero-agent[mcp]"`). Tools
are high-level (not a 1:1 mirror of CLI subcommands): fewer, well-described
tools work better for LLMs. `run_javascript` is only registered with
--allow-exec (or `allow_exec: true` in config).

Tools reuse the CLI command functions with --json, so behaviour never drifts
between the two surfaces.
"""

import io
import json
import os
from contextlib import redirect_stdout

from . import __version__
from .commands import features, prep, read, toc, write
from .term import ZotError, set_verbosity

_DEFAULTS = dict(
    json=True, yes=True, quiet=True, debug=False,
    base=None, token=None, user_id=None,
    limit=25, all=False, detail="concise", samples=1000, format="json",
    collection=None, item_type=None, tag=None,
    max_level=4, cap=400,
)

# `zot pdf-prep` reads more knobs than a tool call should have to spell out, and
# an unset one is not harmless here: overlap and timeout are arithmetic, so None
# would raise rather than fall back.
_PREP_DEFAULTS = dict(
    overlap=0.008, timeout=3600, single=None, rtl=False, rotate=False,
    no_ocr=False, force=False, replace=False, prune=False, out=None,
    trash_annotated=False,
    title=None, attachment=None, split="auto", profile="balanced",
)


class _Args:
    """Namespace whose missing attributes read as None (commands use getattr)."""
    def __init__(self, **kw):
        for k, v in {**_DEFAULTS, **kw}.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        return None


def _run(func, **kw):
    """Run a command function with --json, capture stdout, return parsed data."""
    args = _Args(**kw)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            func(args)
    except ZotError as e:
        return {"error": str(e)}
    text = buf.getvalue().strip()
    if not text:
        return {"ok": True}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"message": text}


def serve(cli_args):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise SystemExit(
            "The MCP server needs the optional dependency. Install with:\n"
            "  uv tool install \"zotero-agent[mcp]\"   (or  pipx install \"zotero-agent[mcp]\")"
        ) from e

    from .config import load_config
    set_verbosity(quiet=True, debug=False)
    allow_exec = bool(getattr(cli_args, "allow_exec", False)) or bool(load_config().get("allow_exec"))

    mcp = FastMCP("zotero-agent", version=__version__)

    @mcp.tool()
    def search_items(query: str, limit: int = 25, item_type: str = "", tag: str = "") -> dict:
        """Full-text search the local Zotero library. Returns matching items."""
        return _run(read.cmd_search, query=query, limit=limit,
                    item_type=item_type or None, tag=tag or None)

    @mcp.tool()
    def get_item(key: str) -> dict:
        """Fetch one item's full metadata by Zotero key or Better BibTeX citekey."""
        return _run(read.cmd_get, key=key)

    @mcp.tool()
    def get_item_pdf_path(key: str) -> dict:
        """Return the local filesystem path(s) of an item's PDF attachment(s)."""
        return _run(read.cmd_pdf, key=key)

    @mcp.tool()
    def get_pdf_outline(key: str) -> dict:
        """Read the table of contents (bookmarks) embedded in an item's PDF.

        Empty `entries` means the PDF has none — Zotero's reader will show an
        empty Outline tab. Use scan_pdf_outline to build one.
        """
        return _run(toc.cmd_toc, action="show", key=key)

    @mcp.tool()
    def scan_pdf_outline(key: str, cap: int = 400) -> dict:
        """Gather the evidence needed to build a table of contents for a PDF.

        Returns `suggestion` plus the evidence behind it:
          contents-links     the book's contents page links to its chapters;
                             `contentsToc.entries` already hold exact pages.
          contents-printed-numbers
                             the contents page prints page numbers, already
                             mapped to physical pages with a `confidence` each.
          typography         no contents page; `headingCandidates` lists lines
                             that look like headings, with size/bold/page.
          ocr-needed         page images only, nothing to read.

        Prefer contentsToc over headingCandidates whenever it is non-empty: that
        hierarchy is the publisher's. Build entries as
        [{level, title, page}] with page = physicalPage, and write them with
        set_pdf_outline. Never invent page numbers.
        """
        return _run(toc.cmd_toc, action="scan", key=key, cap=cap)

    @mcp.tool()
    def set_pdf_outline(key: str, entries: list, max_level: int = 4) -> dict:
        """Write a table of contents into an item's PDF, replacing any existing one.

        `entries` is [{"level": 1, "title": "...", "page": 15}, ...] with 1-based
        physical pages and levels that never jump by more than one. The previous
        outline is snapshotted first, so undo_last reverses this.
        """
        import json as _json
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            _json.dump(entries, fh)
            path = fh.name
        try:
            return _run(toc.cmd_toc, action="set", key=key, from_=path,
                        max_level=max_level)
        finally:
            os.unlink(path)

    @mcp.tool()
    def analyze_pdf_scan(key: str) -> dict:
        """Report whether an item's PDF is a scan, and how it would be prepared.

        Reads nothing into the library and changes nothing. `hasText: false`
        means the file is page images: it cannot be searched, quoted or
        summarized until prepare_pdf_scan has run. `doublePage: true` means one
        landscape page holds two printed pages, and `gutter` is where the fold
        is, as a fraction of page width.
        """
        return _run(prep.cmd_pdf_prep, keys=[key], **_PREP_DEFAULTS, dry_run=True)

    @mcp.tool()
    def prepare_pdf_scan(key: str, ocr: str = None, profile: str = "balanced",
                         split: str = "auto", gutter: float = None) -> dict:
        """Split, OCR and shrink an item's scanned PDF; attach the result to the item.

        Slow — roughly half a second per page, so a book takes minutes. Call
        analyze_pdf_scan first and tell the user what it will do.

        The processed PDF is attached *beside* the original and tagged
        `pdf-prep`; the original is kept, and calling this again on the same
        item is a no-op. `ocr` is a tesseract language string ("spa", "spa+eng")
        and defaults to the item's own language field. `profile` is balanced,
        quality (300 dpi OCR, larger file) or small. `split` is auto, always or
        never; `gutter` forces the cut as a fraction of page width.
        """
        return _run(prep.cmd_pdf_prep, keys=[key],
                    **{**_PREP_DEFAULTS, "profile": profile, "split": split},
                    ocr=ocr, gutter=gutter)

    @mcp.tool()
    def list_collections() -> dict:
        """List all collections (key, name, item count)."""
        return _run(read.cmd_collections, all=True)

    @mcp.tool()
    def get_collection_items(collection: str, recursive: bool = False) -> dict:
        """List the items in a collection (by key or name). Zotero files items in
        one collection at a time, so pass recursive=True to include subcollections."""
        return _run(read.cmd_export, collection=collection, format="json", out=None,
                    recursive=recursive)

    @mcp.tool()
    def library_stats() -> dict:
        """Library analytics: counts by item type and year, PDFs, missing abstracts."""
        return _run(read.cmd_stats)

    @mcp.tool()
    def find_missing(field: str, collection: str = "") -> dict:
        """List items missing a field (abstract, date, doi, url, ...)."""
        return _run(read.cmd_missing, field=field, collection=collection or None, detail="concise")

    @mcp.tool()
    def search_by_author(name: str) -> dict:
        """List items whose author matches a name (substring, case-insensitive)."""
        return _run(read.cmd_author, name=name, detail="concise")

    @mcp.tool()
    def create_item(kind: str, identifier: str, collection: str = "", attach_pdf: bool = False,
                    check_duplicate: bool = False) -> dict:
        """Add an item by identifier. kind is 'doi', 'isbn' or 'arxiv'. With
        check_duplicate, refuse when a close title+author match already exists."""
        return _run(write.cmd_add, kind=kind, identifier=identifier,
                    collection=collection or None, pdf=attach_pdf,
                    check_duplicate=check_duplicate)

    @mcp.tool()
    def attach_to_item(key: str, file: str = "", url: str = "", link: bool = False,
                       title: str = "") -> dict:
        """Attach a local file, a page snapshot, or a link to an existing item.
        Give exactly one of file or url; link=True stores the URL without a snapshot."""
        return _run(write.cmd_attach, key=key, file=file or None, url=url or None,
                    link=link, title=title or None)

    @mcp.tool()
    def fetch_open_access_pdf(keys: list = None, collection: str = "") -> dict:
        """Look for an open-access PDF for items already in the library, and attach
        what it finds. Items that already have a PDF are skipped."""
        return _run(write.cmd_pdf_fetch, keys=keys or [], collection=collection or None,
                    retry_with_pdf=False)

    @mcp.tool()
    def update_items(edits: list) -> dict:
        """Apply a batch of edits, undoable. Each edit is an object with a "key"
        plus any of: set (field→value map), addTags, removeTags, addToCollection,
        trash (bool). Example: [{"key":"ABCD1234","set":{"date":"2021"},"addTags":["ml"]}]."""
        return features.apply_edits_data(edits, dry_run=False, yes=True)

    @mcp.tool()
    def manage_tags(action: str, tag: str = "", keys: list = None, new: str = "") -> dict:
        """Manage tags. action: add/rm (need keys), rename (needs new), purge, normalize."""
        return _run(write.cmd_tag, action=action, tag=tag or None,
                    keys=keys or [], new=new or None, dry_run=False, map=None)

    @mcp.tool()
    def move_to_collection(collection: str, keys: list) -> dict:
        """Add items (by key or citekey) to a collection (by key or name)."""
        return _run(write.cmd_move, collection=collection, keys=keys)

    @mcp.tool()
    def create_note(key: str, text: str) -> dict:
        """Attach a child note (HTML or plain text) to an item."""
        return _run(write.cmd_note, key=key, text=text, file=None, if_not_exists=False, dry_run=False)

    @mcp.tool()
    def find_duplicates(by: str = "title", collection: str = "", fuzzy: bool = False) -> dict:
        """Find duplicate items (does NOT merge). by: 'title' or 'doi'."""
        return _run(write.cmd_dedupe, by=by, collection=collection or None,
                    merge=False, fuzzy=fuzzy, threshold=0.9)

    @mcp.tool()
    def merge_duplicates(by: str = "doi", collection: str = "") -> dict:
        """Merge duplicate groups, keeping the oldest as master. NOT reversible —
        take a backup first. by: 'title' or 'doi'."""
        return _run(write.cmd_dedupe, by=by, collection=collection or None,
                    merge=True, fuzzy=False, threshold=0.9)

    @mcp.tool()
    def enrich_metadata(field: str, source: str = "crossref", collection: str = "", limit: int = 0) -> dict:
        """Fill a missing field (doi/date/abstract) from Crossref or OpenAlex. Undoable."""
        return _run(features.cmd_enrich, field=field, source=source,
                    collection=collection or None, limit=limit, delay=0.3, dry_run=False)

    @mcp.tool()
    def export_bibliography(keys: list, style: str = "apa") -> dict:
        """Render a formatted bibliography (CSL) for the given item keys/citekeys."""
        return _run(read.cmd_bib, keys=keys, style=style, linkwrap=False, out=None)

    @mcp.tool()
    def undo_last() -> dict:
        """Undo the most recent update/enrich batch, restoring items' prior state."""
        return _run(features.cmd_undo, op="last", keep=False)

    if allow_exec:
        @mcp.tool()
        def run_javascript(code: str) -> dict:
            """Run arbitrary privileged JavaScript in Zotero's context (advanced;
            enabled because --allow-exec / allow_exec is set). Return a value."""
            from . import audit
            from .config import require_config
            from .http import post_code
            cfg = require_config(_Args())
            env = post_code(cfg, code)
            audit.record("mcp:run_javascript", code, env)
            return env

    mcp.run()
