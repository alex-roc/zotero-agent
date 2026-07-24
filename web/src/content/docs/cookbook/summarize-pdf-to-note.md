---
title: Summarize a PDF into a note
description: Read an item's attached PDF, summarize it bottom-up, and save the result as a child note in Zotero.
---

## The problem

You have a 60-page report attached to a Zotero item and you want a structured
summary you can find later — living *on the item*, not in a separate app.
Zotero has no built-in "summarize this attachment," and copying text out to an
LLM by hand loses the link back to the reference.

## Via an AI agent

> "Summarize the PDF on item `@ojedaDigitalizacion2025` chapter by chapter, keep
> page references, fold in my existing highlights, and save it as a note on the
> item."

The agent resolves the item, gets the PDF path, reads it directly (in page
ranges), summarizes bottom-up so each step fits in context, incorporates your
annotations, and writes the result back as a child note.

## Via the CLI

The CLI locates the PDF and manages the note; **you** (or your agent) do the
reading and writing of prose.

```bash
zot pdf @ojedaDigitalizacion2025        # -> local path to the PDF
zot annotations @ojedaDigitalizacion2025 # your highlights (what you flagged matters)
```

Read the PDF file directly with a PDF-capable tool — only the page ranges you
need. For long documents, summarize **bottom-up**: section → chapter → whole,
keeping page references at each level. Then save the summary as a child note:

```bash
zot note @ojedaDigitalizacion2025 --file summary.html --if-not-exists
zot notes @ojedaDigitalizacion2025       # list the item's notes to confirm
```

`zot annotations <key> --to-note` can also turn your existing highlights straight
into a note.

## Safety net

Notes are low-risk: they are added as **child items** and are reversible via
trash, not permanent erase. Prefer notes over writing PDF annotations back —
placing highlights requires fragile coordinate math. Use `--if-not-exists` to
avoid creating a duplicate note if you re-run the workflow. To remove a note,
send it to the trash rather than erasing it.
