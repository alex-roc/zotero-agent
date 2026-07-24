"""zotero-agent — local read-write control of a Zotero library.

Read path  : Zotero's local HTTP API  (GET /api/users/<id>/...)  — fast.
Write path : the zotero-agent bridge plugin (POST /zotero-agent)  — arbitrary JS.

Stdlib only in the core (urllib) — no runtime dependencies. The optional MCP
server (`zot mcp`) needs the `[mcp]` extra.
"""

__version__ = "0.2.1"
