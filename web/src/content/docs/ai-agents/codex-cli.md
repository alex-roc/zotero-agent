---
title: Codex CLI
description: Connect zotero-agent to Codex CLI via MCP, or let it drive the zot CLI through AGENTS.md.
---

Codex CLI can use `zotero-agent` two ways.

## Via MCP

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.zotero-agent]
command = "zot"
args = ["mcp"]
```

Install the MCP extra first (`uv tool install "zotero-agent[mcp]"`) and verify
with `zot ping`.

## Via the CLI + AGENTS.md

Codex also reads a repository's `AGENTS.md`, so inside a project you can skip MCP
entirely and let it call the `zot` CLI directly. The repo root ships an
[`AGENTS.md`](https://github.com/alex-roc/zotero-agent/blob/main/AGENTS.md) that
documents the read commands, the guarded write commands, the JSONL batch-edit
flow (`zot apply` / `zot undo`), and the safety rules — everything Codex needs to
operate the library from the shell.

See the [MCP overview](/zotero-agent/ai-agents/mcp/) for the full tool list and
safety notes.
