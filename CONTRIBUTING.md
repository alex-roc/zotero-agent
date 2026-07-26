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

To point your installed `zot` at the checkout (with the PDF engine) instead of
the PyPI release: `uv tool install --force --editable . --with pymupdf`.

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
git commit -am "release: X.Y.Z" && git tag vX.Y.Z && git push --follow-tags
```

The tag triggers `.github/workflows/release.yml`, which builds the wheel + the
XPI, publishes the GitHub Release (versioned **and** stable asset names),
publishes to PyPI, and re-commits `updates.json` with the released XPI's
`update_hash`. CI fails if `updates.json` lags the package version.

## Reporting bugs / requesting features

Use the issue templates. For bugs, include the output of `zot ping` and
`zot --version`. For anything security-related, see [`SECURITY.md`](SECURITY.md).
