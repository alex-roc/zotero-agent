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
  pages and OCR them so they can be searched and read. Also use it when the user
  wants to know where their library's disk space goes or to reclaim it: shrink
  oversized PDFs, and drop orphan attachments and saved page snapshots. Requires
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
zot disk                                                # where the attachment GBs are
zot toc show|scan <key>                                 # a PDF's table of contents
```

Editing & organizing (these are **writes** — see safety below):

```bash
zot add doi|isbn|arxiv <id> [--pdf] [--collection C]    # import by identifier
zot add isbn <id> --check-duplicate                     # refuse if already there
zot attach <key> --file <path> | --url <url> [--link]   # attach to an existing item
zot pdf-fetch <key…> | --collection C                   # find an open-access PDF
zot dedupe [--by title|doi|content] [--plan f] [--merge] # find duplicates; plan a merge
zot merge --from plan.jsonl                             # execute a merge plan (NOT undoable)
zot tag add|rm <tag> <key…>   |   tag rename <old> --new <n>   |   tag purge
zot set <field> <value> <key…>                          # edit a field
zot move <collection> <key…>                            # add items to a collection
zot collection <name> [--parent K]                      # create a (sub)collection
zot note <key> --file note.html [--if-not-exists]       # add a child note
zot toc set|auto|clear <key> [--from f] [--dry-run]     # write a PDF's outline
zot pdf-prep <key…> | --collection C [--dry-run]        # split + OCR a scan
zot shrink <key…> | --min-mb N [--dry-run]              # downsample fat PDFs in place
zot gc [--orphans] [--snapshots] [--empty-trash]        # drop what nothing points at
```

Batch / higher-level (all **undoable** except merges — see safety below):

```bash
zot apply edits.jsonl [--dry-run]     # declarative batch edit; see below
zot undo last | <op-id> | list        # restore a prior apply/enrich
zot enrich --field doi|date|abstract --source crossref|openalex [--dry-run]
zot tag normalize [--map old_new.csv] [--dry-run]   # fold case/space tag variants
zot dedupe --by title --fuzzy         # near-duplicate titles (Levenshtein)
zot dedupe --by content               # items sharing a file, whatever their titles
zot tag from-collections --rules r.json [--out f|--apply]  # tags from the folder tree
```

`zot apply` is the batch primitive: each JSONL line is
`{"key":"ABCD1234","set":{"date":"2021"},"addTags":["ml"],"removeTags":[],"addToCollection":"Name","trash":false}`.
It snapshots the affected items first, so `zot undo` can restore them (a merge is
**not** reversible). This is how you do LLM-assisted bulk edits: *you* decide the
values, write the JSONL, and `zot apply` writes them — the CLI never calls an LLM.

`zot missing` uses the reliable `getField` check, not the empty-string search
condition (which silently returns 0 — see recipes.md). Use `exec` only for
operations these commands don't cover.

**`enrich` verifies before it writes — trust it, but read what it rejects.**
Crossref and OpenAlex always answer, and the answer used to be written as-is: on
a real library, 6 of 6 sampled proposals were different works ("Mujeres libres en
política" → a Brill human-rights dataset). Now every search hit must clear three
independent signals — title similarity ≥ 0.92 (`--min-similarity` to move it),
year within ±1 when both are known, and the item's first-author surname among the
candidate's authors. An item with **no year and no author** needs 0.98, because
title similarity is then the only evidence: at 0.94 the check accepted "The OECD
Going Digital Measurement Roadmap" as the *2026* edition of itself.

**A fourth signal, added after a measured failure: the title has to be able to
identify a work at all.** On items created from PDF filenames, titles like
"deposito", "vermis" and "Esbozo" matched real Crossref records at similarity
**1.000** — perfect matches against entirely different works. No similarity
threshold can catch that, so `verify` now rejects a vague title (fewer than four
significant words) with the reason `vague-title` unless another signal actually
corroborated it. Two subtleties that cost a wrong DOI each: a surname does not
corroborate a title that *is* that surname ("Marias" by Marías), and a year only
corroborates when **both sides** have one — an item's 1980 proves nothing against
a candidate that declares no date. `enrich` also skips the network call entirely
for those, so a library full of filename-derived titles no longer burns requests.

Expect a high rejection rate — 418 of 638 on a real run — and read the
`Rejected N candidate(s): title 380, year 26, author 12` line as the feature
working, not as a failure. Items that **already have a DOI** skip the guessing
entirely: `enrich` looks them up by that DOI, which is exact.

```bash
zot enrich --field abstract --dry-run     # shows the matched title + similarity
zot enrich --field doi --min-similarity 0.95   # stricter still
```

**Duplicates: propose, review, then merge.** `Zotero.Items.merge` cannot be
undone, and grouping by title alone is wrong more often than right — on a real
library 20 of 46 groups were distinct works (five different *Estadística*
textbooks by Spiegel and Triola; the 3rd and 4th editions of Scott). So `dedupe`
scores each group and only calls it *confident* when nothing contradicts it.

An **identifier decides first, in both directions**: two records carrying the
same ISBN or DOI are one work even if their years fight (Taylor and Bogdan 1992
and 1996 share an ISBN because one is the reprint; an ISBN-10 and its ISBN-13
count as one number), and two carrying *different* ones are two works even when
everything else matches — Hull's "The Effect of Essentialism on Taxonomy" parts
(I) and (II) agree on author, year and nearly the whole title.

Then what no identifier can override: same author (compared by containment, so
"Banda" matches "Banda, Juan M.") and no two different *formal* item types — a
thesis and the journal article drawn from it stay separate, while webpage/blogPost
pairs are treated as one thing imported twice.

Then the title, which is the weakest signal of all. **The hard case is the
deliberate parallel**: same author, same year, same publisher, one word apart. A
title differing only by a **numeral** is a series — the fuzzy axis was otherwise
proposing to merge the six volumes of Gramsci's *Cuadernos de la cárcel* into one
item. A title differing by a **real word** is another work: "para el profesorado"
against "para el estudiantado", "Hacktivism" against "Hacktivismo". These two
only fire where they can help — on `--by title` the titles are identical by
construction, and on `--by content` they stand down, since there the titles are
expected to disagree. Last come edition and year, unless an identifier already
spoke.

The cost is one-directional and deliberate: a real duplicate whose titles differ
by a word lands in review instead of confident. Merging cannot be undone; a
second look can.

```bash
zot dedupe                          # groups, flagged ⚠ with the reason
zot dedupe --plan merges.jsonl      # a reviewable plan: delete the lines you reject
zot merge --from merges.jsonl       # execute what survived (NOT undoable)
zot dedupe --merge                  # confident groups only; --force for the rest
```

The plan carries what you need to decide — edition, publisher, creators, ISBN,
PDF and note counts — because key/title/year alone is exactly what is not enough.

**`--by content` finds the duplicates a title never will.** Two items holding the
same file are the same work even when their titles have nothing in common, and
that is the usual shape of the problem: on one library all 19 hits had one record
titled after the *filename* — `2-1-8160`, `Game Programming Patterns (Robert
Nystrom) z-lib.sk)` — which is what a record created from a filename looks like.
Because the records disagree about everything, this axis picks the master by
**metadata richness** (identifier, author, year; a filename-looking title is
penalised) instead of by age: the stub is often the older of the two. Choosing a
master that lacks the PDF is safe — Zotero keeps the attachments of everything it
absorbs.

Two things this axis does differently. The year and the edition stop vetoing,
because the shared file already settles that it is one document: Taylor and
Bogdan 1992 and 1996 share an ISBN and a file, and one is the reprint. The author
and type checks stay, because *those* are what the real false positive looks
like — **a shared file is not always a duplicate.** A chapter filed with its
whole book (Dussel inside Lander's *La colonialidad del saber*), a journal issue
holding several articles, one cover image attached to four papers: all of these
share bytes and none should be merged. Expect them as ⚠ and read the plan.

Hashing a whole library inside one bridge call would time out, so size comes
first and md5 runs only where two files already agree on their exact byte count —
24 hashes out of 2,340 files on a 16 GB library.

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
- **`pdf-prep` is for OCR; `zot shrink` is for weight.** They were one command
  and it lied: with `--no-ocr` and nothing to split, prep copied the file byte for
  byte (150.6 MB → 150.6 MB) and attached the copy, because ocrmypdf's optimiser
  only runs during an OCR pass. That path now reports `nothing-to-do` and points
  at `shrink`, which downsamples the page images with Ghostscript while leaving
  the text layer and the page count alone — so Zotero's annotations still anchor.

  ```bash
  zot disk                              # what the store weighs, and where
  zot shrink --min-mb 25 --dry-run      # candidates, with the measured gain
  zot shrink ABCD1234                   # one item, replaced in place
  ```

  **Both verdicts are recorded, so a sweep is cheap to repeat.** Shrinking is
  lossy — downsampling something already downsampled re-encodes it — so rewritten
  files get a `shrunk` tag. Files that came back no smaller get `shrink-nogain`,
  because finding that out costs the same Ghostscript minutes as a success: on one
  library 126 of 194 files did not compress, and an unmarked re-run would spend
  those hours again to reach the same answer. Later sweeps skip both and say so
  (`--force` overrides, and means it). A timeout or an unreadable file is *not*
  recorded — those might work next time. Sweep one band at
  a time with `--min-mb`/`--max-mb`: the fat tail is where the obvious wins are,
  but the middle of the distribution holds more total bytes — on one library the
  13 files over 50 MB were 1.09 GiB while the 201 files of 10-20 MB were 2.70 GiB.

  200 dpi is the default because it is the measured sweet spot for scanned books:
  about a fifth of the original, still legible down to pencil marginalia. The
  result is only kept when the page count survives and the file is ≤80% of the
  original, so a run over 35 real books shrank 13 and left 22 untouched. Nothing
  is lost by trying. Needs `ghostscript` and `qpdf`.

- **`zot gc` removes what nothing points at**: page snapshots (the item keeps its
  URL) and *unclaimed* attachments. Be precise about that second one — **a
  parentless attachment is not junk.** Zotero lists it as an item like any other,
  and dragging a PDF in without metadata is how half a library gets built: on a
  real library all 268 parentless attachments were filed in collections and were
  books, 1.1 GB of them. `--orphans` therefore only takes attachments that
  *nothing* claims — no parent, no collection, no tags, no annotations — and
  reports how many it kept. Attachments carrying highlights are never binned,
  because annotations belong to the attachment and do not survive it.

  Space comes back only once the trash is emptied: `zot gc --empty-trash` is
  permanent, so `zot backup` first. Snapshots are the safe, high-yield target —
  989 of them were 1 GB on that library — but check the parent still has its URL,
  since a snapshot is your only copy if the page has rotted away.

- **`zot tag from-collections --rules rules.json`** harvests the meaning already
  encoded in the folder tree, which is where a pre-tagging library keeps it. The
  rules file is `{"containers": [...], "rules": [{"match": regex, "tags": [...]}]}`;
  matching is case- and accent-insensitive. **Put every structural branch in
  `containers`** — root folders, "Articulos", "Z. Archivo" — or the top of the
  tree shouts over everything under it: with the root branch counted, one run
  tagged 1318 of 3019 items `#digitalización`, a label that separates nothing.
  The command warns when a tag covers more than 40% of the library. Use `--out`
  for a reviewable plan, `--apply` to write it undoably.
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
