# Contributing to zotero-agent

Thanks for your interest! This is a small, focused project — a CLI + MCP server +
Zotero bridge plugin for **local** library control. Contributions that keep it
simple, safe, and dependency-light are very welcome.

## Ground rules

- **Core stays stdlib-only.** The `zotero_agent` core must not add runtime
  dependencies. Anything heavier goes behind an optional extra — today `[mcp]`
  (the MCP server) and `[toc]` (PyMuPDF, for `zot toc`). Reach the optional
  dependency through one guard function and import it nowhere else, so the rest
  of the package stays importable, and testable, without it.
- **Writes are guarded.** New write commands must respect `confirm_write` (refuse
  non-interactive runs without `--yes`) and, where sensible, support `--dry-run`
  and snapshot for `zot undo`.
- **Behaviour parity.** MCP tools reuse the CLI command functions — don't fork the
  logic.

## Dev setup

```bash
git clone https://github.com/alex-roc/zotero-agent.git && cd zotero-agent
./install.sh                              # dev shim on PATH + skill + XPI
python3 -m unittest discover -s tests     # tests (no network, no live Zotero)
uvx ruff check src tests                  # lint
uv build                                  # build wheel + sdist
```

Needs Python 3.10+. The tests use a fake in-process Zotero server
(`tests/fake_zotero.py`), so they run without Zotero. For a real end-to-end check
against your own library, set `ZOT_LIVE=1` and run `zot ping` with Zotero open.

The PDF tests skip unless PyMuPDF is present, so run them with it at least once
before touching `src/zotero_agent/pdf/`:

```bash
uv pip install pymupdf && python3 -m unittest discover -s tests
```

## Switching `zot` between the dev tree and a release

There is **one `zot`**, and the last install wins. Keep a single name rather than a
second one for development: an alias only exists in interactive shells, so it would
not apply in scripts, in cron, or when an MCP client launches the CLI.

```bash
# dev: `zot` becomes the working tree, and follows your edits with no reinstall
cd /path/to/zotero-agent && uv tool install --force --editable ".[mcp,toc]"

# release: `zot` becomes what users get
uv tool install --force --refresh "zotero-agent[mcp,toc]"
```

`--refresh` is not decorative: without it uv can serve cached index metadata and
hand you the previous version.

**Know which one is answering.** Both print the same version number, so the CLI
says it itself:

```console
$ zot --version
zot (zotero-agent) 0.4.0 (dev)      # `(dev)` = running from a checkout
$ zot ping | tail -1
zot source       : ~/dev/zotero-agent/src/zotero_agent (dev tree)
```

That is `constants.IS_DEV_TREE`: the package sits outside any `site-packages`. The
`zot source` line also tells uv from Homebrew from pipx, which `PATH` order alone
hides — on macOS `/opt/homebrew/bin` normally precedes `~/.local/bin`, so a Homebrew
install silently shadows a uv one.

For a one-off run without touching your install, `cli/zot` is a shim that puts
`./src` on `sys.path` (`python3 cli/zot ping`).

**They share config and state.** `~/.config/zotero-agent/config.json` and
`~/.local/state/zotero-agent/` are fixed to `$HOME`
(`src/zotero_agent/constants.py`), so every copy uses the same token — no re-`init`
— but they also share `audit.jsonl` and the `undo/` snapshots. Only
`ZOTERO_AGENT_BASE` / `_TOKEN` / `_USER_ID` can be overridden per run; the
directories cannot. So use `--dry-run` and 1–2 items for destructive experiments,
the same discipline the skill asks of agents.

**A version mismatch after a bump is the check working.** Raise `__version__` and
`zot ping` will report the installed plugin as behind, because the XPI in Zotero
still declares the old one. Rebuild and reinstall it (`bash plugin/build.sh`) and
`ping` goes quiet.

**Install the skill once, linked, from the checkout** — `zot skill install --link`
symlinks `~/.claude/skills/zotero` at `skill/`, so your edits apply immediately.
Do not run `zot skill install --force` from a *released* copy afterwards: it
unlinks the symlink and copies in a snapshot (`assets.install_skill`), and you stop
seeing your own changes. Without `--force` it refuses instead — that is the net.

## Making a change

1. Branch from `main`.
2. Keep commits focused; update `docs/`, the `skill/`, and `CHANGELOG.md` when you
   change behaviour (see the "Unreleased" section).
3. Run tests + ruff. Rebuild the XPI (`bash plugin/build.sh`) if you touched the
   plugin.
4. Open a PR describing what changed and how you verified it.

## Docs live in two places

Three documents exist twice: plain Markdown under `docs/` (for the repo) and a
Starlight page under `web/src/content/docs/` (for the site). They are **variants**,
not copies — the web ones carry frontmatter, site-relative links and asides — so
neither is generated from the other:

| Fact | Repo | Website |
|------|------|---------|
| architecture | `docs/architecture.md` | `web/src/content/docs/architecture.md` |
| security | `docs/security.md` | `web/src/content/docs/security.md` |
| install | `docs/install.md` | `web/src/content/docs/getting-started/install.md` |

`tests/test_doc_parity.py` keeps them honest: every fact listed there must appear
in **both** copies, and retired wording (e.g. `zot plugin build`) must appear in
neither. **When you document a new fact about installing, updating or security,
add it to `SHARED_FACTS`** — that is what stops one copy from going stale, which
has already happened once.

The command reference is different: `docs/commands.md` and the site's
`reference/commands.md` are both **generated** from the argparse tree by
`scripts/gen_cli_reference.py`, and CI fails if they drift. Never edit them by
hand.

## Cutting a release

One version number covers the CLI *and* the plugin, and Zotero's auto-update
depends on `updates.json` announcing it, so bump them together:

```bash
# 1. bump the single source of truth
$EDITOR src/zotero_agent/__init__.py           # __version__ = "X.Y.Z"
# 2. keep the plugin's declared version in step (a test enforces this)
$EDITOR plugin/zotero-agent-bridge/manifest.json   # "version"
$EDITOR plugin/zotero-agent-bridge/bootstrap.js    # BRIDGE.version
# 3. point the auto-update manifest at the new tag
python scripts/gen_updates_json.py
# 4. move CHANGELOG's [Unreleased] into the new version, then
python -m unittest discover -s tests && python scripts/gen_cli_reference.py
git commit -am "release: X.Y.Z" && git tag -a vX.Y.Z -m "vX.Y.Z" && git push --follow-tags
```

The `-a` is not decoration: `--follow-tags` pushes **annotated** tags only, so a
lightweight `git tag vX.Y.Z` stays on your machine and the release silently never
starts (this happened with v0.7.0 — the fix was a separate `git push origin
vX.Y.Z`, not a force-push, which would have re-run the whole workflow).

The tag triggers `.github/workflows/release.yml`, which builds the wheel + the
XPI, publishes the GitHub Release (versioned **and** stable asset names),
publishes to PyPI, and re-commits **two** manifests: `updates.json` with the
released XPI's `update_hash`, and `packaging/homebrew/zotero-agent.rb` with the
published sdist's `sha256`. CI fails if either lags the package version.

Then hand the formula to the tap — **this step is the mechanism, not a shortcut**.
The tap does not poll (the formula only changes at a release); it has a weekly
schedule purely as a net for a release where this was forgotten:

```bash
gh workflow run sync.yml --repo alex-roc/homebrew-tap
```

It runs on your own `gh` credentials, which is why no token is stored anywhere.
Watch it: the run installs and `brew test`s the formula on macOS, and that is the
only place `brew install` is actually exercised.

## The Homebrew route

Nothing about the formula is edited by hand — `url` and `sha256` come from the
sdist the release published, because hatchling sdists are not byte-identical
across machines, so the hash is only knowable after CI builds it.

What you *do* touch is the dependency lock, and only when `pyproject.toml`'s
dependencies change:

```bash
python scripts/gen_homebrew_formula.py --relock             # after a pyproject change
python scripts/gen_homebrew_formula.py --relock --upgrade   # deliberately take newer extras
```

`--relock` keeps the existing pins (uv only moves them with `--upgrade`), which is
why CI can regenerate and diff without turning into noise every time `mcp`
releases. The lock is what makes `brew install` deliver `zot mcp` and `zot toc`:
the formula installs the package with `--no-deps` and takes everything else from
the lock, which the generator **embeds into the formula**. So a `--relock` without
regenerating the formula fails `--check`, and `tests/test_homebrew.py` fails if an
extra pyproject offers is missing from the lock. See `dev-docs/03-releasing.md` for
the tap itself.

## Reporting bugs / requesting features

Use the issue templates. For bugs, include the output of `zot ping` and
`zot --version`. For anything security-related, see [`SECURITY.md`](SECURITY.md).
