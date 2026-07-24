---
title: Configuration
description: The config file, the token, environment variables, and global flags — and the order they resolve in.
---

`zotero-agent` needs three things to reach your library: a **base URL** (where
Zotero's HTTP server listens), a **token** (to authenticate to the bridge), and
your **userID**. All three are set up by `zot init` and stored in one config
file.

## The config file

`zot init` writes `~/.config/zotero-agent/config.json` with `0600` permissions:

```json
{
  "base": "http://localhost:23119",
  "token": "generated-random-token",
  "user_id": "2960998"
}
```

- **base** — Zotero's local HTTP server. The default is
  `http://localhost:23119`; the bridge endpoint is `POST /zotero-agent` there.
- **token** — a random `secrets.token_urlsafe(24)` string. This is the single
  source of truth: the `zot` CLI writes it and the plugin reads it, so rotating
  the token is just editing this file — **no Zotero restart needed**.
- **user_id** — your Zotero library userID, auto-detected by `zot init` /
  `zot ping`.

## The token

Every write request carries the header `X-Zotero-Agent-Token`. Resolution order
for the token the **plugin** uses:

1. Zotero pref `extensions.zotero-agent.token`, if set (takes precedence), else
2. the `token` field in `~/.config/zotero-agent/config.json`.

Without a configured token the endpoint fails closed with **403** — it never runs
code with no token. Treat the token like a password; it is `0600` but readable by
any process running as you. See the [security model](/zotero-agent/security/).

## Environment variables

Override any config field without editing the file:

| Variable | Overrides |
|----------|-----------|
| `ZOTERO_AGENT_BASE` | `base` |
| `ZOTERO_AGENT_TOKEN` | `token` |
| `ZOTERO_AGENT_USER_ID` | `user_id` |

## Global flags

The same three can be set per-invocation, which wins over everything:

```bash
zot --base http://localhost:23119 --token "$TOK" --user-id 2960998 ping
```

Other global flags: `--json`, `-q`/`--quiet`, `--debug`, `--yes`. See the
[command reference](/zotero-agent/reference/commands/).

## Precedence

From highest to lowest:

```
command-line flags  >  ZOTERO_AGENT_* env vars  >  ~/.config/zotero-agent/config.json
```

For the token specifically, remember the **plugin** side also checks the Zotero
pref `extensions.zotero-agent.token` first — set it if you'd rather keep the
token in Zotero than in the config file.
