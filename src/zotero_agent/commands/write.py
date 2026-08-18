"""Write and organisation commands. All go through the bridge and are guarded."""

import json
import re
import sys

from .. import match
from ..constants import EXIT_GENERIC, EXIT_NOTFOUND
from ..http import is_loopback, run_js
from ..jslib import collection_items_scope, field_name, scope_js
from ..output import dump_json
from ..resolve import keys_from, resolve_key
from ..term import confirm_write, debug, die, info

# Every translator Zotero offers for the identifier, tried in turn. Taking only
# translators[0] is why ISBN imports failed wholesale: for an ISBN the first
# offer is "Library of Congress ISBN", which answers nothing for most books,
# while BnF and K10plus (offers 2 and 3) resolve them fine. DOIs never showed the
# bug because CrossRef is first there.
_TRANSLATE_JS = r"""
var identifier = %(identifier)s, kind = %(kind)s, colArg = %(collection)s;
var wantPdf = %(pdf)s, checkDup = %(check_dup)s;
var ident = {};
if (kind === 'doi') ident.DOI = identifier;
else if (kind === 'isbn') ident.ISBN = identifier;
else if (kind === 'arxiv') ident.arXiv = identifier;
else return { error: 'unsupported kind: ' + kind + ' (use doi/isbn/arxiv)' };

function fresh(tr) {
  var t = new Zotero.Translate.Search();
  t.setIdentifier(ident);
  if (tr) t.setTranslator(tr);
  return t;
}

var translators = await fresh(null).getTranslators();
if (!translators || !translators.length) {
  return { added: [], attempts: [], error_detail: 'no translator handles this ' + kind };
}

async function attempt(opts) {
  var attempts = [];
  for (var tr of translators) {
    try {
      var got = await fresh(tr).translate(opts);
      if (got && got.length) return { items: got, translator: tr.label, attempts: attempts };
      attempts.push({ translator: tr.label, error: 'no items returned' });
    } catch (e) {
      attempts.push({ translator: tr.label, error: String(e && e.message ? e.message : e) });
    }
  }
  return { items: null, attempts: attempts };
}

function norm(t) { return String(t || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }
function sim(a, b) {
  if (a === b) return 1;
  var la = a.length, lb = b.length;
  if (!la || !lb) return 0;
  var d = [];
  for (var i = 0; i <= la; i++) d[i] = [i];
  for (var j = 0; j <= lb; j++) d[0][j] = j;
  for (var i = 1; i <= la; i++) for (var j = 1; j <= lb; j++) {
    var c = a[i - 1] === b[j - 1] ? 0 : 1;
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
  }
  return 1 - d[la][lb] / Math.max(la, lb);
}

// Look for something close enough that adding would duplicate it. Searching by
// the first words of the title keeps this cheap enough to run before every add.
async function findDuplicate(title, lastName) {
  var words = norm(title).split(' ').filter(function (w) { return w.length > 2; }).slice(0, 4);
  if (!words.length) return null;
  var s = new Zotero.Search();
  s.libraryID = Zotero.Libraries.userLibraryID;
  s.addCondition('itemType', 'isNot', 'attachment');
  s.addCondition('itemType', 'isNot', 'note');
  s.addCondition('title', 'contains', words.join(' '));
  var ids = await s.search();
  var candidates = ids.length ? await Zotero.Items.getAsync(ids) : [];
  var target = norm(title);
  for (var it of candidates) {
    if (sim(target, norm(it.getField('title'))) < %(threshold)s) continue;
    if (lastName) {
      var match = it.getCreators().some(function (c) {
        return norm(c.lastName || c.name || '') === norm(lastName);
      });
      if (!match) continue;
    }
    return { key: it.key, title: it.getField('title'), date: it.getField('date'), type: it.itemType };
  }
  return null;
}

if (checkDup) {
  // Resolve the metadata without saving, so a duplicate is caught before it exists.
  var probe = await attempt({ libraryID: false });
  if (!probe.items) return { added: [], attempts: probe.attempts };
  var meta = probe.items[0] || {};
  var first = (meta.creators || [])[0] || {};
  var dup = await findDuplicate(meta.title || '', first.lastName || first.name || '');
  if (dup) return { added: [], attempts: probe.attempts, duplicate: dup,
                    candidate: { title: meta.title, translator: probe.translator } };
}

var opts = { libraryID: Zotero.Libraries.userLibraryID };
if (colArg) {
  var col = await Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID, colArg)
    || Zotero.Collections.getByLibrary(Zotero.Libraries.userLibraryID, true)
        .find(function (c) { return c.name === colArg; });
  if (col) opts.collections = [col.id];
}
var run = await attempt(opts);
if (!run.items) return { added: [], attempts: run.attempts };

var out = [];
for (var it of run.items) {
  var rec = { key: it.key, title: it.getField('title'), type: it.itemType, pdf: null };
  if (wantPdf) {
    try {
      var att = await Zotero.Attachments.addAvailablePDF(it);
      if (att) rec.pdf = 'attached';
    } catch (e) { rec.pdfError = String(e); }
  }
  out.push(rec);
}
return { added: out, translator: run.translator, attempts: run.attempts };
"""

DUP_THRESHOLD = 0.9


def cmd_add(args):
    from ..config import require_config
    cfg = require_config(args)
    check_dup = getattr(args, "check_duplicate", False)
    code = _TRANSLATE_JS % {
        "identifier": json.dumps(args.identifier),
        "kind": json.dumps(args.kind),
        "collection": json.dumps(args.collection or ""),
        "pdf": "true" if args.pdf else "false",
        "check_dup": "true" if check_dup else "false",
        "threshold": DUP_THRESHOLD,
    }
    res = run_js(cfg, code, label="add")
    added = res.get("added", [])
    attempts = res.get("attempts", [])
    for a in attempts:
        debug("translator %s: %s" % (a.get("translator"), a.get("error")))
    if args.json:
        dump_json(res)
        return
    dup = res.get("duplicate")
    if dup:
        die("already in the library: %s %s (%s, %s) — re-run without "
            "--check-duplicate to add it anyway"
            % (dup["key"], (dup.get("title") or "")[:60], dup.get("type"), dup.get("date") or "n/d"),
            code=EXIT_GENERIC)
    if not added:
        # Which translators were tried, and what each said: the difference between
        # "this identifier has no metadata" and "the service was down".
        detail = "; ".join("%s: %s" % (a.get("translator"), a.get("error")) for a in attempts)
        die("nothing added for %s %s — %s" % (args.kind, args.identifier,
                                              detail or res.get("error_detail") or "no translator handled it"),
            code=EXIT_NOTFOUND)
    if res.get("translator"):
        debug("resolved by translator: %s" % res["translator"])
    for a in added:
        pdf = "  [PDF %s]" % a["pdf"] if a.get("pdf") else ("  [PDF failed]" if a.get("pdfError") else "")
        print("Added %-10s %-14s %s%s" % (a["key"], a["type"], (a["title"] or "")[:60], pdf))


# A group is only safe to merge unattended when nothing contradicts it. Titles
# collide constantly in a real library — five different *Estadística* textbooks
# by Spiegel and Triola, the 3rd and 4th editions of Scott's *Social Network
# Analysis* — and `Zotero.Items.merge` cannot be undone, so anything with a
# disagreeing author, year or edition has to be looked at by a human first.
# Item types that name a distinct bibliographic object. A thesis and the journal
# article drawn from it share a title, an author and almost a year — Shannon's
# 1937 thesis and its 1938 paper — and are still two things you cite separately.
# Web-ish types are excluded because there the type is mostly import noise: the
# same post arrives as `webpage` from one translator and `blogPost` from another.
FORMAL_TYPES = frozenset({
    "book", "bookSection", "journalArticle", "conferencePaper", "thesis",
    "report", "dataset", "preprint", "manuscript", "encyclopediaArticle",
})


def merge_confidence(group):
    """Return (confident, reason) for one duplicate group.

    Pure: `group` is a list of dicts with title/year/firstAuthor/edition, exactly
    what the dedupe scan returns. Absent values never veto — they are unknowns,
    not disagreements.
    """
    authors = sorted({match.norm_title(i.get("firstAuthor") or "") for i in group} - {""})
    # Compare by containment, not equality: the same person shows up as
    # "Banda" and "Banda, Juan M." depending on how the record was imported.
    for i, a in enumerate(authors):
        for b in authors[i + 1:]:
            if a not in b and b not in a:
                return False, "different authors"
    editions = {match.norm_title(str(i.get("edition") or "")) for i in group}
    editions.discard("")
    if len(editions) > 1:
        return False, "different editions"
    years = sorted(y for y in (match.year_of(i.get("year")) for i in group) if y)
    if years and years[-1] - years[0] > match.MAX_YEAR_DRIFT:
        return False, "years %d-%d" % (years[0], years[-1])
    formal = {i.get("type") for i in group if i.get("type") in FORMAL_TYPES}
    if len(formal) > 1:
        return False, "different item types (%s)" % ", ".join(sorted(formal))
    return True, ""


_DEDUPE_SCAN = (
    "function norm(t){ return String(t||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); }\n"
    "function sim(a,b){ if(a===b) return 1; var la=a.length, lb=b.length; if(!la||!lb) return 0;\n"
    "  var d=[]; for(var i=0;i<=la;i++){ d[i]=[i]; } for(var j=0;j<=lb;j++){ d[0][j]=j; }\n"
    "  for(var i=1;i<=la;i++){ for(var j=1;j<=lb;j++){ var c=a[i-1]===b[j-1]?0:1;\n"
    "    d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+c); } }\n"
    "  return 1 - d[la][lb]/Math.max(la,lb); }\n"
    "function detail(it){ var cr = it.getCreators();\n"
    "  var atts = it.getAttachments().map(function(id){ return Zotero.Items.get(id); })\n"
    "    .filter(function(a){ return a && a.attachmentContentType === 'application/pdf'; });\n"
    "  return { key: it.key, type: it.itemType, title: it.getField('title'),\n"
    "    year: (String(it.getField('date')||'').match(/\\d{4}/)||[null])[0],\n"
    "    firstAuthor: cr.length ? (cr[0].lastName || cr[0].name || '') : '',\n"
    "    creators: cr.map(function(c){ return c.lastName || c.name || ''; }).join('; '),\n"
    "    edition: it.getField('edition') || '',\n"
    "    publisher: it.getField('publisher') || it.getField('publicationTitle') || '',\n"
    "    doi: it.getField('DOI') || '', pdfs: atts.length, notes: it.getNotes().length,\n"
    "    abstract: (it.getField('abstractNote')||'').length, dateAdded: String(it.dateAdded) }; }\n"
    "var groups = {};\n"
    "for (var it of items) {\n"
    "  var kv = (by === 'doi') ? (it.getField('DOI')||'').toLowerCase().trim() : norm(it.getField('title'));\n"
    "  if (!kv) continue; (groups[kv] = groups[kv] || []).push(it);\n"
    "}\n"
    "var dup = Object.keys(groups).map(function(k){return groups[k];}).filter(function(g){return g.length>1;});\n"
    "if (fuzzy && by === 'title') {\n"
    "  var singles = Object.keys(groups).filter(function(k){return groups[k].length===1;});\n"
    "  var blocks = {};\n"
    "  for (var i=0;i<singles.length;i++){ var pref=singles[i].slice(0,6); (blocks[pref]=blocks[pref]||[]).push(singles[i]); }\n"
    "  for (var pk in blocks){ var ks=blocks[pk]; if(ks.length<2) continue; var used={};\n"
    "    for (var a=0;a<ks.length;a++){ if(used[a]) continue; var grp=[groups[ks[a]][0]];\n"
    "      for (var b=a+1;b<ks.length;b++){ if(used[b]) continue; if(sim(ks[a],ks[b])>=threshold){ grp.push(groups[ks[b]][0]); used[b]=1; } }\n"
    "      if (grp.length>1) dup.push(grp); } }\n"
    "}\n"
    "var report = dup.map(function(g){ return g.map(detail); });\n"
    "return { by: by, fuzzy: fuzzy, groups: report.length, duplicates: report };"
)

# Merging across item types is fine, but Zotero wants the secondaries to agree
# with the master first — otherwise webpage/blogPost pairs (a third of the real
# merges in one library) fail.
_MERGE_JS = r"""
var PLAN = %s;
var log = [];
for (var entry of PLAN) {
  try {
    var master = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, entry.master);
    if (!master) { log.push({ master: entry.master, ok: false, error: 'master not found' }); continue; }
    var others = [];
    for (var k of entry.others) {
      var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, k);
      if (it) others.push(it);
    }
    if (!others.length) { log.push({ master: entry.master, ok: false, error: 'no secondaries found' }); continue; }
    for (var o of others) {
      if (o.itemType !== master.itemType) {
        o.setType(Zotero.ItemTypes.getID(master.itemType));
        await o.saveTx();
      }
    }
    await Zotero.Items.merge(master, others);
    log.push({ master: entry.master, ok: true, absorbed: others.length,
               title: String(master.getField('title') || '').slice(0, 60) });
  } catch (e) {
    log.push({ master: entry.master, ok: false, error: String(e).slice(0, 160) });
  }
}
return { merged: log.filter(function(r){ return r.ok; }).length,
         absorbed: log.filter(function(r){ return r.ok; }).reduce(function(s,r){ return s + r.absorbed; }, 0),
         failed: log.filter(function(r){ return !r.ok; }), log: log };
"""


def _plan_entry(group, confident, reason):
    """One merge proposal: oldest item is master, the rest get absorbed."""
    ordered = sorted(group, key=lambda i: i.get("dateAdded") or "")
    master, others = ordered[0], ordered[1:]
    return {
        "master": master["key"],
        "others": [i["key"] for i in others],
        "confident": confident,
        "reason": reason,
        "title": master.get("title") or "",
        "items": ordered,
    }


def cmd_dedupe(args):
    from ..config import require_config
    cfg = require_config(args)
    fuzzy = getattr(args, "fuzzy", False)
    code = ("var by = %r, fuzzy = %s, threshold = %s;\n" % (
        args.by, "true" if fuzzy else "false", repr(getattr(args, "threshold", 0.9)))
    ) + scope_js(args.collection) + _DEDUPE_SCAN
    res = run_js(cfg, code, label="dedupe")

    plan = []
    for group in res["duplicates"]:
        confident, reason = merge_confidence(group)
        plan.append(_plan_entry(group, confident, reason))
    sure = [p for p in plan if p["confident"]]
    unsure = [p for p in plan if not p["confident"]]
    res["confident"] = len(sure)
    res["needsReview"] = len(unsure)

    if getattr(args, "plan", None):
        with open(args.plan, "w", encoding="utf-8") as fh:
            for entry in plan:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print("Wrote %d group(s) to %s — %d confident, %d need review."
              % (len(plan), args.plan, len(sure), len(unsure)))
        info("Delete the lines you don't want, then:  zot merge --from %s" % args.plan)
        return
    if args.json:
        res["plan"] = plan
        dump_json(res)
        return

    print("Found %d duplicate group(s) by %s%s — %d confident, %d need review."
          % (res["groups"], res["by"], " (fuzzy)" if res.get("fuzzy") else "",
             len(sure), len(unsure)))
    for entry in plan[: args.samples]:
        flag = "" if entry["confident"] else "  ⚠ %s" % entry["reason"]
        print("  --%s" % flag)
        for it in entry["items"]:
            print("    %-10s [%s] %-28s %s" % (
                it["key"], it.get("year") or "????",
                (it.get("firstAuthor") or "")[:28], (it.get("title") or "")[:52]))
    if res["groups"] > args.samples:
        info("  ... (%d more group(s))" % (res["groups"] - args.samples))

    if not args.merge:
        if res["groups"]:
            info("Review first:  zot dedupe --plan merges.jsonl   (then `zot merge --from`)")
        return

    doomed = plan if args.force else sure
    if unsure and not args.force:
        info("Skipping %d group(s) that need review — inspect them with --plan, "
             "or pass --force to merge everything." % len(unsure))
    if not doomed:
        print("Nothing to merge.")
        return
    _run_merge(cfg, args, doomed)


def _run_merge(cfg, args, plan):
    absorbed = sum(len(p["others"]) for p in plan)
    confirm_write(args, "Merging %d group(s) removes %d item(s) and CANNOT be undone "
                        "(take a `zot backup` first)." % (len(plan), absorbed))
    payload = [{"master": p["master"], "others": p["others"]} for p in plan]
    res = run_js(cfg, _MERGE_JS % json.dumps(payload), label="merge")
    if args.json:
        dump_json(res)
        return
    print("Merged %d group(s), absorbing %d item(s)." % (res["merged"], res["absorbed"]))
    for bad in res.get("failed", [])[:10]:
        info("  failed %s: %s" % (bad.get("master"), bad.get("error")))


def cmd_merge(args):
    """Execute a merge plan produced by `zot dedupe --plan`."""
    from ..config import require_config
    cfg = require_config(args)
    source = sys.stdin if args.source == "-" else open(args.source, encoding="utf-8")
    try:
        plan = []
        for n, line in enumerate(source, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                die("%s line %d: %s" % (args.source, n, exc))
            if not entry.get("master") or not entry.get("others"):
                die("%s line %d: needs 'master' and a non-empty 'others'" % (args.source, n))
            plan.append(entry)
    finally:
        if source is not sys.stdin:
            source.close()
    if not plan:
        print("Nothing to merge.")
        return
    if args.dry_run:
        print("DRY-RUN — would merge %d group(s), absorbing %d item(s):"
              % (len(plan), sum(len(p["others"]) for p in plan)))
        for entry in plan[: args.samples]:
            print("  %s ← %s   %s" % (entry["master"], ", ".join(entry["others"]),
                                      (entry.get("title") or "")[:50]))
        return
    _run_merge(cfg, args, plan)


def cmd_tag(args):
    action = getattr(args, "action", None)
    if action == "normalize":
        from .features import cmd_tag_normalize
        return cmd_tag_normalize(args)
    if action == "from-collections":
        from .features import cmd_tag_from_collections
        if not getattr(args, "rules", None):
            die("tag from-collections needs --rules FILE (see docs for the format)")
        return cmd_tag_from_collections(args)
    from ..config import require_config
    cfg = require_config(args)
    keys = [resolve_key(cfg, k) for k in (args.keys or [])]
    if args.action in ("rm", "rename", "purge") or (args.action == "add" and len(keys) > 5):
        confirm_write(args, "This modifies tags on %s." % (("%d items" % len(keys)) if keys else "the whole library"))
    code = (
        "var action=%r, tag=%r, newTag=%r, keys=%s; var lib=Zotero.Libraries.userLibraryID; var n=0;\n"
        "if (action==='rename') { await Zotero.Tags.rename(lib, tag, newTag); return { renamed:[tag,newTag] }; }\n"
        "if (action==='purge') { await Zotero.Tags.purge(lib); return { purged:true }; }\n"
        "await Zotero.DB.executeTransaction(async function(){ for (var k of keys){ var it=await Zotero.Items.getByLibraryAndKeyAsync(lib,k); if(!it) continue; if(action==='add') it.addTag(tag); else it.removeTag(tag); await it.save(); n++; } });\n"
        "return { action: action, tag: tag, items: n };"
    ) % (args.action, args.tag or "", getattr(args, "new", None) or "", json.dumps(keys))
    res = run_js(cfg, code, label="tag")
    if res.get("renamed"):
        print("Renamed tag %r -> %r" % tuple(res["renamed"]))
    elif res.get("purged"):
        print("Purged unused tags.")
    else:
        print("%sed tag %r on %d item(s)." % (res["action"].capitalize(), res["tag"], res["items"]))


def cmd_set(args):
    from ..config import require_config
    cfg = require_config(args)
    keys = [resolve_key(cfg, k) for k in keys_from(args.keys)]
    confirm_write(args, "This sets '%s' on %d item(s)." % (args.field, len(keys)))
    field = field_name(args.field)
    code = (
        "var field=%r, value=%r, keys=%s; var lib=Zotero.Libraries.userLibraryID; var n=0, errs=[];\n"
        "await Zotero.DB.executeTransaction(async function(){ for (var k of keys){ var it=await Zotero.Items.getByLibraryAndKeyAsync(lib,k); if(!it){errs.push(k);continue;} try{ it.setField(field, value); await it.save(); n++; }catch(e){ errs.push(k+': '+e); } } });\n"
        "return { field: field, items: n, errors: errs };"
    ) % (field, args.value, json.dumps(keys))
    res = run_js(cfg, code, label="set")
    print("Set %s on %d item(s)." % (res["field"], res["items"]))
    if res.get("errors"):
        info("errors: " + "; ".join(map(str, res["errors"])))


def cmd_move(args):
    from ..config import require_config
    cfg = require_config(args)
    keys = [resolve_key(cfg, k) for k in keys_from(args.keys)]
    confirm_write(args, "This adds %d item(s) to collection '%s'." % (len(keys), args.collection))
    code = (
        "var colArg=%r, keys=%s; var lib=Zotero.Libraries.userLibraryID;\n"
        "var col = await Zotero.Collections.getByLibraryAndKey(lib, colArg) || Zotero.Collections.getByLibrary(lib,true).find(function(c){return c.name===colArg;});\n"
        "if(!col) return { error:'collection not found: '+colArg };\n"
        "var n=0; await Zotero.DB.executeTransaction(async function(){ for(var k of keys){ var it=await Zotero.Items.getByLibraryAndKeyAsync(lib,k); if(!it) continue; it.addToCollection(col.id); await it.save(); n++; } });\n"
        "return { collection: col.name, key: col.key, moved: n };"
    ) % (args.collection, json.dumps(keys))
    res = run_js(cfg, code, label="move")
    print("Added %d item(s) to '%s' (%s)." % (res["moved"], res["collection"], res["key"]))


def cmd_collection(args):
    from ..config import require_config
    cfg = require_config(args)
    code = (
        "var name=%r, parentArg=%r; var lib=Zotero.Libraries.userLibraryID;\n"
        "var col=new Zotero.Collection(); col.name=name; col.libraryID=lib;\n"
        "if(parentArg){ var p=await Zotero.Collections.getByLibraryAndKey(lib,parentArg)||Zotero.Collections.getByLibrary(lib,true).find(function(c){return c.name===parentArg;}); if(!p) return {error:'parent not found: '+parentArg}; col.parentID=p.id; }\n"
        "var id=await col.saveTx();\n"
        "return { key: Zotero.Collections.get(id).key, name: name };"
    ) % (args.name, args.parent or "")
    res = run_js(cfg, code, label="collection")
    print("Created collection '%s' (%s)." % (res["name"], res["key"]))


def cmd_note(args):
    from ..config import require_config
    cfg = require_config(args)
    key = resolve_key(cfg, args.key)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            html = fh.read()
    elif args.text is not None:
        html = args.text
    else:
        html = sys.stdin.read()
    if "<" not in html:
        html = "".join("<p>%s</p>" % line for line in html.splitlines() if line.strip())
    if args.dry_run:
        preview = re.sub(r"<[^>]+>", " ", html)
        preview = re.sub(r"\s+", " ", preview).strip()
        print("DRY-RUN — would add a child note to %s:" % key)
        print("  %s" % preview[:200])
        return
    code = (
        "var html = %s; var ifNotExists = %s;\n"
        "var parent = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, %r);\n"
        "if (!parent) return { error: 'item not found: ' + %r };\n"
        "if (ifNotExists) {\n"
        "  var exists = parent.getNotes().map(function(i){return Zotero.Items.get(i).getNote();})\n"
        "    .some(function(n){ return n === html; });\n"
        "  if (exists) return { skipped: true, parent: parent.key };\n"
        "}\n"
        "var note = new Zotero.Item('note'); note.setNote(html); note.parentID = parent.id;\n"
        "var id = await note.saveTx();\n"
        "return { noteKey: Zotero.Items.get(id).key, parent: parent.key };"
    ) % (json.dumps(html), "true" if args.if_not_exists else "false", key, key)
    res = run_js(cfg, code, label="note")
    if res.get("skipped"):
        info("An identical note already exists on %s; skipped." % res["parent"])
        return
    print("Added note %s to item %s" % (res["noteKey"], res["parent"]))


# --------------------------------------------------------------------------- #
# attachments on items that already exist
# --------------------------------------------------------------------------- #
_ATTACH_JS = r"""
var key = %(key)s, source = %(source)s, mode = %(mode)s, title = %(title)s;
var parent = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, key);
if (!parent) return { error: 'item not found: ' + key };
if (!parent.isRegularItem()) return { error: key + ' is not a regular item (cannot hold attachments)' };
var opts = { parentItemID: parent.id };
if (title) opts.title = title;
var att;
if (mode === 'file') { opts.file = source; att = await Zotero.Attachments.importFromFile(opts); }
else if (mode === 'link') { opts.url = source; att = await Zotero.Attachments.linkFromURL(opts); }
else { opts.url = source; att = await Zotero.Attachments.importFromURL(opts); }
return { attachmentKey: att.key, parent: parent.key, parentTitle: parent.getField('title'),
         mode: mode, path: att.getFilePath ? att.getFilePath() : null };
"""


def cmd_attach(args):
    """Attach a local file, a snapshot, or a link to an item that already exists.

    `add --pdf` only ever covered the moment of creation, which left the common
    case — a PDF downloaded later, a link to the publisher's page — to hand-written
    `zot exec` JS with no guard on the item it touched.
    """
    import os

    from ..config import require_config
    cfg = require_config(args)
    if bool(args.file) == bool(args.url):
        die("give exactly one of --file or --url")
    key = resolve_key(cfg, args.key)
    if args.file:
        source = os.path.abspath(os.path.expanduser(args.file))
        # Zotero reads the path, not us — but when it runs on this machine (the
        # normal case) a missing file is worth catching before the round-trip.
        if is_loopback(cfg) and not os.path.exists(source):
            die("file not found: %s" % source, code=EXIT_NOTFOUND)
        mode, what = "file", source
    else:
        source = args.url
        mode, what = ("link" if args.link else "snapshot"), source
    confirm_write(args, "This attaches %s to item %s." % (what, key))
    res = run_js(cfg, _ATTACH_JS % {
        "key": json.dumps(key), "source": json.dumps(source),
        "mode": json.dumps(mode), "title": json.dumps(args.title or ""),
    }, label="attach")
    if args.json:
        dump_json(res)
        return
    print("Attached %s (%s) to %s %s" % (res["attachmentKey"], res["mode"], res["parent"],
                                         (res.get("parentTitle") or "")[:50]))


# --------------------------------------------------------------------------- #
# open-access PDF lookup for items already in the library
# --------------------------------------------------------------------------- #
_PDF_FETCH_JS = r"""
var keys = %(keys)s, skipWithPdf = %(skip)s;
var out = [];
for (var key of keys) {
  var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, key);
  if (!it) { out.push({ key: key, status: 'not-found' }); continue; }
  if (skipWithPdf) {
    var has = it.getAttachments().map(function (id) { return Zotero.Items.get(id); })
      .some(function (a) { return a.attachmentContentType === 'application/pdf'; });
    if (has) { out.push({ key: key, title: it.getField('title'), status: 'has-pdf' }); continue; }
  }
  try {
    var att = await Zotero.Attachments.addAvailablePDF(it);
    out.push({ key: key, title: it.getField('title'),
               status: att ? 'attached' : 'none', attachmentKey: att ? att.key : null });
  } catch (e) {
    out.push({ key: key, title: it.getField('title'), status: 'error', error: String(e).slice(0, 200) });
  }
}
return { results: out };
"""


def cmd_pdf_fetch(args):
    """Ask Zotero to find an open-access PDF for items already in the library.

    Same resolver as `add --pdf` (`Zotero.Attachments.addAvailablePDF`), which was
    reachable only while creating an item. Success rates are genuinely low for
    books; the point is that the attempt no longer needs hand-written JS.
    """
    from ..config import require_config
    cfg = require_config(args)
    if args.collection:
        keys = run_js(cfg, collection_items_scope(args.collection) +
                      "return items.map(function (i) { return i.key; });", label="pdf-fetch")
    else:
        keys = [resolve_key(cfg, k) for k in keys_from(args.keys)]
    if not keys:
        die("no items to look up", code=EXIT_NOTFOUND)
    confirm_write(args, "This downloads and attaches PDFs to %d item(s)." % len(keys))
    res = run_js(cfg, _PDF_FETCH_JS % {
        "keys": json.dumps(keys), "skip": "false" if args.retry_with_pdf else "true",
    }, label="pdf-fetch", timeout=max(120, 20 * len(keys)))
    results = res.get("results", [])
    if args.json:
        dump_json(res)
        return
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if r["status"] in ("attached", "error"):
            print("%-10s %-9s %s" % (r["key"], r["status"], (r.get("title") or "")[:55]))
    print("\n%s" % ", ".join("%d %s" % (n, s) for s, n in sorted(counts.items())))
