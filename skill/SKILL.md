---
name: zotero
description: >-
  Control a local Zotero library programmatically — search, read, create, edit,
  tag, organize into collections, delete, and export items — via the `zot` CLI
  (read API + the zotero-exec write endpoint). Use whenever the user wants to
  query or modify their Zotero library, batch-edit references, manage tags or
  collections, find items missing metadata (no abstract/date/DOI), find
  duplicates, export citations, or run arbitrary Zotero JS. Also use it to read
  or ask questions about an item's PDF, summarize a document at multiple levels
  (whole/chapter/section), read a PDF's highlights/annotations, or create notes
  on items. Requires the zotero-exec plugin installed and Zotero running.
---

# Zotero control (via the `zot` CLI)

You control a running Zotero instance through **`zot`**, a stdlib-only Python CLI.

- **Reads** go through Zotero's local HTTP API (fast, GET-only).
- **Writes** go through the `zotero-exec` plugin: `zot exec` runs arbitrary
  privileged Zotero JS in-process. This is the only complete local write path
  (Zotero's HTTP API is read-only by design; see `references/setup.md`).

`zot` is on `PATH` after install, or run `scripts/zot` from this skill.

## First: confirm the setup is live

Run `zot ping`. It must show the local API up, the zotexec endpoint answering
`1+1 == 2`, and a known userID. If anything fails, point the user to
`references/setup.md` — do **not** try to work around a missing plugin.

## Reading (prefer the fast API)

```bash
zot search "bolivia" --limit 25        # full-text search
zot search "x" --tag "#digitalización" # filter by tag
zot search "x" --item-type book        # filter by type
zot get <ITEMKEY>                       # one item's fields
zot pdf <ITEMKEY>                       # local path(s) of the item's PDF(s)
zot collections                         # key, #items, name
zot tags                                # #items, tag
```

Add `--json` to any read command for machine-readable output.

## Writing (via `zot exec`)

`zot exec` sends JavaScript to the plugin. The code is an **async function
body** with `Zotero` (and `ZoteroPane`, `window` when a UI window exists) in
scope. `return` a value to get it back as JSON.

Three ways to pass code:

```bash
zot exec 'return Zotero.Users.getCurrentUserID();'   # inline
zot exec script.js                                    # from a file
echo 'return 1+1;' | zot exec -                       # from stdin
```

For anything non-trivial, **write the JS to a file** in the scratchpad and run
`zot exec file.js` — easier to review and re-run than inline quoting.

The full, canonical recipe book (create/edit items, collections, tags, delete,
attachments, search conditions, bulk transactions, export, duplicates) is in
**`references/recipes.md`**. Read it before composing write operations.

## PDFs: answer questions, summarize, save notes

When the user wants to ask about an item's PDF, summarize a book/chapter/section,
or save a summary back into Zotero, read **`references/pdf-and-notes.md`**. The
short version:

- `zot pdf <ITEMKEY>` prints the PDF's local path. **Read that file directly**
  with your PDF-reading tool (it takes page ranges — read only what you need).
- For long documents, summarize **bottom-up** (section → chapter → whole) so each
  step fits in context; keep page references.
- Fold in the user's existing highlights (`pdf.getAnnotations()`) — they mark
  what matters to them.
- Save results as a **child note** (`new Zotero.Item('note')` → `setNote(html)`
  → `parentID` → `saveTx()`), not as PDF annotations (writing highlights needs
  fragile coordinate math). Notes are reversible (trash, not erase).

## Safe workflow for bulk / destructive operations

Arbitrary JS = full power over the library. Before any batch write or deletion:

1. **Back up** `zotero.sqlite` (tell the user the path from `zot exec 'return Zotero.DataDirectory.dir;'`).
2. **Disable auto-sync** in Zotero → Preferences → Sync (so a mistake doesn't propagate).
3. **Dry-run first**: run a read-only version that returns the count and a few
   sample titles of what *would* change, and show it to the user.
4. Apply to **1–2 items** and verify before running on the full set.
5. Use `Zotero.DB.executeTransaction()` for large batches (see recipes).
6. Deletions: prefer the trash (`item.deleted = true; saveTx()`), not
   `eraseTx()`, unless the user explicitly wants permanent removal.
7. Re-enable sync when done.

When in doubt about scope, confirm with the user before writing.

## Output discipline

Return structured data (`JSON.stringify(...)`) from exec when the user wants
data; return a short summary string when they want a confirmation. Don't dump
whole-library exports into chat — write large results to a file.
