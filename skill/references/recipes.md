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
- [File sync / WebDAV storage](#file-sync--webdav-storage)

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

---

## File sync / WebDAV storage

Zotero syncs **metadata** through zotero.org and **attachment files** through a
separate storage backend. When that backend is WebDAV, everything lives behind
one controller:

```js
const ctl = Zotero.Sync.Runner.getStorageController('webdav');
```

Reading the current setup needs no controller — it is all prefs:

```js
return JSON.stringify({
  protocol: Zotero.Prefs.get('sync.storage.protocol'),   // 'zotero' | 'webdav'
  scheme:   Zotero.Prefs.get('sync.storage.scheme'),     // 'https'
  url:      Zotero.Prefs.get('sync.storage.url'),        // host+path, NO scheme
  username: Zotero.Prefs.get('sync.storage.username'),
  verified: Zotero.Prefs.get('sync.storage.verified'),
  downloadMode: Zotero.Prefs.get('sync.storage.downloadMode.personal'),
});
```

**`sync.storage.url` holds host + path without the scheme** (`example.com/dav`),
and Zotero appends its own `zotero/` subdirectory: the effective root is
`<scheme>://<user>:<pass>@<url>/zotero/`. Point it at the parent, never at a
directory you already called `zotero`.

### Switching to another WebDAV server

The order matters, and three of these steps are the ones people get wrong.

```js
const ctl = Zotero.Sync.Runner.getStorageController('webdav');

Zotero.Prefs.set('sync.storage.protocol', 'webdav');
Zotero.Prefs.set('sync.storage.scheme', 'https');
Zotero.Prefs.set('sync.storage.url', 'webdav.example.org');
Zotero.Prefs.set('sync.storage.username', 'alex');
Zotero.Prefs.set('sync.storage.verified', false);

ctl.clearCachedCredentials();
await ctl.setPassword(PASSWORD);          // async — see below
ctl._rootURI = false; ctl._parentURI = false;   // force a rebuild
await ctl._init();

try { await ctl.checkServer(); Zotero.Prefs.set('sync.storage.verified', true); }
catch (e) {
  if (e.error === 'ZOTERO_DIR_NOT_FOUND') {  // exactly where the UI asks "create it?"
    await ctl._createServerDirectory();
    await ctl.checkServer();
    Zotero.Prefs.set('sync.storage.verified', true);
  } else throw e;
}
```

- **`getPassword()`/`setPassword()` are `async`.** Without `await`, `ctl.getPassword() === pw`
  compares a Promise to a string and is **always false** — with no error to warn you. The
  password itself lives in the login manager (origin `chrome://zotero`), not in `prefs.js`.
- **`ctl.rootURI` throws `"rootURI not set"` until `_init()` has run**, and `_init()` needs the
  username *and* password already stored — it builds the URI with the credentials inside. So a
  bare read of `rootURI` right after changing prefs blows up; that error usually means "you
  called it too early", not "the config is wrong".
- **`checkServer()` is the *Verify Server* button.** It throws a `VerificationError` whose
  `.error` is a code (`NO_URL`, `NO_USERNAME`, `NO_PASSWORD`, `INVALID_URL`,
  `ZOTERO_DIR_NOT_FOUND`); read `e.error`, not the message.

### The step everyone forgets: reset the file sync history

Zotero tracks per-attachment sync state, so after pointing at a **new** server it still believes
those files are uploaded — they are, but to the *old* one. The new server then stays nearly
empty and **nothing reports an error**.

```js
const L = Zotero.Sync.Storage.Local;
await L.resetAllSyncStates(Zotero.Libraries.userLibraryID);   // libraryID is required
```

This is *Settings → Sync → Reset → Reset File Sync History*. It only flips every imported
attachment to `SYNC_STATE_TO_UPLOAD` (= 0); it touches no file on disk. Check the result:

```js
return await Zotero.DB.queryAsync(
  "SELECT syncState, COUNT(*) n FROM itemAttachments JOIN items USING (itemID) "
  + "WHERE libraryID=? GROUP BY syncState", [Zotero.Libraries.userLibraryID]);
// 0 TO_UPLOAD · 1 TO_DOWNLOAD · 2 IN_SYNC · 3 FORCE_UPLOAD · 4 FORCE_DOWNLOAD · 5 IN_CONFLICT
```

**Migrating servers never deletes anything from the old one**, so the previous backend stays as
a frozen snapshot you can fall back to — and going back is the same recipe with the old URL.
Attachments added *after* the switch exist only on the new server.

### Running the sync

```js
Zotero.Sync.Runner.sync({background: false});   // NO await — it can run for hours
return "sync started";
```

`await`ing it would hold the bridge request open for the whole upload and time out. Watch
progress on the server side (file count / bytes), not from `exec`. A full re-upload is
resumable: files already up move to `IN_SYNC` and are skipped on the next run.

**Two limits worth knowing before proposing WebDAV to anyone**: it stores files for the
**personal library only** (group-library attachments require paid Zotero Storage), and it never
replaces zotero.org for metadata.
