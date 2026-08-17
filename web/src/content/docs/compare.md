---
title: Compare
description: How zotero-agent compares to zotero-mcp, pyzotero, Better BibTeX JSON-RPC, and Beaver — honestly.
---

There are several good ways to automate Zotero. They optimize for different
things. This page is honest about where each one wins.

## At a glance

| | Local write | Needs account / API key | Works offline | Agent-ready (MCP) | Open source | Security docs |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **zotero-agent** | ✓ | no | ✓ | ✓ | ✓ | ✓ |
| zotero-mcp | web only | yes | no | ✓ | ✓ | partial |
| pyzotero | web API | yes | no | library | ✓ | n/a |
| Better BibTeX JSON-RPC | almost none | no | ✓ | no | ✓ | n/a |
| Beaver | ✓ (cloud backend) | freemium account | no | GUI | no | partial |

## The honest read

**zotero-agent** — full read-write on your *local* library, no account, no API
key, works offline, MCP-ready. Its edge is exactly that combination: local
write + offline + privacy. Working on the files themselves also makes things
possible that a web API cannot reach at all — `zot toc` builds and embeds a PDF's
table of contents, which fixes the empty Outline tab that Zotero's reader
[cannot fill itself](https://github.com/zotero/zotero/issues/3396), and
`zot pdf-prep` splits and OCRs a scanned book in place, so a shelf of
two-pages-at-a-time scans becomes searchable and quotable. The cost is
that writes need a small privileged plugin with a documented
[security model](/zotero-agent/security/), which you install yourself.

**zotero-mcp** — excellent, and the better choice **if you already use zotero.org
sync**. It writes through the Zotero *Web* API, which means it needs an account,
an API key, and network access — and your data round-trips through the cloud. If
you live in the synced Zotero world already, that's a natural fit; if you want
local-only and offline, it isn't.

**pyzotero** — the mature Python client for the Zotero Web API. It's a *library*,
not an agent tool, and it also writes only through the web API (account + API key,
online). Reach for it when you're writing Python against your synced library, not
when you want a local CLI or an MCP server.

**Better BibTeX JSON-RPC** — great for what it does (citekey resolution, search,
export) and it's local and offline. But it writes **almost nothing** (only
`autoexport.add`, `collection.scanAUX`), so it can't do the metadata edits,
dedup, or tagging jobs `zotero-agent` is built for. `zotero-agent` actually uses
BBT's JSON-RPC to resolve citekeys.

**Beaver** — a capable AI-assisted Zotero experience, but it runs against a
**cloud backend** and a freemium account, and it's a GUI product rather than an
open, scriptable, local tool. Different trade-off: convenience and hosted
intelligence versus local control and privacy.

## When to pick what

- You want **local, offline, private** read-write and/or an **MCP/CLI** you can
  script → **zotero-agent**.
- You already sync with **zotero.org** and want an agent that fits that world →
  **zotero-mcp**.
- You're writing **Python** against your synced library → **pyzotero**.
- You just need **citekeys, search, export** locally → **Better BibTeX**.
