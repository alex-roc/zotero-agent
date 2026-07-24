"""Write and organisation commands. All go through the bridge and are guarded."""

import json
import re
import sys

from ..constants import EXIT_NOTFOUND
from ..http import run_js
from ..jslib import field_name, scope_js
from ..output import dump_json
from ..resolve import keys_from, resolve_key
from ..term import confirm_write, die, info


def cmd_add(args):
    from ..config import require_config
    cfg = require_config(args)
    code = (
        "var identifier = %r, kind = %r, colArg = %r, wantPdf = %s;\n"
        "var translate = new Zotero.Translate.Search();\n"
        "var ident = {};\n"
        "if (kind === 'doi') ident.DOI = identifier;\n"
        "else if (kind === 'isbn') ident.ISBN = identifier;\n"
        "else if (kind === 'arxiv') ident.arXiv = identifier;\n"
        "else return { error: 'unsupported kind: ' + kind + \" (use doi/isbn/arxiv)\" };\n"
        "translate.setIdentifier(ident);\n"
        "var translators = await translate.getTranslators();\n"
        "if (!translators || !translators.length) return { error: 'no metadata found for ' + kind + ' ' + identifier };\n"
        "translate.setTranslator(translators[0]);\n"
        "var opts = { libraryID: Zotero.Libraries.userLibraryID };\n"
        "if (colArg) { var col = await Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID, colArg)"
        " || Zotero.Collections.getByLibrary(Zotero.Libraries.userLibraryID, true).find(function(c){return c.name===colArg;});"
        " if (col) opts.collections = [col.id]; }\n"
        "var items = await translate.translate(opts);\n"
        "var out = [];\n"
        "for (var it of items) {\n"
        "  var rec = { key: it.key, title: it.getField('title'), type: it.itemType, pdf: null };\n"
        "  if (wantPdf) { try { var att = await Zotero.Attachments.addAvailablePDF(it); if (att) rec.pdf = 'attached'; } catch (e) { rec.pdfError = String(e); } }\n"
        "  out.push(rec);\n"
        "}\n"
        "return { added: out };"
    ) % (args.identifier, args.kind, args.collection or "", "true" if args.pdf else "false")
    res = run_js(cfg, code, label="add")
    added = res.get("added", [])
    if args.json:
        dump_json(res)
        return
    if not added:
        die("nothing added", code=EXIT_NOTFOUND)
    for a in added:
        pdf = "  [PDF %s]" % a["pdf"] if a.get("pdf") else ("  [PDF failed]" if a.get("pdfError") else "")
        print("Added %-10s %-14s %s%s" % (a["key"], a["type"], (a["title"] or "")[:60], pdf))


def cmd_dedupe(args):
    from ..config import require_config
    cfg = require_config(args)
    if args.merge:
        where = ("collection '%s'" % args.collection) if args.collection else "the WHOLE LIBRARY"
        confirm_write(args, "Merging duplicates across %s modifies items (take a `zot backup` first)." % where)
    fuzzy = getattr(args, "fuzzy", False)
    code = (
        "var doMerge = %s, by = %r, fuzzy = %s, threshold = %s;\n"
    ) % ("true" if args.merge else "false", args.by,
         "true" if fuzzy else "false", repr(getattr(args, "threshold", 0.9))) + scope_js(args.collection) + (
        "function norm(t){ return String(t||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); }\n"
        "function sim(a,b){ if(a===b) return 1; var la=a.length, lb=b.length; if(!la||!lb) return 0;\n"
        "  var d=[]; for(var i=0;i<=la;i++){ d[i]=[i]; } for(var j=0;j<=lb;j++){ d[0][j]=j; }\n"
        "  for(var i=1;i<=la;i++){ for(var j=1;j<=lb;j++){ var c=a[i-1]===b[j-1]?0:1;\n"
        "    d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+c); } }\n"
        "  return 1 - d[la][lb]/Math.max(la,lb); }\n"
        "var groups = {};\n"
        "for (var it of items) {\n"
        "  var kv = (by === 'doi') ? (it.getField('DOI')||'').toLowerCase().trim() : norm(it.getField('title'));\n"
        "  if (!kv) continue; (groups[kv] = groups[kv] || []).push(it);\n"
        "}\n"
        "var dup = Object.keys(groups).map(function(k){return groups[k];}).filter(function(g){return g.length>1;});\n"
        "if (fuzzy && by === 'title') {\n"
        "  var singles = Object.keys(groups).filter(function(k){return groups[k].length===1;});\n"
        "  var blocks = {};\n"  # block by a cheap prefix key so we don't do O(n^2) over the whole library
        "  for (var i=0;i<singles.length;i++){ var pref=singles[i].slice(0,6); (blocks[pref]=blocks[pref]||[]).push(singles[i]); }\n"
        "  for (var pk in blocks){ var ks=blocks[pk]; if(ks.length<2) continue; var used={};\n"
        "    for (var a=0;a<ks.length;a++){ if(used[a]) continue; var grp=[groups[ks[a]][0]];\n"
        "      for (var b=a+1;b<ks.length;b++){ if(used[b]) continue; if(sim(ks[a],ks[b])>=threshold){ grp.push(groups[ks[b]][0]); used[b]=1; } }\n"
        "      if (grp.length>1) dup.push(grp); } }\n"
        "}\n"
        "var report = dup.map(function(g){ return g.map(function(it){ return { key: it.key, title: it.getField('title'), year: (String(it.getField('date')||'').match(/\\d{4}/)||[null])[0] }; }); });\n"
        "var merged = 0;\n"
        "if (doMerge) { for (var g of dup) { g.sort(function(a,b){ return String(a.dateAdded).localeCompare(String(b.dateAdded)); });\n"
        "  var master = g[0], others = g.slice(1); await Zotero.Items.merge(master, others); merged += others.length; } }\n"
        "return { by: by, fuzzy: fuzzy, groups: report.length, duplicates: report, mergedAway: merged };"
    )
    res = run_js(cfg, code, label="dedupe")
    if args.json:
        dump_json(res)
        return
    print("Found %d duplicate group(s) by %s%s." % (res["groups"], res["by"], " (fuzzy)" if res.get("fuzzy") else ""))
    for g in res["duplicates"][: args.samples]:
        print("  --")
        for it in g:
            print("    %-10s [%s] %s" % (it["key"], it.get("year") or "????", (it["title"] or "")[:60]))
    if res["groups"] > args.samples:
        info("  ... (%d more groups)" % (res["groups"] - args.samples))
    if args.merge:
        print("Merged away %d duplicate item(s)." % res["mergedAway"])
    elif res["groups"]:
        info("Re-run with --merge (and --yes) to consolidate, keeping the oldest as master.")


def cmd_tag(args):
    if getattr(args, "action", None) == "normalize":
        from .features import cmd_tag_normalize
        return cmd_tag_normalize(args)
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
