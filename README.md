# zotero-cli-skill

Control a **local Zotero** library programmatically — search, read, create,
edit, tag, organize, delete, export — from your terminal or from an AI agent
(Claude Code). No cloud, no daemon, no pasting JS into a console by hand.

```
Agent / user → [ zotero skill | zot CLI ] ─┬─ read  → Zotero local API /api/…  (GET, fast)
                                            └─ write → POST /zotexec (zotero-exec plugin, JS)
```

Zotero's local HTTP API is **read-only** by design, so writes go through a tiny
bootstrap plugin (`zotero-exec`) that exposes one token-protected endpoint
running privileged Zotero JS in-process. See [`docs/architecture.md`](docs/architecture.md)
for why.

## What's inside

| Path | What |
|------|------|
| `plugin/zotero-exec/` | The write endpoint (`POST /zotexec`), ~200 lines. |
| `cli/zot` | Stdlib-only Python CLI. **Read/analyze:** `search`, `get`, `cite`, `pdf`, `collections`, `tags`, `export`, `missing`, `author`, `stats`, `recent`, `bib`, `annotations`, `related`, `notes`, `lint`. **Edit/organize** (safe writes): `add`, `dedupe`, `tag`, `set`, `move`, `collection`, `note`. **Escape hatch:** `exec`. **Safety/setup:** `backup`, `ping`, `init`. Global flags: `--json`, `-q`, `--yes`, `--base/--token/--user-id`. |
| `skill/` | The `zotero` skill for Claude Code (SKILL.md + recipe book + evals). |
| `docs/` | Install, security model, architecture. |
| `install.sh` | Wires it all up. |

## Quickstart

```bash
git clone https://github.com/alex-roc/zotero-cli-skill.git && cd zotero-cli-skill
./install.sh                # skill + CLI + config; builds dist/zotexec.xpi
# in Zotero: Tools -> Plugins -> gear -> Install Plugin From File -> dist/zotexec.xpi
zot init                    # auto-detects your userID via the plugin
zot ping                    # verify all three layers
```

Full instructions: [`docs/install.md`](docs/install.md).

## Using the CLI

```bash
zot search "bolivia" --limit 10        # read (fast API)
zot collections                         # list collections
zot get ABCD1234                        # one item's fields (Zotero key or BBT citekey)
zot cite myCitekey2025                   # resolve a Better BibTeX citekey -> key + PDF
zot pdf myCitekey2025                    # PDF path (accepts key or citekey)
zot export "My Collection" --format csljson   # export (json/csv/csljson/bibtex/ris)
zot missing abstract --collection SS5MVVB6   # items lacking a field
zot author "Ojeda"                            # items by an author
zot stats                                     # library analytics
zot add doi 10.1371/journal.pmed.0020124 --pdf   # import by identifier (+ OA PDF)
zot dedupe --collection SS5MVVB6 --merge --yes   # find & merge duplicates (scoped)
zot tag add "#revisar" ABCD1234 EFGH5678 --yes   # bulk tag
zot set publisher "Lab TecnoSocial" ABCD1234 --yes
zot note ABCD1234 --file summary.html         # add a child note
zot backup                                    # snapshot the DB before big edits
zot exec risky.js --dry-run                   # preview writes without persisting
zot exec 'return Zotero.version;'       # write path: run privileged JS
zot exec my-script.js                   # ...from a file
echo 'return 1+1;' | zot exec -         # ...from stdin
```

The write workhorse is `zot exec`: the argument is a file, `-` (stdin), or
inline JS. The code is an async function body with `Zotero` in scope; `return`
comes back as JSON. The canonical recipe book (create/edit/tag/move/delete/
export/dedup) is [`skill/references/recipes.md`](skill/references/recipes.md).

## Using with Claude Code

`install.sh` symlinks the skill to `~/.claude/skills/zotero`. Ask Claude things
like *"export collection SS5MVVB6 to JSON"*, *"tag every abstract-less item
#revisar"*, *"find duplicate titles"*, *"summarize the PDF of this item chapter
by chapter and save it as a note"*, or *"what does this paper say about X?"* —
it drives `zot` (including `zot pdf` to read the attached PDF) and follows a safe
workflow (backup, sync-off, dry-run, test-small) for bulk or destructive edits.

## Requirements

- Zotero 7 or 9.x running, local API enabled (default).
- Python 3.8+ (stdlib only).
- macOS is tested; Linux/Windows paths are noted in `docs/install.md`.

## Security

Arbitrary local JS execution, gated by a required token + browser-origin
rejection + loopback binding. Read [`docs/security.md`](docs/security.md) before
exposing anything. License: [MIT](LICENSE).

## Development

```bash
python3 -m unittest discover -s tests   # run the CLI unit tests (stdlib only, no network)
bash plugin/build.sh                     # rebuild dist/zotexec.xpi
```

Canonical sources live in `cli/` and `plugin/`; `install.sh` copies them into
`skill/scripts/` so the skill is self-contained when shared.
