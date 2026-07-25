---
title: Security model
description: The three-layer model that protects the arbitrary-JS bridge endpoint — token, origin guard, loopback — plus residual risk.
---

`POST /zotero-agent` runs **arbitrary privileged JavaScript** inside Zotero. That
is powerful and deliberately so — it is the price of a complete local write path.
Read this before installing. The endpoint is protected by three layers, and every
write is recorded to an append-only audit log.

## Why not the old debug-bridge?

Earlier Zotero automation leaned on Better BibTeX's **debug-bridge**, which ran
unauthenticated code over a loopback port. That surface **no longer exists** in
current Better BibTeX (9.x), and it was never token-protected. `zotero-agent`
takes the opposite stance: a single, purpose-built endpoint that **fails closed**
without a token and actively rejects browser-origin requests. Same capability,
defended.

## 1. Token (required)

Every request must carry the header `X-Zotero-Agent-Token` matching the
configured token. Without a configured token the endpoint returns **403**
(fail-closed) — it never runs code with no token. Resolution order:

1. Zotero pref `extensions.zotero-agent.token` (if set), else
2. the `token` field in `~/.config/zotero-agent/config.json`.

The config file is the single source of truth the `zot` CLI writes and the plugin
reads, so rotating the token needs no Zotero restart. `zot init` generates a
random `secrets.token_urlsafe(24)` token and writes the config `0600`.

## 2. Origin / host guard (anti-CSRF / DNS-rebinding)

A web page in your browser can POST to `localhost`. Two things stop it:

- **Zotero's own server** rejects cross-origin requests before they reach the
  endpoint. In testing, a request carrying `Origin: http://evil.example.com` gets
  the connection **closed with an empty reply**, and a spoofed non-loopback
  `Host` gets **HTTP 400** — neither ever runs code.
- **The endpoint** adds a second barrier: it returns **403** when an `Origin` or
  `Referer` header with an `http(s)://` scheme is present (browsers always send
  one; the CLI sends none), or when `Host` is not a loopback name (`localhost`,
  `127.0.0.1`, `::1`).

Combined with the token (which a cross-site attacker cannot read), this closes
the browser attack surface. Verified behavior:

| Request | Result |
|---------|--------|
| no token | 403 |
| wrong token | 403 |
| browser `Origin` | connection closed (Zotero) |
| non-loopback `Host` | 400 (Zotero) |
| valid token, loopback | 200 |

## 3. Loopback binding

Zotero's HTTP server binds to loopback only by default, so the endpoint is not
reachable from other machines. Do not change that binding.

## Distribution & updates

The plugin is not signed by Zotero (it is not in Zotero's plugin directory), so
its trust chain is HTTPS plus the public repo:

- The XPI is published **only** as a GitHub Release asset, built in CI from the
  tagged source (`scripts/build_xpi.py`) as a deterministic zip — you can rebuild
  a release from its tag and compare bytes.
- Updates use Zotero's own plugin-update mechanism: the manifest's `update_url`
  points at `updates.json` in the repo, which carries the release URL **and** the
  asset's `sha256` (`update_hash`). Zotero refuses an update whose hash does not
  match, so a file swapped at the download URL cannot be installed.
- The bridge is ~200 lines of readable JS, and `zot ping` reports the running
  plugin's version so you can see what is actually loaded.

## Residual risk & guidance

- Anyone who can read your config file gets the token. It is `0600`, but treat
  the token like a password. Rotate it by editing the config (no restart) or
  setting the pref.
- The code you send has full library access. The skill and agent workflow enforce
  a safe sequence (backup, sync-off, dry-run, test on 1–2 items) for
  bulk/destructive ops — see [Quickstart: AI agent](/zotero-agent/getting-started/quickstart-agent/).
- The token is **not** a secret against local processes running as your user; it
  defends against browser-origin and other-host access, not against code you
  already run locally.
