"""Deciding whether an external record really is the item in hand.

Crossref and OpenAlex always answer. Ask either one for "Mujeres libres en
política" and you get *something* back — in one measured run, a Brill
human-rights dataset. Writing that DOI onto the item is worse than leaving the
field empty, because a wrong identifier is invisible until someone follows the
citation.

So every lookup here is a *candidate* until three independent signals agree:
the title matches closely, the year is compatible, and the author is the same
person. The functions are pure and string-only — no network, no Zotero — so the
thresholds can be tested directly, which is the whole reason they live in their
own module.
"""

import difflib
import html
import re
import unicodedata

# A title has to be nearly identical, not merely similar. 0.92 accommodates
# case, punctuation and a leading chapter number ("27. Civil Society in the
# Digital Age"); it rejects same-topic-different-paper, which is the failure
# mode that matters.
MIN_TITLE_SIMILARITY = 0.92

# With neither a year nor an author to cross-check, title similarity is the
# only evidence there is, so it has to carry the whole weight alone. Measured:
# at 0.94 this still accepted "The OECD Going Digital Measurement Roadmap" as
# "The OECD Going Digital Measurement Roadmap 2026" — a different edition.
MIN_TITLE_SIMILARITY_UNCORROBORATED = 0.98

# Publication years disagree by a year all the time (online-first, print lag,
# the record saying 2010 for a book Zotero has as 2011), so allow a ±1 slip.
MAX_YEAR_DRIFT = 1


def strip_accents(text):
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def norm_title(text):
    """Casefold, drop accents and punctuation, collapse whitespace."""
    flat = strip_accents(text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", flat)).strip()


def title_similarity(a, b):
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def year_of(value):
    """First 4-digit year in a free-text date field, or None."""
    found = re.search(r"\d{4}", str(value or ""))
    return int(found.group(0)) if found else None


def years_compatible(a, b):
    """True when the years agree, or when either side does not know one."""
    ya, yb = year_of(a), year_of(b)
    if ya is None or yb is None:
        return True
    return abs(ya - yb) <= MAX_YEAR_DRIFT


def surname_present(surname, candidate_authors):
    """True when `surname` appears among the candidate's author names.

    Substring rather than equality: sources disagree on compound surnames
    ("García Zaballos" vs "Garcia Zaballos M."), and the item's own field is
    just as likely to hold either half.
    """
    needle = norm_title(surname)
    if not needle:
        return True  # nothing to check against — not a reason to reject
    haystack = norm_title(" ".join(candidate_authors or []))
    return needle in haystack


def clean_abstract(text):
    """Crossref ships abstracts as JATS XML; strip it down to plain text."""
    if not text:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", text)
    unescaped = html.unescape(without_tags)
    collapsed = re.sub(r"\s+", " ", unescaped).strip()
    # The separator after the label is whatever the publisher felt like: a
    # colon, a hyphen, or a Spanish em/en dash.
    return re.sub(r"^(Abstract|Resumen|ABSTRACT|RESUMEN)[\s:.\-‐-―]*", "", collapsed)


def verify(item_title, item_year, item_surname, candidate,
           min_similarity=MIN_TITLE_SIMILARITY):
    """Decide whether `candidate` is the same work as the item.

    `candidate` is the normalised dict the lookup helpers in
    `commands/features.py` build: {"title": str, "year": ..., "authors": [...]}.
    Returns
    (accepted, similarity, reason) — `reason` names the signal that failed, so
    a --dry-run can explain itself.
    """
    similarity = title_similarity(item_title, candidate.get("title"))
    corroborated = bool(year_of(item_year)) or bool((item_surname or "").strip())
    floor = min_similarity if corroborated else max(min_similarity,
                                                    MIN_TITLE_SIMILARITY_UNCORROBORATED)
    if similarity < floor:
        return False, similarity, "title"
    if not years_compatible(item_year, candidate.get("year")):
        return False, similarity, "year"
    if not surname_present(item_surname, candidate.get("authors")):
        return False, similarity, "author"
    return True, similarity, ""
