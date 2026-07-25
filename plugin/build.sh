#!/usr/bin/env bash
#
# build.sh — package the zotero-agent bridge plugin into an installable .xpi
#
# A maintainer/CI task: the XPI is distributed only as a GitHub Release asset, so
# users never run this. The zipping lives in scripts/build_xpi.py (deterministic,
# and it stamps the package version into the plugin).
#
# Output: dist/zotero-agent-bridge-<version>.xpi  (+ a stable symlink).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
DIST="$REPO/dist"

VERSION="$(PYTHONPATH="$REPO/src" python3 -c \
  "from zotero_agent import __version__; print(__version__)")"
OUT="$DIST/zotero-agent-bridge-$VERSION.xpi"

mkdir -p "$DIST"
rm -f "$OUT"
python3 "$REPO/scripts/build_xpi.py" "$OUT"

# stable name for docs/release assets to reference
ln -sf "zotero-agent-bridge-$VERSION.xpi" "$DIST/zotero-agent-bridge.xpi"
echo "       $DIST/zotero-agent-bridge.xpi -> zotero-agent-bridge-$VERSION.xpi"
