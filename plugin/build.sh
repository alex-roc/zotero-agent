#!/usr/bin/env bash
#
# build.sh — package the zotero-agent bridge plugin into an installable .xpi
#
# An .xpi is just a zip of the plugin source with manifest.json at its root.
# Output: dist/zotero-agent-bridge-<version>.xpi  (+ a stable symlink).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/zotero-agent-bridge"
REPO="$(cd "$HERE/.." && pwd)"
DIST="$REPO/dist"

VERSION="$(python3 -c "import json; print(json.load(open('$SRC/manifest.json'))['version'])")"
OUT="$DIST/zotero-agent-bridge-$VERSION.xpi"

mkdir -p "$DIST"
rm -f "$OUT"

# zip from inside the source dir so manifest.json/bootstrap.js sit at the root
( cd "$SRC" && zip -q -X -r "$OUT" manifest.json bootstrap.js )

# stable name for docs/install.sh to reference
ln -sf "zotero-agent-bridge-$VERSION.xpi" "$DIST/zotero-agent-bridge.xpi"

echo "Built: $OUT"
echo "       $DIST/zotero-agent-bridge.xpi -> zotero-agent-bridge-$VERSION.xpi"
