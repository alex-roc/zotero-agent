---
title: zot exec — JS recipes
description: The Zotero JavaScript recipe book for zot exec — read, edit, tag, collections, search conditions, and the gotchas.
---

`zot exec` sends JavaScript to the bridge plugin, which runs it inside Zotero's
privileged context. Every snippet below is an **async function body**: `Zotero`,
`ZoteroPane`, and `window` are already in scope, and whatever you `return` comes
back as JSON.

```bash
zot exec 'return Zotero.version;'    # inline
zot exec script.js                    # from a file
echo 'return 1+1;' | zot exec -       # from stdin
zot exec script.js --dry-run          # intercept writes, report only
```

For anything non-trivial, write the JS to a file and run `zot exec file.js` —
easier to review and re-run than inline quoting. These call the same API as
*Tools → Developer → Run JavaScript* (with Async on), so anything documented for
that console works here verbatim.

:::tip[Prefer the built-in commands]
Reach for `zot search`, `zot missing`, `zot apply`, `zot dedupe` and friends
before hand-writing `exec` — they wrap this logic reliably (and sidestep gotchas
like the abstract-search one below). Use `exec` only for what the commands don't
cover. See the [command reference](/zotero-agent/reference/commands/).
:::

## Reading items

```javascript
// Currently selected in the UI (only when a window exists)
var items = ZoteroPane.getSelectedItems();

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

// All items in a collection (by key)
var col = await Zotero.Collections.getByLibraryAndKey(
    Zotero.Libraries.userLibraryID, 'SS5MVVB6'
);
var items = col.getChildItems();
```

## Item fields

```javascript
item.getField('title')
item.getField('date')
item.getField('abstractNote')     // abstract
item.getField('DOI')
item.getField('publicationTitle') // journal
item.itemType                     // 'book', 'journalArticle', ...
item.getCreators()                // authors
item.getTags()                    // [{tag, type}, ...]
item.key                          // unique key
```

## Create an item

```javascript
var item = new Zotero.Item('journalArticle'); // 'book', 'report', ...
item.setField('title', 'Título del artículo');
item.setField('date', '2024');
item.setCreators([{ firstName: 'Juan', lastName: 'Pérez', creatorType: 'author' }]);
return await item.saveTx();
```

## Edit fields (single & bulk)

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
var colID = await col.saveTx();

// Move item into / out of a collection
item.addToCollection(collectionID);    await item.saveTx();
item.removeFromCollection(collectionID); await item.saveTx();
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

// Color a tag, purge unused
Zotero.Tags.setColor(Zotero.Libraries.userLibraryID, '#digitalización', '#FF6B6B');
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

Common `addCondition(field, operator, value)` forms (always set
`s.libraryID = Zotero.Libraries.userLibraryID;` first):

| field | operator | value | matches |
|-------|----------|-------|---------|
| `tag` | `is` | `#x` | items tagged exactly `#x` |
| `quicksearch-fields` | `contains` | text | free-text |
| `itemType` | `is` / `isNot` | `book`, `attachment` | by type |
| `noCollections` | `true` | `` | items in no collection |
| `date` | `is` / `isBefore` / `isAfter` | `2024` | by date |

## Gotcha: "missing field" searches

:::caution
`addCondition('abstractNote', 'is', '')` does **not** work — it returns 0,
because Zotero doesn't store an unset field as an empty string. Filter on the
field value instead:
:::

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

The same `filter on getField()` pattern applies to any "missing field X" query.
This is exactly what `zot missing` does for you.

## Environment helpers

```javascript
return Zotero.Users.getCurrentUserID();   // library userID
return Zotero.DataDirectory.dir;          // data dir (contains zotero.sqlite)
return Zotero.version;                     // Zotero version
```

## Bulk-operation safety (recap)

Before batch writes or deletions: back up `zotero.sqlite` (`zot backup`), disable
auto-sync, dry-run (return counts + samples), test on 1–2 items, use
`Zotero.DB.executeTransaction()` for large batches, prefer trash over erase, and
re-enable sync afterward. See the [security model](/zotero-agent/security/).
