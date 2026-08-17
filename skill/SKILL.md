---
name: zotero
description: >-
  Control a local Zotero library programmatically — search, read, create, edit,
  tag, organize into collections, delete, and export items — via the `zot` CLI
  (read API + the zotero-agent bridge write endpoint). Use whenever the user wants to
  query or modify their Zotero library, batch-edit references, manage tags or
  collections, find items missing metadata (no abstract/date/DOI), find
  duplicates, export citations, or run arbitrary Zotero JS. Also use it to add
  items by DOI/ISBN/arXiv, find and merge duplicates, edit fields/tags in bulk,
  get library stats, format bibliographies, read or ask questions about an
  item's PDF, summarize a document at multiple levels (whole/chapter/section),
  read a PDF's highlights/annotations, generate a PDF's table of contents /
  bookmarks / outline so Zotero's reader can navigate it, or create notes on
  items. Also use it to prepare scanned PDFs: split two-up scans into single
  pages, OCR them so they can be searched and read, and shrink them. Requires
  the zotero-agent bridge plugin installed and Zotero running.
---

# Zotero control (via the `zot` CLI)

You control a running Zotero instance through **`zot`**, a stdlib-only Python CLI.

- **Reads** go through Zotero's local HTTP API (fast, GET-only).
- **Writes** go through the `zotero-agent` bridge plugin: `zot exec` runs arbitrary
  privileged Zotero JS in-process. This is the only complete local write path
  (Zotero's HTTP API is read-only by design; see `references/setup.md`).

`zot` is on `PATH` after install (`uv tool install zotero-agent`,
`brew install alex-roc/tap/zotero-agent`, or the repo's `install.sh`). If the bridge endpoint is not answering, the user must install the
plugin XPI in Zotero — it is published only here (permanent link):
`https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi`
→ *Tools → Plugins → gear → "Install Plugin From File…"*. Do not try to build it.

## First: confirm the setup is live

Run `zot ping`. It must show the local API up, the bridge endpoint answering
`1+1 == 2`, a known userID, and the `zot` version. If anything fails, point the
user to `references/setup.md` — do **not** try to work around a missing plugin.

If Zotero is simply not running, or the plugin needs the restart Zotero keeps
asking for, `zot restart` handles it without the user touching the app — it waits
for the bridge to answer again. It is disruptive, so ask first and then pass
`--yes`: `zot restart --plugin --yes` reloads only the bridge (Zotero stays
open), `zot restart --yes` restarts Zotero, and with Zotero down it starts it.

> Beyond this skill (Claude Code), `zot mcp` exposes the same operations as an
> MCP server for Claude Desktop, Codex CLI, Gemini CLI and Cursor. See the repo's
> `docs/` and website for per-client setup; the safety rules below apply equally.

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
the abstract-search one). Reads/analysis:

```bash
zot export <collection|name> --format json|csv|csljson|bibtex|biblatex|ris [--out f]
zot export <collection|name> --recursive                # + items in subcollections
zot missing abstract|date|doi|url [--collection KEY]   # items lacking a field
zot author "Ojeda"                                      # items by an author
zot stats                                               # library analytics
zot recent [--limit N]                                  # recently added
zot bib <key…|@citekey…> --style apa                    # formatted bibliography
zot annotations <key> [--to-note]                       # PDF highlights (opt. → note)
zot related <key>                                       # related items
zot notes <key>                                         # list an item's notes
zot lint                                                # data-quality report
zot toc show|scan <key>                                 # a PDF's table of contents
```

Editing & organizing (these are **writes** — see safety below):

```bash
zot add doi|isbn|arxiv <id> [--pdf] [--collection C]    # import by identifier
zot add isbn <id> --check-duplicate                     # refuse if already there
zot attach <key> --file <path> | --url <url> [--link]   # attach to an existing item
zot pdf-fetch <key…> | --collection C                   # find an open-access PDF
zot dedupe [--collection C] [--merge]                   # find/merge duplicates
zot tag add|rm <tag> <key…>   |   tag rename <old> --new <n>   |   tag purge
zot set <field> <value> <key…>                          # edit a field
zot move <collection> <key…>                            # add items to a collection
zot collection <name> [--parent K]                      # create a (sub)collection
zot note <key> --file note.html [--if-not-exists]       # add a child note
zot toc set|auto|clear <key> [--from f] [--dry-run]     # write a PDF's outline
zot pdf-prep <key…> | --collection C [--dry-run]        # split/OCR/shrink a scan
```

Batch / higher-level (all **undoable** except merges — see safety below):

```bash
zot apply edits.jsonl [--dry-run]     # declarative batch edit; see below
zot undo last | <op-id> | list        # restore a prior apply/enrich
zot enrich --field doi|date|abstract --source crossref|openalex [--dry-run]
zot tag normalize [--map old_new.csv] [--dry-run]   # fold case/space tag variants
zot dedupe --by title --fuzzy         # near-duplicate titles (Levenshtein)
```

`zot apply` is the batch primitive: each JSONL line is
`{"key":"ABCD1234","set":{"date":"2021"},"addTags":["ml"],"removeTags":[],"addToCollection":"Name","trash":false}`.
It snapshots the affected items first, so `zot undo` can restore them (a merge is
**not** reversible). This is how you do LLM-assisted bulk edits: *you* decide the
values, write the JSONL, and `zot apply` writes them — the CLI never calls an LLM.

`zot missing` uses the reliable `getField` check, not the empty-string search
condition (which silently returns 0 — see recipes.md). Use `exec` only for
operations these commands don't cover.

**One item shape.** Every command that emits items in `--json` uses the same flat
record — `key, citekey, type, title, date, year, creators, venue, doi, url, tags,
abstract` — whether it reads through the HTTP API or the bridge. `get`, `search`
and `recent` take `--raw` when you specifically want Zotero's own wire format
(`{data:{itemType, DOI, citationKey}}`); everything else should use the flat one.

**Collections are not recursive.** `zot export C` and `zot missing --collection C`
see only the items filed directly in C — a collection whose items all live in
subcollections looks empty. Pass `--recursive` to `export` when that matters.

**Bibliographies: use `zot export --format biblatex`.** It goes through Zotero's
native exporter. Better BibTeX keeps a separate export cache that can hold stale
citekeys and is not invalidated by regenerating keys or restarting Zotero, so
anything routed through BBT's `item.export` may disagree with `zot get`.

**Global flags** (all commands): `--json` (machine output), `-q/--quiet`,
`--debug`, `--yes` (confirm writes non-interactively), and config overrides
`--base/--token/--user-id` (or `ZOTERO_AGENT_*` env). **Exit codes:** 0 ok, 1 error,
2 connection/exec, 3 not-found, 4 config. For big `--json` reads, note that
`author`/`missing` omit abstracts by default (`--detail full` to include them).

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
- To make a PDF navigable in Zotero's **Outline** tab, `zot toc scan <ITEMKEY>
  --json` hands you the evidence, you decide the hierarchy, and `zot toc set
  <ITEMKEY> --from -` writes it. Prefer the book's own contents page over
  typographic guessing, and never invent page numbers — the same reference file
  has the full procedure. Needs the `[toc]` extra.
- **If the PDF has no text layer, there is nothing to read.** `zot pdf-prep
  <ITEMKEY> --dry-run` says so in one line, and without `--dry-run` fixes it:
  two-up scans are split into single pages, OCR adds the text layer, and the
  file shrinks. Run it *before* `zot toc`, before summarizing, and before any
  question about the document's content — those all depend on text existing.
  The processed PDF is attached beside the original and tagged `pdf-prep`, so
  re-running is a no-op; `--prune` trashes the superseded originals afterwards.
  Needs the `[toc]` extra and OCRmyPDF (`zot pdf-prep` prints how to install it).

## Safe workflow for bulk / destructive operations

Arbitrary JS = full power over the library. Before any batch write or deletion:

The write **commands** (`add`, `dedupe --merge`, `set`, `move`, bulk/removing
`tag`, `exec` with detected writes) are safe-by-default: they refuse to run
non-interactively unless you pass `--yes` (and prompt on a TTY). Before a bulk
or destructive run:

1. **Back up** with `zot backup` (snapshots `zotero.sqlite`, prints the path).
   Especially before `zot dedupe --merge`.
2. **Disable auto-sync** in Zotero → Preferences → Sync (so a mistake doesn't propagate).
3. **Dry-run / scope first**: for batch edits prefer **`zot apply edits.jsonl --dry-run`**,
   whose preview runs **no** JS and therefore cannot persist. `zot exec script.js
   --dry-run` still *executes* the script with best-effort write interception — it
   can leak writes on Zotero 7, so it is **not** a guarantee; `zot backup` is.
   Prefer scoping `dedupe`/`missing` to `--collection` over the whole library.
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
