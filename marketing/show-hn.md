# Show HN

**Gate (from README.md):** do not post until PyPI is live, MCP is verified in ≥2
clients, Linux is tested, and the cookbook is live.

**When:** submit on a weekday morning US time (roughly 8-10am ET) for the best
shot at the front page. Post the first comment immediately after submitting, then
stay in the thread for the day. HN rewards candor and punishes hype — be plain
about what it is and what the trade-offs are.

---

## Title

```
Show HN: Local read-write CLI and MCP server for Zotero (no account or API key)
```

## URL

```
https://github.com/alex-roc/zotero-agent
```

## First comment (post immediately after submitting)

Author here. Zotero (the reference manager) ships a local HTTP API, but it's
**read-only** — every write returns 501/400 and there's no pref to enable it. So
the existing automation tools (zotero-mcp, pyzotero) can only write through the
*zotero.org web API*, which means a cloud account, an API key, and sync turned on.
There was no way to edit your library locally and offline.

zotero-agent is my take on the local path. It's three pieces:

- a **bridge plugin** that registers one endpoint, `POST /zotero-agent`, running
  privileged JS inside Zotero's own context — the only complete local write path;
- a stdlib-only **CLI** (`zot`): search, bulk metadata edit (previewed + undoable),
  dedupe/merge (incl. fuzzy), enrich missing DOI/date/abstract from Crossref and
  OpenAlex, tag normalize, import by DOI/ISBN/arXiv, export bibtex/ris/csljson,
  summarize a PDF into a note;
- an **MCP server** so agents (Claude Desktop, Codex CLI, Gemini CLI, Cursor) and
  the Claude Code skill can drive all of the above.

**On the security trade-off, since it matters:** that endpoint runs *arbitrary
privileged JavaScript*. That's deliberate — it's what buys a complete local write
path — but it's the thing to scrutinize. It's guarded by three layers: (1) a
required token, fail-closed (no token → 403), stored `0600`; (2) an origin/host
guard so a web page in your browser can't reach it (browser Origin → connection
closed; non-loopback Host → 400) — that plus the token closes the CSRF /
DNS-rebinding surface; (3) loopback-only binding. What the token does **not**
defend against is other code already running locally as your user — it's not a
sandbox, it's a local write path. Full writeup:
https://github.com/alex-roc/zotero-agent/blob/main/docs/security.md

It's MIT. `uv tool install "zotero-agent[mcp]"` then install the plugin XPI from
Releases. It's early — feedback, and especially holes in the security model, very
welcome.

---

**Reminder:** don't editorialize the title after posting, don't ask for upvotes,
and reply to critical comments first — those are where the trust is won.
