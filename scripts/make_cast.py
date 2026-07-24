#!/usr/bin/env python3
"""Author the README/website demo as an asciicast v2 file, then render to GIF.

The command output below is captured verbatim from a real run (read-only + a
--dry-run), so regenerating needs no Zotero and is fully reproducible:

    python scripts/make_cast.py                                   # -> web/public/demo.cast
    agg --font-size 20 --theme monokai web/public/demo.cast web/public/demo.gif

(agg = asciinema gif generator, `brew install agg` — a single binary, no
browser/ttyd, unlike vhs.) Update the output strings here when the CLI's output
changes."""
import json

WIDTH, HEIGHT = 92, 24
GREEN = "[32m"
DIM = "[90m"
RESET = "[0m"

events = []
t = [0.0]


def emit(s):
    events.append([round(t[0], 3), "o", s])


def wait(dt):
    t[0] += dt


def prompt():
    emit(GREEN + "$ " + RESET)


def type_cmd(cmd):
    prompt()
    for ch in cmd:
        emit(ch)
        wait(0.045)
    wait(0.35)
    emit("\r\n")


def out(lines, per_line=0.06, pause=1.3):
    for ln in lines:
        emit(ln + "\r\n")
        wait(per_line)
    wait(pause)


def comment(text, pause=0.8):
    # a shell comment: typed, no output
    type_cmd(text)
    wait(pause)


wait(0.6)
comment("# zotero-agent: local read-write control of Zotero — shell or AI agent")

type_cmd("zot ping")
out([
    "Zotero local API : up (HTTP 200)",
    "bridge endpoint  : up (/zotero-agent, 1+1 == 2)",
    "userID           : 2960998",
    "zot version      : 0.2.1",
])

type_cmd('zot search "bolivia" --limit 4')
out([
    DIM + "... showing 4 of 375 — use --all to fetch everything" + RESET,
    "84EPQIZ4   bookSection     2025   Bolivia 2025: Digitalización, hiperabigarramiento",
    "EUGAM49M   journalArticle         Apuntes críticos sobre la filosofía política en Bolivia",
    "RRZAKF9M   webpage                Orígenes de la Sociología boliviana",
    "VTH5YVQF   journalArticle  1959   Gustavo A. Otero y su Contribución a la Sociología",
])

type_cmd("zot stats")
out([
    "Library: 2865 items · 344 collections · 145 tags",
    "PDFs: 1643 with · 1222 without   |   1654 without abstract",
    "",
    "By type:",
    "   980  book",
    "   903  journalArticle",
    "   460  webpage",
    "   172  blogPost",
    "   101  bookSection",
])

comment("# batch edits are declarative and undoable — preview first (runs NO JS):")
type_cmd("zot apply edits.jsonl --dry-run")
out([
    "DRY-RUN — no changes will be persisted.",
    "Would apply 2 edit(s):",
    "  ABCD1234   set date; +tags ['review']",
    "  EFGH5678   → To Read",
])

comment("# nothing was written. local, private, reversible — that's the whole pitch.", pause=2.5)

header = {"version": 2, "width": WIDTH, "height": HEIGHT,
          "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"}}
with open("web/public/demo.cast", "w", encoding="utf-8") as fh:
    fh.write(json.dumps(header) + "\n")
    for ev in events:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
print("wrote web/public/demo.cast (%d events, %.1fs)" % (len(events), t[0]))
