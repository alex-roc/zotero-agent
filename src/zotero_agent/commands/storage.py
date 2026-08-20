"""What the library weighs, and how to make it weigh less.

Three commands over one inventory of the attachment store:

- disk   : where the gigabytes are (big PDFs, page snapshots, orphans, trash)
- shrink : downsample oversized PDFs in place, verifying before replacing
- gc     : trash the attachments nothing points at, and empty the bin

"Reduce my library" is most of what people actually want from a reference
manager they have fed for a decade, and until now answering even "why is this
16 GB?" meant hand-writing JS.
"""

import json
import os
import shutil
import tempfile

from ..http import run_js
from ..output import dump_json
from ..pdf import shrink as shrinklib
from ..resolve import keys_from, resolve_key
from ..term import confirm_write, die, info

MB = 1024 * 1024

# Shrinking is lossy: it downsamples the page images. Doing it twice re-encodes
# what was already re-encoded, so a re-run over the same sweep would quietly
# degrade every file it had already done. pdf-prep solves this with a tag; so
# does this. Marked attachments are skipped unless --force says otherwise.
SHRINK_TAG = "shrunk"

# One pass over every attachment. `getFilePathAsync` is what resolves linked
# files and a configured base directory, so never rebuild storage/<KEY>/ by hand.
_INVENTORY_JS = r"""
var lib = Zotero.Libraries.userLibraryID;
var all = await Zotero.Items.getAll(lib, false, true, false);
// getAnnotations() throws on link attachments (URL-only, no file), which a real
// library has plenty of — so ask, never assume.
function countAnnotations(it) {
  try { return it.getAnnotations ? it.getAnnotations().length : 0; } catch (e) { return 0; }
}
var out = [];
for (var it of all) {
  if (!it.isAttachment()) continue;
  var path = null, size = 0;
  try { path = await it.getFilePathAsync(); } catch (e) {}
  if (path) { try { size = (await IOUtils.stat(path)).size; } catch (e) { size = 0; } }
  var parent = it.parentItem;
  out.push({
    key: it.key,
    parentKey: parent ? parent.key : null,
    title: parent ? String(parent.getField('title') || '').slice(0, 70)
                  : String(it.getField('title') || '').slice(0, 70),
    year: parent ? (String(parent.getField('date') || '').match(/\d{4}/) || [''])[0] : '',
    contentType: it.attachmentContentType || '',
    linkMode: it.attachmentLinkMode,
    linked: it.attachmentLinkMode === Zotero.Attachments.LINK_MODE_LINKED_FILE,
    size: size,
    annotations: countAnnotations(it),
    collections: it.getCollections ? it.getCollections().length : 0,
    tags: it.getTags ? it.getTags().length : 0,
    tagNames: it.getTags ? it.getTags().map(function (t) { return t.tag; }) : [],
    deleted: !!it.deleted,
    hasFile: !!path
  });
}
var trashed = all.filter(function (i) { return i.deleted; }).length;
return { attachments: out, trashedItems: trashed };
"""


def _inventory(cfg):
    res = run_js(cfg, _INVENTORY_JS, label="storage:inventory") or {}
    return res.get("attachments", []), res.get("trashedItems", 0)


# A top-level attachment is NOT junk. Zotero shows it in the items list like any
# other row, and dragging a PDF in without metadata is how a lot of libraries are
# built: on one real library all 268 "orphans" were filed in a collection and
# were books — an encyclopedia, Koyré, municipal development plans. Deleting them
# would have destroyed 1.1 GB of content the user reads.
#
# So being parentless is not enough. Something is disposable only when nothing
# else claims it either: no collection, no tags, no annotations.
def is_disposable_orphan(att):
    return (not att.get("parentKey")
            and not att.get("collections")
            and not att.get("tags")
            and not att.get("annotations")
            and not att.get("deleted"))


def _human(nbytes):
    if nbytes >= 1024 * MB:
        return "%.1f GB" % (nbytes / float(1024 * MB))
    if nbytes >= MB:
        return "%.0f MB" % (nbytes / float(MB))
    return "%.0f KB" % (nbytes / 1024.0)


# --------------------------------------------------------------------------- #
# disk
# --------------------------------------------------------------------------- #
def cmd_disk(args):
    from ..config import require_config
    cfg = require_config(args)
    atts, trashed_items = _inventory(cfg)

    pdfs = [a for a in atts if a["contentType"] == "application/pdf"]
    snapshots = [a for a in atts if a["contentType"] == "text/html"]
    orphans = [a for a in atts if not a["parentKey"]]
    trashed = [a for a in atts if a["deleted"]]
    # Trashed files are already counted (and reported) under "in trash";
    # listing them again as candidates to shrink is just double vision.
    heavy = sorted([a for a in pdfs if a["size"] >= args.min_mb * MB and not a["deleted"]],
                   key=lambda a: -a["size"])
    total = sum(a["size"] for a in atts)

    summary = {
        "attachments": len(atts), "totalBytes": total,
        "pdfs": {"count": len(pdfs), "bytes": sum(a["size"] for a in pdfs)},
        "snapshots": {"count": len(snapshots), "bytes": sum(a["size"] for a in snapshots)},
        "orphans": {"count": len(orphans), "bytes": sum(a["size"] for a in orphans)},
        "trashed": {"count": len(trashed), "bytes": sum(a["size"] for a in trashed)},
        "trashedItems": trashed_items,
        "heavyPdfs": heavy[: args.samples],
    }
    if args.json:
        dump_json(summary)
        return

    print("My Library attachments: %s across %d file(s)" % (_human(total), len(atts)))
    print("  %-12s %5d  %10s" % ("PDFs", len(pdfs), _human(summary["pdfs"]["bytes"])))
    print("  %-12s %5d  %10s   (page snapshots — the item keeps its URL without them)"
          % ("snapshots", len(snapshots), _human(summary["snapshots"]["bytes"])))
    print("  %-12s %5d  %10s   (no parent item — Zotero still lists them as items)"
          % ("parentless", len(orphans), _human(summary["orphans"]["bytes"])))
    print("  %-12s %5d  %10s   (%d item(s) in the trash)"
          % ("in trash", len(trashed), _human(summary["trashed"]["bytes"]), trashed_items))
    if heavy:
        print("\nPDFs over %d MB (%d, %s):"
              % (args.min_mb, len(heavy), _human(sum(a["size"] for a in heavy))))
        for a in heavy[: args.samples]:
            print("  %6s  %-9s %-5s %s" % (_human(a["size"]), a["parentKey"] or "(orphan)",
                                           a["year"] or "", (a["title"] or "")[:52]))
        if len(heavy) > args.samples:
            info("  ... (%d more)" % (len(heavy) - args.samples))
        info("Reclaim with:  zot shrink --min-mb %d --dry-run" % args.min_mb)
    if snapshots or orphans or trashed:
        info("Clean up with: zot gc --dry-run")
    # Group libraries keep their files in the same storage/ directory but sync
    # through Zotero's servers, not WebDAV — so `du` on the data directory can be
    # far larger than this, and those files are NOT strays to be swept up.
    info("Counts My Library only; group-library files share storage/ and are not included.")


# --------------------------------------------------------------------------- #
# shrink
# --------------------------------------------------------------------------- #
def _shrink_targets(cfg, args):
    """The PDFs to consider, from explicit keys or from a size sweep."""
    atts, _ = _inventory(cfg)
    pdfs = [a for a in atts if a["contentType"] == "application/pdf"
            and a["hasFile"] and not a["deleted"] and not a["linked"]]
    if args.keys:
        # keys_from() only reads the CLI/stdin list; resolving citekeys is a
        # separate step, exactly as prep and write do it.
        wanted = {resolve_key(cfg, k) for k in keys_from(args.keys)}
        chosen = [a for a in pdfs if a["key"] in wanted or a["parentKey"] in wanted]
        missing = wanted - {a["key"] for a in chosen} - {a["parentKey"] for a in chosen}
        for key in sorted(missing):
            info("no local PDF for %s — skipped" % key)
        return sorted(chosen, key=lambda a: -a["size"])
    upper = args.max_mb * MB if getattr(args, "max_mb", None) else None
    swept = [a for a in pdfs if a["size"] >= args.min_mb * MB
             and (upper is None or a["size"] < upper)]
    if not getattr(args, "force", False):
        done = [a for a in swept if SHRINK_TAG in (a.get("tagNames") or [])]
        if done:
            info("Skipping %d file(s) already shrunk (--force to redo)." % len(done))
        swept = [a for a in swept if SHRINK_TAG not in (a.get("tagNames") or [])]
    return sorted(swept, key=lambda a: -a["size"])


def _attachment_path(cfg, key):
    res = run_js(cfg, (
        "var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, %r);\n"
        "if (!it) return { error: 'not found' };\n"
        "return { path: await it.getFilePathAsync() };" % key), label="shrink:path") or {}
    return res.get("path")


def _mark_shrunk(cfg, key):
    """Tag the attachment so a later sweep does not re-encode it."""
    run_js(cfg, (
        "var it = await Zotero.Items.getByLibraryAndKeyAsync("
        "Zotero.Libraries.userLibraryID, %r);\n"
        "if (!it) return { ok: false };\n"
        "it.addTag(%s); await it.saveTx();\n"
        "return { ok: true };" % (key, json.dumps(SHRINK_TAG))), label="shrink:tag")


def cmd_shrink(args):
    from ..config import require_config
    cfg = require_config(args)
    if not shrinklib.have_ghostscript():
        die(shrinklib.MISSING_GHOSTSCRIPT)
    if not shrinklib.have_qpdf():
        die(shrinklib.MISSING_QPDF)

    targets = _shrink_targets(cfg, args)
    if not targets:
        print("Nothing to shrink.")
        return
    total_before = sum(a["size"] for a in targets)
    info("Considering %d PDF(s), %s." % (len(targets), _human(total_before)))
    if not args.dry_run:
        confirm_write(args, "This rewrites %d PDF file(s) in place. The originals are "
                            "replaced only when the page count is unchanged and the file "
                            "actually got smaller." % len(targets))

    workdir = tempfile.mkdtemp(prefix="zot-shrink-")
    results, saved = [], 0
    try:
        for a in targets:
            path = _attachment_path(cfg, a["key"])
            if not path or not os.path.exists(path):
                results.append({"key": a["key"], "status": "missing-file"})
                continue
            before = os.path.getsize(path)
            pages_before = shrinklib.page_count(path)
            out = os.path.join(workdir, "%s.pdf" % a["key"])
            ok, err = shrinklib.shrink_file(path, out, dpi=args.dpi,
                                            mono_dpi=args.mono_dpi, timeout=args.timeout)
            if not ok:
                results.append({"key": a["key"], "status": "failed", "error": err})
                info("  %s: %s" % (a["key"], err))
                continue
            after = os.path.getsize(out)
            accept, ratio, reason = shrinklib.verdict(before, after, pages_before,
                                                      shrinklib.page_count(out),
                                                      max_ratio=args.max_ratio)
            row = {"key": a["key"], "parentKey": a["parentKey"], "title": a["title"],
                   "before": before, "after": after,
                   "ratio": round(ratio, 3) if ratio else None,
                   "pages": pages_before,
                   "status": "would-shrink" if accept else "kept",
                   "reason": reason}
            if accept and not args.dry_run:
                if args.out:
                    os.makedirs(args.out, exist_ok=True)
                    shutil.copy2(out, os.path.join(args.out, os.path.basename(path)))
                    row["status"] = "written"
                else:
                    # Same path, same page count: Zotero's annotations still anchor.
                    shutil.move(out, path)
                    row["status"] = "shrunk"
                    _mark_shrunk(cfg, a["key"])
                saved += before - after
            elif accept:
                saved += before - after
            results.append(row)
            if os.path.exists(out):
                os.remove(out)
            if not args.json:
                mark = "→" if accept else "·"
                print("  %s %-9s %7s %s %-7s %s" % (
                    mark, a["parentKey"] or a["key"], _human(before),
                    "→" if accept else " ", _human(after) if accept else "(kept)",
                    (a["title"] or "")[:44]))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    shrunk = [r for r in results if r["status"] in ("would-shrink", "shrunk", "written")]
    if args.json:
        dump_json({"considered": len(targets), "shrunk": len(shrunk),
                   "bytesSaved": saved, "results": results})
        return
    verb = "would reclaim" if args.dry_run else "reclaimed"
    print("%d of %d file(s) shrank — %s %s."
          % (len(shrunk), len(targets), verb, _human(saved)))
    kept = len(targets) - len(shrunk)
    if kept:
        info("%d file(s) left untouched (already compact, or no meaningful gain)." % kept)


# --------------------------------------------------------------------------- #
# gc
# --------------------------------------------------------------------------- #
_GC_JS = r"""
var KEYS = %s, emptyTrash = %s;
var lib = Zotero.Libraries.userLibraryID;
var trashed = 0;
// One saveTx() per item opens one transaction per item, and a thousand of them
// overruns the bridge timeout (measured: 983 snapshots died at ~924). Batch them.
await Zotero.DB.executeTransaction(async function () {
  for (var k of KEYS) {
    var it = await Zotero.Items.getByLibraryAndKeyAsync(lib, k);
    if (it && !it.deleted) { it.deleted = true; await it.save(); trashed++; }
  }
});
var erased = 0;
if (emptyTrash) {
  var all = await Zotero.Items.getAll(lib, false, true, false);
  var doomed = all.filter(function (i) { return i.deleted; });
  for (var d of doomed) { try { await d.eraseTx(); erased++; } catch (e) {} }
}
return { trashed: trashed, erased: erased };
"""


def cmd_gc(args):
    from ..config import require_config
    cfg = require_config(args)
    atts, trashed_items = _inventory(cfg)

    doomed, why = [], {}
    if args.orphans:
        for a in atts:
            if is_disposable_orphan(a):
                doomed.append(a)
                why[a["key"]] = "orphan"
        filed = [a for a in atts
                 if not a["parentKey"] and not a["deleted"] and not is_disposable_orphan(a)]
        if filed and not args.json:
            info("Keeping %d parentless attachment(s) that are filed, tagged or annotated "
                 "— Zotero lists those as items." % len(filed))
    if args.snapshots:
        for a in atts:
            if a["contentType"] == "text/html" and not a["deleted"] and a["parentKey"]:
                doomed.append(a)
                why[a["key"]] = "snapshot"
    # Never bin a file somebody has highlighted: the annotations live on the
    # attachment and do not survive it.
    kept_annotated = [a for a in doomed if a["annotations"]]
    doomed = [a for a in doomed if not a["annotations"]]

    reclaim = sum(a["size"] for a in doomed)
    trash_bytes = sum(a["size"] for a in atts if a["deleted"])
    if args.json:
        dump_json({"toTrash": [{"key": a["key"], "why": why[a["key"]], "size": a["size"],
                                "title": a["title"]} for a in doomed],
                   "bytes": reclaim, "keptAnnotated": len(kept_annotated),
                   "trashBytes": trash_bytes, "trashedItems": trashed_items})
        return

    if doomed:
        print("Would trash %d attachment(s), %s:" % (len(doomed), _human(reclaim)))
        counts = {}
        for a in doomed:
            counts[why[a["key"]]] = counts.get(why[a["key"]], 0) + 1
        for kind, n in sorted(counts.items()):
            print("  %-10s %5d" % (kind, n))
    else:
        print("Nothing to collect.")
    if kept_annotated:
        info("Keeping %d annotated attachment(s) — highlights do not survive them."
             % len(kept_annotated))
    if args.empty_trash and trashed_items:
        print("Would permanently erase %d item(s) already in the trash (%s)."
              % (trashed_items, _human(trash_bytes)))
    if args.dry_run:
        info("Re-run without --dry-run to apply.")
        return
    if not doomed and not (args.empty_trash and trashed_items):
        return

    warning = "This trashes %d attachment(s)." % len(doomed)
    if args.empty_trash:
        warning += " Emptying the trash is PERMANENT — take a `zot backup` first."
    confirm_write(args, warning)
    res = run_js(cfg, _GC_JS % (json.dumps([a["key"] for a in doomed]),
                                "true" if args.empty_trash else "false"), label="gc")
    print("Trashed %d attachment(s)." % res.get("trashed", 0))
    if res.get("erased"):
        print("Permanently erased %d item(s) from the trash." % res["erased"])
    if doomed and not args.empty_trash:
        info("Space is reclaimed once the trash is emptied: zot gc --empty-trash")
