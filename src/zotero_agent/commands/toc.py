"""`zot toc` — read, detect and write the table of contents of an item's PDF.

Zotero's reader shows a PDF's embedded outline in its sidebar but cannot create
one, and its own auto-extraction is experimental and noisy. Writing a real
outline into the file therefore fixes the sidebar for good, in every reader.

The pipeline is deliberately split so a human or an agent sits in the middle:

    zot toc scan KEY --json     evidence: printed contents, heading candidates
              (decide)          which lines are chapters, and how they nest
    zot toc set KEY --from F    write the decision into the file

`zot toc auto` collapses all three with a deterministic default, for scripted
use. Either way the write is guarded by confirm_write, previewable with
--dry-run, and reversible with `zot undo`.
"""

import os
import shutil
import sys

from ..constants import EXIT_CONFIG, EXIT_GENERIC, EXIT_NOTFOUND, STATE_DIR
from ..output import dump_json
from ..term import confirm_write, die, info
from .read import resolve_pdf_attachment

OCR_HINT = (
    "This PDF has no text layer — it is page images, so there is nothing to read\n"
    "headings from. OCR it first, then re-run:\n"
    "  ocrmypdf --skip-text --rotate-pages --deskew -l spa+eng in.pdf out.pdf"
)


# --------------------------------------------------------------------------- #
# picking the file
# --------------------------------------------------------------------------- #
def _resolve_pdf(args):
    """(cfg, item, attachment) for the item's single PDF, or die explaining."""
    from ..config import require_config
    cfg = require_config(args)
    item, attachment = resolve_pdf_attachment(cfg, args.key, getattr(args, "attachment", None))
    return cfg, item, attachment


def _open(attachment):
    from ..pdf import scan as pdf_scan
    try:
        return pdf_scan.open_pdf(attachment["path"])
    except Exception as exc:
        die("cannot open %s: %s" % (attachment["path"], exc), code=EXIT_GENERIC)


def _context(item, attachment):
    return {"itemKey": item.get("itemKey"), "title": item.get("title"),
            "attachmentKey": attachment.get("attachmentKey"), "path": attachment["path"]}


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #
def _show(args):
    from ..pdf import outline as pdf_outline
    _cfg, item, attachment = _resolve_pdf(args)
    doc = _open(attachment)
    try:
        entries = pdf_outline.read_outline(doc)
    finally:
        doc.close()
    if args.json:
        payload = _context(item, attachment)
        payload["entries"] = entries
        dump_json(payload)
        return
    if not entries:
        info("%s has no embedded outline. Try `zot toc scan %s`."
             % (attachment["path"], args.key))
        return
    print(pdf_outline.render_toc_text(entries), end="")


def _scan_report(args, item, attachment, doc):
    from ..pdf import scan as pdf_scan
    report = _context(item, attachment)
    report.update(pdf_scan.scan(doc, offset=args.offset, cap=args.cap))
    return report


def _scan(args):
    _cfg, item, attachment = _resolve_pdf(args)
    doc = _open(attachment)
    try:
        report = _scan_report(args, item, attachment, doc)
    finally:
        doc.close()

    if args.json:
        dump_json(report)
        return

    print("%s  (%d pages)" % (attachment["path"], report["pages"]))
    print("text layer   : %s (%.0f chars/page)"
          % ("yes" if report["textLayer"] else "NO", report["charsPerPage"]))
    print("page labels  : %s" % ("yes" if report["pageLabels"] else "no"))
    print("existing TOC : %d entries" % len(report["existingOutline"]))
    print("suggestion   : %s" % report["suggestion"])
    if report["suggestion"] == "ocr-needed":
        print()
        print(OCR_HINT)
        return

    contents = report["contentsToc"]
    if contents["entries"]:
        print("\ncontents page(s) %s, read by %s — %d entries:"
              % (", ".join(map(str, contents["pages"])), contents["source"],
                 len(contents["entries"])))
        for entry in contents["entries"][: args.samples]:
            printed = entry.get("printedPage")
            print("  %sL%d  p.%-4s %-16s %s"
                  % ("  " * (entry.get("level", 1) - 1), entry.get("level", 1),
                     entry["physicalPage"],
                     "(printed %s, %s)" % (printed, entry["confidence"]) if printed
                     else "(%s)" % entry["confidence"],
                     entry["title"][:60]))
        _report_more(contents["entries"], args.samples)

    if report["headingCandidates"]:
        print("\n%d typographic heading candidate(s), body text is %.1fpt:"
              % (len(report["headingCandidates"]), report["bodyFontSize"]))
        for candidate in report["headingCandidates"][: args.samples]:
            print("  p.%-4s %5.1fpt %-5s score %d  %s"
                  % (candidate["page"], candidate["size"],
                     "bold" if candidate["bold"] else "", candidate["score"],
                     candidate["text"][:60]))
        _report_more(report["headingCandidates"], args.samples)
        if report["truncated"]:
            info("note: candidates were capped at %d (highest-scoring kept); "
                 "raise it with --cap." % args.cap)

    print("\nNext: `zot toc auto %s --dry-run`, or feed `--json` to an agent and "
          "write its answer back with `zot toc set %s --from -`." % (args.key, args.key))


def _report_more(rows, samples):
    if len(rows) > samples:
        print("  ... and %d more (--samples %d, or --json for all)"
              % (len(rows) - samples, len(rows)))


def _read_source(source):
    if source == "-":
        return sys.stdin.read()
    try:
        with open(source, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        die("cannot read %s: %s" % (source, exc), code=EXIT_NOTFOUND)


def _set(args):
    from ..pdf import outline as pdf_outline
    if not args.from_:
        die("`zot toc set` needs --from FILE (or --from - to read stdin). "
            "The format is one 'title<TAB>page' per line, indented by level; "
            "`zot toc show --json` and `zot toc scan --json` both feed it.",
            code=EXIT_GENERIC)
    raw = _read_source(args.from_)
    try:
        entries = pdf_outline.load_entries(raw)
    except ValueError as exc:
        die(str(exc), code=EXIT_GENERIC)
    if not entries:
        die("no outline entries in %s" % args.from_, code=EXIT_GENERIC)
    _apply(args, entries, "toc set")


def _auto(args):
    from ..pdf import scan as pdf_scan
    resolved = _resolve_pdf(args)
    _cfg, item, attachment = resolved
    doc = _open(attachment)
    try:
        report = _scan_report(args, item, attachment, doc)
    finally:
        doc.close()
    if report["suggestion"] == "ocr-needed":
        die(OCR_HINT, code=EXIT_GENERIC)
    entries = pdf_scan.auto_entries(report, max_level=args.max_level)
    if not entries:
        die("found no headings to build an outline from. Inspect the evidence with "
            "`zot toc scan %s --json`." % args.key, code=EXIT_NOTFOUND)
    info("route: %s (%d entries)" % (report["suggestion"], len(entries)))
    _apply(args, entries, "toc auto", resolved=resolved)


def _clear(args):
    _apply(args, [], "toc clear")


# --------------------------------------------------------------------------- #
# the write
# --------------------------------------------------------------------------- #
def _apply(args, entries, label, resolved=None):
    """Normalize, preview or write, and leave an undo snapshot behind.

    `resolved` lets a caller that already located the file pass it in, so one
    `zot toc auto` costs one bridge round-trip instead of two.
    """
    from ..pdf import outline as pdf_outline
    from .features import snapshot_outline

    cfg, item, attachment = resolved or _resolve_pdf(args)
    path = attachment["path"]
    doc = _open(attachment)
    clean, warnings = pdf_outline.normalize(entries, page_count=doc.page_count,
                                            max_level=args.max_level)
    for warning in warnings:
        info("note: " + warning)
    if entries and not clean:
        doc.close()
        die("every entry was rejected — nothing to write", code=EXIT_GENERIC)

    if args.dry_run:
        previous = pdf_outline.read_outline(doc)
        doc.close()
        print("DRY-RUN — %s is not modified." % path)
        print("Outline would go from %d to %d entries." % (len(previous), len(clean)))
        if clean:
            print()
            print(pdf_outline.render_toc_text(clean), end="")
        return

    confirm_write(args, "This rewrites the outline of %s (%d entries)."
                  % (path, len(clean)))

    previous = pdf_outline.read_outline(doc)
    context = _context(item, attachment)
    context["entries"] = previous
    op_id = snapshot_outline(label.replace(" ", "-"), context)

    if args.backup:
        info("backed the original file up to %s" % _backup(path, attachment, op_id))

    try:
        if clean:
            mode = pdf_outline.write_outline(doc, clean, path)
        else:
            mode = pdf_outline.clear_outline(doc, path)
    except Exception as exc:
        die("failed to write the outline: %s" % exc, code=EXIT_GENERIC)
    finally:
        if not doc.is_closed:
            doc.close()

    if args.json:
        dump_json({"path": path, "written": len(clean), "previous": len(previous),
                   "save": mode, "opId": op_id, "warnings": warnings})
    else:
        print("Wrote %d outline entr%s to %s (%s save)."
              % (len(clean), "y" if len(clean) == 1 else "ies", path, mode))
        info("Undo with:  zot undo %s   (or `zot undo last`)" % op_id)

    if getattr(args, "mark_for_sync", False):
        _mark_for_sync(cfg, attachment.get("attachmentKey"))


def _backup(path, attachment, op_id):
    """Copy the untouched PDF into the state dir, next to the undo snapshots.

    Deliberately *not* alongside the original: `storage/<KEY>/` is Zotero's own
    directory, and leaving a second file in it invites Zotero to treat the stray
    copy as part of the attachment on the next sync or consistency check.
    """
    folder = os.path.join(STATE_DIR, "pdf-backups")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, "%s-%s-%s" % (op_id, attachment.get("attachmentKey"),
                                                os.path.basename(path)))
    shutil.copy2(path, target)
    return target


def _mark_for_sync(cfg, attachment_key):
    """Tell Zotero the file changed so a sync re-uploads it.

    Zotero only notices in-app edits; a file rewritten underneath it is picked up
    on the next hash check, which may be much later. This is opt-in because every
    rewritten PDF is re-uploaded whole, and that adds up fast against a storage
    quota.
    """
    from ..http import run_js
    code = """
var att = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, %r);
if (!att) return { marked: false, reason: 'attachment not found' };
var L = Zotero.Sync && Zotero.Sync.Storage && Zotero.Sync.Storage.Local;
if (!L || typeof L.SYNC_STATE_TO_UPLOAD === 'undefined') {
  return { marked: false, reason: 'this Zotero build exposes no sync-state API' };
}
att.attachmentSyncState = L.SYNC_STATE_TO_UPLOAD;
await att.saveTx();
return { marked: true };
""" % attachment_key
    result = run_js(cfg, code, label="toc-mark-sync") or {}
    if result.get("marked"):
        info("marked %s for re-upload on the next sync." % attachment_key)
    else:
        info("could not mark the attachment for sync: %s"
             % result.get("reason", "unknown"))


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
_ACTIONS = {"show": _show, "scan": _scan, "set": _set, "auto": _auto, "clear": _clear}


def cmd_toc(args):
    from ..pdf import load_pymupdf
    if load_pymupdf() is None:
        from ..pdf import INSTALL_HINT
        die(INSTALL_HINT, code=EXIT_CONFIG)
    _ACTIONS[args.action](args)
