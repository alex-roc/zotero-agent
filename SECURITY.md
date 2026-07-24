# Security Policy

`zotero-agent` deliberately exposes a local endpoint that runs **arbitrary
privileged JavaScript** inside Zotero. That capability is the whole point (it is
the only complete local write path), so we take its security model seriously and
document it honestly in [`docs/security.md`](docs/security.md).

## The model, in short

- **Token required** — every request must carry `X-Zotero-Agent-Token` matching
  the configured token; missing/wrong ⇒ `403` (fail-closed).
- **Origin guard** — requests carrying a web `Origin`/`Referer`, or a non-loopback
  `Host`, are rejected (anti-CSRF / DNS-rebinding).
- **Loopback binding** — Zotero's server listens on loopback by default.
- **Audit log** — every execution is recorded at
  `~/.local/state/zotero-agent/audit.jsonl` (hash + first line + result).

Known limit: the token does **not** protect against another process running as
the same local user. See `docs/security.md` for the full threat model.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Instead, use
GitHub's **[Report a vulnerability](https://github.com/alex-roc/zotero-agent/security/advisories/new)**
(private advisory) on this repository. If that is unavailable, open a minimal
issue asking for a private contact and we will follow up.

Please include: affected version (`zot --version`), platform, and a minimal
reproduction. We aim to acknowledge within a week.

## Supported versions

The latest released `0.x` version receives security fixes. Pre-1.0, older minor
versions are not maintained.
