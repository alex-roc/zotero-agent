#!/usr/bin/env python3
"""Build the bridge plugin XPI — a repo/CI tool, not part of the shipped package.

Users never build the XPI: it is distributed **only** as a GitHub Release asset
(and Zotero auto-updates it from `updates.json`). This script is what the release
workflow and `plugin/build.sh` call.

The package version (src/zotero_agent/__init__.py) is the single source of truth
and is injected into the XPI's manifest.json and bootstrap.js, so a released
plugin can never disagree with the CLI it talks to.

    python scripts/build_xpi.py                 # -> dist/zotero-agent-bridge-<version>.xpi
    python scripts/build_xpi.py OUT.xpi
"""

import json
import os
import re
import sys
import zipfile

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from zotero_agent import __version__  # noqa: E402

PLUGIN_SRC = os.path.join(_ROOT, "plugin", "zotero-agent-bridge")
DIST = os.path.join(_ROOT, "dist")


def _plugin_files():
    """Every plugin file, relative to the plugin root, in a stable order."""
    found = []
    for dirpath, dirnames, filenames in os.walk(PLUGIN_SRC):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name == ".DS_Store":
                continue
            full = os.path.join(dirpath, name)
            found.append((full, os.path.relpath(full, PLUGIN_SRC).replace(os.sep, "/")))
    return found


def _with_version(rel, raw):
    """Stamp the package version into the two places the plugin declares it."""
    if rel == "manifest.json":
        data = json.loads(raw.decode("utf-8"))
        data["version"] = __version__
        return (json.dumps(data, indent="\t", ensure_ascii=False) + "\n").encode("utf-8")
    if rel == "bootstrap.js":
        text = raw.decode("utf-8")
        text, n = re.subn(r'(\n\s*version:\s*")[^"]*(")', r"\g<1>%s\g<2>" % __version__, text, count=1)
        if n != 1:
            raise SystemExit("build_xpi: could not find BRIDGE.version in bootstrap.js")
        return text.encode("utf-8")
    return raw


def build_xpi(dest):
    """Zip the plugin source into an installable .xpi at `dest`. Returns dest.

    Deterministic (fixed timestamps, sorted entries), so the same source always
    produces the same bytes and a release asset is reproducible.
    """
    files = _plugin_files()
    if not any(rel == "manifest.json" for _, rel in files):
        raise SystemExit("build_xpi: no manifest.json in %s" % PLUGIN_SRC)
    parent = os.path.dirname(os.path.abspath(dest))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for full, rel in files:
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(full, "rb") as fh:
                zf.writestr(info, _with_version(rel, fh.read()))
    return dest


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        DIST, "zotero-agent-bridge-%s.xpi" % __version__)
    build_xpi(dest)
    print("Built: %s (version %s)" % (dest, __version__))


if __name__ == "__main__":
    main()
