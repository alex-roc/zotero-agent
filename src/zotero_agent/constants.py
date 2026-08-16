"""Names, paths, and exit codes — the single place branding is defined."""

import os

from . import __version__

# Branding. The plugin endpoint, the token header, the config dir and the env
# prefix all share the `zotero-agent` name so there is one brand, not three.
ENDPOINT_PATH = "/zotero-agent"
TOKEN_HEADER = "X-Zotero-Agent-Token"
TOKEN_PREF = "extensions.zotero-agent.token"
ENV_PREFIX = "ZOTERO_AGENT"  # ZOTERO_AGENT_BASE / _TOKEN / _USER_ID

# The bridge plugin's add-on ID, as declared in plugin/.../manifest.json. Needed
# to reach it through Zotero's AddonManager (see `zot restart --plugin`);
# tests/test_zot.py keeps the two copies in sync.
PLUGIN_ID = "zotero-agent-bridge@zotero-agent"

# macOS fallback for starting Zotero when the config has no recorded binary.
# Both Zotero 6 and 7 claim it, which is why the recorded path wins (see
# admin.remember_exe).
ZOTERO_BUNDLE_ID = "org.zotero.zotero"

CONFIG_DIR = os.path.expanduser("~/.config/zotero-agent")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STATE_DIR = os.path.expanduser("~/.local/state/zotero-agent")

DEFAULT_BASE = "http://localhost:23119"

# The bridge plugin has exactly one distribution channel: the GitHub Release
# asset. Zotero then auto-updates it from updates.json, so this URL is the only
# one users ever need — it always resolves to the newest XPI.
XPI_URL = "https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi"

VERSION = __version__

# Where this CLI runs from. A released install lives inside site-packages; an
# editable install (or `cli/zot`) imports the package straight out of a working
# tree. Both print the same version, so without this nobody — a user filing a bug,
# a maintainer switching between the two — can tell which one answered. `zot ping`
# prints it and `--version` marks a dev tree.
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))


def is_dev_tree(path=None):
    """True when `path` is a checkout rather than an installed copy."""
    parts = (path or SOURCE_DIR).split(os.sep)
    return not ("site-packages" in parts or "dist-packages" in parts)


IS_DEV_TREE = is_dev_tree()

# Exit codes (documented; kept < 126 to avoid shell conflicts).
EXIT_GENERIC = 1       # generic error / failed check
EXIT_CONN = 2          # cannot reach Zotero, or a bridge runtime error
EXIT_NOTFOUND = 3      # item / collection / citekey not found
EXIT_CONFIG = 4        # missing or invalid configuration
