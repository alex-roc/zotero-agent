# Command reference

_Auto-generated from the `zot` CLI (v0.8.4) — do not edit by hand; run `python scripts/gen_cli_reference.py`._

Global flags on every command: `--json`, `-q/--quiet`, `--debug`, `--yes`, `--base/--token/--user-id` (or `ZOTERO_AGENT_*`). Exit codes: 0 ok, 1 error, 2 connection/exec, 3 not-found, 4 config.

## Read & analyze

### `zot search`

```
zot search [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--limit LIMIT] [--all]
                  [--item-type ITEM_TYPE] [--tag TAG] [--raw]
                  query
```

| Argument | Description |
|----------|-------------|
| `query` |  |
| `--limit` |  |
| `--all` | fetch all results (paginate) |
| `--item-type` |  |
| `--tag` |  |
| `--raw` | emit the read API's own JSON instead of the shared flat item shape |

### `zot get`

```
zot get [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json] [--raw]
               key
```

| Argument | Description |
|----------|-------------|
| `key` | Zotero item key, or a BBT citekey (prefix @ to force) |
| `--raw` | emit the read API's own JSON instead of the shared flat item shape |

### `zot cite`

```
zot cite [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json]
                citekey
```

| Argument | Description |
|----------|-------------|
| `citekey` |  |

### `zot pdf`

```
zot pdf [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json]
               key
```

| Argument | Description |
|----------|-------------|
| `key` | item/attachment key, or a BBT citekey (prefix @ to force) |

### `zot collections`

```
zot collections [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID]
                       [-q] [--debug] [-y] [--json] [--limit LIMIT] [--all]
```

| Argument | Description |
|----------|-------------|
| `--limit` |  |
| `--all` | fetch all (paginate) |

### `zot tags`

```
zot tags [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json] [--limit LIMIT] [--all]
```

| Argument | Description |
|----------|-------------|
| `--limit` |  |
| `--all` | fetch all (paginate) |

### `zot export`

```
zot export [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json]
                  [--format {json,csv,csljson,bibtex,biblatex,ris}]
                  [--out OUT] [--recursive]
                  collection
```

| Argument | Description |
|----------|-------------|
| `collection` | collection key or name |
| `--format` |  |
| `--out` | write to file instead of stdout |
| `--recursive` | include items in subcollections (default: only items filed directly in this collection) |

### `zot missing`

```
zot missing [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                   [--debug] [-y] [--json] [--collection COLLECTION]
                   [--detail {concise,full}]
                   field
```

| Argument | Description |
|----------|-------------|
| `field` | field or alias: abstract, date, doi, url, publisher, publication |
| `--collection` | limit to a collection (key or name) |
| `--detail` | full keeps abstracts |

### `zot author`

```
zot author [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--detail {concise,full}]
                  name
```

| Argument | Description |
|----------|-------------|
| `name` |  |
| `--detail` | full keeps abstracts |

### `zot stats`

```
zot stats [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                 [--debug] [-y] [--json]
```

### `zot recent`

```
zot recent [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--limit LIMIT] [--raw]
```

| Argument | Description |
|----------|-------------|
| `--limit` |  |
| `--raw` | emit the read API's own JSON instead of the shared flat item shape |

### `zot bib`

```
zot bib [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json] [--style STYLE] [--linkwrap]
               [--out OUT]
               keys [keys ...]
```

| Argument | Description |
|----------|-------------|
| `keys` | item keys or citekeys |
| `--style` | CSL style id (e.g. apa, chicago-note-bibliography) |
| `--linkwrap` |  |
| `--out` |  |

### `zot annotations`

```
zot annotations [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID]
                       [-q] [--debug] [-y] [--json] [--to-note]
                       [--samples SAMPLES]
                       key
```

| Argument | Description |
|----------|-------------|
| `key` |  |
| `--to-note` | write annotations into a child note |
| `--samples` |  |

### `zot related`

```
zot related [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                   [--debug] [-y] [--json]
                   key
```

| Argument | Description |
|----------|-------------|
| `key` |  |

### `zot notes`

```
zot notes [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                 [--debug] [-y] [--json]
                 key
```

| Argument | Description |
|----------|-------------|
| `key` |  |

### `zot lint`

```
zot lint [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json] [--samples SAMPLES]
```

| Argument | Description |
|----------|-------------|
| `--samples` | examples to show per issue |

## Edit & organize

### `zot add`

```
zot add [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json] [--pdf] [--collection COLLECTION]
               [--check-duplicate]
               {doi,isbn,arxiv} identifier
```

| Argument | Description |
|----------|-------------|
| `kind` |  |
| `identifier` |  |
| `--pdf` | also try to attach an open-access PDF |
| `--collection` | add to this collection (key or name) |
| `--check-duplicate` | refuse to add if a close title+author match is already in the library |

### `zot dedupe`

```
zot dedupe [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--by {title,doi,content}]
                  [--collection COLLECTION] [--plan FILE] [--merge] [--force]
                  [--fuzzy] [--threshold THRESHOLD] [--samples SAMPLES]
```

| Argument | Description |
|----------|-------------|
| `--by` | what makes two items the same: their title, their DOI, or the file they share ('content' finds the ones whose titles do not resemble each other) |
| `--collection` | limit to a collection (key or name); else whole library |
| `--plan` | write the merge plan as JSONL for review, then run `zot merge --from FILE` |
| `--merge` | merge the confident groups now (master is the oldest item, or the best-documented one with --by content); NOT undoable |
| `--force` | with --merge, also merge groups whose author/year/edition disagree |
| `--fuzzy` | also group near-identical titles (Levenshtein); title axis only |
| `--threshold` | similarity threshold for --fuzzy (0-1) |
| `--samples` |  |

### `zot tag`

```
zot tag [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json] [--new NEW] [--map MAP] [--rules RULES]
               [--out FILE] [--apply] [--dry-run] [--samples SAMPLES]
               {add,rm,rename,purge,normalize,from-collections} [tag]
               [keys ...]
```

| Argument | Description |
|----------|-------------|
| `action` |  |
| `tag` | the tag (for add/rm/rename) |
| `keys` | item keys/citekeys (for add/rm; '-' reads stdin) |
| `--new` | new tag name (for rename) |
| `--map` | CSV old,new mapping file (for normalize) |
| `--rules` | JSON rules file (for from-collections): {containers:[...], rules:[{match, tags}]} |
| `--out` | write the plan as JSONL for `zot apply` (for from-collections) |
| `--apply` | write the tags now, undoably (for from-collections) |
| `--dry-run` | preview (for normalize / from-collections) |
| `--samples` |  |

### `zot set`

```
zot set [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json]
               field value keys [keys ...]
```

| Argument | Description |
|----------|-------------|
| `field` | field or alias (e.g. abstract, publisher, date) |
| `value` |  |
| `keys` | item keys/citekeys ('-' reads stdin) |

### `zot move`

```
zot move [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json]
                collection keys [keys ...]
```

| Argument | Description |
|----------|-------------|
| `collection` |  |
| `keys` | item keys/citekeys ('-' reads stdin) |

### `zot collection`

```
zot collection [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID]
                      [-q] [--debug] [-y] [--json] [--parent PARENT]
                      name
```

| Argument | Description |
|----------|-------------|
| `name` |  |
| `--parent` | parent collection (key or name) |

### `zot note`

```
zot note [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json] [--file FILE] [--text TEXT]
                [--if-not-exists] [--dry-run]
                key
```

| Argument | Description |
|----------|-------------|
| `key` |  |
| `--file` | read note body (HTML or text) from a file |
| `--text` | note body as a string |
| `--if-not-exists` | skip if an identical note already exists (idempotent) |
| `--dry-run` | show what would be added, don't write |

## PDF outlines

### `zot toc`

```
zot toc [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json] [--from FILE] [--attachment ATTACHMENT]
               [--dry-run] [--max-level MAX_LEVEL] [--offset OFFSET]
               [--backup] [--mark-for-sync] [--cap CAP] [--samples SAMPLES]
               {show,scan,set,auto,clear} key
```

| Argument | Description |
|----------|-------------|
| `action` | show the embedded outline, scan for evidence, set one from a file, build one automatically, or remove it |
| `key` | item/attachment key, or a BBT citekey (prefix @ to force) |
| `--from` | outline to write (for set); '-' reads stdin. Text or JSON. |
| `--attachment` | attachment key, when the item has several PDFs |
| `--dry-run` | preview the outline; don't touch the file |
| `--max-level` | deepest nesting level to keep (default 4) |
| `--offset` | force printed-page → physical-page delta instead of detecting it |
| `--backup` | copy the untouched PDF into ~/.local/state/zotero-agent first |
| `--mark-for-sync` | tell Zotero to re-upload the file on the next sync |
| `--cap` | max heading candidates in a scan |
| `--samples` | rows to print per section of a scan |

## Batch (undoable)

### `zot apply`

```
zot apply [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                 [--debug] [-y] [--json] [--dry-run] [--samples SAMPLES]
                 file
```

| Argument | Description |
|----------|-------------|
| `file` | JSONL file, or '-' for stdin |
| `--dry-run` | preview writes, don't persist |
| `--samples` |  |

### `zot undo`

```
zot undo [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json] [--keep]
                [op]
```

| Argument | Description |
|----------|-------------|
| `op` | op id, 'last' (default), or 'list' |
| `--keep` | don't delete the snapshot after undo |

### `zot enrich`

```
zot enrich [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] --field {doi,date,abstract}
                  [--source {crossref,openalex}] [--collection COLLECTION]
                  [--limit LIMIT] [--delay DELAY]
                  [--min-similarity MIN_SIMILARITY] [--dry-run]
                  [--samples SAMPLES]
```

| Argument | Description |
|----------|-------------|
| `--field` |  |
| `--source` |  |
| `--collection` | limit to a collection (key or name) |
| `--limit` | cap items looked up (0 = no cap) |
| `--delay` | seconds between API calls (be polite) |
| `--min-similarity` | title-similarity floor for accepting a search hit (0-1); items with no year and no author need 0.98 regardless |
| `--dry-run` | preview, don't write |
| `--samples` |  |

## Setup & escape hatch

### `zot ping`

```
zot ping [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json]
```

### `zot init`

```
zot init [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json]
```

### `zot skill`

```
zot skill [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                 [--debug] [-y] [--json] [--dest DEST] [--project] [--force]
                 [--link]
                 {install,path,agents-md}
```

| Argument | Description |
|----------|-------------|
| `action` | install it, print the bundled source path, or print AGENTS.md to stdout |
| `--dest` | install here (default: ~/.claude/skills/zotero) |
| `--project` | install into ./.claude/skills/zotero (this project only) |
| `--force` | replace an existing install |
| `--link` | symlink the source instead of copying (dev checkout) |

### `zot backup`

```
zot backup [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--dir DIR]
```

| Argument | Description |
|----------|-------------|
| `--dir` | destination dir (default: ~/.config/zotero-agent/backups) |

### `zot sync`

```
zot sync [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json]
```

### `zot restart`

```
zot restart [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                   [--debug] [-y] [--json] [--plugin] [--no-launch]
                   [--timeout TIMEOUT]
```

| Argument | Description |
|----------|-------------|
| `--plugin` | reload only the zotero-agent plugin, leaving Zotero running |
| `--no-launch` | never start the Zotero app; only act on a running one |
| `--timeout` | seconds to wait for the bridge to answer again (default: 90) |

### `zot exec`

```
zot exec [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json] [--dry-run]
                source
```

| Argument | Description |
|----------|-------------|
| `source` |  |
| `--dry-run` | intercept writes and report what would change (best-effort) |

### `zot mcp`

```
zot mcp [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json] [--allow-exec]
```

| Argument | Description |
|----------|-------------|
| `--allow-exec` | expose the run_javascript tool (arbitrary JS) |

### `zot completion`

```
zot completion [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID]
                      [-q] [--debug] [-y] [--json]
                      {bash,zsh,fish}
```

| Argument | Description |
|----------|-------------|
| `shell` |  |

## Other

### `zot pdf-prep`

```
zot pdf-prep [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID]
                    [-q] [--debug] [-y] [--json] [--collection COLLECTION]
                    [--attachment ATTACHMENT] [--split {auto,always,never}]
                    [--gutter GUTTER] [--overlap OVERLAP] [--single PAGES]
                    [--rtl] [--ocr LANG] [--no-ocr]
                    [--profile {balanced,quality,small}] [--rotate]
                    [--title TITLE] [--out DIR] [--replace] [--prune]
                    [--trash-annotated] [--force] [--timeout TIMEOUT]
                    [--dry-run]
                    [keys ...]
```

| Argument | Description |
|----------|-------------|
| `keys` | item keys or BBT citekeys ('-' reads stdin) |
| `--collection` | process every item in a collection (key or name) |
| `--attachment` | attachment key, when the item has several PDFs |
| `--split` | split two-up scans into one page per leaf (default: auto-detect) |
| `--gutter` | force the cut as a fraction of page width (0.5 = middle) |
| `--overlap` | extra width each half keeps past the cut (default 0.008) |
| `--single` | pages to leave whole, e.g. '1,2,147' (covers, fold-outs) |
| `--rtl` | right-to-left book: right half first |
| `--ocr` | tesseract languages (default: from the item's language field) |
| `--no-ocr` | split and optimise only; leave the file without a text layer |
| `--profile` | balanced (default), quality (300 dpi OCR, bigger), or small |
| `--rotate` | let OCR fix sideways pages |
| `--title` | title for the new attachment (default: 'PDF (OCR)') |
| `--out` | write the result to a directory instead of attaching it |
| `--replace` | trash the original attachment once the new one is attached |
| `--prune` | trash originals superseded by an earlier run; processes nothing |
| `--trash-annotated` | also trash originals carrying highlights (they do NOT follow the new file — Zotero ties them to the attachment) |
| `--force` | reprocess items already prepared |
| `--timeout` | seconds to allow OCR per item |
| `--dry-run` | analyse and report the plan; touch nothing |

### `zot merge`

```
zot merge [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                 [--debug] [-y] [--json] --from FILE [--dry-run]
                 [--samples SAMPLES]
```

| Argument | Description |
|----------|-------------|
| `--from` | JSONL merge plan, or '-' for stdin |
| `--dry-run` | preview, don't merge |
| `--samples` |  |

### `zot attach`

```
zot attach [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--file FILE] [--url URL] [--link]
                  [--title TITLE]
                  key
```

| Argument | Description |
|----------|-------------|
| `key` | item key, or a BBT citekey (prefix @ to force) |
| `--file` | local file to import as an attachment |
| `--url` | URL to attach (a snapshot unless --link) |
| `--link` | store the URL as a link, not a snapshot |
| `--title` | attachment title (defaults to Zotero's) |

### `zot pdf-fetch`

```
zot pdf-fetch [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID]
                     [-q] [--debug] [-y] [--json] [--collection COLLECTION]
                     [--retry-with-pdf]
                     [keys ...]
```

| Argument | Description |
|----------|-------------|
| `keys` | item keys or BBT citekeys; '-' reads them from stdin |
| `--collection` | every item in a collection (key or name) |
| `--retry-with-pdf` | also try items that already have a PDF attached |

### `zot disk`

```
zot disk [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                [--debug] [-y] [--json] [--min-mb MIN_MB] [--samples SAMPLES]
```

| Argument | Description |
|----------|-------------|
| `--min-mb` | threshold for listing heavy PDFs (default 25) |
| `--samples` |  |

### `zot shrink`

```
zot shrink [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--min-mb MIN_MB] [--max-mb MAX_MB]
                  [--force] [--dpi DPI] [--mono-dpi MONO_DPI]
                  [--max-ratio MAX_RATIO] [--out DIR] [--timeout TIMEOUT]
                  [--dry-run]
                  [keys ...]
```

| Argument | Description |
|----------|-------------|
| `keys` | item or attachment keys/citekeys ('-' reads stdin); omit to sweep everything over --min-mb |
| `--min-mb` | with no keys, shrink every PDF at least this big (default 25) |
| `--max-mb` | with no keys, stop at this size — lets you sweep one band at a time |
| `--force` | re-examine files already tagged 'shrunk' or 'shrink-nogain' (re-shrinking is lossy: it re-encodes them again) |
| `--dpi` | target resolution for colour/grey images (default 200) |
| `--mono-dpi` | target resolution for bitonal images (default 300) |
| `--max-ratio` | keep the original unless the rewrite is at most this fraction of its size (default 0.80) |
| `--out` | write results to DIR instead of replacing in place |
| `--timeout` | seconds to allow per file |
| `--dry-run` | report the plan, touch nothing |

### `zot gc`

```
zot gc [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
              [--debug] [-y] [--json] [--orphans] [--snapshots]
              [--empty-trash] [--dry-run]
```

| Argument | Description |
|----------|-------------|
| `--orphans` | attachments nothing claims: no parent, no collection, no tags, no annotations (a filed parentless PDF is an item, and is kept) |
| `--snapshots` | saved page snapshots (the item keeps its URL) |
| `--empty-trash` | also erase everything already in the trash — PERMANENT |
| `--dry-run` | report, don't write |
