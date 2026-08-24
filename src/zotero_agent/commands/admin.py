"""Setup and escape-hatch commands: init, ping, exec, backup, sync, restart."""

import datetime
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error

from ..constants import (
    CONFIG_DIR,
    CONFIG_PATH,
    DEFAULT_BASE,
    ENDPOINT_PATH,
    EXIT_CONN,
    EXIT_GENERIC,
    IS_DEV_TREE,
    PLUGIN_ID,
    SOURCE_DIR,
    VERSION,
    XPI_URL,
    ZOTERO_BUNDLE_ID,
)
from ..http import http_get, is_loopback, post_code, run_js
from ..jslib import DRYRUN_PREAMBLE, WRITE_RE
from ..term import confirm_write, die, info


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
        print("bridge plugin    : %s" % _plugin_status(env.get("version")))
    else:
        print("bridge endpoint  : FAIL (%s)" % (env.get("error") or env))
        ok = False
    print("userID           : %s" % (cfg.get("userID") or "UNKNOWN"))
    print("zot version      : %s" % VERSION)
    # Which install answered. Two copies of the same version (an editable one and a
    # released one, or brew's and uv's) are otherwise indistinguishable here — and
    # this is the output people paste into bug reports. `~` keeps the username out.
    print("zot source       : %s%s" % (SOURCE_DIR.replace(os.path.expanduser("~"), "~", 1),
                                       " (dev tree)" if IS_DEV_TREE else ""))
    sys.exit(0 if ok else 1)


def _plugin_status(plugin_version):
    """Describe the installed plugin relative to this CLI.

    The plugin and the CLI are released together and share a version, so a
    mismatch means one of the two was not updated — worth surfacing, since
    `zot ping` is where people look when something behaves oddly.
    """
    if not plugin_version:
        return ("unknown (plugin predates 0.2.1) — update it: Tools -> Plugins "
                "-> gear -> Check for Updates")
    if plugin_version == VERSION:
        return plugin_version
    mine, theirs = _version_tuple(VERSION), _version_tuple(plugin_version)
    if theirs < mine:
        return ("%s — older than this CLI (%s); Zotero auto-updates it, or force "
                "it now: Tools -> Plugins -> gear -> Check for Updates"
                % (plugin_version, VERSION))
    if theirs > mine:
        return ("%s — newer than this CLI (%s); upgrade it: uv tool upgrade zotero-agent"
                % (plugin_version, VERSION))
    return "%s (CLI reports %s)" % (plugin_version, VERSION)


def _version_tuple(version):
    """(1, 10, 0) from '1.10.0' — numeric, so 0.10 sorts above 0.9. Any
    non-numeric suffix (rc1, dev) is ignored rather than guessed at."""
    parts = []
    for chunk in str(version).split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


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


BACKUP_RE = re.compile(r"^zotero-(\d{8})-(\d{6})\.sqlite(-wal|-shm)?$")
DEFAULT_KEEP_DAYS = 3


def _prune_backups(dest_dir, keep_days):
    """Keep the newest snapshot of each of the `keep_days` most recent days.

    Snapshots pile up fast — a busy day leaves three 400 MB copies — and nothing
    ever removed them, so the directory grew about a gigabyte a day. Pruning by
    *day* rather than by count is what preserves real coverage: three copies made
    this afternoon are one bad afternoon, not three restore points.

    Returns (removed_names, freed_bytes).
    """
    if keep_days <= 0:
        return [], 0
    by_stamp = {}
    for name in os.listdir(dest_dir):
        m = BACKUP_RE.match(name)
        if m:
            by_stamp.setdefault((m.group(1), m.group(2)), []).append(name)
    keep_dates = sorted({date for date, _ in by_stamp}, reverse=True)[:keep_days]
    newest_of_day = {}
    for date, tm in by_stamp:
        if date in keep_dates and tm > newest_of_day.get(date, ""):
            newest_of_day[date] = tm
    removed, freed = [], 0
    for (date, tm), names in sorted(by_stamp.items()):
        if newest_of_day.get(date) == tm:
            continue
        for name in names:
            path = os.path.join(dest_dir, name)
            try:
                size = os.path.getsize(path)
                os.remove(path)
            except OSError:
                continue
            removed.append(name)
            freed += size
    return removed, freed


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
    keep_days = getattr(args, "keep_days", DEFAULT_KEEP_DAYS)
    removed, freed = _prune_backups(dest_dir, keep_days)
    if removed:
        print("Pruned %d older snapshot%s (%.0f MB freed; keeping %d day%s)"
              % (len(removed), "" if len(removed) == 1 else "s",
                 freed / (1024 * 1024), keep_days, "" if keep_days == 1 else "s"))


def cmd_sync(args):
    from ..config import require_config
    cfg = require_config(args)
    res = run_js(cfg, "try { await Zotero.Sync.Runner.sync({background:false}); return {started:true}; } catch(e){ return {error:String(e)}; }", label="sync")
    if res.get("started"):
        print("Sync triggered.")
    else:
        die("could not sync: %s (is a Zotero sync account configured?)" % res.get("error"), code=EXIT_GENERIC)


# --------------------------------------------------------------------------- #
# restart: bring Zotero — or just the bridge plugin — back up from the terminal
# --------------------------------------------------------------------------- #
RESTART_TIMEOUT = 90       # seconds to wait for the bridge to answer again
SHUTDOWN_TIMEOUT = 30      # seconds to wait for the old process to let go of the port
PROBE_TIMEOUT = 3          # a probe polls a dying port; it must fail fast
POLL_INTERVAL = 0.5
SCHEDULE_DELAY_MS = 500    # see below

# Both fragments schedule the disruptive part on the main window's event loop
# instead of doing it inline: the HTTP response has to leave *before* the process
# (or the plugin's scope) goes away, or a perfectly good restart comes back as a
# connection error.
_QUIT_JS = """
var w = Zotero.getMainWindow();
if (!w) return { error: 'no Zotero main window; cannot schedule a restart' };
w.setTimeout(function () {
  try {
    Zotero.Utilities.Internal.quit(true);
  } catch (e) {
    Services.startup.quit(Ci.nsIAppStartup.eAttemptQuit | Ci.nsIAppStartup.eRestart);
  }
}, %(delay)d);
return { scheduled: true };
"""

# Reloading the plugin is a disable/enable cycle. `Addon.reload()` looks like the
# obvious call and even resolves, but leaves the plugin loaded — Zotero never
# tears the scope down, so the bridge keeps answering with the old code.
#
# The cycle cannot run in this plugin's own scope: disabling it unloads exactly
# the realm a callback would live in. So it is evaluated in the main window's
# realm instead, and reports back through a pref rather than a return value —
# the HTTP request that started it is long gone by then.
_RELOAD_CYCLE_JS = """
setTimeout(async function () {
  var { AddonManager } = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
  var addon = await AddonManager.getAddonByID(%(id)s);
  if (!addon) return;
  // Safety net: leaving the bridge disabled would mean fixing it by hand in
  // Tools -> Plugins, so re-enabling is attempted again well after the cycle.
  setTimeout(function () { try { addon.enable(); } catch (e) {} }, %(gap)d + 10000);
  try {
    await addon.disable();
    await new Promise(function (r) { setTimeout(r, %(gap)d); });
  } finally {
    await addon.enable();
    Zotero.Prefs.set(%(noncepref)s, %(nonce)s, true);
  }
}, %(delay)d);
"""

_RELOAD_JS = """
var w = Zotero.getMainWindow();
if (!w) return { error: 'no Zotero main window; cannot reload the plugin' };
var { AddonManager } = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
if (!(await AddonManager.getAddonByID(%(id)s))) {
  return { error: 'plugin ' + %(id)s + ' is not installed in this Zotero' };
}
w.eval(%(cycle)s);
return { scheduled: true };
"""

# The freshly loaded plugin is the one that answers with the nonce this run
# generated: proof the cycle completed, not just that something is listening.
_NONCE_JS = "return Zotero.Prefs.get(%(noncepref)s, true) || null;"
_CLEAR_NONCE_JS = "Zotero.Prefs.clear(%(noncepref)s, true); return true;"

NONCE_PREF = "extensions.zotero-agent.reloadNonce"
RELOAD_GAP_MS = 1200       # how long the plugin stays disabled


def _js(template, **extra):
    """Fill a fragment above, JSON-quoting every value that lands in the JS."""
    params = {"id": json.dumps(PLUGIN_ID), "noncepref": json.dumps(NONCE_PREF),
              "path": json.dumps(ENDPOINT_PATH), "delay": SCHEDULE_DELAY_MS,
              "gap": RELOAD_GAP_MS}
    params.update(extra)
    return template % params


def _probe(cfg):
    """(alive, plugin_version) from one cheap round-trip to the bridge."""
    env = post_code(cfg, "return 1 + 1;", timeout=PROBE_TIMEOUT)
    if env.get("ok") and env.get("result") == 2:
        return True, env.get("version")
    return False, None


def _wait_for(cfg, alive, deadline):
    """Poll until the bridge reaches the wanted state. Returns (reached, version)."""
    while True:
        state, version = _probe(cfg)
        if state == alive:
            return True, version
        if time.monotonic() >= deadline:
            return False, None
        time.sleep(POLL_INTERVAL)


def remember_exe(cfg):
    """Ask a running Zotero where its own binary is, and record it in the config.

    Guessing is not good enough: on macOS a machine can hold `Zotero 6.app` and
    `Zotero 7.app`, both claiming `org.zotero.zotero`, so "open Zotero" is a coin
    flip between a version that has the plugin and one that cannot run it. Asking
    while Zotero is up is exact, and it is the only moment the answer exists.
    """
    from ..config import save_config
    env = post_code(cfg, "return Services.dirsvc.get('XREExeF', Ci.nsIFile).path;",
                    timeout=PROBE_TIMEOUT)
    exe = env.get("result") if env.get("ok") else None
    if exe and exe != cfg.get("app") and os.path.exists(exe):
        cfg["app"] = exe
        save_config(cfg)
    return cfg.get("app")


def _launch_command(cfg):
    """How to start Zotero on this machine, as an argv list — or None."""
    exe = cfg.get("app")
    if exe and os.path.exists(exe):
        # On macOS hand the .app to LaunchServices rather than exec'ing the
        # binary: same result, but it activates the existing app the way a user
        # would, instead of leaving a second dock entry behind.
        app = exe.split("/Contents/MacOS/")[0]
        if sys.platform == "darwin" and app.endswith(".app"):
            return ["open", "-a", app]
        return [exe]
    if sys.platform == "darwin":
        return ["open", "-b", ZOTERO_BUNDLE_ID]
    found = shutil.which("zotero") or shutil.which("Zotero")
    return [found] if found else None


def _launch_zotero(cfg):
    """Start the Zotero app detached. Returns the command run, or None if this
    machine offers no way to find it."""
    cmd = _launch_command(cfg)
    if not cmd:
        return None
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "posix":
        kwargs["start_new_session"] = True   # survive this shell
    subprocess.Popen(cmd, **kwargs)  # noqa: S603
    return shlex.join(cmd)   # app paths contain spaces; keep it copy-pasteable


def _restart_done(args, action, version, started):
    seconds = time.monotonic() - started
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "action": action, "plugin": version,
                          "seconds": round(seconds, 1)}, indent=2))
    else:
        print("Bridge is back after %.0fs (plugin %s)." % (seconds, version or "unknown"))


def cmd_restart(args):
    """Restart Zotero, reload just the bridge plugin, or start Zotero if it is down —
    and in every case wait until the bridge answers again."""
    from ..config import require_config
    cfg = require_config(args)
    started = time.monotonic()
    timeout = getattr(args, "timeout", None)
    timeout = RESTART_TIMEOUT if timeout is None else timeout
    alive, _ = _probe(cfg)

    if getattr(args, "plugin", False):
        if not alive:
            die("the bridge is not answering, so there is no plugin to reload. "
                "Run `zot restart` to start or restart Zotero itself.", code=EXIT_CONN)
        confirm_write(args, "This reloads the zotero-agent plugin inside a running Zotero.")
        return _reload_plugin(cfg, args, timeout, started)

    if alive:
        confirm_write(args, "This restarts Zotero; unsaved state in open windows may be lost.")
        remember_exe(cfg)   # while we still can: it is the launch fallback below
        run_js(cfg, _js(_QUIT_JS), timeout=PROBE_TIMEOUT + 10, label="restart")
        info("Asked Zotero to restart; waiting for it to shut down...")
        down, _ = _wait_for(cfg, False, time.monotonic() + SHUTDOWN_TIMEOUT)
        if not down:
            die("Zotero is still answering %ds after the restart request — it did "
                "not shut down. Restart it from the Zotero window."
                % SHUTDOWN_TIMEOUT, code=EXIT_GENERIC)
    else:
        info("Zotero is not answering; starting it...")

    # Zotero relaunches itself after `quit(true)`, but a failed relaunch would
    # otherwise leave the user with no Zotero at all — so the launch fallback
    # covers both "it was down" and "it went down and stayed down".
    deadline = time.monotonic() + timeout
    if not alive:
        _launch_or_die(cfg, args)
    info("Waiting for the bridge (up to %ds)..." % timeout)
    up, version = _wait_for(cfg, True, deadline)
    if not up and alive:
        info("Zotero did not come back on its own; launching it...")
        _launch_or_die(cfg, args)
        up, version = _wait_for(cfg, True, time.monotonic() + timeout)
    if not up:
        die("the bridge did not answer within %ds. Check that Zotero started, "
            "then run `zot ping`." % timeout, code=EXIT_CONN)
    _restart_done(args, "restart" if alive else "start", version, started)


def _launch_or_die(cfg, args):
    if getattr(args, "no_launch", False):
        die("Zotero is not running and --no-launch was given.", code=EXIT_GENERIC)
    if not is_loopback(cfg):
        die("Zotero is not answering at %s, which is not this machine — start it "
            "there, or drop --base." % cfg["base"], code=EXIT_CONN)
    cmd = _launch_zotero(cfg)
    if not cmd:
        die("could not find the Zotero app to start (no `app` in the config and no "
            "`zotero` on PATH). Start it yourself; `zot restart` will remember "
            "where it lives from then on.", code=EXIT_GENERIC)
    info("Started Zotero (%s)." % cmd)


def _reload_plugin(cfg, args, timeout, started):
    """Swap the bridge plugin for a freshly loaded copy without closing Zotero.

    This is the cheap answer to "Zotero says restart to finish updating the
    plugin": only the add-on is torn down and started again.
    """
    nonce = secrets.token_hex(8)
    cycle = _js(_RELOAD_CYCLE_JS, nonce=json.dumps(nonce))
    run_js(cfg, _js(_RELOAD_JS, cycle=json.dumps(cycle)),
           timeout=PROBE_TIMEOUT + 10, label="restart:plugin")
    info("Reloading the bridge plugin...")
    deadline = time.monotonic() + timeout
    while True:
        time.sleep(POLL_INTERVAL)
        env = post_code(cfg, _js(_NONCE_JS), timeout=PROBE_TIMEOUT)
        if env.get("ok") and env.get("result") == nonce:
            post_code(cfg, _js(_CLEAR_NONCE_JS), timeout=PROBE_TIMEOUT)
            return _restart_done(args, "reload", env.get("version"), started)
        if time.monotonic() >= deadline:
            die("the plugin did not come back within %ds. Zotero itself should "
                "still be running: check `zot ping`, and if the endpoint stays "
                "down, re-enable Zotero Agent Bridge in Tools -> Plugins (or run "
                "`zot restart`)." % timeout, code=EXIT_CONN)


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
        exe = remember_exe(cfg)   # so `zot restart` can start Zotero later
        if exe:
            print("Detected app     : %s" % exe)
        print("\nAll set. Try:  zot ping")
    else:
        print("\nCould not reach the zotero-agent bridge yet:")
        print("  %s" % (env.get("error") or env))
        print("\nInstall the plugin in Zotero — download the XPI:")
        print("  %s" % XPI_URL)
        print("then Tools -> Plugins -> gear -> \"Install Plugin From File...\"")
        print("(no restart needed). Re-run `zot init` to auto-detect your userID.")


# --------------------------------------------------------------------------- #
# bundled assets: the agent skill and the bridge plugin
# --------------------------------------------------------------------------- #
def _skill_dest(args):
    if args.dest:
        return args.dest
    root = os.path.join(os.getcwd(), ".claude", "skills") if args.project \
        else os.path.expanduser("~/.claude/skills")
    return os.path.join(root, "zotero")


def cmd_skill(args):
    """Install (or locate) the bundled agent skill; print the portable AGENTS.md."""
    from .. import assets
    if args.action == "path":
        print(assets.asset_path("skill"))
        return
    if args.action == "agents-md":
        with open(assets.asset_path("agents-md"), encoding="utf-8") as fh:
            sys.stdout.write(fh.read())
        return

    dest = assets.install_skill(_skill_dest(args), force=args.force, link=args.link)
    print("Installed skill  : %s%s" % (dest, " (symlink)" if args.link else ""))
    print("\nNext: start a new Claude Code session and ask about your library.")
    print("Check the bridge first with `zot ping`; if it is down, install the")
    print("plugin XPI from %s" % XPI_URL)


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
