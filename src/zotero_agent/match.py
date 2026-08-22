"""Deciding whether an external record really is the item in hand.

Crossref and OpenAlex always answer. Ask either one for "Mujeres libres en
política" and you get *something* back — in one measured run, a Brill
human-rights dataset. Writing that DOI onto the item is worse than leaving the
field empty, because a wrong identifier is invisible until someone follows the
citation.

So every lookup here is a *candidate* until three independent signals agree:
the title matches closely, the year is compatible, and the author is the same
person. And when there is no year and no author, the title itself has to be
specific enough to identify anything: a one-word title matches something
everywhere, perfectly, and no similarity threshold can tell that apart. The functions are pure and string-only — no network, no Zotero — so the
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

# A title only identifies a work if it carries enough information to be unique.
# Measured on a library whose items had been created from PDF filenames: titles
# like "deposito", "vermis" and "Esbozo" all matched real Crossref records at
# similarity 1.000 — a perfect match against a different work entirely. No
# threshold on similarity can catch that, because the similarity is genuinely
# perfect; what fails is the premise that the title is an identifier.
#
# So an uncorroborated title also has to clear a floor of its own. Four
# significant words is the measured line: "Ética de la inteligencia artificial"
# keeps four after stopwords and passes, while "El Giro Afectivo" keeps two and
# is held back for a human to look at.
MIN_DISTINCTIVE_WORDS = 4
MIN_DISTINCTIVE_CHARS = 18

# Words that carry no identifying weight, in the two languages this library
# lives in. Kept deliberately short: this is not a stopword list for search,
# only for judging whether a title says anything.
_FILLER = frozenset("""
a an the of and or in on to for with without from by at as is are be
el la los las un una unos unas de del y o en con sin para por al sobre
que su sus lo se es son ser mas mas
""".split())


def strip_accents(text):
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def norm_title(text):
    """Casefold, drop accents and punctuation, collapse whitespace."""
    flat = strip_accents(text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", flat)).strip()



def significant_words(text):
    """Words of a title that actually carry identity: no fillers, no 1-2 letters."""
    return [w for w in norm_title(text).split()
            if len(w) > 2 and w not in _FILLER]


def title_is_distinctive(text):
    """Can this title identify a work on its own?

    Used only when there is no year and no author to cross-check. A short or
    generic title matches *something* in every bibliographic database, and the
    match is perfect, so similarity cannot be the guard here.
    """
    words = significant_words(text)
    if len(words) >= MIN_DISTINCTIVE_WORDS:
        return True
    # a couple of long words can still be specific ("Zettelkasten Methode")
    return len("".join(words)) >= MIN_DISTINCTIVE_CHARS and len(words) >= 2



def author_corroborates(item_title, item_surname):
    """¿El autor es una señal *independiente* del título?

    El módulo se apoya en que título, año y autor son tres pruebas distintas.
    Deja de ser cierto cuando el título es el propio apellido — pasa con fichas
    creadas desde nombres de archivo como "Marias (1980). Historia de la
    filosofia", donde el parseo se quedó en "Marias". Contarlo como corroboración
    es contar la misma evidencia dos veces, y en una prueba real hizo aceptar la
    tesis doctoral de otra persona llamada igual.
    """
    surname = norm_title(item_surname)
    if not surname:
        return False
    words = significant_words(item_title)
    if len(words) > 2:
        return True          # el título dice bastante más que el apellido
    title = " ".join(words)
    return not (title == surname or title in surname or surname in title)


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

    # Una señal solo corrobora si se ha podido COMPARAR de verdad. Tener año en
    # el ítem no sirve de nada si el candidato no trae ninguno: ahí no hay
    # comprobación, solo la ilusión de tenerla. Fue así como un ítem titulado
    # "Marias" con año 1980 aceptó una tesis de Unicamp sin fecha declarada.
    year_checked = (year_of(item_year) is not None
                    and year_of(candidate.get("year")) is not None)
    author_checked = (author_corroborates(item_title, item_surname)
                      and bool(candidate.get("authors")))
    corroborated = year_checked or author_checked

    floor = min_similarity if corroborated else max(min_similarity,
                                                    MIN_TITLE_SIMILARITY_UNCORROBORATED)
    if similarity < floor:
        return False, similarity, "title"
    if not years_compatible(item_year, candidate.get("year")):
        return False, similarity, "year"
    if not surname_present(item_surname, candidate.get("authors")):
        return False, similarity, "author"
    # Lo último: si el título no identifica nada por sí solo y ninguna otra
    # señal llegó a comprobarse, la coincidencia perfecta no prueba nada.
    if not corroborated and not title_is_distinctive(item_title):
        return False, similarity, "vague-title"
    return True, similarity, ""
