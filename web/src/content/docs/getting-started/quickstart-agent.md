---
title: Quickstart — AI agent
description: Point an AI agent at your local Zotero library via MCP or the zot CLI, and run bulk edits safely.
---

`zotero-agent` gives an AI agent full read-write access to your **local** Zotero
library. You describe the outcome in plain language; the agent drives `zot` and
follows a safe workflow for anything bulk or destructive. Two ways to connect:

1. **MCP server** (`zot mcp`) — structured tools for Claude Desktop, Codex CLI,
   Gemini CLI, Cursor, and any MCP client.
2. **The `zot` CLI + `AGENTS.md`** — for agents that run shell commands and read
   a repo's `AGENTS.md` (Codex CLI, Gemini CLI, Aider). No MCP needed.

Both drive the same library and obey the same safety rules.

## Install with the MCP extra

```bash
uv tool install "zotero-agent[mcp]"   # or: pipx install "zotero-agent[mcp]"
# a Homebrew install already includes it: brew install alex-roc/tap/zotero-agent
zot init && zot ping                   # confirm the bridge is answering
```

The MCP server is launched as `zot mcp` over stdio. Add `--allow-exec` only if
you want to expose the raw `run_javascript` tool.

## Connect your client

Per-client config lives in [AI agents](/zotero-agent/ai-agents/mcp/). The short
version — most clients take the same shape:

```json
{ "mcpServers": { "zotero-agent": { "command": "zot", "args": ["mcp"] } } }
```

For **Claude Code**, install the bundled skill with `zot skill install` — then just
ask about your library, no MCP config needed. See
[Claude Code](/zotero-agent/ai-agents/claude-code/).

## What you can ask

Once connected, prompts like these work directly:

> "Tag every abstract-less item `#needs-abstract` and merge duplicate titles in
> collection *Reading list*."

> "Fill in missing DOIs from Crossref for everything in *To Read*."

> "Summarize this paper's PDF chapter by chapter and save it as a note on the item."

> "Import DOI 10.1371/journal.pmed.0020124 with its open-access PDF."

## The safety net

The agent doesn't just run writes blindly. For bulk or destructive operations it
follows this workflow (and the write commands themselves refuse to run without
confirmation):

1. **Back up** `zotero.sqlite` (`zot backup`) — always before `dedupe --merge`.
2. **Disable auto-sync** so a mistake doesn't propagate to zotero.org.
3. **Dry-run / scope** first — preview counts and samples, prefer `--collection`
   over the whole library.
4. **Test on 1–2 items** and verify before the full set.
5. Prefer **trash over permanent erase**.
6. **Re-enable sync** when done.

Batch edits (`update_items`, `enrich_metadata`, `zot apply`) snapshot first, so
`undo_last` / `zot undo` can restore them. **Merges are not reversible** — the
backup is the guarantee. Every write goes through the token-protected bridge and
is recorded to an append-only audit log. See the [security model](/zotero-agent/security/).

## The MCP tools

`search_items`, `get_item`, `get_item_pdf_path`, `list_collections`,
`get_collection_items`, `library_stats`, `find_missing`, `search_by_author`,
`create_item`, `update_items` (batch, undoable), `manage_tags`,
`move_to_collection`, `create_note`, `find_duplicates`, `merge_duplicates`,
`enrich_metadata`, `export_bibliography`, `undo_last`, and — only with
`--allow-exec` — `run_javascript`.
