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

Add `--json` to any read command for machine-readable output. Read commands
that list (`search`, `collections`, `tags`) stop at `--limit` and print a
`showing N of M` notice on stderr — pass `--all` to paginate through everything.

### Common operations (prefer these over hand-written `exec`)

These are thin, reliable commands built on the Zotero JS API — reach for them
before writing ad-hoc JS, so you don't re-derive logic (or re-hit gotchas like
the abstract-search one):

```bash
zot export <collection|name> --format json|csv|bibtex|biblatex|ris [--out f]
zot missing abstract|date|doi|url [--collection KEY]   # items lacking a field
zot author "Ojeda"                                      # items by an author
zot notes <ITEMKEY>                                     # list an item's notes
zot note  <ITEMKEY> --file note.html [--dry-run]        # add a child note
zot lint                                                # data-quality report
```

`zot missing` uses the reliable `getField` check, not the empty-string search
condition (which silently returns 0 — see recipes.md). Use `exec` only for
operations these commands don't cover.

### Better BibTeX citekeys

Users often refer to items by their **BBT citekey** (e.g.
`ojedaDigitalizacionSocietalTeorias2025`), not the 8-char Zotero key. `zot get`
and `zot pdf` accept either — a citekey is auto-detected (prefix with `@` to
force it). To resolve a citekey explicitly:

```bash
zot cite <CITEKEY>          # -> Zotero item key, title, PDF path(s)
zot pdf  <CITEKEY>          # PDF path directly (citekey or Zotero key)
zot get  <CITEKEY>          # item fields
```

Resolution goes through Better BibTeX's JSON-RPC, so it needs the BBT plugin
installed (it is, for anyone using citekeys).

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
- Save results with **`zot note <ITEMKEY> --file note.html`** (a child note),
  not as PDF annotations (writing highlights needs fragile coordinate math).
  Notes are reversible (trash, not erase); `zot notes <ITEMKEY>` lists them.

## Safe workflow for bulk / destructive operations

Arbitrary JS = full power over the library. Before any batch write or deletion:

1. **Back up** with `zot backup` (snapshots `zotero.sqlite`, prints the path).
2. **Disable auto-sync** in Zotero → Preferences → Sync (so a mistake doesn't propagate).
3. **Dry-run first**: `zot exec script.js --dry-run` intercepts writes and reports
   what *would* change without persisting; show it to the user. (Best-effort — a
   script that reads back its own new writes may error; the backup is the hard
   guarantee.) For structured commands, `zot note … --dry-run` works too.
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
