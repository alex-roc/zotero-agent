# Installation

Two parts: the **`zot` CLI** (+ optional MCP server / Claude Code skill), and the
**`zotero-agent` bridge plugin** (a one-click XPI install from Zotero's UI — no
restart needed).

## Install the CLI

The easy path (no checkout needed):

```bash
uv tool install zotero-agent           # or: pipx install zotero-agent
uv tool install "zotero-agent[mcp]"    # include the MCP server (zot mcp)
uv tool install "zotero-agent[toc]"    # include the PDF engine (zot toc)
uv tool install "zotero-agent[mcp,toc]"   # both
```

Needs **Python 3.10+**. The core is stdlib-only; the two extras are the only
dependencies, and each is optional:

| Extra | Pulls in | Enables |
|-------|----------|---------|
| `mcp` | `mcp` | `zot mcp`, the Model Context Protocol server |
| `toc` | `pymupdf` | `zot toc`, reading and writing PDF outlines; `zot pdf-prep`, splitting scans |

`zot toc` without the extra exits with the exact command that fixes it, so
installing it later is fine. Note that PyMuPDF is a multi-megabyte binary wheel —
that, not licensing, is why it is not a hard dependency (this project is
AGPL-3.0, the same licence).

### Preparing scanned PDFs (`zot pdf-prep`)

Splitting a two-up scan needs only the `[toc]` extra. Adding a **text layer**
also needs [OCRmyPDF] and its own dependencies, which are programs rather than
Python packages, so they are installed by the system's package manager:

```bash
brew install ocrmypdf tesseract-lang unpaper jbig2enc   # macOS
sudo apt install ocrmypdf tesseract-ocr-spa unpaper     # Debian/Ubuntu
```

`tesseract-lang` (or `tesseract-ocr-<lang>`) is what makes languages other than
English available — without it, OCR of a Spanish book silently comes out wrong
rather than failing. `unpaper` powers `--clean`, which despeckles the image
before recognition and measurably improves the text; `jbig2enc` shrinks bitonal
scans further. Running `zot pdf-prep` without OCRmyPDF exits with these exact
commands, and `--no-ocr` splits and optimises without it.

[OCRmyPDF]: https://ocrmypdf.readthedocs.io/

### Homebrew (macOS / Linux)

```bash
brew install alex-roc/tap/zotero-agent
```

That single command is the whole CLI: unlike the uv/pipx routes, the formula
ships **both extras**, so `zot mcp` and `zot toc` work immediately. It has to —
Homebrew replaces a keg wholesale on every upgrade, so anything added to it
afterwards would vanish at the next `brew upgrade`. Expect ~35 MB of downloads
and ~100 MB installed, most of it PyMuPDF.

```bash
brew upgrade zotero-agent    # the CLI; the Zotero plugin updates itself
```

If you installed by two routes at once (say uv first, then Homebrew), **`PATH`
order decides which one runs** — on macOS `/opt/homebrew/bin` normally comes before
`~/.local/bin`, so the Homebrew one wins. `command -v zot` tells you which, and
both share the same config and state, so nothing needs reconfiguring either way.

The formula is generated from the sdist each release publishes to PyPI and
mirrored into [the tap](https://github.com/alex-roc/homebrew-tap) as part of that
release, which also installs and tests it on macOS before you see it. It can
therefore trail a fresh release by a few minutes, but it can never disagree with
one. If you want a new version the moment it lands, use `uv tool upgrade`.

The package also carries the agent surfaces (skill, `AGENTS.md`) — see
[The agent skill](#the-agent-skill) below; no clone needed for those either.

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
> Expected: it is distributed outside Zotero's plugin directory. Proceed — see
> [`security.md`](security.md#distribution--updates) for the trust chain (CI build
> + `sha256`-verified updates).

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
# bridge plugin    : 0.5.0
# userID           : 2960998
# zot version      : 0.5.0
# zot source       : ~/.local/share/uv/tools/zotero-agent/lib/python3.13/site-packages/zotero_agent
```

If the endpoint is FAIL, the plugin is not loaded — reinstall the XPI via
*Tools → Plugins → gear → Install Plugin From File…* and check it is enabled.
The **bridge plugin** line is the installed plugin's own version; when it differs
from `zot version`, `ping` says which side to update.

The **zot source** line says which install answered — useful when more than one
route is present, since they all report the same version: `~/.local/share/uv/…`
is uv, `/opt/homebrew/Cellar/…` is Homebrew, and a path outside any
`site-packages` is a checkout, which `zot --version` also marks as `(dev)`.
Include this line in bug reports.

## Updating

The CLI and the plugin are released together and share a version number.

```bash
uv tool upgrade zotero-agent      # the CLI (or: pipx upgrade zotero-agent)
brew upgrade zotero-agent         # if you installed it with Homebrew
```

If `zot --version` still reports the old one, uv is serving cached index
metadata — add `--refresh`:

```bash
uv tool install --force --refresh --with mcp zotero-agent
```

**The plugin updates itself.** Its manifest declares an `update_url` pointing at
[`updates.json`](../updates.json) in this repo, so Zotero notices a new release
and upgrades the plugin the way it does for any other plugin — you install the
XPI by hand exactly once.

Zotero checks **once every 24 hours** (`extensions.update.interval`), so right
after a release your plugin will still report the old version for a while. That
is normal. To pull it in immediately:

*Tools → Plugins → the **gear icon** (top-right of the Plugins window) → **Check
for Updates***

The gear menu belongs to the plugin *list*; it is not in a plugin's detail pane
(where "Allow automatic updates" lives — leaving that on *Default* is correct).
Then run `zot ping`: `bridge plugin` and `zot version` should match.

If Zotero asks for a restart to finish the update, you do not have to leave the
terminal:

```bash
zot restart --plugin   # reload just the bridge; Zotero stays open
zot restart            # restart Zotero itself
```

Both wait until `POST /zotero-agent` answers again and then print the plugin
version, so whatever you run next will reach a live bridge. `zot restart` also
starts Zotero when it is not running at all (`--no-launch` if you would rather it
did not). Being disruptive, both prompt for confirmation — scripts and agents
must pass `--yes`.

If Zotero does not offer the update, ask it directly what it sees:

```bash
zot exec 'var {AddonManager} = ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
var a = await AddonManager.getAddonByID("zotero-agent-bridge@zotero-agent");
return await new Promise(function (resolve) {
  var res = { installedVersion: a.version, updateFound: false };
  a.findUpdates({
    onUpdateAvailable: function (addon, i) { res.updateFound = true; res.offeredVersion = i.version; },
    onNoUpdateAvailable: function () {},
    onUpdateFinished: function (addon, status) { res.status = status; resolve(res); }
  }, AddonManager.UPDATE_WHEN_USER_REQUESTED);
});'
```

`status: 0` with an `offeredVersion` means the update path is healthy (this only
queries; it installs nothing). If it reports no update, check `a.updateURL` and
that `updates.json` on `main` announces the new version. Worst case, reinstall
the XPI from the permanent link above.

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
   brew uninstall zotero-agent             # if you installed it with Homebrew
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
