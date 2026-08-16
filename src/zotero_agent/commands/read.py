"""Read and analysis commands (fast local API where possible, bridge otherwise)."""

import csv
import io
import json

from ..constants import EXIT_NOTFOUND
from ..http import (
    api_export_all,
    api_export_keys,
    api_list,
    api_url,
    bbt_rpc,
    http_get,
    run_js,
    truncation_notice,
)
from ..jslib import (
    ITEM_MAP,
    collection_items_scope,
    field_name,
    resolve_collection_js,
    scope_js,
)
from ..output import dump_json, flatten_item, print_items, project, write_or_print
from ..resolve import resolve_key
from ..term import die, info


def cmd_search(args):
    from ..config import require_config
    cfg = require_config(args)
    params = {"q": args.query, "format": "json"}
    if args.item_type:
        params["itemType"] = args.item_type
    if args.tag:
        params["tag"] = args.tag
    items, total = api_list(cfg, "items", params, args.all, args.limit)
    print_items(items, args.json, getattr(args, "raw", False))
    if not args.json:
        truncation_notice(len(items), total, args.all)


def cmd_get(args):
    from ..config import require_config
    cfg = require_config(args)
    key = resolve_key(cfg, args.key)
    _, body = http_get(api_url(cfg, "items/" + key))
    data = json.loads(body)
    if args.json:
        dump_json(data if getattr(args, "raw", False) else flatten_item(data))
    else:
        d = data.get("data", data)
        for k, v in d.items():
            print("%-20s %s" % (k, v))


def cmd_cite(args):
    """Resolve a Better BibTeX citekey to its Zotero item key, title and PDF path(s)."""
    from ..config import require_config
    cfg = require_config(args)
    results = bbt_rpc(cfg, "item.search", [args.citekey]) or []
    match = None
    for r in results:
        if r.get("citekey") == args.citekey or r.get("citation-key") == args.citekey:
            match = r
            break
    if not match:
        die("citekey not found in Better BibTeX: %s" % args.citekey, code=EXIT_NOTFOUND)
    item_key = match.get("id", "").rstrip("/").split("/")[-1]
    atts = bbt_rpc(cfg, "item.attachments", [args.citekey]) or []
    pdfs = [a.get("path") for a in atts if str(a.get("path", "")).lower().endswith(".pdf")]
    out = {
        "citekey": args.citekey,
        "itemKey": item_key,
        "title": match.get("title"),
        "itemType": match.get("type"),
        "pdfs": pdfs,
    }
    if args.json:
        dump_json(out)
    else:
        print("%-10s %s" % (item_key, out["title"]))
        for p in pdfs:
            print("  PDF: " + p)


def pdf_paths(cfg, key):
    """{itemKey, title, pdfs:[{attachmentKey, path, title}]} for an item or
    attachment key (or BBT citekey).

    Always ask Zotero for the path rather than building `storage/<KEY>/...`
    ourselves: getFilePath() is what resolves linked files and a configured base
    directory. Shared by `zot pdf` and `zot toc`.
    """
    key = resolve_key(cfg, key)
    code = """
var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, %r);
if (!it) return { error: 'item not found: ' + %r };
var out = [];
var atts = it.isAttachment() ? [it.id] : it.getAttachments();
for (var id of atts) {
  var att = Zotero.Items.get(id);
  if (att.attachmentContentType === 'application/pdf') {
    out.push({ attachmentKey: att.key, path: att.getFilePath(), title: att.getField('title') });
  }
}
return { itemKey: it.key, title: it.getField('title'), pdfs: out };
""" % (key, key)
    return run_js(cfg, code, label="pdf") or {}


def cmd_pdf(args):
    """Print the local path(s) of the PDF attachment(s) of an item."""
    from ..config import require_config
    cfg = require_config(args)
    result = pdf_paths(cfg, args.key)
    pdfs = result.get("pdfs", [])
    if args.json:
        dump_json(result)
        return
    if not pdfs:
        die("no PDF attachments found for item %s" % args.key, code=EXIT_NOTFOUND)
    for p in pdfs:
        print(p["path"])


def cmd_collections(args):
    from ..config import require_config
    cfg = require_config(args)
    data, total = api_list(cfg, "collections", None, args.all, args.limit)
    if args.json:
        dump_json(data)
        return
    for c in data:
        d = c.get("data", {})
        meta = c.get("meta", {})
        print("%-10s %-4s %s" % (d.get("key", ""), meta.get("numItems", ""), d.get("name", "")))
    truncation_notice(len(data), total, args.all)


def cmd_tags(args):
    from ..config import require_config
    cfg = require_config(args)
    data, total = api_list(cfg, "tags", None, args.all, args.limit)
    if args.json:
        dump_json(data)
        return
    for t in data:
        d = t.get("data", t)
        meta = t.get("meta", {})
        print("%-6s %s" % (meta.get("numItems", ""), d.get("tag", "")))
    truncation_notice(len(data), total, args.all)


def cmd_export(args):
    from ..config import require_config
    cfg = require_config(args)
    fmt = args.format
    recursive = getattr(args, "recursive", False)
    if fmt in ("bibtex", "biblatex", "ris"):
        if recursive:
            # Name every item explicitly: the collection endpoint cannot see into
            # subcollections, so it would silently export only the top level.
            keys = run_js(cfg, collection_items_scope(args.collection, True) +
                          "return items.map(function (i) { return i.key; });", label="export")
            text = api_export_keys(cfg, keys, fmt)
            total = len(keys)
        else:
            # resolve to a collection key, then page the read API's native exporter
            # (never truncating — the old code capped at limit=100).
            key = run_js(cfg, resolve_collection_js(args.collection) + "return col.key;", label="export")
            text, total = api_export_all(cfg, "collections/%s/items/top" % key, fmt)
        write_or_print(args.out, text)
        if args.out and total is not None:
            info("Wrote %d items (%s) to %s" % (total, fmt, args.out))
        return
    if fmt == "csljson":
        code = collection_items_scope(args.collection, recursive) + (
            "return items.map(function(it){ return Zotero.Utilities.Item.itemToCSLJSON"
            "  ? Zotero.Utilities.Item.itemToCSLJSON(it) : Zotero.Utilities.itemToCSLJSON(it); });"
        )
        data = run_js(cfg, code, label="export")
        write_or_print(args.out, json.dumps(data, indent=2, ensure_ascii=False))
        if args.out:
            info("Wrote %d items (CSL-JSON) to %s" % (len(data), args.out))
        return
    # json / csv: build structured data via the JS API
    code = ITEM_MAP + collection_items_scope(args.collection, recursive) + (
        "return { collection: col.name, key: col.key, items: items.map(mapItem) };"
    )
    res = run_js(cfg, code, label="export")
    items = res.get("items", [])
    if fmt == "json":
        write_or_print(args.out, json.dumps(items, indent=2, ensure_ascii=False))
    else:  # csv
        buf = io.StringIO()
        cols = ["key", "citekey", "type", "year", "date", "title", "creators", "venue", "doi", "url", "tags"]
        w = csv.writer(buf)
        w.writerow(cols)
        for it in items:
            row = [it.get(c, "") for c in cols]
            row[cols.index("creators")] = "; ".join(it.get("creators", []))
            row[cols.index("tags")] = "; ".join(it.get("tags", []))
            w.writerow(row)
        write_or_print(args.out, buf.getvalue())
    if args.out:
        info("Wrote %d items to %s" % (len(items), args.out))


def cmd_missing(args):
    from ..config import require_config
    cfg = require_config(args)
    field = field_name(args.field)
    code = ITEM_MAP + scope_js(args.collection) + (
        "var miss = items.filter(function(i){ return !String(i.getField(%r) || '').trim(); });\n"
        "return { field: %r, total: items.length, missing: miss.length, items: miss.map(mapItem) };"
    ) % (field, field)
    res = run_js(cfg, code, label="missing")
    if args.json:
        dump_json(project(res, args.detail))
        return
    print("%d of %d items are missing '%s':" % (res["missing"], res["total"], res["field"]))
    for it in res["items"]:
        print("  %-10s %-15s %s" % (it["key"], it["type"], (it["title"] or "")[:70]))


def cmd_author(args):
    from ..config import require_config
    cfg = require_config(args)
    code = ITEM_MAP + (
        "var q = %r.toLowerCase();\n"
    ) % args.name + scope_js(None) + (
        "var mine = items.filter(function(it){ return it.getCreators().some(function(c){\n"
        "  return ((c.firstName||'')+' '+(c.lastName||c.name||'')).toLowerCase().indexOf(q) !== -1; }); });\n"
        "mine.sort(function(a,b){ return String(b.getField('date')||'').localeCompare(String(a.getField('date')||'')); });\n"
        "return { query: %r, count: mine.length, items: mine.map(mapItem) };"
    ) % args.name
    res = run_js(cfg, code, label="author")
    if args.json:
        dump_json(project(res, args.detail))
        return
    print("%d items with author matching '%s':" % (res["count"], res["query"]))
    for it in res["items"]:
        ck = (" ·" + it["citekey"]) if it.get("citekey") else ""
        print("  [%s] %-14s %s%s" % (it.get("year") or "????", it["type"], (it["title"] or "")[:64], ck))


def cmd_notes(args):
    from ..config import require_config
    cfg = require_config(args)
    key = resolve_key(cfg, args.key)
    code = (
        "var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, %r);\n"
        "if (!it) return { error: 'item not found: ' + %r };\n"
        "var notes = it.getNotes().map(function(id){ var n = Zotero.Items.get(id);\n"
        "  var text = n.getNote().replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ').trim();\n"
        "  return { key: n.key, preview: text.slice(0,100) }; });\n"
        "return { itemKey: it.key, title: it.getField('title'), notes: notes };"
    ) % (key, key)
    res = run_js(cfg, code, label="notes")
    if args.json:
        dump_json(res)
        return
    print("%s — %d note(s)" % (res["title"] or res["itemKey"], len(res["notes"])))
    for n in res["notes"]:
        print("  %-10s %s" % (n["key"], n["preview"]))


def cmd_related(args):
    from ..config import require_config
    cfg = require_config(args)
    key = resolve_key(cfg, args.key)
    code = (
        "var it=await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, %r);\n"
        "if(!it) return { error:'item not found: '+%r };\n"
        "var out=[]; for(var rk of (it.relatedItems||[])){ var r=await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, rk); if(r) out.push({ key:r.key, title:r.getField('title') }); }\n"
        "return { itemKey: it.key, related: out };"
    ) % (key, key)
    res = run_js(cfg, code, label="related")
    if args.json:
        dump_json(res)
        return
    print("%s — %d related" % (res["itemKey"], len(res["related"])))
    for r in res["related"]:
        print("  %-10s %s" % (r["key"], (r["title"] or "")[:64]))


def cmd_annotations(args):
    from ..config import require_config
    from ..term import confirm_write
    cfg = require_config(args)
    key = resolve_key(cfg, args.key)
    if args.to_note:
        confirm_write(args, "This creates a note from the PDF's annotations on %s." % key)
    code = (
        "var key=%r, toNote=%s;\n"
        "var it = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, key);\n"
        "if(!it) return { error:'item not found: '+key };\n"
        "var pdf = it.isAttachment()? it : it.getAttachments().map(function(id){return Zotero.Items.get(id);}).find(function(a){return a.attachmentContentType==='application/pdf';});\n"
        "if(!pdf) return { error:'no PDF attachment for '+key };\n"
        "var anns = pdf.getAnnotations().map(function(a){ return { type:a.annotationType, page:a.annotationPageLabel, color:a.annotationColor, text:a.annotationText||'', comment:a.annotationComment||'' }; });\n"
        "var result = { itemKey: it.key, title: it.getField('title'), count: anns.length, annotations: anns };\n"
        "if (toNote && anns.length) {\n"
        "  var html='<h1>Annotations (extracted)</h1>'+anns.map(function(a){ return '<p><b>p.'+(a.page||'?')+'</b> '+(a.text?('\\u201c'+a.text+'\\u201d'):'')+(a.comment?(' \\u2014 '+a.comment):'')+'</p>'; }).join('');\n"
        "  var note=new Zotero.Item('note'); note.setNote(html); note.parentID = it.isAttachment()? (it.parentID||it.id) : it.id; var nid=await note.saveTx(); result.noteKey=Zotero.Items.get(nid).key;\n"
        "}\n"
        "return result;"
    ) % (key, "true" if args.to_note else "false")
    res = run_js(cfg, code, label="annotations")
    if args.json:
        dump_json(res)
        return
    print("%s — %d annotation(s)" % (res["title"] or res["itemKey"], res["count"]))
    for a in res["annotations"][: args.samples]:
        t = ("“%s”" % a["text"]) if a["text"] else ""
        c = (" — %s" % a["comment"]) if a["comment"] else ""
        print("  p.%-4s %-9s %s%s" % (a.get("page") or "?", a["type"], t[:60], c[:40]))
    if res["count"] > args.samples:
        info("  ... (%d more)" % (res["count"] - args.samples))
    if res.get("noteKey"):
        print("Wrote annotations to note %s" % res["noteKey"])


def cmd_stats(args):
    from ..config import require_config
    cfg = require_config(args)
    code = scope_js(None) + (
        "var byType={}, byYear={}, noAbs=0, withPdf=0;\n"
        "for(var it of items){ byType[it.itemType]=(byType[it.itemType]||0)+1;\n"
        "  var y=(String(it.getField('date')||'').match(/\\d{4}/)||['(none)'])[0]; byYear[y]=(byYear[y]||0)+1;\n"
        "  if(!String(it.getField('abstractNote')||'').trim()) noAbs++;\n"
        "  if(it.getAttachments().map(function(a){return Zotero.Items.get(a);}).some(function(a){return a.attachmentContentType==='application/pdf';})) withPdf++;\n"
        "}\n"
        "var cols=Zotero.Collections.getByLibrary(Zotero.Libraries.userLibraryID, true).length;\n"
        "var tags=await Zotero.Tags.getAll(Zotero.Libraries.userLibraryID);\n"
        "return { totalItems: items.length, collections: cols, tags: ((tags&&tags.length)||0), withPdf: withPdf, withoutPdf: items.length-withPdf, withoutAbstract: noAbs, byType: byType, byYear: byYear };"
    )
    res = run_js(cfg, code, label="stats")
    if args.json:
        dump_json(res)
        return
    print("Library: %d items · %d collections · %d tags" % (res["totalItems"], res["collections"], res["tags"] or 0))
    print("PDFs: %d with · %d without   |   %d without abstract" % (res["withPdf"], res["withoutPdf"], res["withoutAbstract"]))
    print("\nBy type:")
    for k, v in sorted(res["byType"].items(), key=lambda x: -x[1]):
        print("  %4d  %s" % (v, k))
    print("\nBy year:")
    for y in sorted(res["byYear"], reverse=True):
        print("  %-8s %d" % (y, res["byYear"][y]))


def cmd_bib(args):
    from ..config import require_config
    cfg = require_config(args)
    keys = [resolve_key(cfg, k) for k in args.keys]
    params = {"itemKey": ",".join(keys), "format": "bib", "style": args.style}
    if args.linkwrap:
        params["linkwrap"] = 1
    _, body = http_get(api_url(cfg, "items", params))
    write_or_print(args.out, body)


def cmd_recent(args):
    from ..config import require_config
    cfg = require_config(args)
    params = {"sort": "dateAdded", "direction": "desc"}
    items, _ = api_list(cfg, "items/top", params, False, args.limit)
    print_items(items, args.json, getattr(args, "raw", False))


def cmd_lint(args):
    from ..config import require_config
    cfg = require_config(args)
    code = scope_js(None) + (
        "var out = { total: items.length, combinedCreators: [], noDate: [], noCreators: [], duplicateTitles: [] };\n"
        "var seen = {};\n"
        "for (var it of items) {\n"
        "  var cr = it.getCreators();\n"
        "  if (cr.length === 0) out.noCreators.push({ key: it.key, title: it.getField('title') });\n"
        "  for (var c of cr) {\n"
        "    var combined = c.fieldMode === 1 && /,| y | & |;| and /i.test(c.lastName || '');\n"
        "    if (combined) { out.combinedCreators.push({ key: it.key, title: it.getField('title'), field: c.lastName }); break; }\n"
        "  }\n"
        "  if (!String(it.getField('date') || '').trim()) out.noDate.push({ key: it.key, title: it.getField('title') });\n"
        "  var t = String(it.getField('title') || '').toLowerCase().trim();\n"
        "  if (t) { if (seen[t]) out.duplicateTitles.push({ key: it.key, title: it.getField('title'), first: seen[t] }); else seen[t] = it.key; }\n"
        "}\n"
        "return out;"
    )
    res = run_js(cfg, code, label="lint")
    if args.json:
        dump_json(res)
        return
    n = args.samples

    def section(label, rows, fmt):
        print("\n%s: %d" % (label, len(rows)))
        for r in rows[:n]:
            print("  " + fmt(r))
        if len(rows) > n:
            print("  ... (%d more)" % (len(rows) - n))

    print("Scanned %d regular items." % res["total"])
    section("Authors stored in a single combined field", res["combinedCreators"],
            lambda r: "%-10s %-40s | %s" % (r["key"], (r["title"] or "")[:40], r["field"]))
    section("Possible duplicate titles", res["duplicateTitles"],
            lambda r: "%-10s (dup of %s) %s" % (r["key"], r["first"], (r["title"] or "")[:50]))
    section("Items with no date", res["noDate"],
            lambda r: "%-10s %s" % (r["key"], (r["title"] or "")[:60]))
    section("Items with no creators", res["noCreators"],
            lambda r: "%-10s %s" % (r["key"], (r["title"] or "")[:60]))
