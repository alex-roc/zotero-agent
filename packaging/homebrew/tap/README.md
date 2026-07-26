# alex-roc/homebrew-tap

Homebrew formulae for [zotero-agent](https://github.com/alex-roc/zotero-agent) —
local read-write control of a Zotero library, from your terminal or your AI agent.

```bash
brew install alex-roc/tap/zotero-agent
```

That is the whole install: the formula ships the CLI **and** both optional
extras, so `zot mcp` (the MCP server) and `zot toc` (PDF outlines) work out of
the box. Homebrew replaces a keg wholesale on every upgrade, so there is no way
to add an extra afterwards — hence everything, up front.

Then finish the setup in Zotero (the bridge plugin is a separate one-click
install): see the [install guide](https://alex-roc.github.io/zotero-agent/getting-started/install/).

```bash
brew upgrade zotero-agent     # the CLI; the Zotero plugin updates itself
brew uninstall zotero-agent   # config/state live outside the keg, see the guide
```

## How this tap stays current

Nothing here is written by hand. The formula is generated in the main repo
(`scripts/gen_homebrew_formula.py`) from the sdist each release publishes to PyPI,
and `.github/workflows/sync.yml` mirrors it here when that release happens, then
installs and `brew test`s it on macOS before you ever see it. Report issues in the
[main repo](https://github.com/alex-roc/zotero-agent/issues).
