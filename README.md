# zotero-agent

**Full local control of your Zotero library — from your terminal or your AI agent. No cloud, no API key.**

`zot` is a CLI and AI-agent toolkit that gives you full **read-write** control of
your *local* Zotero library: search, bulk-edit metadata, tag, deduplicate, import
by DOI/ISBN/arXiv, export, and summarize PDFs into notes. Zotero's local API is
read-only, so writes go through a tiny plugin exposing a single token-protected
endpoint, with a documented [three-layer security model](docs/security.md). No
zotero.org account, no API key, no cloud — **your library never leaves your machine.**

```
Agent / user → [ MCP server | agent skill | zot CLI ] ─┬─ read  → Zotero local API /api/…  (GET, fast)
                                                        └─ write → POST /zotero-agent (bridge plugin, JS)
```

## Why this exists

The dominant Zotero automation tools (zotero-mcp, pyzotero) can only *write* via
the zotero.org web API — which needs an account, an API key and sync. Zotero's
**local** HTTP API returns `501` on every write. The only way to write locally is
a plugin, and that is exactly what the `zotero-agent` bridge is. That makes this
the local-first, offline, private option: batch metadata edits, real dedup, and
tag cleanup that people have asked Zotero for [since 2016](https://forums.zotero.org/discussion/111815/feature-batch-editing-metadata-for-multiple-items) — done on your own machine.

## Three ways to use it

- **AI agents via MCP** — `zot mcp` is a Model Context Protocol server for Claude
  Desktop, **Codex CLI**, **Gemini CLI**, Cursor, and any MCP client. See
  [`docs/ai-agents.md`](docs/ai-agents.md).
- **Claude Code skill** — the `zotero` skill drives `zot` with a safe workflow.
- **Plain CLI** — script it in bash, pipe it, put it in a Makefile.

## What's inside

| Path | What |
|------|------|
| `src/zotero_agent/` | The Python package: CLI, command modules, JS builders, MCP server. Stdlib-only core. |
| `plugin/zotero-agent-bridge/` | The write endpoint (`POST /zotero-agent`), token-protected, ~200 lines. |
| `skill/` | The `zotero` skill for Claude Code (SKILL.md + recipe book + evals). |
| `docs/` | Install, security model, architecture, AI-agent setup. |
| `web/` | The documentation site (Astro Starlight → GitHub Pages). |

## Install

```bash
# CLI (+ optional MCP server):
uv tool install zotero-agent            # or: pipx install zotero-agent
uv tool install "zotero-agent[mcp]"     # include the MCP server

# then install the bridge plugin in Zotero:
#   Tools → Plugins → gear → "Install Plugin From File" → the .xpi from Releases
zot init      # generates a token, writes config, auto-detects your userID
zot ping      # verify: local API up, bridge answering, userID known
```

From a checkout, `./install.sh` wires up the skill, a dev `zot`, and builds the
XPI. Full instructions: [`docs/install.md`](docs/install.md).

## Using the CLI

```bash
zot search "bolivia" --limit 10               # read (fast API)
zot get ABCD1234                              # one item (Zotero key or BBT citekey)
zot missing abstract --collection SS5MVVB6    # items lacking a field
zot stats                                     # library analytics
zot add doi 10.1371/journal.pmed.0020124 --pdf   # import by identifier (+ OA PDF)
zot dedupe --by title --fuzzy                 # find near-duplicate titles
zot dedupe --merge --yes                      # merge duplicates (oldest = master)
zot enrich --field doi --dry-run              # fill missing DOIs from Crossref
zot apply edits.jsonl                         # declarative batch edit (undoable)
zot undo last                                 # roll it back
zot tag normalize --dry-run                   # fold case/space tag variants
zot export "My Collection" --format bibtex --out refs.bib
zot exec 'return Zotero.version;'             # escape hatch: run privileged JS
```

Add `--json` to any command for machine-readable output. Writes refuse to run
non-interactively without `--yes`. The canonical JS recipe book is
[`skill/references/recipes.md`](skill/references/recipes.md).

## Using with an AI agent

Ask *"tag every abstract-less item #review and merge duplicate titles in
collection X"*, *"fill in missing DOIs"*, or *"summarize this paper's PDF chapter
by chapter and save it as a note"*. The agent drives `zot` and follows a safe
workflow (backup → sync-off → dry-run → small batch) for bulk or destructive edits.
Batch edits are **undoable** (`zot undo`).

## Requirements

- Zotero 7+ (tested through 9.x) running, local API enabled (default).
- Python 3.9+ (stdlib-only core; the MCP server needs the `[mcp]` extra).
- macOS and Linux; Windows paths are noted in `docs/install.md`.

## Security

Arbitrary local JS execution, gated by a required token + browser-origin
rejection + loopback binding, with an append-only audit log. This is a deliberate
capability; read [`docs/security.md`](docs/security.md) before installing.
License: [MIT](LICENSE).

## Development

```bash
python3 -m unittest discover -s tests   # unit + fake-server tests (no network, no Zotero)
uvx ruff check src tests                 # lint
uv build                                 # build wheel + sdist
bash plugin/build.sh                     # rebuild the bridge XPI
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CHANGELOG.md`](CHANGELOG.md).
