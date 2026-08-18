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


if __name__ == "__main__":
    unittest.main()
