"""Setup and escape-hatch commands: init, ping, exec, backup, sync."""

import datetime
import json
import os
import secrets
import shutil
import sys
import urllib.error

from ..constants import (
    CONFIG_DIR,
    CONFIG_PATH,
    DEFAULT_BASE,
    ENDPOINT_PATH,
    EXIT_CONN,
    EXIT_GENERIC,
    VERSION,
)
from ..http import http_get, post_code, run_js
from ..jslib import DRYRUN_PREAMBLE, WRITE_RE
from ..term import confirm_write, die


def _read_source(source):
    if source == "-":
        return sys.stdin.read()
    if os.path.exists(source):
        with open(source, "r", encoding="utf-8") as fh:
            return fh.read()
    return source  # inline JS


def cmd_ping(args):
    from ..config import require_config
    cfg = require_config(args)
    ok = True
    try:
        status, _ = http_get(cfg["base"].rstrip("/") + "/api/")
        print("Zotero local API : up (HTTP %s)" % status)
    except Exception as e:  # noqa: BLE001
        if isinstance(e, urllib.error.HTTPError):
            print("Zotero local API : up (HTTP %s)" % e.code)
        else:
            print("Zotero local API : DOWN (%s)" % e)
            ok = False
    env = post_code(cfg, "return 1 + 1;")
    if env.get("ok") and env.get("result") == 2:
        print("bridge endpoint  : up (%s, 1+1 == 2)" % ENDPOINT_PATH)
    else:
        print("bridge endpoint  : FAIL (%s)" % (env.get("error") or env))
        ok = False
    print("userID           : %s" % (cfg.get("userID") or "UNKNOWN"))
    print("zot version      : %s" % VERSION)
    sys.exit(0 if ok else 1)


def cmd_exec(args):
    from ..config import require_config
    cfg = require_config(args)
    code = _read_source(args.source)
    if not args.dry_run and WRITE_RE.search(code):
        confirm_write(args, "This script appears to modify the library (writes detected).")
    if args.dry_run:
        indented = "\n".join("    " + line for line in code.splitlines())
        env = post_code(cfg, DRYRUN_PREAMBLE % indented)
        from .. import audit
        audit.record("exec:dry-run", code, env)
        if not env.get("ok"):
            die(env.get("error") or "unknown error from the bridge", code=EXIT_CONN)
        res = env.get("result") or {}
        writes = res.get("wouldWrite") or []
        print("DRY-RUN — the script WAS executed with best-effort write interception.")
        print("This is NOT a guarantee: some writes can still persist on Zotero 7. "
              "Take `zot backup` first for a hard guarantee; prefer `zot apply` "
              "(whose dry-run runs no JS) for batch edits.")
        if writes:
            print("Intercepted %d write attempt(s):" % len(writes))
            for w in writes:
                print("  %-16s %s %s" % (w.get("op", ""), w.get("kind", ""), w.get("title", "")))
        else:
            print("Intercepted 0 write attempts.")
        if res.get("error"):
            print(
                "\nNote: the script raised after interception (often a read-back of a\n"
                "not-yet-saved item under dry-run): %s" % res["error"],
                file=sys.stderr,
            )
        return
    env = post_code(cfg, code)
    from .. import audit
    audit.record("exec", code, env)
    if env.get("ok"):
        result = env.get("result")
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif result is not None:
            print(result)
    else:
        die(env.get("error") or "unknown error from the bridge", code=EXIT_CONN)


def cmd_backup(args):
    from ..config import require_config
    cfg = require_config(args)
    data_dir = run_js(cfg, "return Zotero.DataDirectory.dir;", label="backup")
    src = os.path.join(data_dir, "zotero.sqlite")
    if not os.path.exists(src):
        die("zotero.sqlite not found at %s" % src)
    dest_dir = args.dir or os.path.join(CONFIG_DIR, "backups")
    os.makedirs(dest_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    copied = []
    for suffix in ("", "-wal", "-shm"):
        s = src + suffix
        if os.path.exists(s):
            d = os.path.join(dest_dir, "zotero-%s.sqlite%s" % (ts, suffix))
            shutil.copy2(s, d)
            copied.append(d)
    main_copy = copied[0]
    size_mb = os.path.getsize(main_copy) / (1024 * 1024)
    print("Backed up to: %s (%.0f MB)" % (main_copy, size_mb))
    for extra in copied[1:]:
        print("  + %s" % os.path.basename(extra))


def cmd_sync(args):
    from ..config import require_config
    cfg = require_config(args)
    res = run_js(cfg, "try { await Zotero.Sync.Runner.sync({background:false}); return {started:true}; } catch(e){ return {error:String(e)}; }", label="sync")
    if res.get("started"):
        print("Sync triggered.")
    else:
        die("could not sync: %s (is a Zotero sync account configured?)" % res.get("error"), code=EXIT_GENERIC)


def _import_legacy_config():
    """One-time convenience: if the pre-rename config exists, reuse its token/
    userID so upgraders keep working after just reinstalling the XPI."""
    legacy = os.path.expanduser("~/.config/zotero-exec/config.json")
    if not os.path.exists(legacy):
        return None
    try:
        with open(legacy, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def cmd_init(args):
    from ..config import detect_profile, load_config, save_config
    cfg = load_config()

    if not cfg.get("token"):
        legacy = _import_legacy_config()
        if legacy and legacy.get("token"):
            cfg.update({k: legacy[k] for k in ("token", "userID", "base") if legacy.get(k)})
            print("Imported token/userID from the previous zotero-exec config.")
        else:
            cfg["token"] = secrets.token_urlsafe(24)
            print("Generated a new token.")
    cfg.setdefault("base", DEFAULT_BASE)

    profile = detect_profile()
    if profile:
        cfg["profile"] = profile
        print("Detected profile : %s" % profile)
    else:
        print("Profile          : not found (see docs/install.md for your OS)")

    save_config(cfg)
    print("Wrote config     : %s" % CONFIG_PATH)

    env = post_code(cfg, "return Zotero.Users.getCurrentUserID();")
    if env.get("ok") and env.get("result"):
        cfg["userID"] = env["result"]
        save_config(cfg)
        print("Detected userID  : %s" % cfg["userID"])
        print("\nAll set. Try:  zot ping")
    else:
        print("\nCould not reach the zotero-agent bridge yet:")
        print("  %s" % (env.get("error") or env))
        print("\nInstall the plugin and restart Zotero (see docs/install.md),")
        print("then re-run `zot init` to auto-detect your userID.")


# --------------------------------------------------------------------------- #
# shell completion
# --------------------------------------------------------------------------- #
_GLOBAL_FLAGS = "--json --quiet -q --yes -y --debug --base --token --user-id --help -h --version"


def _command_names():
    """Subcommand names, taken straight from the parser so they never drift."""
    from ..cli import build_parser
    parser = build_parser()
    for action in parser._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            return list(action.choices)
    return []


def cmd_completion(args):
    """Emit a shell completion script for `zot` (bash | zsh | fish)."""
    cmds = " ".join(_command_names())
    shell = args.shell
    if shell == "bash":
        print(
            "# zot bash completion — add to ~/.bashrc:  eval \"$(zot completion bash)\"\n"
            "_zot_completion() {\n"
            '  local cur="${COMP_WORDS[COMP_CWORD]}"\n'
            '  if [ "$COMP_CWORD" -eq 1 ]; then\n'
            '    COMPREPLY=( $(compgen -W "%s" -- "$cur") )\n'
            '  elif [[ "$cur" == -* ]]; then\n'
            '    COMPREPLY=( $(compgen -W "%s" -- "$cur") )\n'
            "  else\n"
            '    COMPREPLY=( $(compgen -f -- "$cur") )\n'
            "  fi\n"
            "}\n"
            "complete -F _zot_completion zot" % (cmds, _GLOBAL_FLAGS)
        )
    elif shell == "zsh":
        print(
            "# zot zsh completion — add to ~/.zshrc:  eval \"$(zot completion zsh)\"\n"
            "_zot() {\n"
            "  local -a cmds\n"
            "  cmds=(%s)\n"
            "  if (( CURRENT == 2 )); then\n"
            "    compadd -- $cmds\n"
            '  elif [[ "${words[CURRENT]}" == -* ]]; then\n'
            "    compadd -- %s\n"
            "  else\n"
            "    _files\n"
            "  fi\n"
            "}\n"
            "compdef _zot zot" % (cmds, _GLOBAL_FLAGS)
        )
    elif shell == "fish":
        print("# zot fish completion — save to ~/.config/fish/completions/zot.fish")
        print("complete -c zot -f")
        print("complete -c zot -n __fish_use_subcommand -a '%s'" % cmds)
        for flag in _GLOBAL_FLAGS.split():
            if flag.startswith("--"):
                print("complete -c zot -l %s" % flag[2:])
    else:
        die("unknown shell: %s (use bash, zsh, or fish)" % shell)
