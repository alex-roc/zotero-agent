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
| `cli/zot` | Stdlib-only Python CLI: `search`, `get`, `pdf`, `collections`, `tags`, `exec`, `ping`, `init`. |
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
zot get ABCD1234                        # one item's fields
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
