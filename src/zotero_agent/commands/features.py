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
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import match
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


def _try_json(url):
    try:
        return _http_json(url)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _crossref_candidate(work):
    """Crossref's record, reduced to the shape `match.verify` compares."""
    if not work:
        return None
    parts = (work.get("issued", {}).get("date-parts") or [[None]])[0]
    return {
        "doi": work.get("DOI") or "",
        "title": (work.get("title") or [""])[0],
        "year": parts[0] if parts else None,
        "authors": [(a.get("family") or a.get("name") or "") for a in (work.get("author") or [])],
        "abstract": match.clean_abstract(work.get("abstract")),
    }


def _openalex_candidate(work):
    if not work:
        return None
    index = work.get("abstract_inverted_index")
    abstract = ""
    if index:
        positions = [(loc, word) for word, locs in index.items() for loc in locs]
        positions.sort()
        abstract = match.clean_abstract(" ".join(w for _, w in positions))
    authorships = work.get("authorships") or []
    return {
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "title": work.get("title") or work.get("display_name") or "",
        "year": work.get("publication_year"),
        "authors": [(a.get("author") or {}).get("display_name") or "" for a in authorships],
        "abstract": abstract,
    }


def _lookup_by_doi(doi, source):
    """Fetch the record for a DOI we already hold. No verification needed —
    a DOI is an identifier, so there is nothing to disambiguate."""
    quoted = urllib.parse.quote(doi.strip())
    if source == "openalex":
        return _openalex_candidate(_try_json("https://api.openalex.org/works/doi:" + quoted))
    data = _try_json("https://api.crossref.org/works/" + quoted)
    return _crossref_candidate((data or {}).get("message"))


def _search_candidates(title, source, rows=4):
    """Ask for several results, not one: the best *match* is rarely the top hit,
    and with rows=1 there is nothing to reject in favour of."""
    if source == "openalex":
        q = urllib.parse.urlencode({"search": title[:200], "per-page": rows})
        data = _try_json("https://api.openalex.org/works?" + q)
        return [_openalex_candidate(w) for w in (data or {}).get("results", [])]
    q = urllib.parse.urlencode({"query.bibliographic": title[:200], "rows": rows})
    data = _try_json("https://api.crossref.org/works?" + q)
    return [_crossref_candidate(w) for w in (data or {}).get("message", {}).get("items", [])]


def _value_for(field, candidate):
    if field == "DOI":
        return candidate.get("doi") or None
    if field == "date":
        return str(candidate["year"]) if candidate.get("year") else None
    if field == "abstractNote":
        text = candidate.get("abstract") or ""
        # A one-line "abstract" is a stub, not a summary.
        return text if len(text) > 80 else None
    return None


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
    by_doi = 0
    rejected = {"title": 0, "year": 0, "author": 0, "no-result": 0, "no-value": 0}
    for it in targets:
        title = it.get("title") or ""
        existing_doi = (it.get("doi") or "").strip()
        candidate, similarity, how = None, None, "doi"
        if existing_doi and field != "DOI":
            # The item already carries an identifier: use it. This is exact, and
            # it is the only path with no chance of matching the wrong work.
            candidate = _lookup_by_doi(existing_doi, args.source)
            if candidate:
                by_doi += 1
        elif title:
            how = "search"
            creators = it.get("creators") or []
            surname = creators[0].split()[-1] if creators and creators[0].split() else ""
            best_reason = "no-result"
            for cand in _search_candidates(title, args.source):
                if not cand:
                    continue
                ok, similarity, reason = match.verify(title, it.get("date") or it.get("year"),
                                                      surname, cand,
                                                      min_similarity=args.min_similarity)
                if ok:
                    candidate = cand
                    break
                best_reason = reason
            if not candidate:
                rejected[best_reason] = rejected.get(best_reason, 0) + 1
        if not candidate:
            if how == "doi":
                rejected["no-result"] += 1
            time.sleep(args.delay)
            continue
        value = _value_for(field, candidate)
        if value:
            edits.append({"key": it["key"], "set": {field: value}, "_title": title,
                          "_value": value, "_how": how, "_sim": similarity,
                          "_cand": candidate.get("title") or ""})
        else:
            rejected["no-value"] += 1
        time.sleep(args.delay)

    skipped = sum(rejected.values())
    if skipped:
        info("Rejected %d candidate(s): %s" % (
            skipped, ", ".join("%s %d" % (k, v) for k, v in rejected.items() if v)))
    if by_doi:
        info("%d item(s) resolved by their existing DOI (exact)." % by_doi)
    if not edits:
        print("No values found to fill.")
        return
    if args.dry_run:
        print("DRY-RUN — would set '%s' on %d item(s):" % (field, len(edits)))
        for e in edits[: args.samples]:
            print("  %-10s %s" % (e["key"], (e["_title"] or "")[:60]))
            if e["_how"] == "search":
                print("      matched %.3f  %s" % (e["_sim"] or 0, (e["_cand"] or "")[:60]))
            print("      → %s" % str(e["_value"])[:80])
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


# --------------------------------------------------------------------------- #
# tag from-collections
# --------------------------------------------------------------------------- #
# Libraries that predate tagging keep their meaning in the folder tree: a paper
# filed under "Infodemia en Twitter / Machine learning" is tagged by its
# location and nowhere else. That knowledge is real, and mechanical to harvest —
# which is the point, because hand-tagging a few thousand items never happens.
#
# The one thing that has to be got right is scope. Matching the whole path makes
# the top of the tree shout over everything below it: with a root branch called
# "@Digitalización", a naive pass tagged 1318 of 3019 items `#digitalización`, a
# label so broad it separates nothing. Container segments are therefore dropped
# before matching, so a tag comes from what an item is *about*, not from which
# drawer it lives in.
def tags_for_path(path, rules, containers=()):
    """Tags implied by one collection path (e.g. "Investigacion / Infodemia").

    `rules` is a list of {"match": regex, "tags": [...]}; matching is
    case- and accent-insensitive. Pure and regex-only — no Zotero, no network.
    """
    # Split first, normalise after: norm_title drops the "/" separators, so
    # normalising the whole path would collapse it into a single segment.
    #
    # Container names are compared with punctuation intact, because that is
    # often the only thing telling a container from a real topic: the branch
    # "@Digitalización" and the leaf "Digitalización" are different collections,
    # and norm_title would make them identical.
    def container_key(segment):
        return match.strip_accents(segment).strip().lower()

    raw = [s for s in str(path or "").split("/")]
    skip = {container_key(c) for c in containers}
    kept = [match.norm_title(s) for s in raw if container_key(s) not in skip]
    kept = [s for s in kept if s]
    haystack = " / ".join(kept) if kept else " / ".join(
        s for s in (match.norm_title(x) for x in raw) if s)
    found = set()
    for rule in rules:
        try:
            if re.search(rule["match"], haystack):
                found.update(rule.get("tags") or [])
        except re.error as exc:
            raise ValueError("bad regex %r: %s" % (rule.get("match"), exc)) from exc
    return found


def load_tag_rules(path):
    """Read the rules file: {"containers": [...], "rules": [{match, tags}]}."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        die("cannot read rules file %s: %s" % (path, exc))
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        die("%s: needs a non-empty 'rules' list of {match, tags}" % path)
    for rule in rules:
        if not rule.get("match") or not rule.get("tags"):
            die("%s: every rule needs 'match' and 'tags'" % path)
    return data.get("containers") or [], rules


_PATHS_JS = r"""
var lib = Zotero.Libraries.userLibraryID;
var cache = {};
function cpath(id) {
  if (cache[id]) return cache[id];
  var c = Zotero.Collections.get(id);
  if (!c) return '';
  var p = c.name, parent = c.parentID, guard = 0;
  while (parent && guard++ < 12) {
    var pc = Zotero.Collections.get(parent);
    if (!pc) break;
    p = pc.name + ' / ' + p;
    parent = pc.parentID;
  }
  cache[id] = p;
  return p;
}
var all = await Zotero.Items.getAll(lib, true, false, false);
var out = [];
for (var it of all) {
  if (!it.isRegularItem()) continue;
  out.push({ key: it.key, paths: it.getCollections().map(cpath),
             tags: it.getTags().map(function (t) { return t.tag; }) });
}
return { items: out };
"""


def cmd_tag_from_collections(args):
    from ..config import require_config
    cfg = require_config(args)
    containers, rules = load_tag_rules(args.rules)
    res = run_js(cfg, _PATHS_JS, label="tag:paths")
    edits, counts = [], {}
    for it in res["items"]:
        have = set(it["tags"])
        wanted = set()
        for path in it["paths"]:
            wanted |= tags_for_path(path, rules, containers)
        new = sorted(wanted - have)
        if not new:
            continue
        edits.append({"key": it["key"], "addTags": new})
        for tag in new:
            counts[tag] = counts.get(tag, 0) + 1

    if not edits:
        print("No new tags implied by the collection tree.")
        return
    total = len(res["items"])
    print("%d of %d item(s) would gain tags:" % (len(edits), total))
    for tag, n in sorted(counts.items(), key=lambda kv: -kv[1])[: args.samples]:
        share = 100.0 * n / total
        flag = "   ⚠ covers %.0f%% of the library" % share if share > 40 else ""
        print("  %5d  %s%s" % (n, tag, flag))
    if len(counts) > args.samples:
        info("  ... (%d more tag(s))" % (len(counts) - args.samples))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            for e in edits:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        print("Wrote %d edit(s) to %s — apply with: zot apply %s" % (len(edits), args.out, args.out))
        return
    if args.dry_run:
        info("Re-run with --out FILE to save the plan, or --apply to write it now.")
        return
    if not args.apply:
        info("Nothing written. Use --apply to write, or --out FILE for a reviewable plan.")
        return
    confirm_write(args, "This adds tags to %d item(s)." % len(edits))
    op_id = _snapshot(cfg, [e["key"] for e in edits], "tag-from-collections")
    body = _APPLY_BODY % json.dumps(edits)
    r = run_js(cfg, body, label="tag-from-collections:apply")
    print("Tagged %d item(s)." % r["applied"])
    if op_id:
        info("Undo with:  zot undo %s" % op_id)
