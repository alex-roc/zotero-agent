# Security model

`POST /zotexec` runs **arbitrary privileged JavaScript** inside Zotero. That is
powerful and deliberately so — it is the price of a complete local write path.
The endpoint is protected by three layers.

## 1. Token (required)

Every request must carry the header `X-Zotexec-Token` matching the configured
token. Without a configured token the endpoint returns **403** (fail-closed) —
it never runs code with no token. Token resolution order:

1. Zotero pref `extensions.zotexec.token` (if set), else
2. the `token` field in `~/.config/zotero-exec/config.json`.

The config file is the single source of truth the `zot` CLI writes and the
plugin reads, so rotating the token needs no Zotero restart. `zot init`
generates a random `secrets.token_urlsafe(24)` token and writes the config with
`0600` permissions.

## 2. Origin / Host guard (anti-CSRF / DNS-rebinding)

A web page in your browser can POST to `localhost`. Two things stop it:

- **Zotero's own server** rejects cross-origin requests before they reach the
  endpoint. In testing, a request carrying `Origin: http://evil.example.com`
  gets the connection **closed with an empty reply**, and a spoofed non-loopback
  `Host` gets **HTTP 400** — neither ever runs code.
- **The endpoint** adds a second barrier: it returns **403** when an `Origin`
  or `Referer` header with an `http(s)://` scheme is present (browsers always
  send one; the CLI sends none), or when `Host` is not a loopback name
  (`localhost`, `127.0.0.1`, `::1`).

Combined with the token (which a cross-site attacker cannot read), this closes
the browser attack surface. Verified behavior:

| request | result |
|---------|--------|
| no token | 403 |
| wrong token | 403 |
| browser `Origin` | connection closed (Zotero) |
| non-loopback `Host` | 400 (Zotero) |
| valid token, loopback | 200 |

## 3. Loopback binding

Zotero's HTTP server binds to loopback only by default, so the endpoint is not
reachable from other machines. Do not change that binding.

## Residual risk & guidance

- Anyone who can read your config file gets the token. It is `0600`, but treat
  the token like a password. Rotate it by editing the config (no restart) or
  setting the pref.
- The code you send has full library access. The skill enforces a safe workflow
  (backup, sync-off, dry-run, test on 1–2 items) for bulk/destructive ops — see
  `../skill/SKILL.md`.
- The token is **not** a secret against local processes running as your user;
  it defends against browser-origin and other-host access, not against code you
  already run locally.
