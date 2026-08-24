"""The verification thresholds, tested against the records that fooled us.

Every rejection case here is a real Crossref answer from a live library run: the
top hit for a title search that was a different work entirely. They are the
regression suite for `enrich` writing wrong DOIs.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zotero_agent import match  # noqa: E402


class NormalisationTests(unittest.TestCase):
    def test_accents_and_case_do_not_change_a_title(self):
        self.assertEqual(match.norm_title("Digitalización Societal"),
                         match.norm_title("digitalizacion societal"))

    def test_punctuation_is_flattened(self):
        self.assertEqual(match.norm_title("Peer-to-Peer: The Commons Manifesto!"),
                         "peer to peer the commons manifesto")

    def test_year_is_pulled_out_of_free_text_dates(self):
        self.assertEqual(match.year_of("2021-03-14"), 2021)
        self.assertEqual(match.year_of("28 September 2010"), 2010)
        self.assertIsNone(match.year_of(""))
        self.assertIsNone(match.year_of("n.d."))


class AbstractCleaningTests(unittest.TestCase):
    def test_jats_markup_is_stripped(self):
        raw = "<jats:p>Not since <jats:italic>Marx</jats:italic> identified it.</jats:p>"
        self.assertEqual(match.clean_abstract(raw), "Not since Marx identified it.")

    def test_leading_abstract_label_is_dropped(self):
        self.assertEqual(match.clean_abstract("<jats:p>Abstract: the thing.</jats:p>"),
                         "the thing.")
        self.assertEqual(match.clean_abstract("Resumen — el asunto."), "el asunto.")

    def test_entities_are_unescaped(self):
        self.assertEqual(match.clean_abstract("caf&#233; &amp; leche"), "café & leche")


class VerifyRejectsTheWrongWork(unittest.TestCase):
    """Six live Crossref top hits, none of them the item that was searched for."""

    CASES = [
        ("Mujeres libres en política – Guía para combatir el acoso", "2019", "",
         "Guía mínima para la observancia de la política en materia de igualdad"),
        ("Internet: de las metáforas y las caracterizaciones disciplinares", "2008", "",
         "Y al principio... habló Black"),
        ("Cámaras de eco y desinformación", "2022", "",
         "La gestión de los medios tradicionales en las redes sociales digitales"),
        ("El fin del trámite eterno", "2018", "",
         "Mayor eficacia del gobierno municipal: El Estado más cercano a los ciudadanos"),
        ("La nueva ciudadanía (en red) en Bolivia", "2015", "",
         "Bolivia la nueva: La construcción de una nueva ciudadanía"),
        ("Activismo en las redes sociales online", "2013", "",
         "La invención del ciberespacio"),
    ]

    def test_every_known_false_positive_is_rejected(self):
        for item_title, year, surname, candidate_title in self.CASES:
            with self.subTest(title=item_title):
                ok, _, reason = match.verify(item_title, year, surname,
                                             {"title": candidate_title, "year": None, "authors": []})
                self.assertFalse(ok, "should have rejected %r" % candidate_title)
                self.assertEqual(reason, "title")

    def test_a_different_edition_is_rejected_when_nothing_corroborates(self):
        # 0.944 similarity: passes the normal floor, must fail the uncorroborated one.
        ok, sim, reason = match.verify("The OECD Going Digital Measurement Roadmap", "", "",
                                       {"title": "The OECD Going Digital Measurement Roadmap 2026",
                                        "year": 2026, "authors": []})
        self.assertFalse(ok)
        self.assertEqual(reason, "title")
        self.assertGreater(sim, match.MIN_TITLE_SIMILARITY)

    def test_the_same_edition_check_passes_once_a_year_corroborates(self):
        ok, _, _ = match.verify("The OECD Going Digital Measurement Roadmap", "2019", "",
                                {"title": "The OECD Going Digital Measurement Roadmap",
                                 "year": 2019, "authors": []})
        self.assertTrue(ok)

    def test_wrong_year_is_rejected(self):
        ok, _, reason = match.verify("Network Science", "2016", "Barabási",
                                     {"title": "Network Science", "year": 1998,
                                      "authors": ["Barabási"]})
        self.assertFalse(ok)
        self.assertEqual(reason, "year")

    def test_wrong_author_is_rejected(self):
        ok, _, reason = match.verify("Introduction to Mathematical Sociology", "2012", "Bonacich",
                                     {"title": "Introduction to Mathematical Sociology",
                                      "year": 2012, "authors": ["Coleman"]})
        self.assertFalse(ok)
        self.assertEqual(reason, "author")


class VerifyAcceptsTheRightWork(unittest.TestCase):
    def test_case_only_difference_is_accepted(self):
        ok, _, _ = match.verify("Global sentiments surrounding the COVID-19 pandemic on Twitter",
                                "2020", "Dubey",
                                {"title": "Global Sentiments Surrounding the COVID-19 Pandemic on Twitter",
                                 "year": 2020, "authors": ["Dubey"]})
        self.assertTrue(ok)

    def test_leading_chapter_number_is_accepted(self):
        ok, _, _ = match.verify("Civil society in the digital age", "2011", "Lentz",
                                {"title": "27. Civil Society in the Digital Age",
                                 "year": 2011, "authors": ["Lentz"]})
        self.assertTrue(ok)

    def test_a_year_of_drift_is_tolerated(self):
        ok, _, _ = match.verify("A history of communications", "2010", "Poe",
                                {"title": "A history of communications", "year": 2011,
                                 "authors": ["Poe"]})
        self.assertTrue(ok)

    def test_compound_surname_matches_either_half(self):
        self.assertTrue(match.surname_present("García Zaballos",
                                              ["Antonio García Zaballos", "Marín"]))
        self.assertTrue(match.surname_present("Zaballos", ["Garcia Zaballos, A."]))

    def test_missing_surname_is_not_a_rejection(self):
        self.assertTrue(match.surname_present("", ["Anybody"]))


class VagueTitles(unittest.TestCase):
    """A title has to identify a work before similarity means anything.

    Measured on a library whose items were created from PDF filenames: every one
    of these matched a real Crossref record at similarity 1.000 — a perfect
    match against a completely different work. Similarity cannot catch this;
    only refusing to trust the title can.
    """

    PERFECT_BUT_MEANINGLESS = [
        ("deposito", "Deposito"),
        ("vermis", "Vermis"),
        ("Esbozo", "Esbozo"),
        ("Algorithms", "Algorithms"),
        ("El Giro Afectivo", "El giro afectivo"),
        ("Bruno Latour", "Bruno Latour"),
    ]

    def test_a_vague_title_is_rejected_even_at_perfect_similarity(self):
        for item_title, candidate_title in self.PERFECT_BUT_MEANINGLESS:
            with self.subTest(title=item_title):
                ok, sim, reason = match.verify(
                    item_title, "", "",
                    {"title": candidate_title, "year": None, "authors": []})
                self.assertFalse(ok, "should have rejected %r" % candidate_title)
                self.assertEqual(reason, "vague-title")
                self.assertGreaterEqual(sim, 0.95,
                                        "the point is that similarity was fine")

    def test_a_specific_title_still_passes_uncorroborated(self):
        for title in ["Ética de la inteligencia artificial",
                      "Making sense of world history",
                      "Enfoques y Metodologias en Las Ciencias Sociales"]:
            with self.subTest(title=title):
                ok, _, reason = match.verify(
                    title, "", "", {"title": title, "year": None, "authors": []})
                self.assertTrue(ok, "should have accepted %r (reason: %s)" % (title, reason))

    def test_a_vague_title_is_allowed_once_an_author_corroborates(self):
        # "Algorithms" alone identifies nothing, but with an author it is a
        # normal lookup again — the guard only covers the uncorroborated case.
        ok, _, _ = match.verify("Algorithms", "2011", "Dasgupta",
                                {"title": "Algorithms", "year": 2011,
                                 "authors": ["Sanjoy Dasgupta"]})
        self.assertTrue(ok)

    def test_significant_words_drops_fillers_in_both_languages(self):
        self.assertEqual(match.significant_words("El giro de la ciencia"),
                         ["giro", "ciencia"])
        self.assertEqual(match.significant_words("The Art of the Deal"),
                         ["art", "deal"])


class AuthorMustBeIndependentEvidence(unittest.TestCase):
    """A surname does not corroborate a title that IS that surname.

    It happens with records created from filenames: "Marias (1980). Historia de
    la filosofia" was parsed into the title "Marias" and the author "Marias".
    Counted as two signals, it accepted a namesake's doctoral thesis.
    """

    def test_title_equal_to_surname_does_not_corroborate(self):
        self.assertFalse(match.author_corroborates("Marias", "Marias"))
        self.assertFalse(match.author_corroborates("Valles", "Valles"))

    def test_a_real_title_does_corroborate(self):
        self.assertTrue(match.author_corroborates(
            "Historia de la filosofía occidental", "Marias"))

    def test_the_lookup_now_rejects_the_homonym(self):
        ok, sim, reason = match.verify(
            "Marias", "", "Marias",
            {"title": "Marias", "year": None, "authors": ["J. Marias"]})
        self.assertFalse(ok)
        self.assertEqual(reason, "vague-title")
        self.assertEqual(
            sim, 1.0, "similarity was perfect: that is why another signal was needed")

    def test_a_year_the_candidate_lacks_does_not_corroborate(self):
        # The item has a year, the candidate does not: nothing to compare, so
        # the vague title stays uncorroborated. Real case: "Marias" (1980) was
        # accepting an undated Unicamp thesis.
        ok, sim, reason = match.verify(
            "Marias", "1980", "",
            {"title": "Marias", "year": None, "authors": []})
        self.assertFalse(ok)
        self.assertEqual(reason, "vague-title")
        self.assertEqual(sim, 1.0)

    def test_a_year_both_sides_have_does_corroborate(self):
        ok, _, reason = match.verify(
            "Algorithms", "2011", "",
            {"title": "Algorithms", "year": 2011, "authors": []})
        self.assertTrue(ok, "reason: %s" % reason)


class IsbnNotation(unittest.TestCase):
    def test_an_isbn_10_and_its_isbn_13_are_one_book(self):
        self.assertEqual(
            match.identifiers_verdict(["0-9660176-4-9", "978-0-9660176-4-9"]), "same")

    def test_two_isbns_from_one_publisher_are_still_two_books(self):
        # Splitting on hyphens as well would compare "978", "84", "7476" and
        # call every book from the same imprint a match.
        self.assertEqual(
            match.identifiers_verdict(["978-84-7476-385-0", "978-84-7476-224-2"]),
            "different")

    def test_a_field_holding_two_isbns_matches_on_either(self):
        self.assertEqual(
            match.identifiers_verdict(
                ["978-3-031-58240-0 978-3-031-58241-7", "978-3-031-58240-0"]),
            "same")

    def test_a_lone_identifier_decides_nothing(self):
        self.assertEqual(match.identifiers_verdict(["978-84-7509-816-6", ""]), "unknown")

    def test_a_placeholder_is_not_an_identifier(self):
        self.assertEqual(match.identifiers_verdict(["-", "-"], kind="doi"), "unknown")
        self.assertEqual(match.identifiers_verdict(["n/a", "N/A"], kind="doi"), "unknown")


class SeriesAndParallelTitles(unittest.TestCase):
    def test_a_numeral_in_the_middle_is_found(self):
        self.assertEqual(
            match.series_numeral(["Internet y redes sociales en Bolivia 2 by AGETIC",
                                  "Internet y redes sociales en Bolivia by AGETIC"]),
            "2")

    def test_roman_parts_are_found(self):
        self.assertIsNotNone(
            match.series_numeral(["The Effect of Essentialism on Taxonomy (I)",
                                  "The Effect of Essentialism on Taxonomy (II)"]))

    def test_a_real_word_is_not_a_numeral(self):
        self.assertIsNone(
            match.series_numeral(["Guia para el profesorado", "Guia para el estudiantado"]))

    def test_one_word_apart_is_two_works(self):
        self.assertIsNotNone(
            match.contrasting_words(["Guia para el profesorado",
                                     "Guia para el estudiantado"]))

    def test_a_translation_is_two_entries(self):
        self.assertIsNotNone(match.contrasting_words(["Hacktivism", "Hacktivismo"]))

    def test_case_and_accents_alone_are_not_a_difference(self):
        self.assertIsNone(match.contrasting_words(["Network Science", "network sciencé"]))

    def test_a_numeral_is_not_reported_as_a_word(self):
        self.assertIsNone(match.contrasting_words(["Bolivia 2", "Bolivia"]))


if __name__ == "__main__":
    unittest.main()
