# Zotero forums announcement

**Where:** forums.zotero.org — "Third-party Plugins & Add-ons" (or the general
forum if that fits better).

**Tone note:** you're a maintainer talking to fellow Zotero users, not selling.
Lead with the problem people already know, be plain about the trade-off (it runs
privileged JS), and genuinely ask for a security review — the people here will
give you a real one.

---

**Subject:** zotero-agent — local read-write control of your library from a CLI or AI agent (no account/API key)

I've been building a small open-source tool called **zotero-agent** and wanted to
share it here and, honestly, ask for scrutiny of its security design.

The local HTTP API is read-only — writes return `501`/`400`, and there's no pref
to enable them. So batch metadata editing, real dedup and tag cleanup (things
asked for on these forums since [2016](https://forums.zotero.org/discussion/111815/feature-batch-editing-metadata-for-multiple-items))
still have no local path. Existing automation tools work only through the
zotero.org web API, which means an account, an API key and sync.

zotero-agent takes the other route: a tiny bridge plugin exposes **one**
token-protected endpoint that runs privileged JS in-process, so a CLI (`zot`) or
an AI agent can edit the library **locally**. Nothing leaves the machine — no
account, no key, no cloud.

The endpoint runs arbitrary privileged JS, which is powerful and deliberate, so
it's guarded by three layers: a required token (fail-closed), an origin/host
guard against browser CSRF/DNS-rebinding, and loopback-only binding. It's all
written up here: https://github.com/alex-roc/zotero-agent/blob/main/docs/security.md

**I'd really value feedback on that security model** — especially the browser
attack surface and anything I've missed. Repo (MIT): https://github.com/alex-roc/zotero-agent
