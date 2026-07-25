---
title: FAQ
description: Troubleshooting zotero-agent — 403s, port 23119, unsigned-plugin warnings, PATH, Better BibTeX, and "is this safe?".
---

## `zot: command not found`

`zot` isn't on your `PATH`. If you installed with uv/pipx, make sure the tool bin
directory is on `PATH` (`uv tool update-shell` or add `~/.local/bin`). Confirm
with `which zot`. When configuring an MCP client that can't find it, use the
absolute path from `which zot` in the client config.

## `403` / token errors

A `403` from the bridge means the token layer rejected the request — the endpoint
**fails closed**. Check that:

- `zot init` has run and `~/.config/zotero-agent/config.json` has a `token`.
- If you set the Zotero pref `extensions.zotero-agent.token`, it **takes
  precedence** over the config file — make sure they match (or clear the pref).
- You aren't sending a browser `Origin`/`Referer` — the CLI doesn't; a browser
  always does, and that is rejected by design.

Rotating the token is just editing the config file (or the pref) — no Zotero
restart needed. See the [security model](/zotero-agent/security/).

## Port 23119 busy / "Zotero closed"

Zotero's local HTTP server listens on **port 23119**. If `zot ping` shows the
local API down:

- **Zotero isn't running** — start it; the API and the bridge live inside the app.
- **The local API is disabled** — it's on by default; re-enable it in Zotero's
  settings.
- **Another process took the port** — quit whatever is bound to 23119, or point
  `zot` at the right base with `--base` / `ZOTERO_AGENT_BASE`.

## The bridge endpoint shows `FAIL`

The plugin isn't loaded. Reinstall
[the XPI](https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi)
via *Tools → Plugins → gear → Install Plugin From File…*, confirm "Zotero Agent
Bridge" is enabled, and re-run `zot ping`. See
[Install](/zotero-agent/getting-started/install/).

## `zot ping` says the plugin is older than the CLI

Expected right after a release: Zotero only checks for plugin updates **once every
24 hours**. Force it with *Tools → Plugins → gear icon (top-right of the plugin
list) → Check for Updates* — that menu is on the list, not in a plugin's detail
pane. See [Updating](/zotero-agent/getting-started/install/#updating).

## "This add-on is unsigned / from an unknown source"

Expected for a plugin distributed outside Zotero's plugin directory. Zotero warns
but lets you proceed. The plugin is small (~200 lines) and its source is public — read it
before installing if you like. See the [security model](/zotero-agent/security/).

## Which paths does it use, per OS?

Config lives at `~/.config/zotero-agent/config.json` on macOS and Linux. Zotero's
profile (auto-detected by `zot init`) is at:

| OS | Profile |
|----|---------|
| macOS | `~/Library/Application Support/Zotero/Profiles/<random>.default*` |
| Linux | `~/.zotero/zotero/<random>.default*` |
| Windows | `%APPDATA%\Zotero\Zotero\Profiles\<random>.default*` |

## Does it conflict with Better BibTeX?

No — they coexist. In fact `zotero-agent` **uses** Better BibTeX's JSON-RPC to
resolve citekeys (`zot cite`, and `@citekey` in `zot get` / `zot pdf`). BBT's
own writes are minimal, so there's no overlap with the bridge's write path.

## Is this safe?

The bridge runs arbitrary privileged JavaScript, so it is a real capability — but
it is guarded by three layers (required token, browser-origin rejection, loopback
binding) and logs every write. It does **not** defend against code you already
run locally as your own user, and it does **not** send anything to a cloud. Read
the full [security model](/zotero-agent/security/) before installing, and follow
the backup/dry-run/undo workflow for bulk edits.
