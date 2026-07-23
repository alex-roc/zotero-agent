# Installation

Two parts: the **`zot` CLI + skill** (easy, `install.sh`), and the
**`zotero-exec` plugin** (a one-click XPI install from Zotero's UI — no restart
needed).

## Quick path

```bash
git clone https://github.com/alex-roc/zotero-cli-skill.git && cd zotero-cli-skill
./install.sh
```

`install.sh`:

1. symlinks `skill/` → `~/.claude/skills/zotero` (for Claude Code),
2. copies `cli/zot` and the plugin into `skill/scripts/` (self-contained skill),
3. symlinks `zot` onto your `PATH` (`~/.local/bin/zot`),
4. runs `zot init` (generates token, writes config, detects profile),
5. **builds the plugin XPI** (`dist/zotexec.xpi`) and prints the install steps.

Then install the plugin (next section) and re-run `zot init` to auto-detect
your userID. Finish with `zot ping`.

## Installing the zotero-exec plugin

The standard Zotero flow — **no need to close Zotero.**

1. Build the XPI (done for you by `install.sh`; manually: `bash plugin/build.sh`).
   Result: `dist/zotexec.xpi`.

2. In Zotero: **Tools → Plugins**, click the **gear icon** (top-right of the
   Plugins window) → **"Install Plugin From File…"**.

3. Select `dist/zotexec.xpi`. The plugin "Zotero Exec" appears in the list,
   enabled. No restart required — the `POST /zotexec` endpoint registers on load.

> Zotero will warn that the plugin is not signed / from an unknown source.
> That is expected for a self-built plugin; proceed.

To confirm it loaded, check *Tools → Plugins* for "Zotero Exec", or just run
`zot ping`.

## Token

`zot init` writes a random token to `~/.config/zotero-exec/config.json`
(`0600`). The plugin reads that same file — no extra step, no restart needed to
rotate it. If you prefer a Zotero pref, set `extensions.zotexec.token`; it takes
precedence. See `security.md`.

## Verify

```bash
zot ping
# Zotero local API : up (HTTP 200)
# zotexec endpoint : up (1+1 == 2)
# userID           : 2960998
```

If the endpoint is FAIL, the plugin is not loaded — reinstall `dist/zotexec.xpi`
via *Tools → Plugins → gear → Install Plugin From File…* and check it is enabled.

## Uninstall

Remove "Zotero Exec" from *Tools → Plugins*, then remove
`~/.claude/skills/zotero` and `~/.local/bin/zot`, and delete
`~/.config/zotero-exec/`.

## OS paths (reference)

`zot init` detects your profile automatically; these are only for manual checks:

- **macOS** `~/Library/Application Support/Zotero/Profiles/<random>.default*`
- **Linux** `~/.zotero/zotero/<random>.default*`
- **Windows** `%APPDATA%\Zotero\Zotero\Profiles\<random>.default*`
