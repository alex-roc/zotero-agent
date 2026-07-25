"""Names, paths, and exit codes — the single place branding is defined."""

import os

from . import __version__

# Branding. The plugin endpoint, the token header, the config dir and the env
# prefix all share the `zotero-agent` name so there is one brand, not three.
ENDPOINT_PATH = "/zotero-agent"
TOKEN_HEADER = "X-Zotero-Agent-Token"
TOKEN_PREF = "extensions.zotero-agent.token"
ENV_PREFIX = "ZOTERO_AGENT"  # ZOTERO_AGENT_BASE / _TOKEN / _USER_ID

CONFIG_DIR = os.path.expanduser("~/.config/zotero-agent")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STATE_DIR = os.path.expanduser("~/.local/state/zotero-agent")

DEFAULT_BASE = "http://localhost:23119"

# The bridge plugin has exactly one distribution channel: the GitHub Release
# asset. Zotero then auto-updates it from updates.json, so this URL is the only
# one users ever need — it always resolves to the newest XPI.
XPI_URL = "https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi"

VERSION = __version__

# Exit codes (documented; kept < 126 to avoid shell conflicts).
EXIT_GENERIC = 1       # generic error / failed check
EXIT_CONN = 2          # cannot reach Zotero, or a bridge runtime error
EXIT_NOTFOUND = 3      # item / collection / citekey not found
EXIT_CONFIG = 4        # missing or invalid configuration
