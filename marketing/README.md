# Launch materials (DRAFTS)

Everything in this folder is a **draft** for the launch of `zotero-agent`. Nothing
here is posted automatically. Read each file, edit it in your own voice, and post
it yourself when you're ready. These are starting points, not final copy.

Repo: https://github.com/alex-roc/zotero-agent · License: MIT

## Tagline

> Full local control of your Zotero library — from your terminal or your AI agent.
> No cloud, no API key.

## Cadence rules

Slow and honest beats a spammy blast. Concretely:

- **Max one channel per day.** Don't cross-post everywhere on launch day. Space
  it out so you can actually be present for each one.
- **Respond to every comment for the first 3 days** on each channel. A launch is
  a conversation, not a broadcast. Questions and criticism in the first days are
  the most valuable feedback you'll get.
- **Gate Show HN.** Do not post to Hacker News until *all* of these are true:
  - [ ] Package is live on PyPI (`uv tool install "zotero-agent[mcp]"` works clean)
  - [ ] MCP server verified working in **≥2 clients** (e.g. Claude Desktop + one
        of Codex CLI / Gemini CLI / Cursor)
  - [ ] Tested on **Linux** (not just macOS)
  - [ ] Cookbook / docs site is **live** and linkable
  HN traffic is one-shot and unforgiving — only spend it when the on-ramp is solid.

## Suggested order

1. Zotero forums (the people who've wanted this since 2016)
2. r/zotero (with a GIF)
3. Awesome-lists + directory submissions (rolling, low-effort)
4. Show HN — **only after the gate above is green**

## Channel checklist

- [ ] `zotero-forums-post.md` — forums.zotero.org announcement
- [ ] `reddit-r-zotero.md` — r/zotero post (+ GIF)
- [ ] `show-hn.md` — Hacker News (gated, see above)
- [ ] `awesome-lists.md` — awesome-zotero
- [ ] `awesome-lists.md` — awesome-mcp-servers
- [ ] `awesome-lists.md` — Glama
- [ ] `awesome-lists.md` — Smithery
- [ ] `awesome-lists.md` — mcpservers.org
- [ ] `awesome-lists.md` — PulseMCP
- [ ] `awesome-lists.md` — awesome-claude-code / awesome-claude-skills
- [ ] `awesome-lists.md` — official Zotero plugin directory (plugin only)
- [ ] `github-repo-metadata.md` — set About, topics, social-preview image
- [ ] `metrics.md` — wire up tracking before/at launch

## Files here

| File | What it's for |
|------|---------------|
| `README.md` | This index. |
| `zotero-forums-post.md` | Announcement thread for the Zotero forums. |
| `reddit-r-zotero.md` | r/zotero post led by a concrete story. |
| `show-hn.md` | Show HN title + first comment. |
| `awesome-lists.md` | Exact one-line entries + target list/file, in submission order. |
| `github-repo-metadata.md` | Repo About, topics, social-preview spec. |
| `metrics.md` | What to track and with which free tools. |
