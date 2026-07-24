# Zotero JS recipe book (for `zot exec`)

Every snippet below is an **async function body**: `Zotero`, `ZoteroPane`, and
`window` are already in scope, and whatever you `return` comes back as JSON.
Run with `zot exec file.js`, `zot exec '<inline>'`, or `echo … | zot exec -`.

> These call the same privileged `Zotero.*` API as *Tools → Developer → Run
> JavaScript* (with Async on), so anything documented for that console works
> here verbatim.

## Contents

- [Reading items](#reading-items)
- [Item fields](#item-fields)
- [Create item](#create-item)
- [Edit fields (single & bulk)](#edit-fields)
- [Collections](#collections)
- [Tags](#tags)
- [Delete items](#delete-items)
- [Attachments / PDFs](#attachments--pdfs)
- [Search conditions](#search-conditions)
- [Utility scripts](#utility-scripts)
- [Environment helpers](#environment-helpers)

---

## Reading items

```javascript
// Currently selected in the UI (only when a window exists)
var items = ZoteroPane.getSelectedItems();

// By numeric ID
var item = Zotero.Items.get(itemID);

// By key
var item = await Zotero.Items.getByLibraryAndKeyAsync(
    Zotero.Libraries.userLibraryID, 'ITEMKEY'
);

// By tag
var s = new Zotero.Search();
s.libraryID = Zotero.Libraries.userLibraryID;
s.addCondition('tag', 'is', '#digitalización');
var ids = await s.search();
var items = await Zotero.Items.getAsync(ids);

// Free-text
var s = new Zotero.Search();
s.libraryID = Zotero.Libraries.userLibraryID;
s.addCondition('quicksearch-fields', 'contains', 'internet Bolivia');
var ids = await s.search();

// All items in a collection (by key)
var col = await Zotero.Collections.getByLibraryAndKey(
    Zotero.Libraries.userLibraryID, 'SS5MVVB6'
);
var items = col.getChildItems();
```

<a id="item-fields"></a>
## Item fields

```javascript
item.getField('title')
item.getField('date')
item.getField('abstractNote')     // abstract
item.getField('url')
item.getField('DOI')
item.getField('publisher')
item.getField('publicationTitle') // journal
item.itemType                     // 'book', 'journalArticle', ...
item.getCreators()                // authors
item.getTags()                    // [{tag, type}, ...]
item.getCollections()             // collection IDs
item.key                          // unique key
item.id                           // internal numeric id
```

## Create item

```javascript
var item = new Zotero.Item('journalArticle'); // 'book', 'report', ...
item.setField('title', 'Título del artículo');
item.setField('date', '2024');
item.setCreators([{ firstName: 'Juan', lastName: 'Pérez', creatorType: 'author' }]);
var itemID = await item.saveTx();
return itemID;
```

<a id="edit-fields"></a>
## Edit fields

```javascript
// single
item.setField('abstractNote', 'Nuevo resumen...');
await item.saveTx();

// bulk — one transaction for many items (use item.save(), NOT saveTx, inside)
await Zotero.DB.executeTransaction(async function () {
    for (let item of items) {
        item.setField('publisher', 'Nuevo editorial');
        await item.save();
    }
});
```

## Collections

```javascript
// List all
var cols = Zotero.Collections.getByLibrary(Zotero.Libraries.userLibraryID);
return cols.map(c => c.name + ' (' + c.key + ')');

// Create (omit parentID for root)
var col = new Zotero.Collection();
col.name = 'Nueva colección';
// col.parentID = parentCollectionID;
var colID = await col.saveTx();
return colID;

// Move item into / out of a collection
item.addToCollection(collectionID);
await item.saveTx();
item.removeFromCollection(collectionID);
await item.saveTx();
```

## Tags

```javascript
item.addTag('nuevo-tag');
item.removeTag('tag-viejo');
await item.saveTx();

// Rename across the whole library
await Zotero.Tags.rename(Zotero.Libraries.userLibraryID, 'viejo', 'nuevo');

// Delete a tag library-wide
var tagID = Zotero.Tags.getID('tag-a-borrar');
await Zotero.Tags.removeFromLibrary(Zotero.Libraries.userLibraryID, [tagID]);
// (older API: await Zotero.Tags.erase(tagID); — try this if the above is missing)

// Color a tag
Zotero.Tags.setColor(Zotero.Libraries.userLibraryID, '#digitalización', '#FF6B6B');

// Purge unused tags
await Zotero.Tags.purge(Zotero.Libraries.userLibraryID);
```

## Delete items

```javascript
// To trash (recoverable) — PREFERRED
item.deleted = true;
await item.saveTx();
await Zotero.Items.trashTx([id1, id2, id3]);   // several at once

// Permanent (irreversible) — only when explicitly requested
await item.eraseTx();
await Zotero.Items.eraseTx([id1, id2]);
```

<a id="attachments--pdfs"></a>
## Attachments / PDFs

```javascript
var attachments = item.getAttachments();       // attachment IDs
for (let attID of attachments) {
    let att = Zotero.Items.get(attID);
    if (att.attachmentContentType === 'application/pdf') {
        return att.getFilePath();               // local path to the PDF
    }
}
```

## Search conditions

Common `addCondition(field, operator, value)` forms:

| field | operator | value | matches |
|-------|----------|-------|---------|
| `tag` | `is` | `#x` | items tagged exactly `#x` |
| `quicksearch-fields` | `contains` | text | free-text |
| `itemType` | `is` / `isNot` | `book`, `attachment` | by type |
| `abstractNote` | `is` | `` (empty) | items with no abstract |
| `noCollections` | `true` | `` | items in no collection |
| `date` | `is` / `isBefore` / `isAfter` | `2024` | by date |

Always set `s.libraryID = Zotero.Libraries.userLibraryID;` first.

## Utility scripts

### Items with no collection
```javascript
var s = new Zotero.Search();
s.libraryID = Zotero.Libraries.userLibraryID;
s.addCondition('noCollections', 'true', '');
var ids = await s.search();
return ids.length + ' ítems sin colección';
```

### Items with no abstract
> ⚠️ The search condition `addCondition('abstractNote', 'is', '')` does **not**
> work — it returns 0 because Zotero doesn't store an unset field as an empty
> string. Filter on the field value instead (verified: 1654/2865 items):
```javascript
var s = new Zotero.Search();
s.libraryID = Zotero.Libraries.userLibraryID;
s.addCondition('itemType', 'isNot', 'attachment');
s.addCondition('itemType', 'isNot', 'note');
var ids = await s.search();
var items = await Zotero.Items.getAsync(ids);
var noAbs = items.filter(i => !(i.getField('abstractNote') || '').trim());
return noAbs.map(i => ({ key: i.key, title: i.getField('title') }));
```
The same `filter on getField()` pattern applies to any "missing field X"
query (no date, no DOI, no URL) — the empty-string search condition is unreliable.

### Export a collection as JSON
```javascript
var col = await Zotero.Collections.getByLibraryAndKey(
    Zotero.Libraries.userLibraryID, 'COLLECTION_KEY'
);
var items = col.getChildItems();
return items.map(item => ({
    key: item.key,
    title: item.getField('title'),
    date: item.getField('date'),
    abstract: item.getField('abstractNote'),
    tags: item.getTags().map(t => t.tag),
    type: item.itemType,
}));
```

### Find duplicate titles
```javascript
var s = new Zotero.Search();
s.libraryID = Zotero.Libraries.userLibraryID;
s.addCondition('itemType', 'isNot', 'attachment');
var ids = await s.search();
var items = await Zotero.Items.getAsync(ids);
var seen = {}, dupes = [];
for (let item of items) {
    var t = (item.getField('title') || '').toLowerCase().trim();
    if (!t) continue;
    if (seen[t]) dupes.push(t);
    seen[t] = true;
}
return { count: dupes.length, titles: dupes };
```

## Environment helpers

```javascript
return Zotero.Users.getCurrentUserID();   // library userID
return Zotero.DataDirectory.dir;          // data dir (contains zotero.sqlite)
return Zotero.version;                     // Zotero version
```

---

## Bulk-operation safety (recap)

Before batch writes or deletions: back up `zotero.sqlite`, disable auto-sync,
dry-run (return counts + samples), test on 1–2 items, use
`Zotero.DB.executeTransaction()` for large batches, prefer trash over erase,
re-enable sync afterward. See the skill's SKILL.md for the full checklist.

> **Gotcha — "dry-run by intercepting `save()` LEAKS on Zotero 7."** Wrapping
> `Zotero.Item.prototype.save/saveTx` to no-op does **not** reliably prevent a
> persist (confirmed: a tag added under such a dry-run stayed on the item). So
> never treat "run the code with save intercepted" as a safe preview. The safe
> pattern is to **not execute the write at all** and report the intended change
> from data you already hold (this is why `zot apply --dry-run` runs no JS).
> `zot exec --dry-run` still executes with best-effort interception — `zot
> backup` is the only hard guarantee.
