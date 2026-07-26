#!/usr/bin/env python3
"""Generate the command reference by walking the `zot` argparse tree.

Writes BOTH canonical copies from the one source of truth, so neither drifts
from the CLI:
  - docs/commands.md                              (plain Markdown, for the repo)
  - web/src/content/docs/reference/commands.md    (Starlight page, for the site)

CI runs this then `git diff --exit-code` on both files, so a help-text change
without a regen fails the build. Usage:

    python scripts/gen_cli_reference.py             # rewrite both canonical files
    python scripts/gen_cli_reference.py OUT.md      # write only OUT.md (plain)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zotero_agent import __version__  # noqa: E402
from zotero_agent.cli import build_parser  # noqa: E402

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DOCS_OUT = os.path.join(_ROOT, "docs", "commands.md")
WEB_OUT = os.path.join(_ROOT, "web", "src", "content", "docs", "reference", "commands.md")

# Group subcommands for a readable reference (name -> section).
SECTIONS = [
    ("Read & analyze", ["search", "get", "cite", "pdf", "collections", "tags",
                         "export", "missing", "author", "stats", "recent", "bib",
                         "annotations", "related", "notes", "lint"]),
    ("Edit & organize", ["add", "dedupe", "tag", "set", "move", "collection", "note"]),
    ("PDF outlines", ["toc"]),
    ("Batch (undoable)", ["apply", "undo", "enrich"]),
    ("Setup & escape hatch", ["ping", "init", "skill", "backup", "sync",
                              "exec", "mcp", "completion"]),
]


def _subactions(parser):
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices and hasattr(action, "_ChoicesPseudoAction"):
            return action.choices
    # find the subparsers action
    for action in parser._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            return action.choices
    return {}


def _format_cmd(name, sp):
    lines = ["### `zot %s`\n" % name]
    if sp.description or sp.format_usage():
        usage = sp.format_usage().replace("usage: ", "").strip()
        lines.append("```\n%s\n```\n" % usage)
    # positionals + options (skip the shared globals to keep it short)
    globals_ = {"-h", "--help", "--base", "--token", "--user-id", "-q", "--quiet",
                "--debug", "-y", "--yes", "--json"}
    rows = []
    for action in sp._actions:
        opt = ", ".join(action.option_strings) if action.option_strings else action.dest
        if any(o in globals_ for o in action.option_strings):
            continue
        if action.dest in ("help",):
            continue
        help_text = (action.help or "").strip()
        rows.append((opt, help_text))
    if rows:
        lines.append("| Argument | Description |")
        lines.append("|----------|-------------|")
        for opt, help_text in rows:
            lines.append("| `%s` | %s |" % (opt, help_text))
        lines.append("")
    return "\n".join(lines)


_INTRO = (
    "_Auto-generated from the `zot` CLI (v%s) — do not edit by hand; "
    "run `python scripts/gen_cli_reference.py`._\n"
    "\nGlobal flags on every command: `--json`, `-q/--quiet`, `--debug`, "
    "`--yes`, `--base/--token/--user-id` (or `ZOTERO_AGENT_*`). "
    "Exit codes: 0 ok, 1 error, 2 connection/exec, 3 not-found, 4 config.\n"
)

# Starlight uses the frontmatter `title` as the page H1, so the web copy omits
# the leading "# Command reference" that the plain-Markdown copy carries.
_WEB_FRONTMATTER = (
    "---\n"
    "title: Command reference\n"
    "description: Every zot command and its arguments — auto-generated from the CLI.\n"
    "---\n"
)


def _body(choices):
    parts = [_INTRO % __version__]
    seen = set()
    for title, names in SECTIONS:
        parts.append("## %s\n" % title)
        for name in names:
            if name in choices:
                parts.append(_format_cmd(name, choices[name]))
                seen.add(name)
    leftover = [n for n in choices if n not in seen]
    if leftover:
        parts.append("## Other\n")
        for name in leftover:
            parts.append(_format_cmd(name, choices[name]))
    return "\n".join(parts)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    parser = build_parser()
    choices = _subactions(parser)
    body = _body(choices)

    if len(sys.argv) > 1:  # single explicit target: plain Markdown
        _write(sys.argv[1], "# Command reference\n\n" + body)
        print("Wrote %s (%d commands)" % (sys.argv[1], len(choices)))
        return

    _write(DOCS_OUT, "# Command reference\n\n" + body)
    _write(WEB_OUT, _WEB_FRONTMATTER + "\n" + body)
    print("Wrote %s and %s (%d commands)" % (DOCS_OUT, WEB_OUT, len(choices)))


if __name__ == "__main__":
    main()
