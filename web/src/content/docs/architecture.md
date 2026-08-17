---
title: Architecture
description: The three layers — bridge plugin, zot CLI, agent skill — and why the local write path has to be a plugin.
---

```
Agent / user → [ zotero skill | zot CLI ] ─┬─ read  → local HTTP API  /api/…   (GET, fast)
                                            └─ write → POST /zotero-agent  (bridge plugin, arbitrary JS)
```

Three layers, each doing the one thing it is good at.

## Why the write path is a plugin

Zotero ships a **local HTTP API** at `http://localhost:23119/api/…` that mirrors
the Web API. On Zotero 7 / 9.x it is **read-only by design**: `POST /items` or
`POST /collections` returns `400 "Endpoint does not support method"`, and there
is no preference to enable writing. So the API is perfect for fast reads and
useless for writes.

Other options were evaluated and rejected:

- **Better BibTeX JSON-RPC** is alive but writes almost nothing (only
  `autoexport.add`, `collection.scanAUX`). Fine for search/export, not for
  editing the library.
- **The BBT debug-bridge** that older automation relied on **no longer exists** in
  current Better BibTeX (9.x).

The only complete *local* write path is code running **inside** Zotero's
privileged context, calling `Zotero.Item…saveTx()` and friends directly. That is
exactly what a bootstrap plugin can do. The bridge is a ~200-line plugin that
registers one endpoint, `POST /zotero-agent`, which runs a supplied async JS body
in-process and returns the result as JSON. This mirrors the well-known
`zotero-api-endpoint` plugin pattern.

## The three layers

### Layer 0 — the bridge plugin

`plugin/zotero-agent-bridge/`: the endpoint. Token-protected, origin-guarded,
loopback-only. Fully general — every recipe in the
[JS reference](/zotero-agent/reference/zot-exec-js/) works over it unchanged.
Requires Zotero 7+ (tested through 9.x).

### Layer 1 — the `zot` CLI

Stdlib-only Python. Reads hit the fast local API (`search`, `get`, `cite`, `pdf`,
`collections`, `tags`, `recent`, `bib`, with `--all` pagination). Higher-level
operations are built cleanly on the Zotero JS API (`export`, `missing`, `author`,
`stats`, `annotations`, `related`, `lint`) — as are the write/edit verbs (`add`,
`dedupe`, `tag`, `set`, `move`, `collection`, `note`), each safe-by-default
(refusing non-interactive writes without `--yes`). `exec` is the raw escape hatch
(with `--dry-run`); `backup` snapshots the DB; `ping`/`init` set up.

### Layer 1b — the PDF engine

`src/zotero_agent/pdf/`: the only part that opens a file rather than talking to
Zotero, behind the `[toc]` extra and used by `toc` and `pdf-prep`. PyMuPDF is
reached solely through `require_pymupdf()`, so the rest of the package stays
importable without it. Inside, `pagemap` is deliberately pure — the
printed-page-to-physical-page arithmetic is the subtle part, and keeping it free
of the engine is what makes it testable without a fixture PDF — while `scan`
reads a document and `outline` reads, validates and writes the tree.

`prep`, the `zot pdf-prep` engine, follows the same split: deciding where a
scanned book's gutter falls is arithmetic over an ink profile, so it is pure and
unit-tested, and only analysing, splitting and invoking OCR touch the outside
world. It is also the one place that shells out to a **program** rather than a
library — OCRmyPDF, detected with `shutil.which` and never a hard dependency,
because OCR is optional and its toolchain belongs to the system's package
manager rather than to a Python wheel.

Config precedence: flags > `ZOTERO_AGENT_*` env >
`~/.config/zotero-agent/config.json` — see
[Configuration](/zotero-agent/reference/configuration/).

### Layer 2 — the agent skill

`skill/`: teaches an agent to drive `zot`, including the safe workflow for
bulk/destructive operations. The same operations are also available over MCP via
`zot mcp` — see [AI agents](/zotero-agent/ai-agents/mcp/).

## Anti-duplication

The canonical sources live once: the plugin in `plugin/`, the CLI in `src/`, the JS
recipe book in `skill/references/recipes.md` — docs link to it rather than restating
it. The MCP tools call the same command functions the CLI does, so the two surfaces
cannot diverge.

Distribution follows the same rule: **one artifact per surface, one version for all**.
The CLI, the MCP server and the skill ship in the PyPI package (`zot skill install`
unpacks the skill), while the plugin XPI is published **only** as a GitHub Release
asset. Zotero keeps it current from `updates.json`, which the release workflow
generates from the tag; the build stamps the package version into the plugin, so a
released XPI can never disagree with the CLI it answers — and `zot ping` prints both
versions. See [Install](/zotero-agent/getting-started/install/#updating).

**Homebrew** adds an install route without adding an artifact. The formula is
generated from the sdist a release publishes to PyPI — `scripts/gen_homebrew_formula.py`
fills in the `url`, the `sha256` and a hash-pinned lock of the optional extras. The
tap therefore mirrors PyPI instead of building anything of its own, and no hash is
ever edited by hand: that manual bump is precisely what made the project's first
tap unmaintainable.
