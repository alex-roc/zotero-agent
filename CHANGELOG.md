# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- **The Homebrew tap is no longer an install route.** The formula installed the
  package without the `[mcp]` extra (so `zot mcp` was missing), pinned
  `python@3.13`, and needed a manual `url`/`sha256` bump per release — three
  maintenance edges for a third route that `uv tool install` already covers.
  `packaging/homebrew/` is gone; install with `uv tool` or `pipx`.

### Fixed
- The README's command table still advertised the retired `zot plugin`; a test now
  compares that table against the CLI in both directions.
- `docs/architecture.md` still described bundling the XPI into `skill/scripts/`,
  and `docs/security.md` documented no trust chain for the plugin — it now covers
  CI-built release assets and `sha256`-verified auto-updates.
- Documented the two update gotchas found while verifying 0.3.0: Zotero only
  checks for plugin updates every 24h (and the "Check for Updates" menu lives on
  the plugin *list*, not the detail pane), and `uv` may serve cached index
  metadata unless you pass `--refresh`.

## [0.3.0] — 2026-07-25

### Added
- **The agent skill now ships inside the package**, so `uv tool install
  zotero-agent` delivers it too — no clone needed:
  - **`zot skill install`** copies the skill to `~/.claude/skills/zotero`
    (`--project` for `./.claude/skills/`, plus `--dest`, `--force`, `--link`).
  - **`zot skill path`** prints where the bundled copy lives;
    **`zot skill agents-md`** writes the portable `AGENTS.md` to stdout.
- **`zot ping` now reports the installed plugin's version** and, when it differs
  from the CLI, which side to update. The bridge already returned its version;
  nothing surfaced it.
- **One route for the plugin XPI**: every release publishes a stable asset name,
  so <https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi>
  is a permanent link — used by the docs, the skill and `zot init`'s error path.
- **Docs now explain updating** (`docs/install.md`, website): `uv tool upgrade`
  for the CLI, and Zotero's own auto-update for the plugin.

### Fixed
- **Releases no longer freeze plugin auto-update.** `updates.json` — the manifest
  Zotero polls — was maintained by hand, so a new release would ship without
  announcing itself and installed plugins would silently stay put. The release
  workflow now regenerates it from the tag (with the released XPI's
  `update_hash`) and commits it, and CI fails if it lags the package version
  (`scripts/gen_updates_json.py --check`).
- **The version can no longer drift between the CLI, the plugin manifest and
  `bootstrap.js`.** The XPI build stamps the package version into both plugin
  files, and a test fails if the checked-in copies disagree.

### Changed
- The XPI build moved out of the package into `scripts/build_xpi.py` (a
  maintainer tool used by `plugin/build.sh` and CI) and produces a deterministic
  zip. The package ships no plugin source: the XPI has exactly one distribution
  channel, the release asset.
- `install.sh` now calls `zot skill install --link` instead of hand-rolling the
  symlink, and no longer bundles an XPI into `skill/scripts/`.
- `docs/install.md`'s uninstall section now covers every install method and both
  state directories (`~/.config/zotero-agent`, `~/.local/state/zotero-agent`).

## [0.2.1] — 2026-07-24

### Added
- **`zot completion <bash|zsh|fish>`** — prints a shell completion script for the
  subcommands and global flags (no extra dependency).

### Changed
- The command reference is now generated for **both** `docs/commands.md` and the
  website page from the one argparse source; CI fails if either drifts.

### Fixed
- **`apply`/`update_items` dry-run no longer executes any JS**, so it can never
  persist changes (the old monkey-patch-`save()` interception could leak writes
  on Zotero 7). The preview is reported straight from the parsed edits.
- `dedupe --fuzzy` is now tractable on large libraries (prefix-blocking instead
  of O(n²) over the whole library) — seconds instead of timing out.
- Bridge/read calls that time out now return a clean error instead of an
  uncaught traceback (`post_code` and `main` handle `TimeoutError`/`OSError`).
- `exec --dry-run` now states honestly that it executes the script with
  best-effort interception and may still persist (backup is the guarantee).

## [0.2.0] — 2026-07-23

The project was renamed from `zotero-cli-skill` to **`zotero-agent`** and rebuilt
into an installable Python package with an MCP server.

### Added
- **Python package** `zotero-agent` (installable from PyPI; entry point `zot`).
  The former single-file CLI is now a modular package under `src/zotero_agent/`.
- **MCP server** (`zot mcp`) exposing ~18 high-level tools to any Model Context
  Protocol client (Claude Desktop, Codex CLI, Gemini CLI, Cursor). Optional
  `[mcp]` extra.
- **`zot apply`** — declarative JSONL batch edits (set fields / add-remove tags /
  add to collection / trash), with a pre-image snapshot.
- **`zot undo`** — restore items to their state before an `apply`/`enrich`.
- **`zot enrich`** — fill missing DOI / date / abstract from Crossref or OpenAlex.
- **`zot tag normalize`** — fold case- and whitespace-variant tags together.
- **`zot dedupe --fuzzy`** — group near-identical titles (Levenshtein).
- **Audit log** of every bridge execution at `~/.local/state/zotero-agent/audit.jsonl`.
- `--version` flag; `--json` is now a global flag on every command.
- Fake-Zotero test server; expanded unit + integration tests. CI on GitHub Actions.

### Changed
- **Rebranding:** endpoint `POST /zotexec` → `POST /zotero-agent`; token header
  `X-Zotexec-Token` → `X-Zotero-Agent-Token`; pref `extensions.zotexec.token` →
  `extensions.zotero-agent.token`; config dir `~/.config/zotero-exec` →
  `~/.config/zotero-agent`; env `ZOTEXEC_*` → `ZOTERO_AGENT_*`; plugin →
  "Zotero Agent Bridge" (`zotero-agent-bridge-<version>.xpi`).
- `export`/`bib` no longer silently truncate large collections (paginate fully).
- Minimum Python is now 3.9.

### Migration
Single-user project, no back-compat shim: reinstall the bridge XPI and run
`zot init` to regenerate `~/.config/zotero-agent/config.json`.

## [0.1.0] — 2026-07-23
- Initial release as `zotero-cli-skill`: `zotexec` plugin + `zot` CLI + Claude
  Code skill.

[Unreleased]: https://github.com/alex-roc/zotero-agent/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/alex-roc/zotero-agent/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/alex-roc/zotero-agent/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/alex-roc/zotero-agent/releases/tag/v0.2.0
[0.1.0]: https://github.com/alex-roc/zotero-agent/releases/tag/v0.1.0
