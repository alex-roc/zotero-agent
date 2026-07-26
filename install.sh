#!/usr/bin/env bash
#
# install.sh — wire up zotero-agent on this machine (developer / from-checkout).
#
#   1. symlink zot              -> ~/.local/bin/zot   (dev shim; uses ./src)
#   2. `zot skill install --link` -> ~/.claude/skills/zotero
#   3. build the bridge XPI     -> dist/  (the same artifact a release publishes)
#   4. run `zot init`           (token + config + profile/userID detection)
#   5. print the plugin install steps
#
# Step 2 is the CLI's own `zot skill install` and step 3 is `plugin/build.sh`, so a
# from-checkout install exercises exactly what a released user gets.
#
# For a plain install (no checkout), prefer:  uv tool install zotero-agent
# (add the MCP server with:  uv tool install "zotero-agent[mcp]"), or
# brew install alex-roc/tap/zotero-agent, which includes both extras.
#
# It never edits Zotero prefs or restarts Zotero without asking.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DEST="$HOME/.claude/skills/zotero"
BIN_DEST="$HOME/.local/bin/zot"
PY="$(command -v python3 || true)"

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }

[ -n "$PY" ] || { echo "error: python3 not found on PATH"; exit 1; }

# ---------------------------------------------------------------- #
say "1. CLI on PATH -> $BIN_DEST"
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO/cli/zot" "$BIN_DEST"
info "linked dev shim (ensure ~/.local/bin is on your PATH)"

# ---------------------------------------------------------------- #
# `zot skill install` is the same code path users get from PyPI; --link keeps
# the checkout authoritative so edits to skill/ take effect immediately.
say "2. Skill -> $SKILL_DEST"
"$PY" "$REPO/cli/zot" skill install --link --force --dest "$SKILL_DEST"

# ---------------------------------------------------------------- #
say "3. Build the bridge XPI (local copy; releases ship it as an asset)"
bash "$REPO/plugin/build.sh"
XPI="$REPO/dist/zotero-agent-bridge.xpi"

# ---------------------------------------------------------------- #
say "4. zot init"
"$PY" "$REPO/cli/zot" init || true

# ---------------------------------------------------------------- #
echo
say "5. Install the plugin (standard Zotero flow — no need to close Zotero):"
cat <<EOF
  1) In Zotero:  Tools -> Plugins -> the gear icon (top right)
       -> "Install Plugin From File..."
  2) Choose:  $XPI
  3) Then run:  zot init   (auto-detects your userID)  &&  zot ping
EOF
