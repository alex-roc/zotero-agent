"""zotero-agent — local read-write control of a Zotero library.

Read path  : Zotero's local HTTP API  (GET /api/users/<id>/...)  — fast.
Write path : the zotero-agent bridge plugin (POST /zotero-agent)  — arbitrary JS.

Stdlib only in the core (urllib) — no runtime dependencies. Optional surfaces
ride behind extras: the MCP server (`zot mcp`) needs `[mcp]`, and the PDF
outline commands (`zot toc`) need `[toc]`.

Copyright (C) 2026 zotero-agent contributors.
Licensed under the GNU Affero General Public License v3 or later; see LICENSE.
"""

__version__ = "0.5.0"
