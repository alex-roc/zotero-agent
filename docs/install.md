# Installation

Two parts: the **`zot` CLI + skill** (easy, `install.sh`), and the
**`zotero-agent` bridge plugin** (a one-click XPI install from Zotero's UI — no restart
needed).

## Quick path

```bash
git clone https://github.com/alex-roc/zotero-agent.git && cd zotero-agent
./install.sh
```

`install.sh`:

1. symlinks `skill/` → `~/.claude/skills/zotero` (for Claude Code),
2. copies `cli/zot` and the plugin into `skill/scripts/` (self-contained skill),
3. symlinks `zot` onto your `PATH` (`~/.local/bin/zot`),
4. runs `zot init` (generates token, writes config, detects profile),
5. **builds the plugin XPI** (`dist/zotero-agent-bridge.xpi`) and prints the install steps.

Then install the plugin (next section) and re-run `zot init` to auto-detect
your userID. Finish with `zot ping`.

## Installing the zotero-agent bridge plugin

The standard Zotero flow — **no need to close Zotero.**

1. Build the XPI (done for you by `install.sh`; manually: `bash plugin/build.sh`).
   Result: `dist/zotero-agent-bridge.xpi`.

2. In Zotero: **Tools → Plugins**, click the **gear icon** (top-right of the
   Plugins window) → **"Install Plugin From File…"**.

3. Select `dist/zotero-agent-bridge.xpi`. The plugin "Zotero Agent Bridge" appears in the list,
   enabled. No restart required — the `POST /zotero-agent` endpoint registers on load.

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
# bridge endpoint : up (1+1 == 2)
# userID           : 2960998
```

If the endpoint is FAIL, the plugin is not loaded — reinstall `dist/zotero-agent-bridge.xpi`
via *Tools → Plugins → gear → Install Plugin From File…* and check it is enabled.

## Uninstall

Remove "Zotero Agent Bridge" from *Tools → Plugins*, then remove
`~/.claude/skills/zotero` and `~/.local/bin/zot`, and delete
`~/.config/zotero-agent/`.

## OS paths (reference)

`zot init` detects your profile automatically; these are only for manual checks:

- **macOS** `~/Library/Application Support/Zotero/Profiles/<random>.default*`
- **Linux** `~/.zotero/zotero/<random>.default*`
- **Windows** `%APPDATA%\Zotero\Zotero\Profiles\<random>.default*`
