# GitHub repo metadata

Set these on the repo (Settings + the "About" gear on the repo home page).

## About / description

Short description field (shows under the repo name, ~160 char budget):

```
Full local read-write control of your Zotero library from a CLI or AI agent (MCP). No zotero.org account, no API key, no cloud.
```

Website field: point at the docs site once it's live (GitHub Pages URL).

## Topics

Add all of these (Settings → About → topics):

```
zotero
zotero-plugin
cli
claude-code
claude-skill
mcp
ai-agent
reference-manager
bibliography
local-first
```

Optional extras worth considering: `mcp-server`, `crossref`, `openalex`,
`citation`, `python`.

## Social preview image

**Spec:** 1280×640 PNG (GitHub renders the Open Graph preview at this ratio; it's
what shows when the repo is linked on HN, Reddit, Slack, X, etc.).

- **Set at:** Settings → General → Social preview → Upload an image.
- **Content:**
  - Project name `zotero-agent` — large, top-left or centered.
  - Tagline underneath: *"Full local control of your Zotero library — from your
    terminal or your AI agent. No cloud, no API key."*
  - The ASCII architecture diagram, drawn nicely (redrawn as clean typeset boxes
    and arrows, monospace, not a raw screenshot of text):

    ```
    Agent / user
        │
        ▼
    ┌──────────────────────────────────┐
    │  MCP server  │  skill  │  zot CLI │
    └──────────────────────────────────┘
        │                         │
        ▼ read                    ▼ write
    Zotero local API /api/…   POST /zotero-agent
        (GET, fast)           (bridge plugin, JS)
    ```
  - Small "MIT" tag and the GitHub URL along the bottom.
- **Style:** high contrast, works as a thumbnail; readable in both light and dark
  feeds. Keep generous margins — social cards crop edges. Terminal/monospace
  aesthetic fits the product. Leave real breathing room; don't cram.
- **Alt text** (for the repo README's hero image if reused there): "zotero-agent
  architecture: an agent or user drives an MCP server, Claude skill, or the zot
  CLI, which reads from Zotero's local API and writes through the bridge plugin
  endpoint."
