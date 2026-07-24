# r/zotero post

**Where:** r/zotero. Flair: "Add-ons" / "Tools" (whatever fits).
**Attach a GIF** (see note at bottom) — the demo is the whole post on Reddit.
Keep it short; Redditors bounce off walls of text.

---

**Title:** I let an AI agent clean up 500 items in my Zotero library — locally, no API key

**Body:**

My library had years of cruft: missing DOIs, inconsistent tags, duplicate entries
from importing the same paper twice. I finally got tired of it and built a tool so
I could just *tell* an agent to fix it — running entirely on my own machine.

zotero-agent gives you (or an AI agent) full **read-write** control of your
**local** library. The catch it solves: Zotero's local API is read-only, and the
other automation tools only write through the zotero.org web API (account + API
key + sync). This one writes locally through a tiny token-protected bridge plugin.
No account, no key, no cloud — the library never leaves the machine.

What I ran on those 500 items:
- `zot dedupe` — found and merged duplicates (including fuzzy matches)
- `zot enrich` — pulled missing DOI/date/abstract from Crossref/OpenAlex
- `zot tag normalize` — collapsed my inconsistent tag mess
- bulk metadata edits with `zot apply` — previewed, then applied, and undoable

It's a CLI (`zot`) plus an MCP server, so it works from the terminal, from Claude
Code, or via MCP in Claude Desktop / Codex CLI / Gemini CLI / Cursor.

MIT, install is `uv tool install "zotero-agent[mcp]"`.
Repo: https://github.com/alex-roc/zotero-agent

Happy to answer questions — and genuinely curious what messes other people's
libraries are in.

---

**GIF note:** attach a ~10-15s screen recording showing one concrete flow end to
end — e.g. `zot dedupe` finding duplicates, or an agent in Claude Code being told
"clean up the tags" and the change previewing then applying. Show the *preview →
apply → undoable* moment; that's the trust-builder. Keep it under ~5 MB so Reddit
plays it inline.
