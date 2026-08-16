# Setup (skill quick pointer)

This skill needs two things live:

1. **Zotero running** with its local HTTP API enabled
   (Preferences → Advanced → *Allow other applications on this computer to
   communicate with Zotero* — on by default).
2. **The `zotero-agent` bridge plugin installed**, which adds the `POST /zotero-agent`
   write endpoint.

Verify with `zot ping`.

The plugin XPI is distributed in exactly one place — the latest GitHub Release,
via this permanent link:

```
https://github.com/alex-roc/zotero-agent/releases/latest/download/zotero-agent-bridge.xpi
```

Installing it: *Tools → Plugins → gear icon → "Install Plugin From File…"* → pick
that file. No restart needed; Zotero auto-updates it afterwards. There is no
build step and no other source — never offer to build or fetch it another way.

Full installation instructions — token, config, per-OS paths, updating — live in
the repo's **`docs/install.md`** (or the website's Install page). Security model:
**`docs/security.md`**. Why the write path is a plugin at all:
**`docs/architecture.md`**.

If `zot ping` reports the bridge endpoint as FAIL, the plugin is not loaded —
point the user at the link above; do not attempt writes via the read API
(it is read-only and will return `400 "Endpoint does not support method"`).
`zot ping` also prints the installed plugin's version: if it is older than the
CLI, tell the user to run *Tools → Plugins → gear → Check for Updates*. When
Zotero then asks for a restart, `zot restart --plugin --yes` reloads the bridge
in place; `zot restart --yes` restarts Zotero itself and waits for the endpoint
to come back. With Zotero closed, `zot restart --yes` starts it. Ask before
running any of them — the user may have unsaved work in Zotero.
