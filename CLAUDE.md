# Working conventions

Project-specific rules for AI assistants. Detail lives in `CONTRIBUTING.md` (how to
contribute) and `dev-docs/` (maintainer notes, local-only); this file is only the
things that are easy to get wrong.

## Git

- **Work directly on `main`.** No feature branches, no pull requests — this is a
  single-maintainer project and the PR ceremony buys nothing here. (The two PRs in
  the history are not the convention.)
- **Never commit or push without asking first.** Prepare the change, run the checks,
  then ask.
- `CONTRIBUTING.md` still tells *outside* contributors to branch and open a PR. That
  is correct for them — they cannot push to `main`. Do not "fix" it to match this
  file.

## Before a tag

Three generated artefacts must be in sync, and CI fails on each:

```bash
python3 -m unittest discover -s tests            # 136 tests, no network, no Zotero
uvx ruff check src tests cli/zot scripts
python3 scripts/gen_cli_reference.py             # then: git diff --exit-code
python3 scripts/gen_updates_json.py --check      # the plugin's auto-update manifest
python3 scripts/gen_homebrew_formula.py --check  # the Homebrew formula
```

The release itself is tag-driven (`git tag vX.Y.Z && git push --follow-tags`), and it
ends with one manual step: `gh workflow run sync.yml --repo alex-roc/homebrew-tap`.
See `CONTRIBUTING.md` → "Cutting a release".

## Docs

- Three documents exist **twice** (`docs/` + `web/src/content/docs/`), and
  `tests/test_doc_parity.py` enforces it. A new fact about installing, updating or
  security goes into `SHARED_FACTS`, or one copy will go stale — this has happened.
- `docs/commands.md` and the site's `reference/commands.md` are **generated**. Never
  edit them by hand.
- `dev-docs/` and `marketing/` are **gitignored on purpose**: maintainer notes that
  never ship. Write there freely; it will not appear in a commit.

## Code

- The core stays **stdlib-only**. Anything heavier goes behind an optional extra
  (`[mcp]`, `[toc]`), reached through a single guard function.
- One version number covers the CLI *and* the plugin, sourced from
  `src/zotero_agent/__init__.py`; tests enforce every copy of it.
