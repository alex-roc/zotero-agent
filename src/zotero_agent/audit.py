"""Append-only audit log of every bridge execution.

Because the product *is* a privileged-JS execution endpoint, keeping a local,
tamper-evident-ish record of what ran is a cheap, honest safeguard. One JSONL
line per call in ~/.local/state/zotero-agent/audit.jsonl, rotated by size.

Disabled with ZOTERO_AGENT_NO_AUDIT=1. Never raises into the caller.
"""

import hashlib
import json
import os

from .constants import STATE_DIR

AUDIT_PATH = os.path.join(STATE_DIR, "audit.jsonl")
MAX_BYTES = 5 * 1024 * 1024  # rotate at 5 MB


def _timestamp():
    # datetime.now() is fine at runtime; kept in a helper so tests can patch it.
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _rotate_if_needed():
    try:
        if os.path.exists(AUDIT_PATH) and os.path.getsize(AUDIT_PATH) > MAX_BYTES:
            os.replace(AUDIT_PATH, AUDIT_PATH + ".1")
    except OSError:
        pass


def record(label, code, envelope):
    """Record one bridge call. `envelope` is the parsed {ok, result|error}."""
    if os.environ.get("ZOTERO_AGENT_NO_AUDIT") == "1":
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        _rotate_if_needed()
        code = code or ""
        entry = {
            "ts": _timestamp(),
            "label": label,
            "codeSHA256": hashlib.sha256(code.encode("utf-8")).hexdigest()[:16],
            "codeBytes": len(code),
            "codeHead": code.strip().splitlines()[0][:120] if code.strip() else "",
            "ok": bool(envelope.get("ok")),
        }
        if not envelope.get("ok"):
            entry["error"] = str(envelope.get("error", ""))[:200]
        result = envelope.get("result")
        if isinstance(result, dict) and "wouldWrite" in result:
            entry["dryRunWrites"] = len(result.get("wouldWrite") or [])
        with open(AUDIT_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Auditing must never break the actual operation.
        pass
