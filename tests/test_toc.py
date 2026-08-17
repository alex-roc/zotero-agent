"""Tests for `zot toc` — PDF outline detection and writing.

Two tiers, on purpose. The page-number arithmetic is the part that is subtle and
easy to get quietly wrong, so it lives in pure functions that run everywhere with
no PDF engine and no fixture file. The engine-dependent tests build their own
document with PyMuPDF at runtime — a checked-in binary fixture nobody can read a
diff of would be worse — and skip when the [toc] extra is not installed.

    python -m unittest discover -s tests
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

os.environ["ZOTERO_AGENT_NO_AUDIT"] = "1"

from zotero_agent import cli  # noqa: E402
from zotero_agent.commands import features  # noqa: E402
from zotero_agent.commands import toc as toc_cmd  # noqa: E402
from zotero_agent.pdf import load_pymupdf, outline, pagemap  # noqa: E402
from zotero_agent.term import ZotError, set_verbosity  # noqa: E402

set_verbosity(quiet=True)

pymupdf = load_pymupdf()
needs_engine = unittest.skipUnless(pymupdf is not None,
                                   "PyMuPDF is not installed (the [toc] extra)")


# =========================================================================== #
# pure: roman numerals
# =========================================================================== #
class TestRomanNumerals(unittest.TestCase):
    def test_round_trips(self):
        for n in (1, 4, 9, 14, 40, 49, 90, 99, 154):
            self.assertEqual(pagemap.roman_to_int(pagemap.int_to_roman(n)), n, n)

    def test_is_case_insensitive(self):
        self.assertEqual(pagemap.roman_to_int("XXIV"), 24)
        self.assertEqual(pagemap.roman_to_int("xxiv"), 24)

    def test_rejects_non_numerals(self):
        self.assertEqual(pagemap.roman_to_int("hello"), 0)
        self.assertEqual(pagemap.roman_to_int(""), 0)
        self.assertEqual(pagemap.roman_to_int(None), 0)


# =========================================================================== #
# pure: parsing a printed contents line
# =========================================================================== #
class TestParseTocLine(unittest.TestCase):
    def test_dot_leaders(self):
        got = pagemap.parse_toc_line("Introducción .......... 15")
        self.assertEqual(got, {"title": "Introducción", "printedPage": 15, "roman": False})

    def test_tight_leaders_and_numbered_title(self):
        got = pagemap.parse_toc_line("1.1 Antecedentes....17")
        self.assertEqual(got["title"], "1.1 Antecedentes")
        self.assertEqual(got["printedPage"], 17)

    def test_unicode_leaders_and_roman_page(self):
        got = pagemap.parse_toc_line("Prefacio······ix")
        self.assertEqual(got["printedPage"], 9)
        self.assertTrue(got["roman"])

    def test_plain_spacing(self):
        got = pagemap.parse_toc_line("Bibliografía   201")
        self.assertEqual(got, {"title": "Bibliografía", "printedPage": 201, "roman": False})

    def test_keeps_a_chapter_number_in_the_title(self):
        got = pagemap.parse_toc_line("Chapter 1. Introduction .... 15")
        self.assertEqual(got["title"], "Chapter 1. Introduction")
        self.assertEqual(got["printedPage"], 15)

    def test_non_breaking_space_before_the_leader(self):
        got = pagemap.parse_toc_line("Prefacio . . . . . 12")
        self.assertEqual(got["title"], "Prefacio")
        self.assertEqual(got["printedPage"], 12)

    def test_rejects_a_bare_structural_heading(self):
        # "Capítulo 1" is a heading, not an entry; accepting it would point an
        # outline row at page 1.
        self.assertIsNone(pagemap.parse_toc_line("Capítulo 1"))
        self.assertIsNone(pagemap.parse_toc_line("Chapter 12"))

    def test_rejects_an_exhibit_label(self):
        # A list of figures reads "Tabla 12 ..... 255" on every row; without this
        # the outline fills up with entries called "Tabla".
        self.assertIsNone(pagemap.parse_toc_line("Tabla 12"))
        self.assertIsNone(pagemap.parse_toc_line("Mapa 4"))
        self.assertIsNone(pagemap.parse_toc_line("Figure 3"))
        # ...but a real section whose title merely starts that way is fine.
        got = pagemap.parse_toc_line("Tablas comparativas del período .... 88")
        self.assertEqual(got["printedPage"], 88)

    def test_rejects_a_word_tail_that_looks_roman(self):
        # roman_to_int("mix") is 1009; the ceiling is what stops it.
        self.assertIsNone(pagemap.parse_toc_line("Index — mix"))

    def test_rejects_lines_without_a_page_number(self):
        self.assertIsNone(pagemap.parse_toc_line("Just a sentence of prose"))
        self.assertIsNone(pagemap.parse_toc_line(""))
        self.assertIsNone(pagemap.parse_toc_line("   "))

    def test_rejects_a_bare_folio(self):
        self.assertIsNone(pagemap.parse_toc_line("... 42"))


# =========================================================================== #
# pure: hierarchy from indentation
# =========================================================================== #
class TestLevelsFromIndents(unittest.TestCase):
    def test_ranks_indents_into_levels(self):
        self.assertEqual(pagemap.levels_from_indents([72.0, 90.0, 90.5, 72.0, 108.0]),
                         [1, 2, 2, 1, 3])

    def test_tolerates_justification_jitter(self):
        self.assertEqual(pagemap.levels_from_indents([72.0, 73.5, 72.4]), [1, 1, 1])

    def test_empty(self):
        self.assertEqual(pagemap.levels_from_indents([]), [])

    def test_caps_at_max_level(self):
        indents = [10.0, 30.0, 50.0, 70.0, 90.0, 110.0, 130.0]
        self.assertEqual(max(pagemap.levels_from_indents(indents, max_level=3)), 3)


# =========================================================================== #
# pure: printed page -> physical page
# =========================================================================== #
class TestResolvePages(unittest.TestCase):
    def test_two_numbering_series_resolve_independently(self):
        """The case a single global offset cannot express, and the reason this
        module exists: roman front matter and arabic body have different deltas."""
        entries = [{"title": "Preface", "printedPage": 5, "roman": True},
                   {"title": "Chapter 1", "printedPage": 1, "roman": False},
                   {"title": "Chapter 2", "printedPage": 8, "roman": False}]
        folios = {("r", 5): 5, ("d", 1): 6, ("d", 8): 13}
        got = pagemap.resolve_pages(entries, folio_map=folios, page_count=20)
        self.assertEqual([e["physicalPage"] for e in got], [5, 6, 13])
        self.assertEqual({e["confidence"] for e in got}, {"folio"})

    def test_page_labels_win_over_folios(self):
        entries = [{"title": "Ch 1", "printedPage": 3, "roman": False}]
        got = pagemap.resolve_pages(entries, label_map={"3": 40},
                                    folio_map={("d", 3): 99}, page_count=100)
        self.assertEqual(got[0]["physicalPage"], 40)
        self.assertEqual(got[0]["confidence"], "labels")

    def test_roman_entry_looks_itself_up_as_a_roman_label(self):
        entries = [{"title": "Preface", "printedPage": 4, "roman": True}]
        got = pagemap.resolve_pages(entries, label_map={"iv": 7}, page_count=50)
        self.assertEqual(got[0]["physicalPage"], 7)

    def test_explicit_offset_fills_the_gaps(self):
        entries = [{"title": "A", "printedPage": 10, "roman": False}]
        got = pagemap.resolve_pages(entries, offset=12, page_count=100)
        self.assertEqual(got[0]["physicalPage"], 22)
        self.assertEqual(got[0]["confidence"], "offset")

    def test_unmapped_entries_borrow_the_voted_delta(self):
        entries = [{"title": "A", "printedPage": 1, "roman": False},
                   {"title": "B", "printedPage": 2, "roman": False},
                   {"title": "C", "printedPage": 50, "roman": False}]  # no evidence
        got = pagemap.resolve_pages(entries, folio_map={("d", 1): 11, ("d", 2): 12},
                                    page_count=200)
        self.assertEqual(got[2]["physicalPage"], 60)
        self.assertEqual(got[2]["confidence"], "voted")

    def test_clamps_inside_the_document(self):
        entries = [{"title": "A", "printedPage": 9000, "roman": False}]
        got = pagemap.resolve_pages(entries, offset=0, page_count=10)
        self.assertEqual(got[0]["physicalPage"], 10)

    def test_leaves_the_input_untouched(self):
        entries = [{"title": "A", "printedPage": 3, "roman": False}]
        pagemap.resolve_pages(entries, offset=1, page_count=10)
        self.assertNotIn("physicalPage", entries[0])


class TestVoteOffset(unittest.TestCase):
    def test_takes_the_majority_delta(self):
        self.assertEqual(pagemap.vote_offset([(1, 11), (2, 12), (3, 99)]), 10)

    def test_none_without_samples(self):
        self.assertIsNone(pagemap.vote_offset([]))


# =========================================================================== #
# pure: validation
# =========================================================================== #
class TestNormalize(unittest.TestCase):
    def test_lowers_a_level_that_jumps(self):
        entries, warnings = outline.normalize([{"level": 1, "title": "A", "page": 1},
                                               {"level": 3, "title": "B", "page": 2}])
        self.assertEqual([e["level"] for e in entries], [1, 2])
        self.assertTrue(any("level" in w for w in warnings))

    def test_first_entry_is_forced_to_level_one(self):
        entries, _ = outline.normalize([{"level": 4, "title": "A", "page": 1}])
        self.assertEqual(entries[0]["level"], 1)

    def test_clamps_pages_into_the_document(self):
        entries, warnings = outline.normalize([{"level": 1, "title": "A", "page": 900}],
                                              page_count=10)
        self.assertEqual(entries[0]["page"], 10)
        self.assertTrue(any("past the end" in w for w in warnings))

    def test_clamps_pages_below_one(self):
        entries, _ = outline.normalize([{"level": 1, "title": "A", "page": 0}])
        self.assertEqual(entries[0]["page"], 1)

    def test_drops_empty_titles_and_bad_pages(self):
        entries, warnings = outline.normalize([{"level": 1, "title": "  ", "page": 1},
                                               {"level": 1, "title": "B", "page": "x"},
                                               {"level": 1, "title": "C", "page": 3}])
        self.assertEqual([e["title"] for e in entries], ["C"])
        self.assertEqual(len(warnings), 2)

    def test_drops_a_consecutive_duplicate(self):
        entries, _ = outline.normalize([{"level": 1, "title": "A", "page": 1},
                                        {"level": 1, "title": "A", "page": 1}])
        self.assertEqual(len(entries), 1)

    def test_warns_but_keeps_backwards_pages(self):
        """A collection where each chapter prints its own contents legitimately
        produces out-of-order pages. Say so; do not silently reorder someone's
        hierarchy."""
        entries, warnings = outline.normalize([{"level": 1, "title": "A", "page": 40},
                                               {"level": 1, "title": "B", "page": 5}])
        self.assertEqual(len(entries), 2)
        self.assertTrue(any("backwards" in w for w in warnings))

    def test_max_level_truncates_depth(self):
        entries, _ = outline.normalize([{"level": 1, "title": "A", "page": 1},
                                        {"level": 2, "title": "B", "page": 2},
                                        {"level": 3, "title": "C", "page": 3}],
                                       max_level=2)
        self.assertEqual([e["level"] for e in entries], [1, 2, 2])


# =========================================================================== #
# pure: the exchange format
# =========================================================================== #
class TestExchangeFormat(unittest.TestCase):
    ENTRIES = [{"level": 1, "title": "Capítulo 1. Introducción", "page": 15},
               {"level": 2, "title": "1.1 Antecedentes", "page": 17},
               {"level": 1, "title": "Capítulo 2. Método", "page": 48}]

    def test_round_trips_exactly(self):
        text = outline.render_toc_text(self.ENTRIES)
        self.assertEqual(outline.parse_toc_text(text), self.ENTRIES)

    def test_renders_indentation_and_tabs(self):
        text = outline.render_toc_text(self.ENTRIES)
        self.assertEqual(text.splitlines()[1], "  1.1 Antecedentes\t17")

    def test_accepts_tab_indentation(self):
        entries = outline.parse_toc_text("A\t1\n\tB\t2\n")
        self.assertEqual([e["level"] for e in entries], [1, 2])

    def test_accepts_spaces_instead_of_a_tab_separator(self):
        entries = outline.parse_toc_text("Bibliography   201\n")
        self.assertEqual(entries[0], {"level": 1, "title": "Bibliography", "page": 201})

    def test_skips_blanks_and_comments(self):
        self.assertEqual(outline.parse_toc_text("# note\n\nA\t1\n"),
                         [{"level": 1, "title": "A", "page": 1}])

    def test_rejects_a_row_with_no_page(self):
        with self.assertRaises(ValueError):
            outline.parse_toc_text("Chapter 1\n")

    def test_load_entries_sniffs_json(self):
        entries = outline.load_entries('[{"level":1,"title":"A","page":3}]')
        self.assertEqual(entries, [{"level": 1, "title": "A", "page": 3}])

    def test_load_entries_reads_a_scan_report_shape(self):
        """`zot toc scan --json` emits physicalPage; feeding that straight back
        must work, or the documented agent loop has a manual step in it."""
        raw = '{"entries":[{"level":2,"title":"A","physicalPage":9}]}'
        self.assertEqual(outline.load_entries(raw),
                         [{"level": 2, "title": "A", "page": 9}])

    def test_load_entries_sniffs_text(self):
        self.assertEqual(outline.load_entries("A\t1\n"),
                         [{"level": 1, "title": "A", "page": 1}])

    def test_load_entries_on_empty_input(self):
        self.assertEqual(outline.load_entries("   "), [])


# =========================================================================== #
# pure: the typography fallback, for documents with no contents page
# =========================================================================== #
def _line(text, size=12.0, bold=False, y=200.0, x0=72.0, x1=300.0, page=1,
          lines_in_block=1, font="Serif"):
    return {"page": page, "text": text, "size": size, "font": font, "bold": bold,
            "italic": False, "x0": x0, "x1": x1, "y": y, "y1": y + size * 1.2,
            "pageWidth": 420.0, "pageHeight": 640.0, "linesInBlock": lines_in_block}


class TestHeadingScoring(unittest.TestCase):
    """These are the gates, and each one exists because a real book tripped it."""

    def test_a_heading_scores(self):
        from zotero_agent.pdf import scan as pdf_scan
        self.assertGreaterEqual(
            pdf_scan.score_line(_line("2. Determinismo digital", size=14, bold=True), 10.5),
            5)

    def test_a_footnote_is_rejected_for_being_smaller_than_the_body(self):
        """Footnotes are numbered, short and start their block, so they score
        like sections. Size is what separates them."""
        from zotero_agent.pdf import scan as pdf_scan
        footnote = _line("1. Este aforismo puede traducirse así", size=8.4)
        self.assertEqual(pdf_scan.score_line(footnote, 10.5), 0)

    def test_a_full_measure_line_is_rejected_as_running_text(self):
        """A book with no bold that sets block quotes above body size makes every
        quoted line look like a heading; the giveaway is that it fills the column."""
        from zotero_agent.pdf import scan as pdf_scan
        quote = _line("El conocimiento crítico de la sociedad", size=11.0, x0=72, x1=350)
        self.assertEqual(pdf_scan.score_line(quote, 9.5, measure=300.0), 0)
        # The same line, set short, is still a plausible heading.
        short = _line("El conocimiento crítico", size=11.0, x0=72, x1=180)
        self.assertGreater(pdf_scan.score_line(short, 9.5, measure=300.0), 0)

    def test_a_sentence_is_rejected(self):
        from zotero_agent.pdf import scan as pdf_scan
        prose = _line("Una idea. y luego otra idea distinta", size=14)
        self.assertEqual(pdf_scan.score_line(prose, 10.5), 0)

    def test_a_title_containing_a_period_is_kept(self):
        """The prose test only fires on a lower-case continuation, deliberately:
        "Palabras previas. Por Tinta Limón" is a real heading."""
        from zotero_agent.pdf import scan as pdf_scan
        heading = _line("Palabras previas. Por Tinta Limón", size=14, bold=True)
        self.assertGreater(pdf_scan.score_line(heading, 10.5), 0)

    def test_running_heads_and_captions_are_rejected(self):
        from zotero_agent.pdf import scan as pdf_scan
        self.assertEqual(pdf_scan.score_line(_line("Título corriente", y=10.0), 10.5), 0)
        self.assertEqual(pdf_scan.score_line(_line("Tabla 3. Resultados", size=14), 10.5), 0)


class TestTypographyGrouping(unittest.TestCase):
    def test_a_heading_split_over_two_lines_becomes_one(self):
        from zotero_agent.pdf import scan as pdf_scan
        lines = [_line("Sociología de", size=24, bold=True, y=200),
                 _line("la imagen", size=24, bold=True, y=229),
                 _line("Otra cosa", size=24, bold=True, y=400)]
        candidates, _ = pdf_scan.heading_candidates(lines, 10.5)
        self.assertEqual([c["text"] for c in candidates],
                         ["Sociología de la imagen", "Otra cosa"])

    def test_text_repeated_across_pages_is_dropped(self):
        from zotero_agent.pdf import scan as pdf_scan
        lines = [_line("Capítulo corriente", size=14, page=p, y=200) for p in (1, 2, 3, 4)]
        lines.append(_line("Un título real", size=14, page=5, y=200))
        candidates, _ = pdf_scan.heading_candidates(lines, 10.5)
        self.assertEqual([c["text"] for c in candidates], ["Un título real"])

    def test_truncation_is_reported_not_silent(self):
        from zotero_agent.pdf import scan as pdf_scan
        lines = [_line("Título %d" % n, size=14, page=n, y=200) for n in range(1, 30)]
        candidates, truncated = pdf_scan.heading_candidates(lines, 10.5, cap=10)
        self.assertTrue(truncated)
        self.assertEqual(len(candidates), 10)
        self.assertEqual([c["page"] for c in candidates],
                         sorted(c["page"] for c in candidates))  # reading order kept


class TestTypographyLevels(unittest.TestCase):
    def test_numbering_states_its_own_depth(self):
        from zotero_agent.pdf import scan as pdf_scan
        self.assertEqual(pdf_scan.numbering_depth("3. Título"), 1)
        self.assertEqual(pdf_scan.numbering_depth("3.1. Título"), 2)
        self.assertEqual(pdf_scan.numbering_depth("3.1.2. Título"), 3)
        self.assertEqual(pdf_scan.numbering_depth("Sin número"), 0)

    def test_numbered_headings_nest_by_their_number(self):
        from zotero_agent.pdf import scan as pdf_scan
        candidates = [{"text": "1. Uno", "page": 1, "size": 14.0},
                      {"text": "1.1. Uno uno", "page": 2, "size": 12.0},
                      {"text": "1.1.1. Hondo", "page": 3, "size": 12.0},
                      {"text": "2. Dos", "page": 4, "size": 14.0}]
        self.assertEqual([e["level"] for e in pdf_scan.levels_from_typography(candidates)],
                         [1, 2, 3, 1])

    def test_a_cover_size_used_twice_does_not_claim_level_one(self):
        """A 24pt title page in a 300-page book is not an outline level; letting
        it rank first pushes every real chapter down to level 3."""
        from zotero_agent.pdf import scan as pdf_scan
        candidates = [{"text": "Portada", "page": 1, "size": 24.0},
                      {"text": "Portada", "page": 2, "size": 24.0}]
        candidates += [{"text": "Capítulo %d" % n, "page": 10 + n, "size": 12.0}
                       for n in range(1, 5)]
        levels = [e["level"] for e in pdf_scan.levels_from_typography(candidates)]
        self.assertEqual(levels, [1, 1, 1, 1, 1, 1])


# =========================================================================== #
# the CLI surface
# =========================================================================== #
class TestTocParser(unittest.TestCase):
    def test_registered_with_every_action(self):
        parser = cli.build_parser()
        args = parser.parse_args(["toc", "scan", "ABCD1234"])
        self.assertIs(args.func, toc_cmd.cmd_toc)
        self.assertEqual(args.action, "scan")
        for action in ("show", "scan", "set", "auto", "clear"):
            parser.parse_args(["toc", action, "ABCD1234"])

    def test_from_lands_in_from_underscore(self):
        args = cli.build_parser().parse_args(["toc", "set", "K", "--from", "f.txt"])
        self.assertEqual(args.from_, "f.txt")


class TestMissingEngineIsExplained(unittest.TestCase):
    def test_names_the_extra_and_the_command(self):
        args = cli.build_parser().parse_args(["toc", "show", "ABCD1234"])
        with mock.patch("zotero_agent.pdf.load_pymupdf", return_value=None):
            with self.assertRaises(ZotError) as caught:
                toc_cmd.cmd_toc(args)
        self.assertIn("toc", str(caught.exception))
        self.assertIn("pymupdf", str(caught.exception).lower())


# =========================================================================== #
# engine-dependent
# =========================================================================== #
_PROSE = ("Este es un párrafo de relleno con suficiente texto para que la página "
          "tenga una capa de texto de densidad realista y no se confunda con un "
          "escaneo sin OCR. ") * 6


def _build_book(path):
    """A small book: roman front matter, a printed contents page, arabic body.

    Written with real folios in the footer so the printed-number route has to do
    the same work it does on a real scan, and with wrapped body prose so the
    text-layer check sees a realistic character count (insert_text draws a single
    unwrapped line, which reads as a nearly-empty page).
    """
    width, height = 420, 640
    doc = pymupdf.open()

    def folio(page, label):
        page.insert_text((width / 2 - 10, height - 40), label, fontsize=9)

    def prose(page, top=160):
        page.insert_textbox(pymupdf.Rect(72, top, width - 72, height - 60),
                            _PROSE, fontsize=10)

    for label in ("i", "ii"):
        page = doc.new_page(width=width, height=height)
        page.insert_text((72, 120), "Portada", fontsize=20)
        prose(page)
        folio(page, label)

    page = doc.new_page(width=width, height=height)          # contents, folio iii
    page.insert_text((72, 90), "Índice", fontsize=18)
    rows = [(72, "Prefacio . . . . . . . . . . . . . . . v"),
            (72, "Capítulo 1. Introducción . . . . . . . 1"),
            (90, "1.1 Antecedentes . . . . . . . . . . . 3"),
            (72, "Capítulo 2. Método . . . . . . . . . . 6")]
    y = 130
    for x, text in rows:
        page.insert_text((x, y), text, fontsize=10)
        y += 22
    folio(page, "iii")

    page = doc.new_page(width=width, height=height)
    page.insert_text((72, 120), "Agradecimientos", fontsize=14)
    prose(page)
    folio(page, "iv")

    page = doc.new_page(width=width, height=height)
    page.insert_text((72, 120), "Prefacio", fontsize=16)
    prose(page)
    folio(page, "v")

    body = {1: "Capítulo 1. Introducción", 3: "1.1 Antecedentes", 6: "Capítulo 2. Método"}
    for n in range(1, 9):
        page = doc.new_page(width=width, height=height)
        if n in body:
            page.insert_text((72, 110), body[n], fontsize=16)
        prose(page)
        folio(page, str(n))

    doc.save(path)
    doc.close()


@needs_engine
class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.book = os.path.join(cls.dir.name, "book.pdf")
        _build_book(cls.book)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def _copy(self, name):
        import shutil
        target = os.path.join(self.dir.name, name)
        shutil.copy2(self.book, target)
        return target

    def test_scan_finds_the_printed_contents(self):
        from zotero_agent.pdf import scan as pdf_scan
        doc = pdf_scan.open_pdf(self.book)
        try:
            report = pdf_scan.scan(doc)
        finally:
            doc.close()
        self.assertTrue(report["textLayer"])
        self.assertEqual(report["suggestion"], "contents-printed-numbers")
        self.assertEqual(report["contentsToc"]["pages"], [3])
        titles = [e["title"] for e in report["contentsToc"]["entries"]]
        self.assertIn("Capítulo 1. Introducción", titles)

    def test_both_numbering_series_map_correctly(self):
        """Printed v (roman) and printed 1 (arabic) sit five pages apart in the
        file; one global offset would put one of them in the wrong place."""
        from zotero_agent.pdf import scan as pdf_scan
        doc = pdf_scan.open_pdf(self.book)
        try:
            report = pdf_scan.scan(doc)
        finally:
            doc.close()
        placed = {e["title"]: e["physicalPage"] for e in report["contentsToc"]["entries"]}
        self.assertEqual(placed["Prefacio"], 5)
        self.assertEqual(placed["Capítulo 1. Introducción"], 6)
        self.assertEqual(placed["Capítulo 2. Método"], 11)

    def test_write_then_read_round_trips(self):
        from zotero_agent.pdf import scan as pdf_scan
        target = self._copy("written.pdf")
        doc = pdf_scan.open_pdf(target)
        entries, warnings = outline.normalize(
            pdf_scan.auto_entries(pdf_scan.scan(doc)), page_count=doc.page_count)
        self.assertEqual(warnings, [])
        mode = outline.write_outline(doc, entries, target)
        if not doc.is_closed:
            doc.close()
        self.assertEqual(mode, "incremental")

        doc = pdf_scan.open_pdf(target)
        try:
            self.assertEqual(outline.read_outline(doc), entries)
        finally:
            doc.close()

    def test_an_incremental_save_only_appends(self):
        """The point of incremental: existing bytes are untouched, so scanned
        page images are never recompressed."""
        from zotero_agent.pdf import scan as pdf_scan
        target = self._copy("appended.pdf")
        with open(target, "rb") as fh:
            before = fh.read()
        doc = pdf_scan.open_pdf(target)
        outline.write_outline(doc, [{"level": 1, "title": "A", "page": 1}], target)
        if not doc.is_closed:
            doc.close()
        with open(target, "rb") as fh:
            after = fh.read()
        self.assertGreater(len(after), len(before))
        self.assertEqual(after[: len(before)], before)

    def test_clear_removes_the_outline(self):
        from zotero_agent.pdf import scan as pdf_scan
        target = self._copy("cleared.pdf")
        doc = pdf_scan.open_pdf(target)
        outline.write_outline(doc, [{"level": 1, "title": "A", "page": 1}], target)
        if not doc.is_closed:
            doc.close()
        doc = pdf_scan.open_pdf(target)
        outline.clear_outline(doc, target)
        if not doc.is_closed:
            doc.close()
        doc = pdf_scan.open_pdf(target)
        try:
            self.assertEqual(outline.read_outline(doc), [])
        finally:
            doc.close()

    def test_wrapped_titles_are_joined_and_dehyphenated(self):
        from zotero_agent.pdf import scan as pdf_scan
        path = os.path.join(self.dir.name, "wrapped.pdf")
        doc = pymupdf.open()
        page = doc.new_page(width=420, height=640)
        page.insert_text((72, 90), "Contenido", fontsize=18)
        page.insert_text((72, 130), "La Ley de Participación Popular: descentraliza-", fontsize=10)
        page.insert_text((72, 144), "ción desde lo local . . . . . . . 4", fontsize=10)
        page.insert_text((72, 176), "Bibliografía . . . . . . . . . . . 6", fontsize=10)
        page.insert_text((72, 198), "Anexos . . . . . . . . . . . . . . 7", fontsize=10)
        page.insert_text((72, 220), "Índice analítico . . . . . . . . . 8", fontsize=10)
        for _ in range(9):
            filler = doc.new_page(width=420, height=640)
            filler.insert_textbox(pymupdf.Rect(72, 100, 348, 580), _PROSE, fontsize=10)
        doc.save(path)
        doc.close()

        doc = pdf_scan.open_pdf(path)
        try:
            rows = pdf_scan.parse_printed_contents(doc, [1])
        finally:
            doc.close()
        titles = [r["title"] for r in rows]
        self.assertIn("La Ley de Participación Popular: descentralización desde lo local",
                      titles)

    def _columnar_pdf(self, name, heading="Índice"):
        """A contents page that sets page numbers in a right-hand column, the
        way many publishers do. PyMuPDF emits the title and the number as two
        separate lines, so nothing matches "title .... 15"."""
        path = os.path.join(self.dir.name, name)
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=640)
        page.insert_text((230, 90), heading, fontsize=18)
        rows = [(85, "Agradecimientos", "3"),
                (85, "1. Primer capítulo", "5"),
                (99, "1.1. Una subsección", "6"),
                (99, "1.2. Otra subsección", "7"),
                (85, "2. Segundo capítulo", "9")]
        y = 180
        for x, title, number in rows:
            page.insert_text((x, y), title, fontsize=10)
            page.insert_text((412, y), number, fontsize=10)   # right-hand column
            y += 14
        for _ in range(10):
            doc.new_page(width=500, height=640).insert_textbox(
                pymupdf.Rect(72, 100, 428, 580), _PROSE, fontsize=10)
        doc.save(path)
        doc.close()
        return path

    def test_a_two_column_contents_page_is_found_and_parsed(self):
        from zotero_agent.pdf import scan as pdf_scan
        path = self._columnar_pdf("columnar.pdf")
        doc = pdf_scan.open_pdf(path)
        try:
            self.assertIn(1, pdf_scan.find_contents_pages(doc))
            rows = pdf_scan.parse_printed_contents(doc, [1])
        finally:
            doc.close()
        self.assertEqual([r["title"] for r in rows],
                         ["Agradecimientos", "1. Primer capítulo",
                          "1.1. Una subsección", "1.2. Otra subsección",
                          "2. Segundo capítulo"])
        self.assertEqual([r["printedPage"] for r in rows], [3, 5, 6, 7, 9])
        self.assertEqual([r["level"] for r in rows], [1, 1, 2, 2, 1])

    def test_a_list_of_figures_is_not_mistaken_for_the_contents(self):
        """Its running head says "Índice" too; the rows are what give it away."""
        from zotero_agent.pdf import scan as pdf_scan
        path = os.path.join(self.dir.name, "figures.pdf")
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=640)
        page.insert_text((230, 60), "Índice", fontsize=9)     # running head
        y = 120
        for n in range(1, 7):
            page.insert_text((85, y), "Mapa %d" % n, fontsize=10)
            page.insert_text((85, y + 12), "Un mapa de algo . . . . . . . %d" % (n * 10),
                             fontsize=10)
            y += 30
        for _ in range(10):
            doc.new_page(width=500, height=640).insert_textbox(
                pymupdf.Rect(72, 100, 428, 580), _PROSE, fontsize=10)
        doc.save(path)
        doc.close()

        doc = pdf_scan.open_pdf(path)
        try:
            self.assertNotIn(1, pdf_scan.find_contents_pages(doc))
        finally:
            doc.close()


@needs_engine
class TestTocCommand(unittest.TestCase):
    """The command path, with Zotero replaced by a stub — `zot toc` only ever
    asks Zotero for a file path, so that one call is the whole seam."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.pdf = os.path.join(self.dir.name, "item.pdf")
        _build_book(self.pdf)
        self.undo = tempfile.TemporaryDirectory()
        self.addCleanup(self.undo.cleanup)
        self.state = tempfile.TemporaryDirectory()
        self.addCleanup(self.state.cleanup)
        patches = [
            # Patched at its source rather than on `toc`, which now reaches the
            # PDF through the shared `resolve_pdf_attachment`. That resolver then
            # runs for real over this fixture — the "which of several PDFs" and
            # "file missing from disk" checks included.
            mock.patch("zotero_agent.commands.read.pdf_paths", return_value={
                "itemKey": "ABCD1234", "title": "A book", "language": "en",
                "pdfs": [{"attachmentKey": "ATT11111", "path": self.pdf, "title": "PDF"}]}),
            mock.patch("zotero_agent.config.require_config",
                       return_value={"base": "http://x", "token": "t", "userID": "1"}),
            mock.patch.object(features, "UNDO_DIR", self.undo.name),
            mock.patch.object(toc_cmd, "STATE_DIR", self.state.name),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _run(self, *argv):
        args = cli.build_parser().parse_args(list(argv))
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            toc_cmd.cmd_toc(args)
        return buffer.getvalue()

    def test_show_reports_no_outline_yet(self):
        self.assertEqual(self._run("toc", "show", "ABCD1234"), "")

    def test_dry_run_leaves_the_file_alone(self):
        before = os.stat(self.pdf)
        with open(self.pdf, "rb") as fh:
            payload = fh.read()
        out = self._run("toc", "auto", "ABCD1234", "--dry-run")
        self.assertIn("DRY-RUN", out)
        self.assertIn("Capítulo 1. Introducción", out)
        after = os.stat(self.pdf)
        self.assertEqual((before.st_size, before.st_mtime), (after.st_size, after.st_mtime))
        with open(self.pdf, "rb") as fh:
            self.assertEqual(fh.read(), payload)

    def test_auto_writes_and_show_reads_it_back(self):
        self._run("toc", "auto", "ABCD1234", "--yes")
        shown = self._run("toc", "show", "ABCD1234")
        self.assertIn("Capítulo 1. Introducción\t6", shown)
        self.assertIn("  1.1 Antecedentes\t8", shown)

    def test_set_from_a_file_then_undo_restores_the_previous_tree(self):
        self._run("toc", "auto", "ABCD1234", "--yes")
        first = self._run("toc", "show", "ABCD1234")

        source = os.path.join(self.dir.name, "toc.txt")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("Solo capítulo\t2\n")
        self._run("toc", "set", "ABCD1234", "--from", source, "--yes")
        self.assertEqual(self._run("toc", "show", "ABCD1234"), "Solo capítulo\t2\n")

        undo_args = cli.build_parser().parse_args(["undo", "last", "--yes"])
        with redirect_stdout(io.StringIO()):
            features.cmd_undo(undo_args)
        self.assertEqual(self._run("toc", "show", "ABCD1234"), first)

    def test_set_rejects_a_malformed_file(self):
        source = os.path.join(self.dir.name, "bad.txt")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("Chapter with no page\n")
        with self.assertRaises(ZotError):
            self._run("toc", "set", "ABCD1234", "--from", source, "--yes")

    def test_set_without_from_explains_the_format(self):
        with self.assertRaises(ZotError) as caught:
            self._run("toc", "set", "ABCD1234", "--yes")
        self.assertIn("--from", str(caught.exception))

    def test_a_write_refuses_without_yes_when_not_a_tty(self):
        with self.assertRaises(ZotError) as caught:
            self._run("toc", "auto", "ABCD1234")
        self.assertIn("--yes", str(caught.exception))

    def test_backup_keeps_the_original_bytes_outside_zotero_storage(self):
        """The copy must not land next to the original: storage/<KEY>/ belongs to
        Zotero, and a stray second file there invites trouble on sync."""
        with open(self.pdf, "rb") as fh:
            payload = fh.read()
        self._run("toc", "auto", "ABCD1234", "--yes", "--backup")
        self.assertEqual(os.listdir(os.path.dirname(self.pdf)), ["item.pdf"])

        folder = os.path.join(self.state.name, "pdf-backups")
        copies = os.listdir(folder)
        self.assertEqual(len(copies), 1)
        with open(os.path.join(folder, copies[0]), "rb") as fh:
            self.assertEqual(fh.read(), payload)

    def test_clear_empties_the_outline(self):
        self._run("toc", "auto", "ABCD1234", "--yes")
        self._run("toc", "clear", "ABCD1234", "--yes")
        self.assertEqual(self._run("toc", "show", "ABCD1234"), "")

    def test_a_missing_file_on_disk_is_reported(self):
        os.unlink(self.pdf)
        with self.assertRaises(ZotError) as caught:
            self._run("toc", "show", "ABCD1234")
        self.assertIn("missing from disk", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
