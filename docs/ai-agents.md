# Using zotero-agent with AI agents

`zotero-agent` works with any AI coding/agent tool, in two ways:

1. **MCP server** (`zot mcp`) — structured tools, best for Claude Desktop, Codex
   CLI, Gemini CLI, Cursor and other MCP clients.
2. **The `zot` CLI + `AGENTS.md`** — for agents that run shell commands and read a
   repo's `AGENTS.md` (Codex CLI, Gemini CLI, Aider, …). This needs no MCP.

Both drive the **same local library** and follow the same safety rules. Install
the CLI with the MCP extra first:

```bash
uv tool install "zotero-agent[mcp]"   # or: pipx install "zotero-agent[mcp]"
zot init && zot ping                   # confirm the bridge is answering
```

The MCP server is launched as `zot mcp` (stdio). Add `--allow-exec` only if you
want to expose the raw `run_javascript` tool.

## Claude Code (skill)

`./install.sh` links the `zotero` skill into `~/.claude/skills/`. Just ask Claude
about your library — no MCP config needed. To use MCP instead:
`claude mcp add zotero-agent -- zot mcp`.

## Claude Desktop

Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "zotero-agent": { "command": "zot", "args": ["mcp"] }
  }
}
```

## Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.zotero-agent]
command = "zot"
args = ["mcp"]
```

Codex also reads a repository's `AGENTS.md`, so in a project you can skip MCP and
let it call the `zot` CLI directly (see `AGENTS.md` at the repo root).

## Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "zotero-agent": { "command": "zot", "args": ["mcp"] }
  }
}
```

## Cursor

`.cursor/mcp.json` (project) or the global equivalent:

```json
{
  "mcpServers": {
    "zotero-agent": { "command": "zot", "args": ["mcp"] }
  }
}
```

## Any other MCP client

Launch `zot mcp` over stdio with `command: "zot", args: ["mcp"]`. If `zot` is not
on the client's PATH, use the absolute path (`which zot`).

## The tools

`search_items`, `get_item`, `get_item_pdf_path`, `list_collections`,
`get_collection_items`, `library_stats`, `find_missing`, `search_by_author`,
`create_item`, `update_items` (batch, undoable), `manage_tags`,
`move_to_collection`, `create_note`, `find_duplicates`, `merge_duplicates`,
`enrich_metadata`, `export_bibliography`, `undo_last`, and (with `--allow-exec`)
`run_javascript`.

## Safety

Writes go through the token-protected bridge and are recorded to an audit log.
Batch edits (`update_items`, `enrich_metadata`) snapshot first, so `undo_last`
can restore them. **Merges are not reversible** — take a backup before merging.
See [`security.md`](security.md).
