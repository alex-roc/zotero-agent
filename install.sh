#!/usr/bin/env bash
#
# install.sh — wire up the zotero-cli-skill on this machine.
#
#   1. symlink skill/           -> ~/.claude/skills/zotero
#   2. copy cli/zot + plugin/   -> skill/scripts/   (self-contained skill)
#   3. symlink zot              -> ~/.local/bin/zot (on PATH)
#   4. run `zot init`           (token + config + profile/userID detection)
#   5. print the plugin install steps (optionally do them, with Zotero closed)
#
# It never edits Zotero prefs or restarts Zotero without asking.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="zotexec@zotero-cli-skill"
PLUGIN_SRC="$REPO/plugin/zotero-exec"
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
say "2. Bundle CLI + plugin into skill/scripts/ (self-contained)"
mkdir -p "$SKILL_SRC/scripts"
cp "$REPO/cli/zot" "$SKILL_SRC/scripts/zot"
chmod +x "$SKILL_SRC/scripts/zot"
rm -rf "$SKILL_SRC/scripts/zotero-exec"
cp -R "$PLUGIN_SRC" "$SKILL_SRC/scripts/zotero-exec"
info "copied zot + zotero-exec"

# ---------------------------------------------------------------- #
say "3. CLI on PATH -> $BIN_DEST"
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO/cli/zot" "$BIN_DEST"
info "linked (ensure ~/.local/bin is on your PATH)"

# ---------------------------------------------------------------- #
say "4. zot init"
"$PY" "$REPO/cli/zot" init || true

# ---------------------------------------------------------------- #
say "5. Build the plugin XPI"
bash "$REPO/plugin/build.sh"
XPI="$REPO/dist/zotexec.xpi"
cp -L "$XPI" "$SKILL_SRC/scripts/zotexec.xpi" 2>/dev/null && info "bundled XPI into skill/scripts/"
echo
say "Install the plugin (standard Zotero flow — no need to close Zotero):"
cat <<EOF
  1) In Zotero:  Tools -> Plugins -> the gear icon (top right)
       -> "Install Plugin From File..."
  2) Choose:  $XPI
  3) Then run:  zot init   (auto-detects your userID)  &&  zot ping
EOF
info "The bundled skill copy at skill/scripts/ includes this XPI too."
