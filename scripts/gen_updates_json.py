#!/usr/bin/env python3
"""Regenerate updates.json — Zotero's plugin auto-update manifest.

The installed plugin polls `applications.zotero.update_url` (raw updates.json on
main) and upgrades itself when it announces a newer version. That file therefore
has to move with every release, or users silently stay on the version they first
installed — so the release workflow runs this, and CI checks it is in sync.

    python scripts/gen_updates_json.py --xpi dist/zotero-agent-bridge-0.3.0.xpi
    python scripts/gen_updates_json.py --check     # verify without writing
"""

import argparse
import hashlib
import json
import os
import sys

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from zotero_agent import __version__  # noqa: E402

OUT = os.path.join(_ROOT, "updates.json")
PLUGIN_ID = "zotero-agent-bridge@zotero-agent"
REPO = "alex-roc/zotero-agent"
# Kept in step with plugin/zotero-agent-bridge/manifest.json.
STRICT_MIN = "7.0"
STRICT_MAX = "10.*"


def download_url(version):
    """The immutable, per-tag asset URL Zotero should fetch the update from."""
    return "https://github.com/%s/releases/download/v%s/zotero-agent-bridge-%s.xpi" % (
        REPO, version, version)


def build(version, xpi=None):
    update = {
        "version": version,
        "update_link": download_url(version),
        "applications": {"zotero": {"strict_min_version": STRICT_MIN,
                                    "strict_max_version": STRICT_MAX}},
    }
    if xpi:
        with open(xpi, "rb") as fh:
            update["update_hash"] = "sha256:" + hashlib.sha256(fh.read()).hexdigest()
    return {"addons": {PLUGIN_ID: {"updates": [update]}}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xpi", help="the release XPI, to record an update_hash. Pass this "
                                  "only for the artifact actually being uploaded — a hash "
                                  "that does not match the asset makes Zotero refuse the "
                                  "update. Locally, regenerate without it.")
    ap.add_argument("--check", action="store_true",
                    help="fail if updates.json does not announce the current version")
    args = ap.parse_args()

    if args.check:
        with open(OUT, encoding="utf-8") as fh:
            current = json.load(fh)
        announced = current["addons"][PLUGIN_ID]["updates"][0]
        problems = []
        if announced["version"] != __version__:
            problems.append("announces %s, package is %s" % (announced["version"], __version__))
        if announced["update_link"] != download_url(__version__):
            problems.append("update_link does not point at the v%s asset" % __version__)
        if problems:
            print("updates.json is stale: %s\nRun: python scripts/gen_updates_json.py"
                  % "; ".join(problems), file=sys.stderr)
            return 1
        print("updates.json is in sync (v%s)" % __version__)
        return 0

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(build(__version__, args.xpi), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("Wrote %s (v%s%s)" % (OUT, __version__, ", with update_hash" if args.xpi else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
