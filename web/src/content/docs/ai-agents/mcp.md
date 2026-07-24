---
title: MCP overview
description: How zot mcp exposes your local Zotero library to any Model Context Protocol client.
---

`zotero-agent` works with any AI coding or agent tool in two ways:

1. **MCP server** (`zot mcp`) — structured tools, best for Claude Desktop, Codex
   CLI, Gemini CLI, Cursor, and any MCP client.
2. **The `zot` CLI + `AGENTS.md`** — for agents that run shell commands and read
   a repo's `AGENTS.md` (Codex CLI, Gemini CLI, Aider). No MCP needed.

Both drive the **same local library** and follow the same safety rules.

## Install the MCP extra

```bash
uv tool install "zotero-agent[mcp]"   # or: pipx install "zotero-agent[mcp]"
zot init && zot ping                   # confirm the bridge is answering
```

The server is launched as `zot mcp` over stdio. Add `--allow-exec` only if you
want to expose the raw `run_javascript` tool.

## The generic config

Most MCP clients take the same shape — a command and its args:

```json
{
  "mcpServers": {
    "zotero-agent": { "command": "zot", "args": ["mcp"] }
  }
}
```

If `zot` is not on the client's `PATH`, use the absolute path from `which zot`.

Per-client instructions:

- [Claude Code](/zotero-agent/ai-agents/claude-code/)
- [Codex CLI](/zotero-agent/ai-agents/codex-cli/)
- [Gemini CLI](/zotero-agent/ai-agents/gemini-cli/)
- [Cursor](/zotero-agent/ai-agents/cursor/)

## The tools

| Tool | Kind |
|------|------|
| `search_items`, `get_item`, `get_item_pdf_path` | read |
| `list_collections`, `get_collection_items` | read |
| `library_stats`, `find_missing`, `search_by_author` | read |
| `export_bibliography` | read |
| `create_item`, `manage_tags`, `move_to_collection`, `create_note` | write |
| `update_items` (batch, undoable) | write |
| `find_duplicates`, `merge_duplicates` | write |
| `enrich_metadata` (undoable) | write |
| `undo_last` | write |
| `run_javascript` (only with `--allow-exec`) | escape hatch |

## Safety

Writes go through the token-protected bridge and are recorded to an append-only
audit log. Batch tools (`update_items`, `enrich_metadata`) snapshot first, so
`undo_last` can restore them. **Merges are not reversible** — take a backup
before merging. See the [security model](/zotero-agent/security/).
