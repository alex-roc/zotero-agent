#!/usr/bin/env bash
#
# install.sh — wire up zotero-agent on this machine (developer / from-checkout).
#
#   1. symlink skill/           -> ~/.claude/skills/zotero
#   2. build the bridge XPI     -> dist/  (+ bundle into skill/scripts/ for sharing)
#   3. symlink zot              -> ~/.local/bin/zot   (dev shim; uses ./src)
#   4. run `zot init`           (token + config + profile/userID detection)
#   5. print the plugin install steps
#
# For a plain install (no checkout), prefer:  uv tool install zotero-agent
# (add the MCP server with:  uv tool install "zotero-agent[mcp]").
#
# It never edits Zotero prefs or restarts Zotero without asking.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="zotero-agent-bridge@zotero-agent"
PLUGIN_SRC="$REPO/plugin/zotero-agent-bridge"
SKILL_SRC="$REPO/skill"
SKILL_DEST="$HOME/.claude/skills/zotero"
BIN_DEST="$HOME/.local/bin/zot"
PY="$(command -v python3 || true)"

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }

[ -n "$PY" ] || { echo "error: python3 not found on PATH"; exit 1; }

# ---------------------------------------------------------------- #
say "1. Skill -> $SKILL_DEST"
mkdir -p "$HOME/.claude/skills"
if [ -L "$SKILL_DEST" ] || [ -e "$SKILL_DEST" ]; then
  info "already present; refreshing symlink"
  rm -rf "$SKILL_DEST"
fi
ln -s "$SKILL_SRC" "$SKILL_DEST"
info "linked"

# ---------------------------------------------------------------- #
say "2. CLI on PATH -> $BIN_DEST"
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO/cli/zot" "$BIN_DEST"
info "linked dev shim (ensure ~/.local/bin is on your PATH)"

# ---------------------------------------------------------------- #
say "3. Build the bridge XPI"
bash "$REPO/plugin/build.sh"
XPI="$REPO/dist/zotero-agent-bridge.xpi"
mkdir -p "$SKILL_SRC/scripts"
cp -L "$XPI" "$SKILL_SRC/scripts/zotero-agent-bridge.xpi" 2>/dev/null \
  && info "bundled XPI into skill/scripts/ (for a self-contained shared skill)"

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
