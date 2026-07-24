"""Resolve a user-supplied key: a Zotero item key, or a Better BibTeX citekey."""

import re
import sys

from .constants import EXIT_NOTFOUND
from .http import bbt_rpc
from .term import die

ZOTERO_KEY_RE = re.compile(r"^[A-Z0-9]{8}$")


def keys_from(keys):
    """Accept keys as CLI args, or read them from stdin when the sole arg is '-'."""
    if keys == ["-"] or not keys:
        return [ln.strip() for ln in sys.stdin.read().split() if ln.strip()]
    return keys


def resolve_key(cfg, keyish):
    """Return a Zotero item key. Accepts a Zotero key (8 uppercase alnum) as-is,
    or a Better BibTeX citekey (optionally prefixed with '@') resolved via BBT."""
    forced_citekey = keyish.startswith("@")
    ck = keyish[1:] if forced_citekey else keyish
    if not forced_citekey and ZOTERO_KEY_RE.match(ck):
        return ck  # already a Zotero item key
    results = bbt_rpc(cfg, "item.search", [ck]) or []
    for r in results:
        if r.get("citekey") == ck or r.get("citation-key") == ck:
            item_id = r.get("id", "")  # e.g. http://zotero.org/users/2960998/items/WD7FCHBW
            return item_id.rstrip("/").split("/")[-1]
    die("citekey not found in Better BibTeX: %s" % ck, code=EXIT_NOTFOUND)
