<!-- Thanks for contributing! Keep the core stdlib-only and writes guarded. -->

## What & why

<!-- What does this change and what problem does it solve? -->

## How I verified

- [ ] `python -m unittest discover -s tests` passes
- [ ] `uvx ruff check src tests cli/zot` is clean
- [ ] Rebuilt the XPI (`bash plugin/build.sh`) if the plugin changed
- [ ] Updated `docs/` / `skill/` / `CHANGELOG.md` (Unreleased) if behaviour changed
- [ ] (If a live test was relevant) ran `zot ping` / the affected command against a real library

## Notes

<!-- Anything reviewers should know: trade-offs, follow-ups, screenshots. -->
