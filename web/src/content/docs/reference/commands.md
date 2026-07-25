---
title: Command reference
description: Every zot command and its arguments — auto-generated from the CLI.
---

_Auto-generated from the `zot` CLI (v0.3.0) — do not edit by hand; run `python scripts/gen_cli_reference.py`._

Global flags on every command: `--json`, `-q/--quiet`, `--debug`, `--yes`, `--base/--token/--user-id` (or `ZOTERO_AGENT_*`). Exit codes: 0 ok, 1 error, 2 connection/exec, 3 not-found, 4 config.

## Read & analyze

### `zot search`

```
zot search [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--limit LIMIT] [--all]
                  [--item-type ITEM_TYPE] [--tag TAG]
                  query
```

| Argument | Description |
|----------|-------------|
| `query` |  |
| `--limit` |  |
| `--all` | fetch all results (paginate) |
| `--item-type` |  |
| `--tag` |  |

### `zot get`

```
zot get [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json]
               key
```

| Argument | Description |
|----------|-------------|
| `key` | Zotero item key, or a BBT citekey (prefix @ to force) |

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
                  [--out OUT]
                  collection
```

| Argument | Description |
|----------|-------------|
| `collection` | collection key or name |
| `--format` |  |
| `--out` | write to file instead of stdout |

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
                  [--debug] [-y] [--json] [--limit LIMIT]
```

| Argument | Description |
|----------|-------------|
| `--limit` |  |

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
               {doi,isbn,arxiv} identifier
```

| Argument | Description |
|----------|-------------|
| `kind` |  |
| `identifier` |  |
| `--pdf` | also try to attach an open-access PDF |
| `--collection` | add to this collection (key or name) |

### `zot dedupe`

```
zot dedupe [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
                  [--debug] [-y] [--json] [--by {title,doi}]
                  [--collection COLLECTION] [--merge] [--fuzzy]
                  [--threshold THRESHOLD] [--samples SAMPLES]
```

| Argument | Description |
|----------|-------------|
| `--by` |  |
| `--collection` | limit to a collection (key or name); else whole library |
| `--merge` | merge each group (keeps oldest as master) |
| `--fuzzy` | also group near-identical titles (Levenshtein) |
| `--threshold` | similarity threshold for --fuzzy (0-1) |
| `--samples` |  |

### `zot tag`

```
zot tag [-h] [--base BASE] [--token TOKEN] [--user-id USER_ID] [-q]
               [--debug] [-y] [--json] [--new NEW] [--map MAP] [--dry-run]
               [--samples SAMPLES]
               {add,rm,rename,purge,normalize} [tag] [keys ...]
```

| Argument | Description |
|----------|-------------|
| `action` |  |
| `tag` | the tag (for add/rm/rename) |
| `keys` | item keys/citekeys (for add/rm; '-' reads stdin) |
| `--new` | new tag name (for rename) |
| `--map` | CSV old,new mapping file (for normalize) |
| `--dry-run` | preview (for normalize) |
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
                  [--limit LIMIT] [--delay DELAY] [--dry-run]
                  [--samples SAMPLES]
```

| Argument | Description |
|----------|-------------|
| `--field` |  |
| `--source` |  |
| `--collection` | limit to a collection (key or name) |
| `--limit` | cap items looked up (0 = no cap) |
| `--delay` | seconds between API calls (be polite) |
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
