"""Argument parsing and dispatch for the `zot` command."""

import argparse
import urllib.error

from . import __version__
from .commands import admin, features, read, write
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
    p.add_argument("--version", action="version", version="zot (zotero-agent) %s" % __version__)
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

    sp = add("get", read.cmd_get, "fetch one item by Zotero key or BBT citekey")
    sp.add_argument("key", help="Zotero item key, or a BBT citekey (prefix @ to force)")

    sp = add("cite", read.cmd_cite, "resolve a BBT citekey to item key + PDF path(s)")
    sp.add_argument("citekey")

    sp = add("pdf", read.cmd_pdf, "print local path(s) of an item's PDF(s), by key or citekey")
    sp.add_argument("key", help="item/attachment key, or a BBT citekey (prefix @ to force)")

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

    sp = add("dedupe", write.cmd_dedupe, "find (and optionally merge) duplicate items")
    sp.add_argument("--by", choices=["title", "doi"], default="title")
    sp.add_argument("--collection", help="limit to a collection (key or name); else whole library")
    sp.add_argument("--merge", action="store_true", help="merge each group (keeps oldest as master)")
    sp.add_argument("--fuzzy", action="store_true", help="also group near-identical titles (Levenshtein)")
    sp.add_argument("--threshold", type=float, default=0.9, help="similarity threshold for --fuzzy (0-1)")
    sp.add_argument("--samples", type=int, default=10)

    sp = add("tag", write.cmd_tag, "manage tags: add/rm on items, rename/purge, or normalize")
    sp.add_argument("action", choices=["add", "rm", "rename", "purge", "normalize"])
    sp.add_argument("tag", nargs="?", help="the tag (for add/rm/rename)")
    sp.add_argument("keys", nargs="*", help="item keys/citekeys (for add/rm; '-' reads stdin)")
    sp.add_argument("--new", help="new tag name (for rename)")
    sp.add_argument("--map", help="CSV old,new mapping file (for normalize)")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="preview (for normalize)")
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

    add("sync", admin.cmd_sync, "trigger a Zotero sync (needs a sync account)")

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

    sp = add("backup", admin.cmd_backup, "snapshot zotero.sqlite to a timestamped file")
    sp.add_argument("--dir", help="destination dir (default: ~/.config/zotero-agent/backups)")

    sp = add("lint", read.cmd_lint, "report data-quality issues in the library")
    sp.add_argument("--samples", type=int, default=10, help="examples to show per issue")

    sp = add("exec", admin.cmd_exec, "run JS via the bridge. SOURCE is a file, '-' for stdin, or inline JS.")
    sp.add_argument("source")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="intercept writes and report what would change (best-effort)")

    sp = add("mcp", _cmd_mcp, "run the Model Context Protocol server (stdio) — needs the [mcp] extra")
    sp.add_argument("--allow-exec", action="store_true",
                    help="expose the run_javascript tool (arbitrary JS)")

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


def die_print(err):
    import sys
    print("error: " + str(err), file=sys.stderr)
    sys.exit(err.code)


# `die` is re-exported for tests/back-compat; the actual raising lives in term.
_ = die
