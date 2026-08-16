"""Shared rendering helpers: item lists, file/stdout writing, token diet."""

import json
import re
import sys

# The read API's own field names, mapped onto the one item shape this CLI emits.
# Reads that go through the bridge already produce this shape (jslib.ITEM_MAP);
# reads that go through the HTTP API used to leak Zotero's wire format instead —
# `{data: {itemType, DOI, citationKey}}` against `{type, doi, citekey}` — and a
# script written against one silently produced nothing against the other.
_VENUE_FIELDS = ("publicationTitle", "bookTitle", "publisher", "university")


def flatten_item(entry):
    """One API item (or its bare `data` object) in the shared flat item shape."""
    d = entry.get("data", entry) if isinstance(entry, dict) else {}
    creators = []
    for c in d.get("creators", []):
        name = ((c.get("firstName", "") + " ") if c.get("firstName") else "") + \
            (c.get("lastName") or c.get("name") or "")
        creators.append(name.strip())
    date = d.get("date", "") or ""
    year = next((m for m in re.findall(r"\d{4}", date)), None)
    return {
        "key": d.get("key", ""),
        "citekey": d.get("citationKey") or None,
        "type": d.get("itemType", ""),
        "title": d.get("title", ""),
        "date": date,
        "year": year,
        "creators": creators,
        "venue": next((d[f] for f in _VENUE_FIELDS if d.get(f)), ""),
        "doi": d.get("DOI", "") or "",
        "url": d.get("url", "") or "",
        "tags": [t.get("tag", "") for t in d.get("tags", [])],
        "abstract": d.get("abstractNote", "") or "",
    }


def print_items(items, as_json, raw=False):
    if as_json:
        print(json.dumps(items if raw else [flatten_item(i) for i in items],
                         indent=2, ensure_ascii=False))
        return
    for it in items:
        d = it.get("data", {})
        key = d.get("key", "")
        typ = d.get("itemType", "")
        title = d.get("title") or d.get("note") or "(untitled)"
        date = d.get("date", "")
        print("%-10s %-15s %-6s %s" % (key, typ, date, title))


def write_or_print(out, text):
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)


def project(res, detail):
    """Token diet: drop the heavy `abstract` field from item lists unless the
    caller asked for --detail full."""
    if detail == "full":
        return res
    for it in res.get("items", []):
        it.pop("abstract", None)
    return res


def dump_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def emit_broken_pipe_safe():
    """Guard used by main(); kept here so both entry points share it."""
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        pass
