"""Reusable JavaScript fragments injected into the bridge.

Centralising these kills the duplication the monolith had: the collection
resolver and the "all regular items" scope were re-implemented inline in
several commands. Parameters are injected with json.dumps / %r so values are
safely quoted.
"""

import re

# Field name aliases accepted on the CLI, mapped to Zotero's internal names.
FIELD_ALIASES = {
    "abstract": "abstractNote",
    "abstractnote": "abstractNote",
    "date": "date",
    "doi": "DOI",
    "url": "url",
    "publisher": "publisher",
    "publication": "publicationTitle",
}


def field_name(field):
    return FIELD_ALIASES.get(field.lower(), field)


# Heuristic: does the JS look like it writes to the library? (best-effort — see
# docs/security.md; the hard guarantee is `zot backup`, not this regex.)
WRITE_RE = re.compile(
    r"\b(saveTx|eraseTx|trashTx|\.save\s*\(|\.erase\s*\(|addTag|removeTag|"
    r"addToCollection|removeFromCollection|setField|setCreators|setNote|"
    r"Zotero\.Tags\.(rename|purge|removeFromLibraries?)|Zotero\.Items\.(merge|trashTx|eraseTx))"
)


# Serialises a Zotero item to a compact JSON-friendly record (with BBT citekey).
ITEM_MAP = r"""
function mapItem(it) {
  var ck = null;
  try { var k = Zotero.BetterBibTeX && Zotero.BetterBibTeX.KeyManager.get(it.id); ck = k ? k.citationKey : null; } catch (e) {}
  return {
    key: it.key, citekey: ck, type: it.itemType,
    title: it.getField('title'), date: it.getField('date'),
    year: (String(it.getField('date') || '').match(/\d{4}/) || [null])[0],
    creators: it.getCreators().map(function (c) {
      return (c.firstName ? c.firstName + ' ' : '') + (c.lastName || c.name || '');
    }),
    venue: it.getField('publicationTitle') || it.getField('bookTitle')
           || it.getField('publisher') || it.getField('university') || '',
    doi: it.getField('DOI') || '', url: it.getField('url') || '',
    tags: it.getTags().map(function (t) { return t.tag; }),
    abstract: it.getField('abstractNote') || ''
  };
}
"""


def resolve_collection_js(arg):
    """JS that resolves `arg` (a collection key OR name) into the variable `col`,
    or returns {error}."""
    return (
        "var __arg = %r;\n"
        "var col = await Zotero.Collections.getByLibraryAndKey(Zotero.Libraries.userLibraryID, __arg);\n"
        "if (!col) { col = Zotero.Collections.getByLibrary(Zotero.Libraries.userLibraryID, true)"
        ".find(function(c){return c.name === __arg;}); }\n"
        "if (!col) return { error: 'collection not found (key or name): ' + __arg };\n"
    ) % arg


def collection_items_scope(arg):
    """resolve_collection_js + bind `items` to the collection's regular items."""
    return resolve_collection_js(arg) + (
        "var items = col.getChildItems().filter(function(i){return i.isRegularItem();});\n"
    )


def regular_items_scope():
    """Bind `items` to every regular item in the user library (no attachments/notes)."""
    return (
        "var s = new Zotero.Search(); s.libraryID = Zotero.Libraries.userLibraryID;\n"
        "s.addCondition('itemType','isNot','attachment'); s.addCondition('itemType','isNot','note');\n"
        "var ids = await s.search(); var items = (await Zotero.Items.getAsync(ids))"
        ".filter(function(i){return i.isRegularItem();});\n"
    )


def scope_js(collection_arg):
    """Pick the collection scope if a collection was given, else the whole library."""
    return collection_items_scope(collection_arg) if collection_arg else regular_items_scope()


# Preamble that intercepts Zotero's write verbs so a script can run without
# persisting anything. Best-effort: covers the common instance/static write
# methods; scripts that read back their own new writes may still error (that is
# reported). For a hard guarantee, take a `zot backup` first.
DRYRUN_PREAMBLE = r"""
var __log = [];
var __restore = [];
function __wrap(obj, name, label) {
  if (!obj || typeof obj[name] !== 'function') return;
  var orig = obj[name];
  __restore.push(function () { obj[name] = orig; });
  obj[name] = function () {
    var what = 'collection';
    try { what = this.itemType || (this.name !== undefined ? 'collection' : 'item'); } catch (e) {}
    var title = '';
    try { title = (this.getField ? this.getField('title') : this.name) || this.key || ''; } catch (e) {}
    __log.push({ op: label + '.' + name, kind: what, title: title });
    return Promise.resolve(this.id || null);
  };
}
__wrap(Zotero.Item.prototype, 'saveTx', 'Item');
__wrap(Zotero.Item.prototype, 'save', 'Item');
__wrap(Zotero.Item.prototype, 'eraseTx', 'Item');
__wrap(Zotero.Item.prototype, 'erase', 'Item');
__wrap(Zotero.Collection.prototype, 'saveTx', 'Collection');
__wrap(Zotero.Collection.prototype, 'eraseTx', 'Collection');
__wrap(Zotero.Items, 'trashTx', 'Items');
__wrap(Zotero.Items, 'eraseTx', 'Items');
var __result = null, __err = null;
try {
  __result = await (async function () {
%s
  })();
} catch (e) {
  __err = String(e && e.message ? e.message : e);
} finally {
  __restore.forEach(function (f) { f(); });
}
return { dryRun: true, wouldWrite: __log, result: __result, error: __err };
"""
