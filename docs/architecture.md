# Architecture

```
Agent / user → [ zotero skill | zot CLI ] ─┬─ read  → local HTTP API  /api/…   (GET, fast)
                                            └─ write → POST /zotero-agent  (zotero-agent bridge plugin, arbitrary JS)
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
- **The BBT debug-bridge** that older automation relied on **no longer exists**
  in current Better BibTeX (9.x).

The only complete *local* write path is code running **inside** Zotero's
privileged context, calling `Zotero.Item…saveTx()` and friends directly. That
is exactly what a bootstrap plugin can do. the bridge is a ~200-line plugin
that registers one endpoint, `POST /zotero-agent`, which runs a supplied async JS
body in-process and returns the result as JSON. This mirrors the well-known
`zotero-api-endpoint` plugin pattern.

## The three layers

- **Layer 0 — `zotero-agent` bridge plugin** (`plugin/zotero-agent-bridge/`): the endpoint.
  Token-protected, origin-guarded, loopback-only. Fully general — every recipe
  in the memory/reference book works over it unchanged.
- **Layer 1 — `zot` CLI** (`cli/zot`): stdlib-only Python. Reads hit the fast
  local API (`search`, `get`, `cite`, `pdf`, `collections`, `tags`, `recent`,
  `bib`, with `--all` pagination). Higher-level operations are built cleanly on
  the Zotero JS API (`export`, `missing`, `author`, `stats`, `annotations`,
  `related`, `lint`) — and the write/edit verbs (`add` by identifier, `dedupe`,
  `tag`, `set`, `move`, `collection`, `note`) too, each safe-by-default
  (refuse non-interactive writes without `--yes`). `exec` is the raw escape
  hatch (with `--dry-run`); `backup` snapshots the DB; `ping`/`init` set up.
  Config precedence: flags > `ZOTERO_AGENT_*` env > `~/.config/zotero-agent/config.json`.
- **Layer 2 — `zotero` skill** (`skill/`): teaches an agent to drive `zot`,
  including the safe workflow for bulk/destructive operations.

## Anti-duplication

The canonical sources live once: the plugin in `plugin/`, the CLI in `cli/`,
the recipe book in `skill/references/recipes.md`. `install.sh` (and the
skill-packaging step) **copy** the CLI and plugin into `skill/scripts/` so the
skill is self-contained when shared. README and docs link to the recipe book
rather than restating it.
