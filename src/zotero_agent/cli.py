"""Argument parsing and dispatch for the `zot` command."""

import argparse
import urllib.error

from . import __version__, match
from .commands import admin, features, prep, read, storage, toc, write
from .constants import IS_DEV_TREE
from .pdf import shrink as shrink_defaults
from .term import ZotError, die, set_verbosity


def build_parser():
    # Global flags shared by every subcommand (config precedence: flags > env > file).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base", help="Zotero base URL (or $ZOTERO_AGENT_BASE)")
    common.add_argument("--token", help="bridge token (or $ZOTERO_AGENT_TOKEN)")
    common.add_argument("--user-id", dest="user_id", help="library userID (or $ZOTERO_AGENT_USER_ID)")
    common.add_argument("-q", "--quiet", action="store_true", help="suppress non-essential notices")
    common.add_argument("--debug", action="store_true", help="verbose diagnostics to stderr")
    common.add_argument("-y", "--yes", action="store_true", help="assume yes; don't prompt for writes")
    common.add_argument("--json", action="store_true", help="machine-readable JSON output (where supported)")

    p = argparse.ArgumentParser(
        prog="zot",
        description="Control a local Zotero library. Reads use the local HTTP API; "
        "writes go through the zotero-agent bridge plugin. Global flags (--json, "
        "-q, --yes, --base/--token/--user-id) go after the subcommand. Exit codes: "
        "0 ok, 1 error, 2 connection/exec, 3 not-found, 4 config.",
    )
    # The `(dev)` marker matters because switching between an editable install and
    # a released one leaves the version identical: see constants.IS_DEV_TREE.
    p.add_argument("--version", action="version",
                   version="zot (zotero-agent) %s%s" % (__version__, " (dev)" if IS_DEV_TREE else ""))
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, func, help):
        sp = sub.add_parser(name, help=help, parents=[common])
        sp.set_defaults(func=func)
        return sp

    add("ping", admin.cmd_ping, "check the read API and the bridge endpoint")
    add("init", admin.cmd_init, "generate token, write config, auto-detect userID")

    sp = add("search", read.cmd_search, "full-text search items (read API)")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--all", action="store_true", help="fetch all results (paginate)")
    sp.add_argument("--item-type", dest="item_type")
    sp.add_argument("--tag")
    sp.add_argument("--raw", action="store_true",
                    help="emit the read API's own JSON instead of the shared flat item shape")

    sp = add("get", read.cmd_get, "fetch one item by Zotero key or BBT citekey")
    sp.add_argument("key", help="Zotero item key, or a BBT citekey (prefix @ to force)")
    sp.add_argument("--raw", action="store_true",
                    help="emit the read API's own JSON instead of the shared flat item shape")

    sp = add("cite", read.cmd_cite, "resolve a BBT citekey to item key + PDF path(s)")
    sp.add_argument("citekey")

    sp = add("pdf", read.cmd_pdf, "print local path(s) of an item's PDF(s), by key or citekey")
    sp.add_argument("key", help="item/attachment key, or a BBT citekey (prefix @ to force)")

    sp = add("toc", toc.cmd_toc, "read/detect/write a PDF's table of contents — needs the [toc] extra")
    sp.add_argument("action", choices=["show", "scan", "set", "auto", "clear"],
                    help="show the embedded outline, scan for evidence, set one from "
                         "a file, build one automatically, or remove it")
    sp.add_argument("key", help="item/attachment key, or a BBT citekey (prefix @ to force)")
    sp.add_argument("--from", dest="from_", metavar="FILE",
                    help="outline to write (for set); '-' reads stdin. Text or JSON.")
    sp.add_argument("--attachment", help="attachment key, when the item has several PDFs")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="preview the outline; don't touch the file")
    sp.add_argument("--max-level", dest="max_level", type=int, default=4,
                    help="deepest nesting level to keep (default 4)")
    sp.add_argument("--offset", type=int,
                    help="force printed-page → physical-page delta instead of detecting it")
    sp.add_argument("--backup", action="store_true",
                    help="copy the untouched PDF into ~/.local/state/zotero-agent first")
    sp.add_argument("--mark-for-sync", dest="mark_for_sync", action="store_true",
                    help="tell Zotero to re-upload the file on the next sync")
    sp.add_argument("--cap", type=int, default=400, help="max heading candidates in a scan")
    sp.add_argument("--samples", type=int, default=20, help="rows to print per section of a scan")

    sp = add("pdf-prep", prep.cmd_pdf_prep,
             "prepare a scanned PDF: split double pages, OCR, shrink — needs [toc] + ocrmypdf")
    sp.add_argument("keys", nargs="*", help="item keys or BBT citekeys ('-' reads stdin)")
    sp.add_argument("--collection", help="process every item in a collection (key or name)")
    sp.add_argument("--attachment", help="attachment key, when the item has several PDFs")
    sp.add_argument("--split", choices=["auto", "always", "never"], default="auto",
                    help="split two-up scans into one page per leaf (default: auto-detect)")
    sp.add_argument("--gutter", type=float,
                    help="force the cut as a fraction of page width (0.5 = middle)")
    sp.add_argument("--overlap", type=float, default=0.008,
                    help="extra width each half keeps past the cut (default 0.008)")
    sp.add_argument("--single", metavar="PAGES",
                    help="pages to leave whole, e.g. '1,2,147' (covers, fold-outs)")
    sp.add_argument("--rtl", action="store_true", help="right-to-left book: right half first")
    sp.add_argument("--ocr", metavar="LANG",
                    help="tesseract languages (default: from the item's language field)")
    sp.add_argument("--no-ocr", dest="no_ocr", action="store_true",
                    help="split and optimise only; leave the file without a text layer")
    sp.add_argument("--profile", choices=["balanced", "quality", "small"], default="balanced",
                    help="balanced (default), quality (300 dpi OCR, bigger), or small")
    sp.add_argument("--rotate", action="store_true", help="let OCR fix sideways pages")
    sp.add_argument("--title", help="title for the new attachment (default: 'PDF (OCR)')")
    sp.add_argument("--out", metavar="DIR",
                    help="write the result to a directory instead of attaching it")
    sp.add_argument("--replace", action="store_true",
                    help="trash the original attachment once the new one is attached")
    sp.add_argument("--prune", action="store_true",
                    help="trash originals superseded by an earlier run; processes nothing")
    sp.add_argument("--trash-annotated", dest="trash_annotated", action="store_true",
                    help="also trash originals carrying highlights (they do NOT "
                         "follow the new file — Zotero ties them to the attachment)")
    sp.add_argument("--force", action="store_true", help="reprocess items already prepared")
    sp.add_argument("--timeout", type=int, default=3600, help="seconds to allow OCR per item")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="analyse and report the plan; touch nothing")

    sp = add("collections", read.cmd_collections, "list collections (read API)")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--all", action="store_true", help="fetch all (paginate)")

    sp = add("tags", read.cmd_tags, "list tags (read API)")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--all", action="store_true", help="fetch all (paginate)")

    sp = add("export", read.cmd_export, "export a collection's items (by key or name)")
    sp.add_argument("collection", help="collection key or name")
    sp.add_argument("--format", choices=["json", "csv", "csljson", "bibtex", "biblatex", "ris"], default="json")
    sp.add_argument("--out", help="write to file instead of stdout")
    sp.add_argument("--recursive", action="store_true",
                    help="include items in subcollections (default: only items filed "
                         "directly in this collection)")

    sp = add("missing", read.cmd_missing, "list items missing a field (abstract/date/doi/url/...)")
    sp.add_argument("field", help="field or alias: abstract, date, doi, url, publisher, publication")
    sp.add_argument("--collection", help="limit to a collection (key or name)")
    sp.add_argument("--detail", choices=["concise", "full"], default="concise", help="full keeps abstracts")

    sp = add("author", read.cmd_author, "list items whose author matches a name")
    sp.add_argument("name")
    sp.add_argument("--detail", choices=["concise", "full"], default="concise", help="full keeps abstracts")

    sp = add("add", write.cmd_add, "add an item by identifier (doi/isbn/arxiv), with optional PDF")
    sp.add_argument("kind", choices=["doi", "isbn", "arxiv"])
    sp.add_argument("identifier")
    sp.add_argument("--pdf", action="store_true", help="also try to attach an open-access PDF")
    sp.add_argument("--collection", help="add to this collection (key or name)")
    sp.add_argument("--check-duplicate", dest="check_duplicate", action="store_true",
                    help="refuse to add if a close title+author match is already in the library")

    sp = add("dedupe", write.cmd_dedupe, "find duplicate items; --plan writes a reviewable merge plan")
    sp.add_argument("--by", choices=["title", "doi", "content"], default="title",
                    help="what makes two items the same: their title, their DOI, or "
                         "the file they share ('content' finds the ones whose titles "
                         "do not resemble each other)")
    sp.add_argument("--collection", help="limit to a collection (key or name); else whole library")
    sp.add_argument("--plan", metavar="FILE",
                    help="write the merge plan as JSONL for review, then run `zot merge --from FILE`")
    sp.add_argument("--merge", action="store_true",
                    help="merge the confident groups now (master is the oldest item, or "
                         "the best-documented one with --by content); NOT undoable")
    sp.add_argument("--force", action="store_true",
                    help="with --merge, also merge groups whose author/year/edition disagree")
    sp.add_argument("--fuzzy", action="store_true",
                    help="also group near-identical titles (Levenshtein); title axis only")
    sp.add_argument("--threshold", type=float, default=0.9, help="similarity threshold for --fuzzy (0-1)")
    sp.add_argument("--samples", type=int, default=10)

    sp = add("merge", write.cmd_merge, "execute a merge plan from `zot dedupe --plan` (NOT undoable)")
    sp.add_argument("--from", dest="source", required=True, metavar="FILE",
                    help="JSONL merge plan, or '-' for stdin")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="preview, don't merge")
    sp.add_argument("--samples", type=int, default=20)

    sp = add("tag", write.cmd_tag, "manage tags: add/rm on items, rename/purge, or normalize")
    sp.add_argument("action", choices=["add", "rm", "rename", "purge", "normalize", "from-collections"])
    sp.add_argument("tag", nargs="?", help="the tag (for add/rm/rename)")
    sp.add_argument("keys", nargs="*", help="item keys/citekeys (for add/rm; '-' reads stdin)")
    sp.add_argument("--new", help="new tag name (for rename)")
    sp.add_argument("--map", help="CSV old,new mapping file (for normalize)")
    sp.add_argument("--rules", help="JSON rules file (for from-collections): "
                                    "{containers:[...], rules:[{match, tags}]}")
    sp.add_argument("--out", metavar="FILE",
                    help="write the plan as JSONL for `zot apply` (for from-collections)")
    sp.add_argument("--apply", action="store_true",
                    help="write the tags now, undoably (for from-collections)")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="preview (for normalize / from-collections)")
    sp.add_argument("--samples", type=int, default=20)

    sp = add("set", write.cmd_set, "set a field on one or more items")
    sp.add_argument("field", help="field or alias (e.g. abstract, publisher, date)")
    sp.add_argument("value")
    sp.add_argument("keys", nargs="+", help="item keys/citekeys ('-' reads stdin)")

    sp = add("move", write.cmd_move, "add items to a collection (by key or name)")
    sp.add_argument("collection")
    sp.add_argument("keys", nargs="+", help="item keys/citekeys ('-' reads stdin)")

    sp = add("collection", write.cmd_collection, "create a collection (optionally under a parent)")
    sp.add_argument("name")
    sp.add_argument("--parent", help="parent collection (key or name)")

    sp = add("apply", features.cmd_apply, "apply a JSONL edit script (set/tags/collection/trash), undoable")
    sp.add_argument("file", help="JSONL file, or '-' for stdin")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="preview writes, don't persist")
    sp.add_argument("--samples", type=int, default=20)

    sp = add("undo", features.cmd_undo, "restore items from an apply/enrich snapshot")
    sp.add_argument("op", nargs="?", default="last", help="op id, 'last' (default), or 'list'")
    sp.add_argument("--keep", action="store_true", help="don't delete the snapshot after undo")

    sp = add("enrich", features.cmd_enrich, "fill missing DOI/date/abstract from Crossref/OpenAlex")
    sp.add_argument("--field", required=True, choices=["doi", "date", "abstract"])
    sp.add_argument("--source", choices=["crossref", "openalex"], default="crossref")
    sp.add_argument("--collection", help="limit to a collection (key or name)")
    sp.add_argument("--limit", type=int, default=0, help="cap items looked up (0 = no cap)")
    sp.add_argument("--delay", type=float, default=0.3, help="seconds between API calls (be polite)")
    sp.add_argument("--min-similarity", dest="min_similarity", type=float, default=match.MIN_TITLE_SIMILARITY,
                    help="title-similarity floor for accepting a search hit (0-1); "
                         "items with no year and no author need %.2f regardless"
                         % match.MIN_TITLE_SIMILARITY_UNCORROBORATED)
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="preview, don't write")
    sp.add_argument("--samples", type=int, default=20)

    sp = add("annotations", read.cmd_annotations, "list a PDF's annotations; --to-note extracts them")
    sp.add_argument("key")
    sp.add_argument("--to-note", dest="to_note", action="store_true", help="write annotations into a child note")
    sp.add_argument("--samples", type=int, default=20)

    sp = add("stats", read.cmd_stats, "library analytics (counts by type/year, PDFs, etc.)")

    sp = add("bib", read.cmd_bib, "render a formatted bibliography for items")
    sp.add_argument("keys", nargs="+", help="item keys or citekeys")
    sp.add_argument("--style", default="apa", help="CSL style id (e.g. apa, chicago-note-bibliography)")
    sp.add_argument("--linkwrap", action="store_true")
    sp.add_argument("--out")

    sp = add("recent", read.cmd_recent, "list recently added items")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--raw", action="store_true",
                    help="emit the read API's own JSON instead of the shared flat item shape")

    add("sync", admin.cmd_sync, "trigger a Zotero sync (needs a sync account)")

    sp = add("restart", admin.cmd_restart,
             "restart Zotero (or reload just the bridge plugin) and wait for it to come back")
    sp.add_argument("--plugin", action="store_true",
                    help="reload only the zotero-agent plugin, leaving Zotero running")
    sp.add_argument("--no-launch", dest="no_launch", action="store_true",
                    help="never start the Zotero app; only act on a running one")
    sp.add_argument("--timeout", type=int, default=admin.RESTART_TIMEOUT,
                    help="seconds to wait for the bridge to answer again (default: %d)"
                         % admin.RESTART_TIMEOUT)

    sp = add("related", read.cmd_related, "list items related to an item")
    sp.add_argument("key")

    sp = add("notes", read.cmd_notes, "list an item's child notes (by key or citekey)")
    sp.add_argument("key")

    sp = add("note", write.cmd_note, "add a child note to an item (by key or citekey)")
    sp.add_argument("key")
    sp.add_argument("--file", help="read note body (HTML or text) from a file")
    sp.add_argument("--text", help="note body as a string")
    sp.add_argument("--if-not-exists", dest="if_not_exists", action="store_true",
                    help="skip if an identical note already exists (idempotent)")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="show what would be added, don't write")

    sp = add("attach", write.cmd_attach, "attach a file, snapshot or link to an existing item")
    sp.add_argument("key", help="item key, or a BBT citekey (prefix @ to force)")
    sp.add_argument("--file", help="local file to import as an attachment")
    sp.add_argument("--url", help="URL to attach (a snapshot unless --link)")
    sp.add_argument("--link", action="store_true", help="store the URL as a link, not a snapshot")
    sp.add_argument("--title", help="attachment title (defaults to Zotero's)")

    sp = add("pdf-fetch", write.cmd_pdf_fetch, "look for an open-access PDF for items already in the library")
    sp.add_argument("keys", nargs="*", help="item keys or BBT citekeys; '-' reads them from stdin")
    sp.add_argument("--collection", help="every item in a collection (key or name)")
    sp.add_argument("--retry-with-pdf", dest="retry_with_pdf", action="store_true",
                    help="also try items that already have a PDF attached")

    sp = add("backup", admin.cmd_backup, "snapshot zotero.sqlite to a timestamped file")
    sp.add_argument("--dir", help="destination dir (default: ~/.config/zotero-agent/backups)")

    sp = add("disk", storage.cmd_disk, "where the attachment store's gigabytes are")
    sp.add_argument("--min-mb", dest="min_mb", type=int, default=25,
                    help="threshold for listing heavy PDFs (default 25)")
    sp.add_argument("--samples", type=int, default=15)

    sp = add("shrink", storage.cmd_shrink,
             "downsample oversized PDFs in place — needs ghostscript + qpdf")
    sp.add_argument("keys", nargs="*", help="item or attachment keys/citekeys ('-' reads stdin); "
                                            "omit to sweep everything over --min-mb")
    sp.add_argument("--min-mb", dest="min_mb", type=int, default=25,
                    help="with no keys, shrink every PDF at least this big (default 25)")
    sp.add_argument("--max-mb", dest="max_mb", type=int,
                    help="with no keys, stop at this size — lets you sweep one band at a time")
    sp.add_argument("--force", action="store_true",
                    help="re-examine files already tagged 'shrunk' or 'shrink-nogain' "
                         "(re-shrinking is lossy: it re-encodes them again)")
    sp.add_argument("--dpi", type=int, default=shrink_defaults.DEFAULT_DPI,
                    help="target resolution for colour/grey images (default %d)"
                         % shrink_defaults.DEFAULT_DPI)
    sp.add_argument("--mono-dpi", dest="mono_dpi", type=int, default=shrink_defaults.DEFAULT_MONO_DPI,
                    help="target resolution for bitonal images (default %d)"
                         % shrink_defaults.DEFAULT_MONO_DPI)
    sp.add_argument("--max-ratio", dest="max_ratio", type=float,
                    default=shrink_defaults.DEFAULT_MAX_RATIO,
                    help="keep the original unless the rewrite is at most this fraction "
                         "of its size (default %.2f)" % shrink_defaults.DEFAULT_MAX_RATIO)
    sp.add_argument("--out", metavar="DIR", help="write results to DIR instead of replacing in place")
    sp.add_argument("--timeout", type=int, default=1800, help="seconds to allow per file")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="report the plan, touch nothing")

    sp = add("gc", storage.cmd_gc, "trash attachments nothing points at (orphans, snapshots)")
    sp.add_argument("--orphans", action="store_true",
                    help="attachments nothing claims: no parent, no collection, no tags, "
                         "no annotations (a filed parentless PDF is an item, and is kept)")
    sp.add_argument("--snapshots", action="store_true",
                    help="saved page snapshots (the item keeps its URL)")
    sp.add_argument("--empty-trash", dest="empty_trash", action="store_true",
                    help="also erase everything already in the trash — PERMANENT")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="report, don't write")

    sp = add("lint", read.cmd_lint, "report data-quality issues in the library")
    sp.add_argument("--samples", type=int, default=10, help="examples to show per issue")

    sp = add("exec", admin.cmd_exec, "run JS via the bridge. SOURCE is a file, '-' for stdin, or inline JS.")
    sp.add_argument("source")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="intercept writes and report what would change (best-effort)")

    sp = add("mcp", _cmd_mcp, "run the Model Context Protocol server (stdio) — needs the [mcp] extra")
    sp.add_argument("--allow-exec", action="store_true",
                    help="expose the run_javascript tool (arbitrary JS)")

    sp = add("completion", admin.cmd_completion, "print a shell completion script (bash/zsh/fish)")
    sp.add_argument("shell", choices=["bash", "zsh", "fish"])

    sp = add("skill", admin.cmd_skill, "install the bundled agent skill (Claude Code), or print AGENTS.md")
    sp.add_argument("action", choices=["install", "path", "agents-md"],
                    help="install it, print the bundled source path, or print AGENTS.md to stdout")
    sp.add_argument("--dest", help="install here (default: ~/.claude/skills/zotero)")
    sp.add_argument("--project", action="store_true",
                    help="install into ./.claude/skills/zotero (this project only)")
    sp.add_argument("--force", action="store_true", help="replace an existing install")
    sp.add_argument("--link", action="store_true",
                    help="symlink the source instead of copying (dev checkout)")

    return p


def _cmd_mcp(args):
    from .mcp_server import serve
    serve(args)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    set_verbosity(getattr(args, "quiet", False), getattr(args, "debug", False))
    import sys
    try:
        args.func(args)
    except ZotError as e:
        die_print(e)
    except urllib.error.HTTPError as e:
        print("error: HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")), file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print("error: cannot reach Zotero (%s). Is it running?" % e.reason, file=sys.stderr)
        sys.exit(2)
    except BrokenPipeError:
        pass
    except (TimeoutError, OSError) as e:
        print("error: request timed out or failed (%s). For heavy operations, "
              "scope with --collection." % e, file=sys.stderr)
        sys.exit(2)


def die_print(err):
    import sys
    print("error: " + str(err), file=sys.stderr)
    sys.exit(err.code)


# `die` is re-exported for tests/back-compat; the actual raising lives in term.
_ = die
