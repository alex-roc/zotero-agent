"""`zot pdf-prep` — turn a scanned PDF into a searchable, single-page, smaller one.

The work itself lives in `pdf/prep.py`; this module is the part that talks to
Zotero and to the user: which item, which file, what to do with the result.

The default is deliberately additive — the processed PDF is attached *beside*
the original, tagged so it can be recognised later. OCR is a lossy judgement
call made by a machine, and the scan is often the only copy the user has. When
a batch has been reviewed, `--replace` (during the run) or `--prune` (after it)
moves the superseded originals to the trash, so the library does not silently
grow a second copy of every book.
"""

import json
import os
import shutil
import tempfile
import time

from ..constants import EXIT_CONFIG, EXIT_NOTFOUND
from ..http import run_js
from ..jslib import collection_items_scope
from ..output import dump_json
from ..resolve import keys_from, resolve_key
from ..term import confirm_write, die, info
from .read import pdf_paths, resolve_pdf_attachment

# Marks the attachments this command creates. Both are load-bearing: the tag is
# what `--prune` searches for, and the note records *which* attachment the new
# file supersedes — without it, pruning would have to guess which of an item's
# PDFs was the original.
PREP_TAG = "pdf-prep"
NOTE_MARKER = "zotero-agent:pdf-prep"


# --------------------------------------------------------------------------- #
# bridge JS
# --------------------------------------------------------------------------- #
_ATTACH_JS = r"""
var parentKey = %(parent)s, path = %(path)s, title = %(title)s;
var replaces = %(replaces)s, marker = %(marker)s, tag = %(tag)s, trashOriginal = %(trash)s;
var trashAnnotated = %(trash_annotated)s;

var parent = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, parentKey);
if (!parent) return { error: 'item not found: ' + parentKey };

var att = await Zotero.Attachments.importFromFile({ file: path, parentItemID: parent.id });
att.setField('title', title);
att.addTag(tag);
// The provenance note is plain JSON in an HTML note: readable by a human in
// Zotero's pane, parseable by --prune without a second source of truth.
att.setNote('<p>' + marker + ' ' + JSON.stringify({ replaces: replaces }) + '</p>');
await att.saveTx();

var trashed = null, keptAnnotations = 0;
if (trashOriginal && replaces) {
  var old = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, replaces);
  if (old) {
    // Highlights belong to the *attachment*, not to the file, so they do not
    // follow the new PDF. Trashing an annotated original therefore throws away
    // the user's reading, which no amount of OCR is worth.
    var count = 0;
    try { count = old.getAnnotations().length; } catch (e) { count = 0; }
    if (count && !trashAnnotated) { keptAnnotations = count; }
    else { old.deleted = true; await old.saveTx(); trashed = old.key; }
  }
}
return { attachmentKey: att.key, parent: parent.key, trashed: trashed,
         keptAnnotations: keptAnnotations };
"""

_PRUNE_JS = r"""
var keys = %(keys)s, marker = %(marker)s, tag = %(tag)s, apply = %(apply)s;
var trashAnnotated = %(trash_annotated)s;
var out = [];
for (var key of keys) {
  var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, key);
  if (!it) { out.push({ key: key, status: 'not-found' }); continue; }
  var atts = it.getAttachments().map(function (id) { return Zotero.Items.get(id); });
  var superseded = [];
  for (var att of atts) {
    if (!att.getTags().some(function (t) { return t.tag === tag; })) continue;
    var note = att.getNote() || '';
    var at = note.indexOf(marker);
    if (at < 0) continue;
    var json = note.slice(at + marker.length).replace(/<[^>]*>/g, '').trim();
    try { var meta = JSON.parse(json); } catch (e) { continue; }
    if (meta && meta.replaces) superseded.push(meta.replaces);
  }
  var done = [], kept = [];
  for (var origKey of superseded) {
    var orig = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, origKey);
    if (!orig || orig.deleted) continue;
    var count = 0;
    try { count = orig.getAnnotations().length; } catch (e) { count = 0; }
    if (count && !trashAnnotated) {
      kept.push({ attachmentKey: orig.key, annotations: count });
      continue;
    }
    if (apply) { orig.deleted = true; await orig.saveTx(); }
    done.push({ attachmentKey: orig.key, title: orig.getField('title') });
  }
  var status = done.length ? (apply ? 'trashed' : 'would-trash')
             : (kept.length ? 'kept-annotated' : 'nothing-to-prune');
  out.push({ key: key, title: it.getField('title'), status: status,
             originals: done, kept: kept });
}
return { results: out };
"""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _target_keys(cfg, args, label):
    if getattr(args, "collection", None):
        keys = run_js(cfg, collection_items_scope(args.collection) +
                      "return items.map(function (i) { return i.key; });", label=label)
    else:
        keys = [resolve_key(cfg, k) for k in keys_from(args.keys)]
    if not keys:
        die("no items to process", code=EXIT_NOTFOUND)
    return keys


def _human_size(n):
    return "%.1f MB" % (n / 1e6) if n >= 1e6 else "%.0f kB" % (n / 1e3)


def _report_line(report):
    size = report.get("pageSize") or {}
    bits = ["%d pages" % report.get("pages", 0),
            "%sx%s pt" % (size.get("width"), size.get("height"))]
    if report.get("imageDpi"):
        bits.append("%d dpi images" % report["imageDpi"])
    bits.append("text layer" if report.get("hasText") else "no text layer")
    if report.get("doublePage"):
        bits.append("double-page (gutter %.3f, confidence %.0f%%)"
                    % (report["gutter"], report["gutterConfidence"] * 100))
    elif report.get("landscape"):
        bits.append("landscape but no clear gutter")
    return ", ".join(str(b) for b in bits)


def _already_processed(item):
    for pdf in item.get("pdfs") or []:
        if PREP_TAG in (pdf.get("tags") or []):
            return pdf
    return None


# --------------------------------------------------------------------------- #
# one item
# --------------------------------------------------------------------------- #
def _process_one(cfg, args, key, workdir):
    """Analyse, split, OCR and (unless --out/--dry-run) attach. Returns a result dict."""
    from ..pdf import prep, scan

    item = pdf_paths(cfg, key)
    existing = _already_processed(item)
    # --dry-run is a diagnosis, so it reports on an already-processed item
    # instead of refusing to look: "what is this file, and what would you do to
    # it" is a fair question to ask twice.
    if existing and not args.force and not args.dry_run:
        return {"key": item.get("itemKey"), "title": item.get("title"),
                "status": "already-processed", "existing": existing.get("attachmentKey")}

    # A processed item now holds two PDFs, and the second one is ours. Without
    # this the plain resolver would refuse the whole item ("choose one with
    # --attachment"), which would make re-running a collection abort on every
    # item it had already done.
    wanted = getattr(args, "attachment", None)
    if not wanted:
        originals = [p for p in item.get("pdfs") or []
                     if PREP_TAG not in (p.get("tags") or [])]
        if len(originals) == 1:
            wanted = originals[0].get("attachmentKey")

    item, attachment = resolve_pdf_attachment(cfg, key, wanted, item=item)
    source = attachment["path"]
    result = {"key": item.get("itemKey"), "title": item.get("title"),
              "attachmentKey": attachment.get("attachmentKey"), "source": source}

    doc = scan.open_pdf(source)
    try:
        report = prep.analyse(doc)
        result["analysis"] = report

        if args.split == "never":
            do_split = False
        elif args.split == "always":
            do_split = True
        else:
            do_split = report.get("doublePage", False)

        cut = args.gutter if args.gutter is not None else report.get("gutter")
        if do_split and cut is None:
            if args.split != "always":
                result["status"] = "no-gutter"
                return result
            # `--split always` is the user overruling the detector, so honour it
            # with the obvious cut rather than refusing: a scan too faint to
            # measure is usually still bound down the middle.
            cut = 0.5
            result["gutterFallback"] = True

        if args.no_ocr and not do_split:
            # Without a split and without OCR there is no work left to do: the
            # old code copied the file byte for byte and attached it as if
            # something had happened. Shrinking lives in `zot shrink` now.
            result["status"] = "nothing-to-do"
            result["hint"] = "already single-page; to reclaim disk use: zot shrink %s" % item["key"]
            return result

        if args.dry_run:
            result["status"] = "would-process"
            if existing:
                result["existing"] = existing.get("attachmentKey")
            result["plan"] = {"split": do_split, "gutter": cut,
                              "ocr": None if args.no_ocr else _language(args, item),
                              "profile": args.profile}
            return result

        stem = os.path.splitext(os.path.basename(source))[0]
        stage = os.path.join(workdir, "split.pdf")
        if do_split:
            try:
                singles = prep.parse_pages(args.single, report.get("pages", 0))
            except ValueError as exc:
                die(str(exc))
            pages = prep.split_document(doc, stage, cut, overlap=args.overlap,
                                        single=singles, rtl=args.rtl)
            result["pagesAfterSplit"] = pages
        else:
            shutil.copy2(source, stage)
    finally:
        doc.close()

    final = stage
    if not args.no_ocr:
        language = _language(args, item)
        result["language"] = language
        ocr_out = os.path.join(workdir, "ocr.pdf")
        started = time.time()
        ok, tail = prep.run_ocr(stage, ocr_out, language, profile=args.profile,
                                rotate=args.rotate, timeout=args.timeout)
        result["ocrSeconds"] = round(time.time() - started, 1)
        if not ok:
            result["status"] = "ocr-failed"
            result["error"] = tail
            return result
        final = ocr_out

    result["sizeBefore"] = os.path.getsize(source)
    result["sizeAfter"] = os.path.getsize(final)

    name = "%s (OCR).pdf" % stem if not args.no_ocr else "%s (split).pdf" % stem
    if args.out:
        destination = os.path.join(os.path.expanduser(args.out), name)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(final, destination)
        result["status"] = "written"
        result["output"] = destination
        return result

    # Zotero copies the file into storage, so a temp path is fine to hand over —
    # but the name it keeps is this one, hence the rename before importing.
    named = os.path.join(workdir, name)
    shutil.move(final, named)
    res = run_js(cfg, _ATTACH_JS % {
        "parent": json.dumps(item.get("itemKey")),
        "path": json.dumps(named),
        "title": json.dumps(args.title or ("PDF (OCR)" if not args.no_ocr else "PDF (split)")),
        "replaces": json.dumps(attachment.get("attachmentKey")),
        "marker": json.dumps(NOTE_MARKER),
        "tag": json.dumps(PREP_TAG),
        "trash": "true" if args.replace else "false",
        "trash_annotated": "true" if args.trash_annotated else "false",
    }, label="pdf-prep", timeout=180)
    if res.get("error"):
        result["status"] = "attach-failed"
        result["error"] = res["error"]
        return result
    result["status"] = "attached"
    result["newAttachment"] = res.get("attachmentKey")
    result["trashed"] = res.get("trashed")
    result["keptAnnotations"] = res.get("keptAnnotations") or 0
    return result


def _language(args, item):
    from ..pdf import prep
    return prep.pick_language(args.ocr, item.get("language"))


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def cmd_pdf_prep(args):
    """Prepare scanned PDFs: split double pages, OCR them, shrink them."""
    from ..config import require_config
    from ..pdf import prep

    cfg = require_config(args)

    if args.prune:
        return _prune(cfg, args)

    if not args.no_ocr and not prep.have_ocr():
        die(prep.OCR_INSTALL_HINT, code=EXIT_CONFIG)

    keys = _target_keys(cfg, args, "pdf-prep")
    if not args.dry_run and not args.out:
        what = "This attaches a processed PDF to %d item(s)" % len(keys)
        confirm_write(args, what + (" and trashes the originals." if args.replace else "."))

    results = []
    for key in keys:
        with tempfile.TemporaryDirectory(prefix="zot-pdf-prep-") as workdir:
            if not args.json and not args.quiet:
                info("processing %s ..." % key)
            results.append(_process_one(cfg, args, key, workdir))
            if not args.json and not args.quiet:
                _print_one(results[-1])

    if args.json:
        dump_json({"results": results})
        return
    _print_summary(results)


def _print_one(result):
    status = result.get("status")
    title = (result.get("title") or "")[:52]
    analysis = result.get("analysis") or {}
    if analysis:
        print("  %s" % _report_line(analysis))
    if status == "already-processed":
        print("  skipped: already has a %s attachment (%s); --force to redo"
              % (PREP_TAG, result.get("existing")))
    elif status == "no-gutter":
        print("  skipped: no confident gutter; pass --gutter FRAC or --no-split")
    elif status == "nothing-to-do":
        print("  nothing to do: --no-ocr on a single-page PDF only ever copied the file")
        if result.get("hint"):
            print("  %s" % result["hint"])
    elif status == "would-process":
        plan = result.get("plan") or {}
        if result.get("existing"):
            print("  note: already has a %s attachment (%s); a run would skip it"
                  % (PREP_TAG, result["existing"]))
        print("  plan: split=%s gutter=%s ocr=%s profile=%s"
              % (plan.get("split"), plan.get("gutter"), plan.get("ocr"), plan.get("profile")))
    elif status == "ocr-failed":
        print("  OCR failed: %s" % (result.get("error") or "").splitlines()[-1:])
    elif status in ("attached", "written"):
        before, after = result.get("sizeBefore", 0), result.get("sizeAfter", 0)
        delta = (after - before) / before * 100 if before else 0
        line = "  %s -> %s (%+.0f%%)" % (_human_size(before), _human_size(after), delta)
        if result.get("pagesAfterSplit"):
            line += ", %d pages" % result["pagesAfterSplit"]
        if result.get("ocrSeconds"):
            line += ", OCR %ss" % result["ocrSeconds"]
        print(line)
        if status == "written":
            print("  wrote %s" % result["output"])
        else:
            print("  attached %s to %s %s" % (result.get("newAttachment"),
                                              result.get("key"), title))
            if result.get("trashed"):
                print("  trashed original %s" % result["trashed"])
            elif result.get("keptAnnotations"):
                print("  kept original %s: it carries %d annotation(s), which do not "
                      "follow the new file (--trash-annotated overrides)"
                      % (result.get("attachmentKey"), result["keptAnnotations"]))


def _print_summary(results):
    counts = {}
    for r in results:
        counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
    saved = sum(r.get("sizeBefore", 0) - r.get("sizeAfter", 0)
                for r in results if r.get("status") in ("attached", "written"))
    line = ", ".join("%d %s" % (n, s) for s, n in sorted(counts.items()))
    if saved > 0:
        line += " — %s saved" % _human_size(saved)
    print("\n%s" % line)


def _prune(cfg, args):
    """Trash the originals that a previous run superseded."""
    keys = _target_keys(cfg, args, "pdf-prep")
    apply = not args.dry_run
    if apply:
        confirm_write(args, "This moves superseded original PDFs of %d item(s) to the "
                            "trash." % len(keys))
    res = run_js(cfg, _PRUNE_JS % {
        "keys": json.dumps(keys), "marker": json.dumps(NOTE_MARKER),
        "tag": json.dumps(PREP_TAG), "apply": "true" if apply else "false",
        "trash_annotated": "true" if args.trash_annotated else "false",
    }, label="pdf-prep", timeout=max(60, 5 * len(keys)))
    results = res.get("results", [])
    if args.json:
        dump_json(res)
        return
    for r in results:
        if r.get("originals") or r.get("kept"):
            print("%-10s %-14s %s" % (r["key"], r["status"], (r.get("title") or "")[:48]))
        for k in r.get("kept") or []:
            print("           kept %s — %d annotation(s); --trash-annotated overrides"
                  % (k["attachmentKey"], k["annotations"]))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n%s" % ", ".join("%d %s" % (n, s) for s, n in sorted(counts.items())))
