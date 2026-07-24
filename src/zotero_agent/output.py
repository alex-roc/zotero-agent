"""Shared rendering helpers: item lists, file/stdout writing, token diet."""

import json
import sys


def print_items(items, as_json):
    if as_json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
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
