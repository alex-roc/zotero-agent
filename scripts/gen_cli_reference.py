#!/usr/bin/env python3
"""Generate a Markdown command reference by walking the `zot` argparse tree.

Keeps the reference in lockstep with the CLI — run in CI before building the
docs site so it never drifts. Usage:

    python scripts/gen_cli_reference.py [output.md]     # default: docs/commands.md
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zotero_agent import __version__  # noqa: E402
from zotero_agent.cli import build_parser  # noqa: E402

# Group subcommands for a readable reference (name -> section).
SECTIONS = [
    ("Read & analyze", ["search", "get", "cite", "pdf", "collections", "tags",
                         "export", "missing", "author", "stats", "recent", "bib",
                         "annotations", "related", "notes", "lint"]),
    ("Edit & organize", ["add", "dedupe", "tag", "set", "move", "collection", "note"]),
    ("Batch (undoable)", ["apply", "undo", "enrich"]),
    ("Setup & escape hatch", ["ping", "init", "backup", "sync", "exec", "mcp"]),
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


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "docs", "commands.md")
    parser = build_parser()
    choices = _subactions(parser)

    doc = ["# Command reference\n",
           "_Auto-generated from the `zot` CLI (v%s) — do not edit by hand; "
           "run `python scripts/gen_cli_reference.py`._\n" % __version__,
           "Global flags on every command: `--json`, `-q/--quiet`, `--debug`, "
           "`--yes`, `--base/--token/--user-id` (or `ZOTERO_AGENT_*`). "
           "Exit codes: 0 ok, 1 error, 2 connection/exec, 3 not-found, 4 config.\n"]

    seen = set()
    for title, names in SECTIONS:
        doc.append("## %s\n" % title)
        for name in names:
            if name in choices:
                doc.append(_format_cmd(name, choices[name]))
                seen.add(name)
    # any command not placed in a section
    leftover = [n for n in choices if n not in seen]
    if leftover:
        doc.append("## Other\n")
        for name in leftover:
            doc.append(_format_cmd(name, choices[name]))

    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(doc))
    print("Wrote %s (%d commands)" % (out, len(choices)))


if __name__ == "__main__":
    main()
