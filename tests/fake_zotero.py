"""A tiny stdlib HTTP server that mimics Zotero's local API + the bridge.

Used by the integration tests so they exercise the real urllib code paths
without a running Zotero. It handles:

  GET  /api/                                 -> 200 (liveness)
  GET  /api/users/<id>/items|collections|tags -> canned JSON + Total-Results
  POST /zotero-agent                          -> {ok, result} from a code->result map

The POST handler validates the token header and returns a canned result chosen
by a substring match against the posted code (see `bridge_results`).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from zotero_agent.constants import ENDPOINT_PATH, TOKEN_HEADER


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _send(self, code, body, headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        cfg = self.server.cfg
        path = self.path.split("?")[0]
        if path == "/api/":
            return self._send(200, "{}")
        for name, payload in cfg["lists"].items():
            if path.endswith("/" + name):
                total = str(cfg.get("totals", {}).get(name, len(payload)))
                return self._send(200, json.dumps(payload), {"Total-Results": total})
        if "/items/" in path:  # single item / bib
            return self._send(200, json.dumps(cfg.get("item", {"data": {"key": "X"}})))
        return self._send(404, "{}")

    def do_POST(self):
        cfg = self.server.cfg
        if self.path != ENDPOINT_PATH:
            return self._send(404, json.dumps({"ok": False, "error": "no such endpoint"}))
        token = self.headers.get(TOKEN_HEADER)
        if token != cfg["token"]:
            return self._send(403, json.dumps({"ok": False, "error": "invalid or missing token"}))
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        code = body.get("code", "")
        self.server.last_code = code
        self.server.last_codes.append(code)
        result = 2  # default: the 1+1 liveness probe
        for needle, value in cfg.get("bridge_results", {}).items():
            if needle in code:
                # A value may be a callable (code) -> result so different
                # snapshot/apply/undo calls can return different things.
                result = value(code) if callable(value) else value
                break
        return self._send(200, json.dumps({"ok": True, "result": result}))


class FakeZotero:
    """Context manager starting the server on an ephemeral port."""

    def __init__(self, token="testtoken", lists=None, totals=None,
                 bridge_results=None, item=None):
        self.cfg = {
            "token": token,
            "lists": lists or {},
            "totals": totals or {},
            "bridge_results": bridge_results or {},
            "item": item or {"data": {"key": "X", "title": "T"}},
        }

    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.cfg = self.cfg
        self.httpd.last_code = None
        self.httpd.last_codes = []
        self.port = self.httpd.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def last_code(self):
        return self.httpd.last_code

    @property
    def last_codes(self):
        return self.httpd.last_codes

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
