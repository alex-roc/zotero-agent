"""HTTP helpers: the read API (GET), the bridge endpoint (POST), and BBT JSON-RPC.

Stdlib urllib only. The bridge round-trip is audited (see audit.py).
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from .constants import ENDPOINT_PATH, EXIT_CONN, EXIT_NOTFOUND, TOKEN_HEADER
from .term import die


def http_get(url, timeout=30):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def http_get_full(url, timeout=30):
    """Like http_get but also returns response headers (for pagination)."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, dict(resp.headers), resp.read().decode("utf-8")


def api_url(cfg, path, params=None):
    uid = cfg.get("userID")
    if not uid:
        die("userID unknown. Run `zot init` (with the plugin installed) to detect it.")
    url = "%s/api/users/%s/%s" % (cfg["base"].rstrip("/"), uid, path.lstrip("/"))
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


def api_list(cfg, path, params=None, want_all=False, limit=25):
    """GET a JSON list endpoint, honoring the read API's pagination.

    Returns (items, total). Without want_all, fetches up to `limit`; with
    want_all, pages through in chunks of 100 until the Total-Results count is
    reached. `total` is the server's Total-Results (int) or None.
    """
    params = dict(params or {})
    collected = []
    total = None
    start = 0
    while True:
        req_limit = 100 if want_all else limit
        params["start"] = start
        params["limit"] = req_limit
        _, headers, body = http_get_full(api_url(cfg, path, params))
        if total is None and headers.get("Total-Results") is not None:
            try:
                total = int(headers["Total-Results"])
            except ValueError:
                total = None
        chunk = json.loads(body)
        if not isinstance(chunk, list):
            return chunk, total
        collected.extend(chunk)
        if not want_all or len(chunk) < req_limit:
            break
        if total is not None and len(collected) >= total:
            break
        start += req_limit
    return collected, total


def api_get_all_keys(cfg, path, params=None):
    """Page through a list endpoint in format=keys, returning a list of item keys.

    Used by exporters that must not truncate: the read API's native bibtex/ris
    exporters cap at a page, so we resolve the full key set first.
    """
    params = dict(params or {})
    params["format"] = "keys"
    keys = []
    start = 0
    total = None
    while True:
        params["start"] = start
        params["limit"] = 100
        _, headers, body = http_get_full(api_url(cfg, path, params))
        if total is None and headers.get("Total-Results") is not None:
            try:
                total = int(headers["Total-Results"])
            except ValueError:
                total = None
        chunk = [k for k in body.strip().splitlines() if k.strip()]
        keys.extend(chunk)
        if len(chunk) < 100:
            break
        if total is not None and len(keys) >= total:
            break
        start += 100
    return keys


def api_export_all(cfg, path, fmt, extra_params=None):
    """Page through a list endpoint in a raw export `fmt` (bibtex/biblatex/ris),
    concatenating every page so large collections are never silently truncated.

    Returns (text, total).
    """
    params = dict(extra_params or {})
    params["format"] = fmt
    params["limit"] = 100
    parts = []
    total = None
    start = 0
    while True:
        params["start"] = start
        _, headers, body = http_get_full(api_url(cfg, path, params))
        if total is None and headers.get("Total-Results") is not None:
            try:
                total = int(headers["Total-Results"])
            except ValueError:
                total = None
        parts.append(body)
        start += 100
        if total is None or start >= total:
            break
    return "\n".join(p.strip("\n") for p in parts if p.strip()), total


def truncation_notice(shown, total, want_all):
    from .term import info
    if not want_all and total is not None and total > shown:
        info("... showing %d of %d — use --all to fetch everything" % (shown, total))


def post_code(cfg, code, timeout=120):
    """POST code to the bridge endpoint. Returns the parsed JSON envelope."""
    url = cfg["base"].rstrip("/") + ENDPOINT_PATH
    body = json.dumps({"code": code}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            TOKEN_HEADER: cfg["token"],
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except OSError:
            raw = ""
        finally:
            e.close()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": "HTTP %s: %s" % (e.code, raw)}
    except urllib.error.URLError as e:
        return {"ok": False, "error": "cannot reach %s (%s)" % (url, e.reason)}
    except (TimeoutError, OSError) as e:
        # a slow bridge call (e.g. a heavy JS loop) can hit the socket timeout;
        # surface it cleanly instead of crashing with a traceback.
        return {"ok": False, "error": "bridge call to %s timed out or failed (%s). "
                "For heavy operations, scope with --collection." % (url, e)}


def bbt_rpc(cfg, method, params, timeout=30):
    """Call the Better BibTeX JSON-RPC endpoint. Returns the `result` or raises."""
    url = cfg["base"].rstrip("/") + "/better-bibtex/json-rpc"
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        die("cannot reach Better BibTeX JSON-RPC (%s). Is the BBT plugin installed?" % e.reason)
    if "error" in payload:
        die("BBT JSON-RPC error: %s" % payload["error"])
    return payload.get("result")


def run_js(cfg, code, timeout=120, label=None):
    """Send JS to the bridge and return the result, or die with the error.

    Records the execution to the audit log (best-effort).
    """
    from . import audit
    env = post_code(cfg, code, timeout=timeout)
    audit.record(label or "run_js", code, env)
    if not env.get("ok"):
        die(env.get("error") or "bridge error", code=EXIT_CONN)
    result = env.get("result")
    if isinstance(result, dict) and result.get("error"):
        die(result["error"], code=EXIT_NOTFOUND)
    return result
