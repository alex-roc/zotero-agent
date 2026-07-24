"""Terminal I/O and verbosity state, shared by every command.

Verbosity is process-global (set once from the parsed CLI flags). Keeping it
here — rather than in each module — gives a single source of truth that both
the CLI and the MCP server import.
"""

import sys

from .constants import EXIT_GENERIC

QUIET = False   # suppress non-essential notices (set from --quiet)
DEBUG = False   # verbose diagnostics to stderr (set from --debug)


def set_verbosity(quiet=False, debug=False):
    global QUIET, DEBUG
    QUIET = quiet
    DEBUG = debug


class ZotError(Exception):
    """A user-facing error carrying an exit code.

    In the CLI, `main` turns this into `error: <msg>` on stderr + sys.exit(code).
    In the MCP server it is caught and returned as a tool error string, so the
    same command functions can be reused without calling sys.exit().
    """

    def __init__(self, msg, code=EXIT_GENERIC):
        super().__init__(msg)
        self.code = code


def die(msg, code=EXIT_GENERIC):
    raise ZotError(msg, code)


def info(msg):
    """Print a non-essential notice to stderr, unless --quiet."""
    if not QUIET:
        print(msg, file=sys.stderr)


def debug(msg):
    if DEBUG:
        print("[debug] " + msg, file=sys.stderr)


def confirm_write(args, description):
    """Guard a write. With --yes, proceed. On a TTY, prompt. Otherwise refuse
    (agents/scripts must pass --yes), so writes are never silent by default."""
    if getattr(args, "yes", False):
        return
    if sys.stdin.isatty() and sys.stdout.isatty():
        resp = input("%s Proceed? [y/N] " % description).strip().lower()
        if resp not in ("y", "yes"):
            die("aborted by user", code=EXIT_GENERIC)
        return
    die("%s Re-run with --yes to confirm (or --dry-run to preview)." % description,
        code=EXIT_GENERIC)
