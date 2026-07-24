"""Config load/save and profile detection.

Config lives in ~/.config/zotero-agent/config.json:
    { "token": "...", "userID": 2960998, "base": "http://localhost:23119" }

The same file is read by the bridge plugin, so rotating the token needs no
Zotero restart. Resolution precedence: flags > env (ZOTERO_AGENT_*) > file > default.
"""

import glob
import json
import os

from .constants import (
    CONFIG_DIR,
    CONFIG_PATH,
    DEFAULT_BASE,
    ENV_PREFIX,
    EXIT_CONFIG,
)
from .term import die


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    os.chmod(CONFIG_PATH, 0o600)


def require_config(args=None):
    """Resolve config with precedence: flags > env (ZOTERO_AGENT_*) > file > default."""
    cfg = load_config()
    env = os.environ
    if env.get(ENV_PREFIX + "_BASE"):
        cfg["base"] = env[ENV_PREFIX + "_BASE"]
    if env.get(ENV_PREFIX + "_TOKEN"):
        cfg["token"] = env[ENV_PREFIX + "_TOKEN"]
    if env.get(ENV_PREFIX + "_USER_ID"):
        cfg["userID"] = env[ENV_PREFIX + "_USER_ID"]
    if args is not None:
        if getattr(args, "base", None):
            cfg["base"] = args.base
        if getattr(args, "token", None):
            cfg["token"] = args.token
        if getattr(args, "user_id", None):
            cfg["userID"] = args.user_id
    if not cfg.get("token"):
        die("No token configured. Run `zot init`, or pass --token / set %s_TOKEN."
            % ENV_PREFIX, code=EXIT_CONFIG)
    cfg.setdefault("base", DEFAULT_BASE)
    return cfg


def detect_profile():
    patterns = [
        "~/Library/Application Support/Zotero/Profiles/*.default*",  # macOS
        "~/.zotero/zotero/*.default*",  # Linux
        "~/AppData/Roaming/Zotero/Zotero/Profiles/*.default*",  # Windows
    ]
    for pat in patterns:
        matches = glob.glob(os.path.expanduser(pat))
        if matches:
            return matches[0]
    return None
