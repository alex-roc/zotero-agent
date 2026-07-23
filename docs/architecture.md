# Architecture

```
Agent / user → [ zotero skill | zot CLI ] ─┬─ read  → local HTTP API  /api/…   (GET, fast)
                                            └─ write → POST /zotexec  (zotero-exec plugin, arbitrary JS)
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
is exactly what a bootstrap plugin can do. `zotero-exec` is a ~200-line plugin
that registers one endpoint, `POST /zotexec`, which runs a supplied async JS
body in-process and returns the result as JSON. This mirrors the well-known
`zotero-api-endpoint` plugin pattern.

## The three layers

- **Layer 0 — `zotero-exec` plugin** (`plugin/zotero-exec/`): the endpoint.
  Token-protected, origin-guarded, loopback-only. Fully general — every recipe
  in the memory/reference book works over it unchanged.
- **Layer 1 — `zot` CLI** (`cli/zot`): stdlib-only Python. `search`, `get`,
  `collections`, `tags` hit the fast read API; `exec` is the write workhorse;
  `ping` validates the stack; `init` is the config wizard.
- **Layer 2 — `zotero` skill** (`skill/`): teaches an agent to drive `zot`,
  including the safe workflow for bulk/destructive operations.

## Anti-duplication

The canonical sources live once: the plugin in `plugin/`, the CLI in `cli/`,
the recipe book in `skill/references/recipes.md`. `install.sh` (and the
skill-packaging step) **copy** the CLI and plugin into `skill/scripts/` so the
skill is self-contained when shared. README and docs link to the recipe book
rather than restating it.
