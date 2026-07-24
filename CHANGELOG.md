# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/alex-roc/zotero-agent/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/alex-roc/zotero-agent/releases/tag/v0.2.0
[0.1.0]: https://github.com/alex-roc/zotero-agent/releases/tag/v0.1.0
