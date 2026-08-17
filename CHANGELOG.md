# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] - 2026-08-17

### Added
- **`zot pdf-prep` — scanned books become searchable without leaving the item.**
  A book scanned on a flatbed arrives as one landscape page per *pair* of printed
  pages with no text layer: it cannot be searched, cited from, or read by an
  agent, and `zot toc` had nothing to work with (it printed an `ocrmypdf` command
  and gave up). The new command analyses the file, splits two-up scans into single
  pages, adds a text layer with OCR, and shrinks the result — Bowles,
  *Introducción a la economía*: 147 two-up pages at 200 dpi → 294 pages,
  24.7 MB → 16.4 MB, searchable, in under three minutes.

  The split is what usually needs a human with Briss, because the binding is
  never exactly centred. `pdf-prep` measures the ink profile of sampled pages and
  applies the **median** cut of the ones with enough ink to be informative — on a
  near-blank page the "widest gap" lands anywhere, so a per-page cut eventually
  slices a chapter opening in half. Each half keeps a sliver past the cut, so the
  ±2% a real binding wanders never clips a letter. `--gutter` forces the cut,
  `--single` leaves covers and fold-outs whole, `--rtl` handles right-to-left books.

  Nothing is discarded by default: the result is attached *beside* the original
  and tagged `pdf-prep`, so re-running a collection skips what it already did.
  `--replace` trashes the original as it goes and `--prune` does it afterwards,
  so a large library does not end up holding two copies of every book. OCR
  language comes from the item's own `language` field.

  Both trashing paths **refuse an original that carries highlights**. Zotero
  anchors annotations to the attachment and to coordinates on a page, so they
  cannot follow a file whose pages have just been split in two: trashing the
  original would take the user's reading with it. `--trash-annotated` overrides.
  Removals go to the trash, never `eraseTx`.

  Splitting needs the `[toc]` extra, already present for `zot toc`; OCR needs
  OCRmyPDF, and `--no-ocr` works without it.

### Changed
- `zot pdf --json` also reports each attachment's tags, and the item's language.
  Both were already in Zotero; `pdf-prep` needs them to recognise its own output
  and to pick an OCR language, and no command should have to fetch an item twice.

## [0.6.0] - 2026-08-16

### Fixed
- **`zot add isbn` only ever tried the first translator Zotero offered, so ISBN
  imports failed wholesale** — 73 of 73 in one batch, including *The structure of
  scientific revolutions*, while all 34 DOI imports in the same batch worked. For an
  ISBN the first offer is "Library of Congress ISBN", which answers nothing for most
  books; BnF and K10plus, offers two and three, resolve them fine. DOIs never showed
  it because CrossRef is first there. `add` now walks the whole list until one
  returns an item, and reports what each said: `--debug` names the translator that
  answered, and a genuine failure lists every attempt, so "no metadata for this
  identifier" is finally distinguishable from "the service was down".

- **`zot export <collection>` silently ignored subcollections.** Zotero files an
  item in one collection at a time, so a collection whose items all live one level
  down exported as empty — with no hint that anything had been skipped. `--recursive`
  walks the descendants and de-duplicates items filed in several of them. For
  bibtex/biblatex/ris it names every item key explicitly, because the read API's
  collection endpoint cannot see past the top level either.

### Changed
- **One item shape across every command.** Reads that went through the HTTP API
  emitted Zotero's wire format (`{data: {itemType, DOI, citationKey}}`) while reads
  through the bridge emitted a flat record (`{type, doi, citekey}`), so a script
  written against `export` quietly produced nothing against `get`/`search`. Both now
  emit the flat record, and its field list is asserted against the JS mapper so the
  two cannot drift again. `get`, `search` and `recent` take **`--raw`** when the
  API's own format is what you want. This is a breaking change for anything reading
  `.data.*` out of those three commands.

### Added
- **`zot attach <key> --file <path>` / `--url <url> [--link]`** — attachments for
  items that already exist. `add --pdf` only ever covered the moment of creation, so
  a PDF downloaded later, or a link to the publisher's page, meant hand-written
  `zot exec` JS with nothing guarding which item it touched.

- **`zot pdf-fetch <keys…> | --collection C`** — the open-access PDF lookup
  (`Zotero.Attachments.addAvailablePDF`) applied to items already in the library,
  which was likewise reachable only through `add --pdf`. Items that already have a
  PDF are skipped unless `--retry-with-pdf`.

- **`zot add --check-duplicate`** — resolves the metadata *without saving*, looks
  for a close title+author match, and refuses instead of creating the duplicate.
  Nothing warned before, and duplicates were only found later by a manual
  `zot dedupe` pass.

- **`zot restart`** — the one thing the CLI could not do was get Zotero itself back
  up, so every plugin update ended in "restart Zotero manually". It now quits with a
  relaunch (`Zotero.Utilities.Internal.quit(true)`), starts Zotero when it is not
  running at all, and in both cases waits for `POST /zotero-agent` to answer before
  returning — so the next command reaches a live bridge.

  `--plugin` is the cheap variant for the common case — Zotero asking for a restart
  to finish updating the plugin: it cycles the add-on off and on again through
  Zotero's `AddonManager`, leaving the window open, and takes about two seconds.
  `Addon.reload()`, the call that looks right, resolves without unloading anything
  and is not used. The cycle runs in the *main window's* realm, because disabling
  the plugin unloads the scope the code itself would be living in, and it confirms
  itself with a per-run nonce written to a pref — "something answers again" would
  also be true of a bridge that never actually reloaded.

  Starting Zotero needs to know *which* Zotero: a Mac can hold `Zotero 6.app` and
  `Zotero 7.app`, both claiming `org.zotero.zotero`, so `open -b` is a coin flip
  between a version that has the plugin and one that cannot run it. `zot init` and
  `zot restart` therefore ask the running instance for its own binary and record it
  as `app` in the config, which is what the launch fallback uses.

  Both defer the disruptive part to the main window's event loop so the HTTP reply
  leaves first; without that a perfectly good restart comes back as a connection
  error. A full restart also waits for the *old* process to let go of the port, so a
  still-answering bridge is reported as a failed restart instead of a success. Being
  disruptive, both prompt for confirmation and need `--yes` non-interactively.

## [0.5.1] - 2026-07-26

### Fixed
- **The Homebrew formula pointed at a PyPI URL that 404s for a fresh release.**
  `/packages/source/z/zotero-agent/…` redirects to the real download path, but it is
  not populated immediately: 0.5.0's `brew install` failed on it minutes after the
  release while the real path already worked. The formula now uses that real path,
  which is `packages/<b2[:2]>/<b2[2:4]>/<b2[4:]>/<file>` where `b2` is the file's
  blake2b-256 digest — derived from the artifact the generator already hashes, so it
  needs no API call and cannot lag a CDN. `--check` rejects the old alias, and
  `--from-pypi` regenerates a formula for an already-published version.

  Found by the tap's own macOS job, which is the only place `brew install` runs.

## [0.5.0] - 2026-07-26

### Added
- **`zot ping` now reports which install answered**, and `zot --version` marks a
  checkout as `(dev)`. Two copies of the same version — an editable install and a
  released one, or Homebrew's and uv's — were indistinguishable from the output,
  which matters both when switching between them and when reading a bug report:

  ```
  zot source       : ~/dev/zotero-agent/src/zotero_agent (dev tree)
  ```

  The path also names the route (`~/.local/share/uv/…`, `/opt/homebrew/Cellar/…`),
  and `~` replaces the home directory so pasted output carries no username.
- **Homebrew is an install route again — `brew install alex-roc/tap/zotero-agent`.**
  0.4.0 retired the old tap because it shipped without the `[mcp]` extra, pinned an
  interpreter by hand, and needed a manual `url`/`sha256` bump per release. All
  three are now structurally impossible:
  - the formula ships **both extras**, from a hash-pinned lock
    (`packaging/homebrew/requirements.txt`) that the generator embeds into it, so a
    lock change without a regenerated formula fails CI — as does a lock that lost
    an extra pyproject still offers;
  - the interpreter pin lives in one constant, the same one the lock is resolved
    for (`scripts/gen_homebrew_formula.py`);
  - `url` and `sha256` are generated by the release workflow from the sdist it
    just published to PyPI, so the formula is a *mirror* of PyPI rather than a
    second build.

  The tap ([`alex-roc/homebrew-tap`](https://github.com/alex-roc/homebrew-tap))
  pulls the generated formula on a schedule and installs + tests it on macOS
  before anyone else does. It needs no stored credentials.

  Unlike the uv/pipx routes, this one includes `zot mcp` and `zot toc` up front:
  Homebrew replaces a keg wholesale on every upgrade, so an extra added afterwards
  would silently disappear at the next `brew upgrade`.

## [0.4.0] - 2026-07-26

### Changed
- **The licence is now AGPL-3.0-or-later** (was MIT). `zot toc` is built on
  PyMuPDF, which is AGPL, and relicensing the project settles the question
  outright rather than leaning on the optional-extra argument. Releases 0.1.0
  through 0.3.0 remain MIT and can still be used under those terms.
- **Minimum Python is now 3.10** (was 3.9), which is what current PyMuPDF
  requires. The CI matrix moved to 3.10 / 3.13.

### Added
- **`zot toc` — read, detect and write a PDF's table of contents.** Zotero's
  reader shows a PDF's embedded outline but cannot create one, and its own
  automatic extraction is experimental and noisy, so most scanned books arrive
  with an empty Outline tab. Five actions: `show`, `scan`, `set`, `auto`,
  `clear`. Needs the new `[toc]` extra (`uv tool install --force
  "zotero-agent[toc]"`); the core stays stdlib-only, and running `zot toc`
  without it exits with the exact command that fixes it.

  Detection prefers **the book's own contents page** over guessing from fonts,
  by three routes in order of reliability:
  - hyperlinked contents pages, where the link destination *is* the page
    (born-digital ebooks) — exact, nothing to infer;
  - printed page numbers, mapped onto physical pages via `/PageLabels`, the
    folios printed on each page, and a title search that confirms each row. Each
    numbering series is resolved independently, so roman front matter and an
    arabic body both land correctly — a single global offset, which is what
    comparable tools use, is wrong for half of any such book. Rows the title
    search cannot confirm are re-placed using the delta the confirmed ones agree
    on;
  - typographic heading candidates, for the many books with no contents page at
    all. This one is mostly about what it rejects: anything set smaller than the
    body text (footnotes — numbered, short and block-initial, they otherwise
    score exactly like sections), anything that fills the column (running text,
    which matters for books that set block quotes above body size and use no
    bold), sentences, figure captions, running heads and over-long lines. Levels
    come from section numbering where the book numbers its sections, and
    otherwise from font size — ignoring sizes that appear on only a page or two,
    so a 24pt title page cannot claim level 1 and push every chapter to level 3.

  Contents pages come in three layouts and all three are handled: dot leaders,
  hyperlinks with no printed number at all, and a right-hand column of page
  numbers (where the title and the number arrive as two unrelated text lines, so
  nothing matches "title .... 15" and the page would otherwise be skipped in
  favour of the list of figures two pages later). Lists of tables and figures are
  rejected even when their running head says "Índice". Wrapped lines are rejoined
  and de-hyphenated, so a title split across three lines is recorded whole
  instead of as its last fragment.

  Writes are guarded by `--yes`, previewable with `--dry-run`, and reversible
  with `zot undo` — which snapshots the *previous outline* rather than copying a
  200 MB book. The save is incremental, so existing bytes (and therefore scanned
  page images) are untouched; `--backup` keeps a full copy of the original under
  `~/.local/state/zotero-agent/pdf-backups/` — outside Zotero's own
  `storage/<KEY>/`, so no stray file confuses it. Zotero's annotations
  live in the database, not the file, so they survive.

  `scan --json` is the agent hand-off: the CLI gathers the evidence, the agent
  decides the hierarchy, `set --from -` writes it — the same division of labour
  as `zot apply`. New MCP tools `get_pdf_outline`, `scan_pdf_outline` and
  `set_pdf_outline`, and a new section in the bundled skill's
  `references/pdf-and-notes.md`.
- A `PDF outlines` group in the command reference, and a cookbook recipe,
  *Give a PDF a table of contents*.

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

[Unreleased]: https://github.com/alex-roc/zotero-agent/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/alex-roc/zotero-agent/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/alex-roc/zotero-agent/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/alex-roc/zotero-agent/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/alex-roc/zotero-agent/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/alex-roc/zotero-agent/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/alex-roc/zotero-agent/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/alex-roc/zotero-agent/releases/tag/v0.2.0
[0.1.0]: https://github.com/alex-roc/zotero-agent/releases/tag/v0.1.0
