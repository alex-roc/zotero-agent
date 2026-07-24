---
title: Gemini CLI
description: Add zotero-agent to Gemini CLI as an MCP server.
---

Add `zotero-agent` to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "zotero-agent": { "command": "zot", "args": ["mcp"] }
  }
}
```

Install the MCP extra first:

```bash
uv tool install "zotero-agent[mcp]"   # or: pipx install "zotero-agent[mcp]"
zot init && zot ping                   # confirm the bridge is answering
```

If `zot` is not on Gemini CLI's `PATH`, use the absolute path from `which zot`.

Gemini CLI also reads a repository's `AGENTS.md`, so inside a project you can let
it drive the `zot` CLI directly instead of using MCP — see
[`AGENTS.md`](https://github.com/alex-roc/zotero-agent/blob/main/AGENTS.md).

See the [MCP overview](/zotero-agent/ai-agents/mcp/) for the tool list and safety
notes.
