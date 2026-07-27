---
title: Install
description: Install the zot CLI, the bridge plugin XPI, and verify the setup with zot ping.
---

Installing `zotero-agent` is two parts: the **`zot` CLI** (a Python package) and
the **bridge plugin** (a one-click XPI you load from Zotero's UI — no restart
needed). The plugin is what makes local writes possible; without it, `zot` can
only read.

## Requirements

- **Zotero 7+** (tested through 9.x) running, with its local API enabled (the
  default).
- **Python 3.10+**. The CLI core is stdlib-only; the MCP server needs the `[mcp]`
  extra and the PDF outline commands need `[toc]`.
- macOS or Linux. Windows works too — see [OS paths](#os-paths) below.

## 1. Install the CLI

```bash
uv tool install zotero-agent            # CLI only
uv tool install "zotero-agent[mcp]"     # CLI + MCP server (for AI agents)
uv tool install "zotero-agent[toc]"     # CLI + PDF engine (zot toc)
uv tool install "zotero-agent[mcp,toc]" # everything
# or, with pipx:
pipx install zotero-agent
pipx install "zotero-agent[mcp]"
```

The core is stdlib-only; the two extras are the only dependencies, and each is
optional:

| Extra | Pulls in | Enables |
|-------|----------|---------|
| `mcp` | `mcp` | `zot mcp`, the Model Context Protocol server |
| `toc` | `pymupdf` | `zot toc`, reading and writing PDF outlines |

`zot toc` without the extra exits with the exact command that fixes it, so
installing it later is fine. Note that PyMuPDF is a multi-megabyte binary wheel —
that, not licensing, is why it is not a hard dependency (this project is
AGPL-3.0, the same licence).

This puts `zot` on your `PATH`.

### Homebrew (macOS / Linux)

```bash
brew install alex-roc/tap/zotero-agent
```

One command, and unlike the uv/pipx routes it ships **both extras** — `zot mcp`
and `zot toc` work immediately. That is not generosity: Homebrew replaces a keg
wholesale on every upgrade, so an extra added afterwards would vanish at the next
`brew upgrade`. Budget ~35 MB of downloads and ~100 MB installed, most of it
PyMuPDF.

```bash
brew upgrade zotero-agent    # the CLI; the Zotero plugin updates itself
```

Installed by two routes at once (uv first, then Homebrew)? **`PATH` order decides
which one runs** — on macOS `/opt/homebrew/bin` normally precedes `~/.local/bin`, so
the Homebrew one wins. `command -v zot` tells you which; both share the same config
and state, so neither needs reconfiguring.

:::note[How the formula stays honest]
It is generated from the sdist each release publishes to PyPI and mirrored into
[the tap](https://github.com/alex-roc/homebrew-tap) as part of that release, which
also installs and tests it on macOS before you see it. So it can trail a fresh
release by a few minutes — but it can never disagree with one. For a new version
the moment it lands, use `uv tool upgrade zotero-agent`.
:::

## 2. Install the bridge plugin

The bridge is a small plugin that exposes one token-protected endpoint,
`POST /zotero-agent`, inside Zotero. Install it through the standard Zotero flow —
**you do not need to close Zotero**:

1. Download the XPI. It is published in one place only, and this link always
   resolves to the newest one:

   [**zotero-agent-bridge.xpi**](https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi)

2. In Zotero: **Tools → Plugins**, click the **gear icon** (top-right) →
   **"Install Plugin From File…"**.
3. Select the `.xpi`. "Zotero Agent Bridge" appears in the list, enabled. The
   endpoint registers on load — no restart required.

You do this **once**: from then on Zotero keeps the plugin updated itself (see
[Updating](#updating)).

:::caution[Unsigned plugin warning]
Zotero will warn that the plugin is not signed / from an unknown source — expected
for a plugin distributed outside Zotero's directory. Proceed; the
[security model](/zotero-agent/security/#distribution--updates) covers the trust
chain (built in CI from the tag, updates verified by `sha256`). See the
[FAQ](/zotero-agent/faq/) if the install is blocked.
:::

## 3. Initialize and verify

```bash
zot init      # generate a token, write config (0600), auto-detect your userID
zot ping      # verify all three layers are live
```

A healthy `zot ping` looks like this:

```console
$ zot ping
Zotero local API : up (HTTP 200)
bridge endpoint  : up (/zotero-agent, 1+1 == 2)
bridge plugin    : 0.5.0
userID           : 2960998
zot version      : 0.5.0
zot source       : ~/.local/share/uv/tools/zotero-agent/lib/python3.13/site-packages/zotero_agent
```

If the **bridge endpoint** shows `FAIL`, the plugin is not loaded — reinstall the
`.xpi` via *Tools → Plugins → gear → Install Plugin From File…* and confirm it is
enabled. **bridge plugin** is the version the installed plugin reports; when it
differs from **zot version**, `ping` tells you which side to update.

**zot source** says which install answered, which matters when more than one route
is present — they all report the same version. `~/.local/share/uv/…` is uv,
`/opt/homebrew/Cellar/…` is Homebrew, and a path outside any `site-packages` is a
checkout, which `zot --version` also marks as `(dev)`. Please include this line in
bug reports.

## Updating

The CLI and the plugin ship together and share a version number.

```bash
uv tool upgrade zotero-agent      # or: pipx upgrade zotero-agent
brew upgrade zotero-agent         # if you installed it with Homebrew
```

If `zot --version` still shows the previous release, uv is using cached index
metadata — force a refresh:

```bash
uv tool install --force --refresh --with mcp zotero-agent
```

**The plugin updates itself.** Its manifest points at an `update_url`
(`updates.json` in the repo), so Zotero picks up new releases like it does for any
other plugin — the manual XPI install happens exactly once.

Zotero checks **once a day** (`extensions.update.interval` = 86400s), so straight
after a release `zot ping` may still show the previous plugin version. To pull it
in now:

*Tools → Plugins → the **gear icon** (top-right of the Plugins window) → **Check
for Updates***

:::note
That gear belongs to the plugin **list**, not to a plugin's detail pane — the
detail pane only has "Allow automatic updates" (leave it on *Default*). If you are
looking at Zotero Agent Bridge's details, go back first.
:::

Then run `zot ping`: `bridge plugin` and `zot version` should agree. If Zotero
never offers the update, see the troubleshooting snippet in
[`docs/install.md`](https://github.com/alex-roc/zotero-agent/blob/main/docs/install.md#updating),
which asks Zotero's own AddonManager what it sees.

## 4. The agent skill (optional)

The Claude Code skill is bundled in the package too — no clone required:

```bash
zot skill install                 # -> ~/.claude/skills/zotero
zot skill install --project       # -> ./.claude/skills/zotero (one project only)
zot skill install --force         # replace an existing install
zot skill path                    # where the bundled copy lives
zot skill agents-md > AGENTS.md   # portable instructions for any shell agent
```

Start a **new** Claude Code session to pick it up, then just ask about your
library. Prefer MCP instead? `claude mcp add zotero-agent -- zot mcp` (needs the
`[mcp]` extra).

## Installing from a checkout

From a git checkout, `./install.sh` wires up everything for local development: it
puts a dev `zot` on your `PATH`, runs `zot skill install --link` (so edits to
`skill/` take effect immediately), runs `zot init`, and builds a local XPI into
`dist/` — the same artifact releases publish. You still install it in Zotero as in
step 2.

## The token

`zot init` writes a random token to `~/.config/zotero-agent/config.json` with
`0600` permissions. The plugin reads that same file, so **rotating the token
needs no Zotero restart** — just edit the file. If you prefer a Zotero pref, set
`extensions.zotero-agent.token`; it takes precedence over the config file. See
[Configuration](/zotero-agent/reference/configuration/) and the
[security model](/zotero-agent/security/).

## Shell completion (optional)

`zot completion <shell>` prints a completion script for `bash`, `zsh`, or `fish`
— it completes subcommand names and global flags, with no extra dependency:

```bash
eval "$(zot completion bash)"   # in ~/.bashrc
eval "$(zot completion zsh)"    # in ~/.zshrc
zot completion fish > ~/.config/fish/completions/zot.fish
```

## OS paths

`zot init` detects your Zotero profile automatically; these are only for manual
checks:

| OS | Profile location |
|----|------------------|
| macOS | `~/Library/Application Support/Zotero/Profiles/<random>.default*` |
| Linux | `~/.zotero/zotero/<random>.default*` |
| Windows | `%APPDATA%\Zotero\Zotero\Profiles\<random>.default*` |

## Uninstall

1. **The plugin** — remove "Zotero Agent Bridge" from *Tools → Plugins*. No
   restart needed; the XPI leaves your profile's `extensions/`.

2. **The CLI** — however you installed it:

   ```bash
   uv tool uninstall zotero-agent          # or: pipx uninstall zotero-agent
   brew uninstall zotero-agent             # if you installed it with Homebrew
   rm ~/.local/bin/zot ~/.claude/skills/zotero   # the ./install.sh dev symlinks
   ```

3. **State on disk** — two directories, neither removed by uninstalling the
   package:

   ```bash
   rm -rf ~/.config/zotero-agent      # config.json (token, userID) + backups/
   rm -rf ~/.local/state/zotero-agent # audit.jsonl + undo/ snapshots
   ```

   Deleting `undo/` discards the snapshots `zot undo` restores from — keep it if
   you may still want to reverse a past `zot apply`.

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
