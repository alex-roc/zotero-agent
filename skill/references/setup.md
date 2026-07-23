# Setup (skill quick pointer)

This skill needs two things live:

1. **Zotero running** with its local HTTP API enabled
   (Preferences → Advanced → *Allow other applications on this computer to
   communicate with Zotero* — on by default).
2. **The `zotero-exec` plugin installed**, which adds the `POST /zotexec`
   write endpoint.

Verify with `zot ping`.

Full installation instructions — installing the plugin, generating the token,
writing config, per-OS paths, restarting Zotero — live in the repo's
**`docs/install.md`**. Security model: **`docs/security.md`**. Why the write
path is a plugin at all: **`docs/architecture.md`**.

If `zot ping` reports the zotexec endpoint as FAIL, the plugin is not loaded —
send the user to `docs/install.md`; do not attempt writes via the read API
(it is read-only and will return `400 "Endpoint does not support method"`).
