"""Non-Python assets shipped with the package: the agent skill and the portable
AGENTS.md.

`zot skill install` has to work for someone who installed from PyPI, so the wheel
force-includes these files under `zotero_agent/_assets/` (see pyproject.toml). In
a dev checkout that directory does not exist, so each asset falls back to its
original location in the repo — the same code path then serves both installs.

The bridge plugin is deliberately *not* here: the XPI is distributed only as a
GitHub Release asset, and Zotero auto-updates it from updates.json. Building it
is a repo/CI job (scripts/build_xpi.py).
"""

import os
import shutil

from .term import die

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_BUNDLED_DIR = os.path.join(_PKG_DIR, "_assets")
# src/zotero_agent/ -> repo root, used only in a dev checkout.
_REPO_DIR = os.path.normpath(os.path.join(_PKG_DIR, os.pardir, os.pardir))

# asset name -> path relative to both _assets/ and a repo checkout
_ASSETS = {"skill": "skill", "agents-md": "AGENTS.md"}

# Never copied into an installed skill: build artifacts and editor noise.
_SKILL_IGNORE = shutil.ignore_patterns("scripts", "__pycache__", ".DS_Store")


def asset_path(name):
    """Absolute path of a bundled asset, or its dev-checkout fallback."""
    rel = _ASSETS[name]
    for candidate in (os.path.join(_BUNDLED_DIR, rel), os.path.join(_REPO_DIR, rel)):
        if os.path.exists(candidate):
            return candidate
    die("asset %r not found — this install looks incomplete; reinstall with "
        "`uv tool install --force zotero-agent`" % name)


def install_skill(dest, force=False, link=False):
    """Put the agent skill at `dest`. Returns the absolute destination path."""
    src = asset_path("skill")
    dest = os.path.abspath(os.path.expanduser(dest))
    if os.path.lexists(dest):
        if not force:
            die("%s already exists — re-run with --force to replace it" % dest)
        if os.path.islink(dest) or os.path.isfile(dest):
            os.unlink(dest)
        else:
            shutil.rmtree(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if link:
        os.symlink(src, dest)
    else:
        shutil.copytree(src, dest, ignore=_SKILL_IGNORE)
    return dest
