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
- **Python 3.9+**. The CLI core is stdlib-only; the MCP server needs the `[mcp]`
  extra.
- macOS or Linux. Windows works too — see [OS paths](#os-paths) below.

## 1. Install the CLI

```bash
uv tool install zotero-agent            # CLI only
uv tool install "zotero-agent[mcp]"     # CLI + MCP server (for AI agents)
# or, with pipx:
pipx install zotero-agent
pipx install "zotero-agent[mcp]"
```

This puts `zot` on your `PATH`.

## 2. Install the bridge plugin

The bridge is a small plugin that exposes one token-protected endpoint,
`POST /zotero-agent`, inside Zotero. Install it through the standard Zotero flow —
**you do not need to close Zotero**:

1. Download `zotero-agent-bridge.xpi` from the project's
   [GitHub Releases](https://github.com/alex-roc/zotero-agent/releases).
2. In Zotero: **Tools → Plugins**, click the **gear icon** (top-right) →
   **"Install Plugin From File…"**.
3. Select the `.xpi`. "Zotero Agent Bridge" appears in the list, enabled. The
   endpoint registers on load — no restart required.

:::caution[Unsigned plugin warning]
Zotero will warn that the plugin is not signed / from an unknown source. That is
expected for a self-built or self-distributed plugin — proceed. See the
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
bridge endpoint  : up (1+1 == 2)
userID           : 2960998
```

If the **bridge endpoint** shows `FAIL`, the plugin is not loaded — reinstall the
`.xpi` via *Tools → Plugins → gear → Install Plugin From File…* and confirm it is
enabled.

## Installing from a checkout

From a git checkout, `./install.sh` wires up everything for local development: it
links the Claude Code skill into `~/.claude/skills/`, puts a dev `zot` on your
`PATH`, runs `zot init`, and builds the XPI (`dist/zotero-agent-bridge.xpi`). You
still install that XPI in Zotero as in step 2.

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

Remove "Zotero Agent Bridge" from *Tools → Plugins*, then `uv tool uninstall
zotero-agent` (or `pipx uninstall`), and delete `~/.config/zotero-agent/`.
