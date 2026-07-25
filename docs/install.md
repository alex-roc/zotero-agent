# Installation

Two parts: the **`zot` CLI** (+ optional MCP server / Claude Code skill), and the
**`zotero-agent` bridge plugin** (a one-click XPI install from Zotero's UI — no
restart needed).

## Install the CLI

The easy path (no checkout needed):

```bash
uv tool install zotero-agent           # or: pipx install zotero-agent
uv tool install "zotero-agent[mcp]"    # include the MCP server (zot mcp)
```

The package also carries the agent surfaces, so no clone is needed for those:

```bash
zot skill install                 # the Claude Code skill -> ~/.claude/skills/zotero
zot skill agents-md > AGENTS.md   # the portable agent instructions
```

From a checkout (developer):

```bash
git clone https://github.com/alex-roc/zotero-agent.git && cd zotero-agent
./install.sh
```

`install.sh`:

1. symlinks a dev `zot` onto your `PATH` (`~/.local/bin/zot`, runs from `./src`),
2. runs `zot skill install --link` → `~/.claude/skills/zotero` (a symlink, so
   edits to `skill/` take effect immediately),
3. builds a local plugin XPI into `dist/` (releases publish that same artifact),
4. runs `zot init` (generates/imports token, writes config, detects profile).

Then install the plugin (next section) and re-run `zot init` to auto-detect
your userID. Finish with `zot ping`.

## The agent skill

The skill ships **inside the package**, so PyPI users get it too:

```bash
zot skill install                 # -> ~/.claude/skills/zotero
zot skill install --project       # -> ./.claude/skills/zotero (this repo only)
zot skill install --force         # replace an existing install
zot skill path                    # where the bundled copy lives
zot skill agents-md > AGENTS.md   # the portable, MCP-free instructions
```

Pick it up in a **new** Claude Code session.

## Installing the zotero-agent bridge plugin

One route, one file — the XPI is published **only** as a release asset, and this
link always points at the newest one:

<https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi>

The standard Zotero flow — **no need to close Zotero.**

1. Download the XPI from that link.

2. In Zotero: **Tools → Plugins**, click the **gear icon** (top-right of the
   Plugins window) → **"Install Plugin From File…"**.

3. Select that `.xpi`. The plugin "Zotero Agent Bridge" appears in the list,
   enabled. No restart required — the `POST /zotero-agent` endpoint registers on load.

Contributors can build the same artifact from a checkout with
`bash plugin/build.sh` (a deterministic zip that stamps the package version into
the plugin, so a build is reproducible and never disagrees with the CLI).

> Zotero will warn that the plugin is not signed / from an unknown source.
> That is expected for a self-built plugin; proceed.

To confirm it loaded, check *Tools → Plugins* for "Zotero Agent Bridge", or just run
`zot ping`.

## Token

`zot init` writes a random token to `~/.config/zotero-agent/config.json`
(`0600`). The plugin reads that same file — no extra step, no restart needed to
rotate it. If you prefer a Zotero pref, set `extensions.zotero-agent.token`; it takes
precedence. See `security.md`.

## Verify

```bash
zot ping
# Zotero local API : up (HTTP 200)
# bridge endpoint  : up (/zotero-agent, 1+1 == 2)
# bridge plugin    : 0.2.1
# userID           : 2960998
# zot version      : 0.2.1
```

If the endpoint is FAIL, the plugin is not loaded — reinstall the XPI via
*Tools → Plugins → gear → Install Plugin From File…* and check it is enabled.
The **bridge plugin** line is the installed plugin's own version; when it differs
from `zot version`, `ping` says which side to update.

## Updating

The CLI and the plugin are released together and share a version number.

```bash
uv tool upgrade zotero-agent      # the CLI (or: pipx upgrade zotero-agent)
```

**The plugin updates itself.** Its manifest declares an `update_url` pointing at
[`updates.json`](../updates.json) in this repo, so Zotero notices a new release
and upgrades the plugin the way it does for any other plugin — you install the
XPI by hand exactly once. To force a check: *Tools → Plugins → gear → Check for
Updates*. Run `zot ping` afterwards to confirm both sides match.

If `ping` reports a plugin older than the CLI and Zotero is not offering the
update, check that plugin auto-updates are enabled in Zotero, or reinstall the
XPI from the link above.

## Shell completion (optional)

`zot completion <shell>` prints a completion script for `bash`, `zsh`, or `fish`:

```bash
# bash — in ~/.bashrc:
eval "$(zot completion bash)"
# zsh — in ~/.zshrc:
eval "$(zot completion zsh)"
# fish:
zot completion fish > ~/.config/fish/completions/zot.fish
```

It completes subcommand names and the global flags; no extra dependency.

## Uninstall

1. **The plugin** — remove "Zotero Agent Bridge" from *Tools → Plugins*. No
   restart needed. (This deletes the XPI from your profile's `extensions/`.)

2. **The CLI** — however you installed it:

   ```bash
   uv tool uninstall zotero-agent          # or: pipx uninstall zotero-agent
   brew uninstall zotero-agent
   rm ~/.local/bin/zot ~/.claude/skills/zotero   # the ./install.sh dev symlinks
   ```

3. **State on disk** — two directories, neither removed by uninstalling the
   package:

   ```bash
   rm -rf ~/.config/zotero-agent      # config.json (token, userID) + backups/
   rm -rf ~/.local/state/zotero-agent # audit.jsonl + undo/ snapshots
   ```

   > Deleting `undo/` discards the snapshots `zot undo` restores from. Keep it if
   > you may still want to reverse a past `zot apply`.

4. **Agent wiring**, if you added it — `claude mcp remove zotero-agent`, plus any
   entry you made in `claude_desktop_config.json`, `~/.codex/config.toml`,
   `~/.gemini/settings.json` or `.cursor/mcp.json`, and the
   `eval "$(zot completion …)"` line in your shell rc.

To confirm nothing is left (e.g. before testing a fresh install):

```bash
command -v zot                                    # nothing
ls -d ~/.config/zotero-agent ~/.local/state/zotero-agent   # No such file
ls ~/Library/Application\ Support/Zotero/Profiles/*/extensions | grep zotero-agent
```

## OS paths (reference)

`zot init` detects your profile automatically; these are only for manual checks:

- **macOS** `~/Library/Application Support/Zotero/Profiles/<random>.default*`
- **Linux** `~/.zotero/zotero/<random>.default*`
- **Windows** `%APPDATA%\Zotero\Zotero\Profiles\<random>.default*`
