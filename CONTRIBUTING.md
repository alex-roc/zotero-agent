# Contributing to zotero-agent

Thanks for your interest! This is a small, focused project — a CLI + MCP server +
Zotero bridge plugin for **local** library control. Contributions that keep it
simple, safe, and dependency-light are very welcome.

## Ground rules

- **Core stays stdlib-only.** The `zotero_agent` core must not add runtime
  dependencies. Anything heavier goes behind an optional extra (like `[mcp]`).
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

The tests use a fake in-process Zotero server (`tests/fake_zotero.py`), so they
run without Zotero. For a real end-to-end check against your own library, set
`ZOT_LIVE=1` and run `zot ping` with Zotero open.

## Making a change

1. Branch from `main`.
2. Keep commits focused; update `docs/`, the `skill/`, and `CHANGELOG.md` when you
   change behaviour (see the "Unreleased" section).
3. Run tests + ruff. Rebuild the XPI (`bash plugin/build.sh`) if you touched the
   plugin.
4. Open a PR describing what changed and how you verified it.

## Reporting bugs / requesting features

Use the issue templates. For bugs, include the output of `zot ping` and
`zot --version`. For anything security-related, see [`SECURITY.md`](SECURITY.md).
