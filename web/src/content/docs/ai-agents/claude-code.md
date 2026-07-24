---
title: Claude Code
description: Use zotero-agent from Claude Code via the bundled skill, or add it as an MCP server.
---

There are two ways to use `zotero-agent` from Claude Code.

## Option A — the skill (recommended)

From a git checkout, `./install.sh` links the `zotero` skill into
`~/.claude/skills/`. After that, just ask Claude about your library — no MCP
config needed. The skill teaches Claude the safe workflow (backup → sync-off →
dry-run → small batch) and points it at the right `zot` commands.

> "Which items in my *To Read* collection are missing a DOI? Fill them in from
> Crossref, dry-run first."

The skill runs `zot ping` to confirm the bridge is live before doing anything,
and refuses to work around a missing plugin.

## Option B — MCP server

Prefer MCP? Register `zot mcp` as a server:

```bash
claude mcp add zotero-agent -- zot mcp
```

Install the MCP extra first (`uv tool install "zotero-agent[mcp]"`) and verify
with `zot ping`. See the [MCP overview](/zotero-agent/ai-agents/mcp/) for the
tool list and safety notes.

## Which should I use?

The skill is the smoother path in Claude Code: it carries the safety workflow and
recipe knowledge with it. Use MCP if you want the exact same structured tools
across several clients, or if you're not working from a checkout.
