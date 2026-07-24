---
title: Import by identifier
description: Add items to Zotero by DOI, ISBN, or arXiv ID — optionally with an open-access PDF — from the terminal or an agent.
---

## The problem

You have a list of DOIs (or ISBNs, or arXiv IDs) from a reading list, a syllabus,
or a paper's references, and you want them in Zotero with full metadata and PDFs.
Clicking each one through the browser connector is slow, and it doesn't script.

## Via an AI agent

> "Add these three DOIs to my *To Read* collection with their open-access PDFs:
> 10.1371/journal.pmed.0020124, 10.1145/3442188.3445922, 10.1038/s41586-021-03819-2."

The agent runs one `zot add` per identifier, attaches the OA PDF when available,
and files each into the collection.

## Via the CLI

```bash
zot add doi 10.1371/journal.pmed.0020124 --pdf                 # DOI + open-access PDF
zot add isbn 9780262035613 --collection "To Read"              # ISBN into a collection
zot add arxiv 2103.00020 --pdf --collection "To Read"          # arXiv + PDF
```

`--pdf` fetches an open-access PDF when one is available; `--collection` files
the new item directly. Metadata is resolved from the identifier, so the imported
item lands with title, authors, date, and DOI already populated.

Scripting a whole list:

```bash
while read -r doi; do
  zot add doi "$doi" --pdf --collection "To Read" --yes
done < dois.txt
```

## Safety net

Imports are additive — they create new items and never modify or delete existing
ones, so they are low-risk. If an import is wrong, send the new item to the trash
(recoverable) rather than erasing it. Run `zot missing doi` or `zot lint`
afterward to confirm the new items came in clean, and see
[Find missing metadata](/zotero-agent/cookbook/find-missing-metadata/) to fill any gaps.
