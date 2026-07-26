"""Higher-level product commands built on a declarative batch primitive.

- apply : run a JSONL edit script (set fields / tags / collection / trash) with
          a pre-image snapshot so it can be undone.
- undo  : restore the items touched by the most recent apply (or a given op id).
- enrich: fill missing DOI / date / abstract from Crossref / OpenAlex.
- tag normalize : fold case-variant / whitespace-variant tags together.

The CLI never calls an LLM: it exposes these primitives, and the agent (skill /
MCP) supplies the intelligence (which items, which values, which tag mapping).
"""

import csv
import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from ..constants import EXIT_NOTFOUND, STATE_DIR, VERSION
from ..http import run_js
from ..jslib import ITEM_MAP, field_name, scope_js
from ..output import dump_json
from ..resolve import resolve_key
from ..term import confirm_write, die, info

UNDO_DIR = os.path.join(STATE_DIR, "undo")
USER_AGENT = "zotero-agent/%s (https://github.com/alex-roc/zotero-agent)" % VERSION


# --------------------------------------------------------------------------- #
# snapshots (for undo)
# --------------------------------------------------------------------------- #
def _op_id():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _snapshot(cfg, keys, label):
    """Capture item.toJSON() for each key and persist it under UNDO_DIR.
    Returns the op id (or None if nothing to snapshot)."""
    keys = list(dict.fromkeys(keys))
    if not keys:
        return None
    code = (
        "var keys=%s; var lib=Zotero.Libraries.userLibraryID; var snap={};\n"
        "for (var k of keys){ var it=await Zotero.Items.getByLibraryAndKeyAsync(lib,k); if(it) snap[k]=it.toJSON(); }\n"
        "return snap;"
    ) % json.dumps(keys)
    snap = run_js(cfg, code, label="snapshot")
    return _persist_snapshot(label, {"items": snap})


def _persist_snapshot(label, payload):
    os.makedirs(UNDO_DIR, exist_ok=True)
    op_id = _op_id()
    path = os.path.join(UNDO_DIR, op_id + ".json")
    body = {"opId": op_id, "label": label}
    body.update(payload)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, ensure_ascii=False)
    return op_id


def snapshot_outline(label, target):
    """Snapshot a PDF's outline before `zot toc` overwrites it.

    Deliberately *not* a copy of the file: a scanned book is hundreds of
    megabytes, and the operation only replaces the outline tree, so storing the
    previous tree restores exactly what was lost for a few kilobytes. The file's
    bytes do change (an incremental save appends), which is why `zot toc set`
    also offers --backup for people who want the original bytes back.
    """
    return _persist_snapshot(label, {"outline": target})


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #
_APPLY_BODY = (
    "var edits=%s; var lib=Zotero.Libraries.userLibraryID; var applied=0, errors=[];\n"
    "await Zotero.DB.executeTransaction(async function(){\n"
    "  for (var e of edits){\n"
    "    var it=await Zotero.Items.getByLibraryAndKeyAsync(lib, e.key);\n"
    "    if(!it){ errors.push(e.key+': not found'); continue; }\n"
    "    try {\n"
    "      if(e.set){ for(var f in e.set){ it.setField(f, e.set[f]); } }\n"
    "      if(e.addTags){ e.addTags.forEach(function(t){ it.addTag(t); }); }\n"
    "      if(e.removeTags){ e.removeTags.forEach(function(t){ it.removeTag(t); }); }\n"
    "      if(e.addToCollection){ var col=await Zotero.Collections.getByLibraryAndKey(lib, e.addToCollection)"
    " || Zotero.Collections.getByLibrary(lib,true).find(function(c){return c.name===e.addToCollection;});"
    " if(col) it.addToCollection(col.id); }\n"
    "      if(e.trash){ it.deleted=true; }\n"
    "      await it.save(); applied++;\n"
    "    } catch(err){ errors.push(e.key+': '+err); }\n"
    "  }\n"
    "});\n"
    "return { applied: applied, errors: errors };"
)


def _load_edits(source):
    """Parse a JSONL edit script (one JSON object per line). '-' reads stdin."""
    import sys
    if source == "-":
        raw = sys.stdin.read()
    else:
        with open(source, "r", encoding="utf-8") as fh:
            raw = fh.read()
    edits = []
    for n, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            die("line %d is not valid JSON: %s" % (n, e))
        if "key" not in obj:
            die("line %d has no 'key' field" % n)
        edits.append(obj)
    return edits


def _prepare_edits(cfg, edits):
    """Resolve citekeys → item keys and normalise field aliases (in place)."""
    for e in edits:
        e["key"] = resolve_key(cfg, e["key"])
        if e.get("set"):
            e["set"] = {field_name(f): v for f, v in e["set"].items()}
    return edits


def apply_edits_data(edits, dry_run=False, yes=True):
    """Programmatic entry point (used by the MCP server). Returns a result dict."""
    from ..config import require_config
    if not edits:
        return {"error": "no edits to apply"}
    try:
        cfg = require_config(None)
        clean = _prepare_edits(cfg, [dict(e) for e in edits])
        body = _APPLY_BODY % json.dumps(clean)
        if dry_run:
            # No JS is executed: we already know the edits, so report them from
            # Python. (Never rely on monkey-patching save() to "preview" — it can
            # leak writes on Zotero 7.)
            return {"dryRun": True, "edits": len(clean),
                    "keys": [e["key"] for e in clean]}
        op_id = _snapshot(cfg, [e["key"] for e in clean], "apply")
        res = run_js(cfg, body, label="apply")
        res["opId"] = op_id
        return res
    except Exception as e:  # noqa: BLE001 — surface as tool error, never crash the server
        return {"error": str(e)}


def cmd_apply(args):
    from ..config import require_config
    cfg = require_config(args)
    edits = _load_edits(args.file)
    if not edits:
        die("no edits to apply", code=EXIT_NOTFOUND)
    _prepare_edits(cfg, edits)
    body = _APPLY_BODY % json.dumps(edits)

    if args.dry_run:
        # Report straight from the parsed edits — no JS runs, so nothing can leak.
        print("DRY-RUN — no changes will be persisted.")
        print("Would apply %d edit(s):" % len(edits))
        for e in edits[: args.samples]:
            ops = []
            if e.get("set"):
                ops.append("set " + ",".join(e["set"]))
            if e.get("addTags"):
                ops.append("+tags %s" % e["addTags"])
            if e.get("removeTags"):
                ops.append("-tags %s" % e["removeTags"])
            if e.get("addToCollection"):
                ops.append("→ %s" % e["addToCollection"])
            if e.get("trash"):
                ops.append("TRASH")
            print("  %-10s %s" % (e["key"], "; ".join(ops)))
        return

    confirm_write(args, "This applies %d edit(s) to the library." % len(edits))
    op_id = _snapshot(cfg, [e["key"] for e in edits], "apply")
    res = run_js(cfg, body, label="apply")
    if args.json:
        res["opId"] = op_id
        dump_json(res)
        return
    print("Applied %d edit(s)." % res["applied"])
    if op_id:
        info("Undo with:  zot undo %s   (or `zot undo last`)" % op_id)
    if res.get("errors"):
        info("errors: " + "; ".join(map(str, res["errors"])))


# --------------------------------------------------------------------------- #
# undo
# --------------------------------------------------------------------------- #
def _list_ops():
    if not os.path.isdir(UNDO_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(UNDO_DIR) if f.endswith(".json"))


def _describe_op(meta):
    if "outline" in meta:
        entries = meta["outline"].get("entries") or []
        return "PDF outline, %d entr%s" % (len(entries), "y" if len(entries) == 1 else "ies")
    return "%d item(s)" % len(meta.get("items", {}))


def _undo_outline(args, meta, snapshot_path):
    """Restore a PDF's previous outline. Rewrites the file, not the library, so
    it never touches Zotero — the snapshot holds everything needed."""
    from ..pdf import outline as pdf_outline
    from ..pdf import scan as pdf_scan
    target = meta["outline"]
    pdf_path = target.get("path")
    if not pdf_path or not os.path.exists(pdf_path):
        die("the PDF this snapshot belongs to is gone: %s" % pdf_path, code=EXIT_NOTFOUND)
    entries = target.get("entries") or []
    confirm_write(args, "This restores the previous outline (%d entries) of %s."
                  % (len(entries), pdf_path))
    doc = pdf_scan.open_pdf(pdf_path)
    try:
        if entries:
            pdf_outline.write_outline(doc, entries, pdf_path)
        else:
            pdf_outline.clear_outline(doc, pdf_path)
    finally:
        if not doc.is_closed:
            doc.close()
    print("Restored the outline of %s (%d entries)." % (pdf_path, len(entries)))
    if not args.keep:
        os.remove(snapshot_path)


def cmd_undo(args):
    from ..config import require_config
    ops = _list_ops()
    if args.op == "list":
        if not ops:
            print("No undo snapshots.")
        for op in ops:
            with open(os.path.join(UNDO_DIR, op + ".json"), encoding="utf-8") as fh:
                meta = json.load(fh)
            print("%-18s %-8s %s" % (op, meta.get("label", ""), _describe_op(meta)))
        return
    if not ops:
        die("no undo snapshots available", code=EXIT_NOTFOUND)
    op_id = ops[-1] if args.op == "last" else args.op
    path = os.path.join(UNDO_DIR, op_id + ".json")
    if not os.path.exists(path):
        die("no such undo snapshot: %s" % op_id, code=EXIT_NOTFOUND)
    with open(path, encoding="utf-8") as fh:
        meta = json.load(fh)
    if "outline" in meta:
        return _undo_outline(args, meta, path)
    cfg = require_config(args)
    snap = meta.get("items", {})
    confirm_write(args, "This restores %d item(s) to their state before '%s'." % (len(snap), op_id))
    code = (
        "var snap=%s; var lib=Zotero.Libraries.userLibraryID; var restored=0, errors=[];\n"
        "await Zotero.DB.executeTransaction(async function(){\n"
        "  for (var k in snap){ var it=await Zotero.Items.getByLibraryAndKeyAsync(lib,k);\n"
        "    if(!it){ errors.push(k+': item is gone (merge/erase is not reversible)'); continue; }\n"
        "    try { it.fromJSON(snap[k]); it.deleted = !!snap[k].deleted; await it.save(); restored++; }\n"
        "    catch(e){ errors.push(k+': '+e); } }\n"
        "});\n"
        "return { restored: restored, errors: errors };"
    ) % json.dumps(snap)
    res = run_js(cfg, code, label="undo")
    print("Restored %d item(s) from snapshot %s." % (res["restored"], op_id))
    if res.get("errors"):
        info("errors: " + "; ".join(map(str, res["errors"])))
    if not args.keep:
        os.remove(path)


# --------------------------------------------------------------------------- #
# enrich (external metadata)
# --------------------------------------------------------------------------- #
def _http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _crossref_lookup(title):
    q = urllib.parse.urlencode({"query.bibliographic": title, "rows": 1})
    try:
        data = _http_json("https://api.crossref.org/works?" + q)
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    items = data.get("message", {}).get("items", [])
    return items[0] if items else None


def _openalex_lookup(title):
    q = urllib.parse.urlencode({"search": title, "per-page": 1})
    try:
        data = _http_json("https://api.openalex.org/works?" + q)
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    results = data.get("results", [])
    return results[0] if results else None


def _openalex_abstract(work):
    idx = work.get("abstract_inverted_index")
    if not idx:
        return None
    positions = []
    for word, locs in idx.items():
        for loc in locs:
            positions.append((loc, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def cmd_enrich(args):
    from ..config import require_config
    cfg = require_config(args)
    field = field_name(args.field)
    # find items missing the field (with title/doi so we can look them up)
    code = ITEM_MAP + scope_js(args.collection) + (
        "var miss = items.filter(function(i){ return !String(i.getField(%r) || '').trim(); });\n"
        "return { field: %r, total: items.length, missing: miss.length, items: miss.map(mapItem) };"
    ) % (field, field)
    res = run_js(cfg, code, label="enrich:scan")
    targets = res["items"]
    if args.limit:
        targets = targets[: args.limit]
    info("Looking up %d item(s) missing '%s' via %s..." % (len(targets), field, args.source))
    edits = []
    for it in targets:
        title = it.get("title") or ""
        if not title:
            continue
        value = None
        if args.source == "openalex" or field == "abstractNote":
            work = _openalex_lookup(title)
            if work:
                if field == "DOI":
                    value = (work.get("doi") or "").replace("https://doi.org/", "")
                elif field == "date":
                    value = str(work.get("publication_year") or "") or None
                elif field == "abstractNote":
                    value = _openalex_abstract(work)
        else:  # crossref
            work = _crossref_lookup(title)
            if work:
                if field == "DOI":
                    value = work.get("DOI")
                elif field == "date":
                    parts = (work.get("issued", {}).get("date-parts") or [[None]])[0]
                    value = str(parts[0]) if parts and parts[0] else None
                elif field == "abstractNote":
                    value = work.get("abstract")
        if value:
            edits.append({"key": it["key"], "set": {field: value}, "_title": title, "_value": value})
        time.sleep(args.delay)

    if not edits:
        print("No values found to fill.")
        return
    if args.dry_run:
        print("DRY-RUN — would set '%s' on %d item(s):" % (field, len(edits)))
        for e in edits[: args.samples]:
            print("  %-10s %s\n      → %s" % (e["key"], (e["_title"] or "")[:60], str(e["_value"])[:80]))
        return
    confirm_write(args, "This sets '%s' on %d item(s) from %s." % (field, len(edits), args.source))
    clean = [{"key": e["key"], "set": e["set"]} for e in edits]
    op_id = _snapshot(cfg, [e["key"] for e in clean], "enrich")
    body = _APPLY_BODY % json.dumps(clean)
    r = run_js(cfg, body, label="enrich:apply")
    print("Enriched %d item(s) with '%s'." % (r["applied"], field))
    if op_id:
        info("Undo with:  zot undo %s" % op_id)


# --------------------------------------------------------------------------- #
# tag normalize
# --------------------------------------------------------------------------- #
def plan_tag_normalization(tags, extra_map=None):
    """Return a {old_tag: new_tag} rename plan folding case/whitespace variants
    together, seeded by an optional explicit mapping. Pure — unit-testable."""
    mapping = dict(extra_map or {})

    def norm(t):
        return " ".join(t.split()).casefold()

    groups = {}
    for t in tags:
        if t:
            groups.setdefault(norm(t), []).append(t)
    for variants in groups.values():
        if len(variants) < 2:
            continue
        # canonical = prefer a variant that carries case (not all-lowercase), then sorted
        canonical = sorted(set(variants), key=lambda s: (s == s.lower(), s))[0]
        for v in set(variants):
            if v != canonical:
                mapping.setdefault(v, canonical)
    return {o: n for o, n in mapping.items() if n and o != n}


def cmd_tag_normalize(args):
    from ..config import require_config
    cfg = require_config(args)
    # gather all tags with usage counts
    tags = run_js(cfg, (
        "var lib=Zotero.Libraries.userLibraryID; var all=await Zotero.Tags.getAll(lib);\n"
        "return all.map(function(t){ return t.tag !== undefined ? t.tag : t; });"
    ), label="tag-normalize:list")
    tags = [t for t in tags if t]

    extra = {}
    if args.map:
        with open(args.map, encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0].strip():
                    extra[row[0].strip()] = row[1].strip()

    mapping = plan_tag_normalization(tags, extra)
    if not mapping:
        print("Tags already normalised — nothing to do.")
        return
    if args.dry_run:
        print("DRY-RUN — would rename %d tag(s):" % len(mapping))
        for o, n in sorted(mapping.items()):
            print("  %-30s → %s" % (o, n))
        return
    confirm_write(args, "This renames %d tag(s) across the library." % len(mapping))
    code = (
        "var mapping=%s; var lib=Zotero.Libraries.userLibraryID; var done=0, errors=[];\n"
        "for (var o in mapping){ try { await Zotero.Tags.rename(lib, o, mapping[o]); done++; } catch(e){ errors.push(o+': '+e); } }\n"
        "return { renamed: done, errors: errors };"
    ) % json.dumps(mapping)
    res = run_js(cfg, code, label="tag-normalize")
    print("Renamed %d tag(s)." % res["renamed"])
    if res.get("errors"):
        info("errors: " + "; ".join(map(str, res["errors"])))
