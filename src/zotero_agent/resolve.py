"""Resolve a user-supplied key: a Zotero item key, or a Better BibTeX citekey."""

import re
import sys

from .constants import EXIT_NOTFOUND
from .http import bbt_rpc
from .term import die

ZOTERO_KEY_RE = re.compile(r"^[A-Z0-9]{8}$")


def keys_from(keys):
    """Accept keys as CLI args, or read them from stdin when the sole arg is '-'.

    Each argument is split on whitespace, as stdin already was: no item key or
    citekey contains a space, and zsh does not word-split an unquoted ``$keys``,
    so ``zot shrink $keys`` used to arrive as ONE argument. That reached Better
    BibTeX as a citekey search and died with "Invalid condition 'groupStart'",
    an error that names nothing the user typed."""
    if keys == ["-"] or not keys:
        return [ln.strip() for ln in sys.stdin.read().split() if ln.strip()]
    return [k for arg in keys for k in arg.split()]


def resolve_key(cfg, keyish):
    """Return a Zotero item key. Accepts a Zotero key (8 uppercase alnum) as-is,
    or a Better BibTeX citekey (optionally prefixed with '@') resolved via BBT."""
    forced_citekey = keyish.startswith("@")
    ck = keyish[1:] if forced_citekey else keyish
    if not ck or any(c.isspace() for c in ck):
        # Never a valid key or citekey; BBT would answer with an opaque RPC error.
        die("not an item key or citekey: %r (pass several keys as separate arguments)"
            % keyish, code=EXIT_NOTFOUND)
    if not forced_citekey and ZOTERO_KEY_RE.match(ck):
        return ck  # already a Zotero item key
    results = bbt_rpc(cfg, "item.search", [ck]) or []
    for r in results:
        if r.get("citekey") == ck or r.get("citation-key") == ck:
            item_id = r.get("id", "")  # e.g. http://zotero.org/users/2960998/items/WD7FCHBW
            return item_id.rstrip("/").split("/")[-1]
    die("citekey not found in Better BibTeX: %s" % ck, code=EXIT_NOTFOUND)
