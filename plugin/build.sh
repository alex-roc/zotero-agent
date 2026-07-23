#!/usr/bin/env bash
#
# build.sh — package the zotero-exec plugin into an installable .xpi
#
# An .xpi is just a zip of the plugin source with manifest.json at its root.
# Output: dist/zotexec-<version>.xpi  (and a stable dist/zotexec.xpi symlink).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/zotero-exec"
REPO="$(cd "$HERE/.." && pwd)"
DIST="$REPO/dist"

VERSION="$(python3 -c "import json,sys; print(json.load(open('$SRC/manifest.json'))['version'])")"
OUT="$DIST/zotexec-$VERSION.xpi"

mkdir -p "$DIST"
rm -f "$OUT"

# zip from inside the source dir so manifest.json/bootstrap.js sit at the root
( cd "$SRC" && zip -q -X -r "$OUT" manifest.json bootstrap.js )

# stable name for docs/install.sh to reference
ln -sf "zotexec-$VERSION.xpi" "$DIST/zotexec.xpi"

echo "Built: $OUT"
echo "       $DIST/zotexec.xpi -> zotexec-$VERSION.xpi"
