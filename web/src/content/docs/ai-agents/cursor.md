---
title: Cursor
description: Add zotero-agent to Cursor as an MCP server, per-project or globally.
---

Add `zotero-agent` to `.cursor/mcp.json` (per-project) or the global equivalent:

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

If `zot` is not on Cursor's `PATH`, use the absolute path from `which zot`.

See the [MCP overview](/zotero-agent/ai-agents/mcp/) for the tool list and safety
notes.
