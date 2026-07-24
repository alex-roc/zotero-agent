# Awesome-list & directory submissions

Submit in the order below. Each is a low-effort PR or form. Space them out (one
channel/day rule still applies — batch the trivial directory submissions, but
don't let them crowd out the days you spend on forums/Reddit/HN).

For every submission: read the list's CONTRIBUTING before opening the PR, keep the
entry alphabetized where the section requires it, and match the surrounding
formatting exactly.

**Canonical one-liner** (reuse everywhere, trim per list style):

> **zotero-agent** — Full local read-write control of a Zotero library from a CLI or AI agent (MCP). No zotero.org account, API key, or cloud.

---

## 1. awesome-zotero

- **Repo:** https://github.com/mohamedelashri/awesome-zotero
- **Target:** `README.md`, under a tools/automation/CLI section (pick the closest
  existing heading; propose one if none fits).
- **Entry:**
  ```markdown
  - [zotero-agent](https://github.com/alex-roc/zotero-agent) — Full local read-write control of a Zotero library from a CLI (`zot`) or AI agent (MCP). No account, API key, or cloud.
  ```

## 2. awesome-mcp-servers

- **Repo:** https://github.com/punkpeye/awesome-mcp-servers (the most-followed one;
  there are forks — submit to this one).
- **Target:** `README.md`, likely a "Knowledge & Memory" or "Developer Tools" /
  research category. Note the emoji legend the list uses (language, scope) and
  apply the right badges (Python; local/self-hosted).
- **Entry:**
  ```markdown
  - [alex-roc/zotero-agent](https://github.com/alex-roc/zotero-agent) 🐍 🏠 — Local read-write control of a Zotero reference library. Search, bulk-edit, dedupe, enrich, tag, import, export. No account or API key.
  ```

## 3. Glama

- **Where:** https://glama.ai/mcp/servers — Glama auto-indexes public MCP servers
  from GitHub. Make sure the repo README has a clear MCP section and the
  `mcp` topic set, then claim/submit the server via the Glama site.
- **Entry / listing text (short description field):**
  ```
  Local read-write control of a Zotero library over MCP — search, bulk-edit, dedupe, enrich, tag, import, export. Runs offline; no account or API key.
  ```

## 4. Smithery

- **Where:** https://smithery.ai — submit via "Add Server"; it reads the repo.
  A `smithery.yaml` in the repo improves the listing (add one later if wanted).
- **Listing text:**
  ```
  zotero-agent — MCP server for full local read-write control of a Zotero library. No zotero.org account or API key; nothing leaves the machine.
  ```

## 5. mcpservers.org

- **Where:** https://mcpservers.org — submission is a PR to its GitHub repo
  (https://github.com/wong2/awesome-mcp-servers backs the site; check its README
  for the exact submission path).
- **Entry:**
  ```markdown
  - [zotero-agent](https://github.com/alex-roc/zotero-agent) — Local read-write control of a Zotero library (search, bulk-edit, dedupe, enrich, tag, import, export). Offline; no account or API key.
  ```

## 6. PulseMCP

- **Where:** https://www.pulsemcp.com — has a "Submit" form for new servers.
- **Listing text:**
  ```
  Full local read-write control of a Zotero reference library over MCP: search, bulk metadata editing (undoable), dedupe/merge, metadata enrichment, tag normalization, import by DOI/ISBN/arXiv, export. Local-first — no account, API key, or cloud.
  ```

## 7. awesome-claude-code / awesome-claude-skills

- **awesome-claude-code:** https://github.com/hesreallyhim/awesome-claude-code
  — target the skills/tools section for the Claude Code `zotero` skill.
  ```markdown
  - [zotero-agent](https://github.com/alex-roc/zotero-agent) — Claude Code skill + CLI for full local read-write control of a Zotero library: search, bulk-edit, dedupe, enrich, tag, cite, summarize PDFs into notes.
  ```
- **awesome-claude-skills:** if a well-maintained list exists at submission time
  (search GitHub for the most-starred `awesome-claude-skills`), submit the same
  entry there, framed as a skill.

---

## Also: official Zotero plugin directory

The **bridge plugin** (not the CLI) can be listed in Zotero's official plugin
directory: https://www.zotero.org/support/plugins — plugins are added via a PR to
https://github.com/zotero/zotero-plugins (add the plugin's `id`, name, description,
and the `update.json` / release URL). This reaches Zotero users who'll never see
an MCP list. Frame it honestly as "adds a token-protected local write endpoint
used by the zotero-agent CLI/agent tooling" — and make sure the security doc is
linked, since reviewers there will care about the privileged-JS endpoint.
