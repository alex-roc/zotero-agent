/*
 * zotero-agent bridge — bootstrap plugin
 *
 * Registers a single local HTTP endpoint:  POST /zotero-agent
 * Body: { "code": "<async JS body>" }  ->  runs the code in Zotero's privileged
 * context and returns { ok: true, result, version } or { ok: false, error }.
 *
 * The endpoint is the write path for the `zot` CLI, the MCP server and the
 * agent skill. See docs/security.md for the threat model. Short version:
 *   - a token is REQUIRED (403 without it),
 *   - browser-origin requests are rejected (CSRF / DNS-rebinding),
 *   - the server binds to loopback (Zotero default).
 *
 * Copyright (C) 2026 zotero-agent contributors.
 * Licensed under the GNU Affero General Public License v3 or later; see LICENSE.
 */

/* eslint-disable no-var */
if (typeof Zotero == "undefined") {
  var Zotero;
}

var BRIDGE = {
  version: "0.8.3",
  endpointPath: "/zotero-agent",
  tokenPref: "extensions.zotero-agent.token",
  tokenHeader: "X-Zotero-Agent-Token",
  configDir: "zotero-agent",
  // AsyncFunction constructor from the privileged realm (preferred executor).
  AsyncFunction: Object.getPrototypeOf(async function () {}).constructor,
};

function log(msg) {
  try {
    Zotero.debug("[zotero-agent] " + msg);
  } catch (e) {
    dump("[zotero-agent] " + msg + "\n");
  }
}

/* ------------------------------------------------------------------ *
 * Token resolution
 *   1. pref override  extensions.zotero-agent.token
 *   2. shared config file  ~/.config/zotero-agent/config.json  { "token": ... }
 * The config file is the single source of truth the `zot` CLI also reads,
 * so rotating the token needs no Zotero restart.
 * ------------------------------------------------------------------ */
async function getConfiguredToken() {
  try {
    var pref = Zotero.Prefs.get(BRIDGE.tokenPref, true);
    if (pref) return String(pref);
  } catch (e) {
    /* pref not set */
  }
  try {
    var home = Services.dirsvc.get("Home", Components.interfaces.nsIFile).path;
    var cfgPath = PathUtils.join(home, ".config", BRIDGE.configDir, "config.json");
    var txt = await Zotero.File.getContentsAsync(cfgPath);
    var cfg = JSON.parse(txt);
    if (cfg && cfg.token) return String(cfg.token);
  } catch (e) {
    /* no config file */
  }
  return null;
}

/* ------------------------------------------------------------------ *
 * Request-origin guard: reject anything that looks like it came from a
 * web page (a real browser sends Origin/Referer with an http(s) scheme).
 * A CLI using urllib sends neither. Also require a loopback Host.
 * ------------------------------------------------------------------ */
function headerGet(headers, name) {
  if (!headers) return null;
  var lower = name.toLowerCase();
  for (var k in headers) {
    if (k.toLowerCase() === lower) return headers[k];
  }
  return null;
}

function originRejected(headers) {
  var origin = headerGet(headers, "Origin");
  var referer = headerGet(headers, "Referer");
  var web = /^https?:\/\//i;
  if (origin && web.test(origin)) return "origin not allowed";
  if (referer && web.test(referer)) return "referer not allowed";
  var host = headerGet(headers, "Host");
  if (host) {
    var h = host.split(":")[0].toLowerCase();
    if (h !== "localhost" && h !== "127.0.0.1" && h !== "[::1]" && h !== "::1") {
      return "host not allowed";
    }
  }
  return null;
}

/* ------------------------------------------------------------------ *
 * Executor: run the user code with Zotero (and ZoteroPane, when a main
 * window exists) in scope. Falls back to evalInSandbox if the
 * AsyncFunction constructor is ever blocked by CSP.
 * ------------------------------------------------------------------ */
async function runCode(code) {
  var win = null;
  try {
    win = Zotero.getMainWindow();
  } catch (e) {
    /* headless */
  }
  var ZoteroPane = win && win.ZoteroPane ? win.ZoteroPane : null;
  try {
    var fn = new BRIDGE.AsyncFunction("Zotero", "ZoteroPane", "window", code);
    return await fn(Zotero, ZoteroPane, win);
  } catch (e) {
    if (e instanceof SyntaxError || /CSP|unsafe-eval|Function/.test(String(e))) {
      // fallback: sandbox with Zotero injected
      var sandbox = Components.utils.Sandbox(
        Components.classes["@mozilla.org/systemprincipal;1"].createInstance(),
        { wantXrays: false }
      );
      sandbox.Zotero = Zotero;
      sandbox.ZoteroPane = ZoteroPane;
      var wrapped = "(async function(){" + code + "})()";
      return await Components.utils.evalInSandbox(wrapped, sandbox);
    }
    throw e;
  }
}

/* ------------------------------------------------------------------ *
 * The endpoint
 * ------------------------------------------------------------------ */
function ExecEndpoint() {}
ExecEndpoint.prototype = {
  supportedMethods: ["POST"],
  supportedDataTypes: ["application/json"],

  init: async function (request) {
    var headers = request && request.headers;
    var data = request && request.data;
    var json = function (code, obj) {
      return [code, "application/json", JSON.stringify(obj)];
    };

    try {
      // 1. auth
      var expected = await getConfiguredToken();
      if (!expected) {
        return json(403, { ok: false, error: "zotero-agent: no token configured" });
      }
      var provided = headerGet(headers, BRIDGE.tokenHeader);
      if (provided !== expected) {
        return json(403, { ok: false, error: "zotero-agent: invalid or missing token" });
      }

      // 2. origin guard
      var bad = originRejected(headers);
      if (bad) {
        return json(403, { ok: false, error: "zotero-agent: " + bad });
      }

      // 3. body
      if (!data || typeof data.code !== "string" || !data.code.trim()) {
        return json(400, { ok: false, error: "zotero-agent: body must be {\"code\": \"...\"}" });
      }

      // 4. audit + run
      log("exec (" + data.code.length + " bytes)");
      var result = await runCode(data.code);
      if (result === undefined) result = null;
      return json(200, { ok: true, result: result, version: BRIDGE.version });
    } catch (e) {
      log("error: " + (e && e.stack ? e.stack : e));
      return json(500, {
        ok: false,
        error: String(e && e.message ? e.message : e),
        stack: e && e.stack ? String(e.stack) : undefined,
      });
    }
  },
};

/* ------------------------------------------------------------------ *
 * Bootstrap lifecycle
 * ------------------------------------------------------------------ */
function registerEndpoint() {
  if (!Zotero.Server || !Zotero.Server.Endpoints) {
    log("Zotero.Server not available; endpoint not registered");
    return;
  }
  Zotero.Server.Endpoints[BRIDGE.endpointPath] = ExecEndpoint;
  log("registered endpoint " + BRIDGE.endpointPath);
}

function unregisterEndpoint() {
  try {
    if (Zotero.Server && Zotero.Server.Endpoints) {
      delete Zotero.Server.Endpoints[BRIDGE.endpointPath];
      log("unregistered endpoint " + BRIDGE.endpointPath);
    }
  } catch (e) {
    /* ignore */
  }
}

// eslint-disable-next-line no-unused-vars
async function startup({ id, version, rootURI }, reason) {
  if (typeof Zotero == "undefined" || !Zotero) {
    Zotero = Components.classes["@zotero.org/Zotero;1"]
      .getService(Components.interfaces.nsISupports)
      .wrappedJSObject;
  }
  // Wait until Zotero core (and Zotero.Server) is ready.
  if (Zotero.initializationPromise) {
    await Zotero.initializationPromise;
  }
  registerEndpoint();
}

// eslint-disable-next-line no-unused-vars
function shutdown(data, reason) {
  unregisterEndpoint();
}

// eslint-disable-next-line no-unused-vars
function install(data, reason) {}

// eslint-disable-next-line no-unused-vars
function uninstall(data, reason) {}
