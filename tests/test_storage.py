"""Shrink's acceptance rule and dedupe's confidence rule.

Both decide whether to do something irreversible — replace a file, merge two
items — so both are pure functions kept away from Ghostscript and Zotero, and
both are tested against the real measurements that motivated them.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zotero_agent.commands.features import tags_for_path  # noqa: E402
from zotero_agent.commands.write import merge_confidence  # noqa: E402
from zotero_agent.pdf import shrink  # noqa: E402

MB = 1024 * 1024


class ShrinkVerdictTests(unittest.TestCase):
    def test_a_real_gain_is_accepted(self):
        # measured: a 600-dpi scan of Freud, 143.6 MB -> 29.5 MB, 155 pages
        ok, ratio, _ = shrink.verdict(143 * MB, 29 * MB, 155, 155)
        self.assertTrue(ok)
        self.assertLess(ratio, 0.25)

    def test_no_meaningful_gain_keeps_the_original(self):
        # measured: 22 of 35 real books came back the same size or bigger
        ok, _, reason = shrink.verdict(121 * MB, 121 * MB, 584, 584)
        self.assertFalse(ok)
        self.assertEqual(reason, "no meaningful gain")

    def test_a_bigger_file_is_rejected(self):
        ok, _, _ = shrink.verdict(83 * MB, 86 * MB, 325, 325)
        self.assertFalse(ok)

    def test_losing_pages_is_rejected_however_small_the_result(self):
        ok, _, reason = shrink.verdict(100 * MB, 1 * MB, 500, 499)
        self.assertFalse(ok)
        self.assertIn("pages", reason)

    def test_unreadable_page_count_is_rejected(self):
        ok, _, reason = shrink.verdict(100 * MB, 10 * MB, None, None)
        self.assertFalse(ok)
        self.assertEqual(reason, "unreadable page count")

    def test_empty_output_is_rejected(self):
        ok, _, reason = shrink.verdict(100 * MB, 0, 10, 10)
        self.assertFalse(ok)
        self.assertEqual(reason, "empty output")

    def test_the_command_downsamples_and_names_the_output(self):
        cmd = shrink.gs_command("in.pdf", "out.pdf", dpi=200, mono_dpi=300)
        self.assertEqual(cmd[0], "gs")
        self.assertIn("-dColorImageResolution=200", cmd)
        self.assertIn("-dGrayImageResolution=200", cmd)
        self.assertIn("-dMonoImageResolution=300", cmd)
        self.assertIn("-sOutputFile=out.pdf", cmd)
        self.assertEqual(cmd[-1], "in.pdf")


class MergeConfidenceTests(unittest.TestCase):
    def test_five_statistics_textbooks_are_not_one_book(self):
        group = [
            {"title": "Estadística", "year": "1991", "firstAuthor": "Spiegel", "edition": "2°"},
            {"title": "Estadística", "year": "2013", "firstAuthor": "Triola", "edition": "11°"},
        ]
        confident, reason = merge_confidence(group)
        self.assertFalse(confident)
        self.assertEqual(reason, "different authors")

    def test_two_editions_of_the_same_book_need_review(self):
        group = [
            {"title": "Social Network Analysis", "year": "2012", "firstAuthor": "Scott", "edition": "Third"},
            {"title": "Social network analysis", "year": "2017", "firstAuthor": "Scott", "edition": "4th ed"},
        ]
        confident, reason = merge_confidence(group)
        self.assertFalse(confident)
        self.assertEqual(reason, "different editions")

    def test_distant_years_need_review_even_with_one_author(self):
        group = [
            {"title": "Conocimiento e interés", "year": "1982", "firstAuthor": "Habermas", "edition": ""},
            {"title": "Conocimiento e interés", "year": "2023", "firstAuthor": "Habermas", "edition": ""},
        ]
        confident, reason = merge_confidence(group)
        self.assertFalse(confident)
        self.assertIn("1982", reason)

    def test_a_true_duplicate_is_confident(self):
        group = [
            {"title": "Network Science", "year": "2016", "firstAuthor": "Barabási", "edition": ""},
            {"title": "Network science", "year": "2016", "firstAuthor": "Barabasi", "edition": ""},
        ]
        confident, reason = merge_confidence(group)
        self.assertTrue(confident, reason)

    def test_a_year_of_drift_stays_confident(self):
        group = [
            {"title": "A history of communications", "year": "2010", "firstAuthor": "Poe", "edition": ""},
            {"title": "A history of communications", "year": "2011", "firstAuthor": "Poe", "edition": ""},
        ]
        self.assertTrue(merge_confidence(group)[0])

    def test_the_same_author_written_two_ways_is_still_one_author(self):
        group = [
            {"title": "A large-scale COVID-19 Twitter chatter dataset", "year": "2020",
             "firstAuthor": "Banda", "edition": ""},
            {"title": "A large-scale COVID-19 Twitter chatter dataset", "year": "2020",
             "firstAuthor": "Banda, Juan M.", "edition": ""},
        ]
        confident, reason = merge_confidence(group)
        self.assertTrue(confident, reason)

    def test_a_thesis_and_its_paper_are_two_citable_things(self):
        group = [
            {"title": "A symbolic analysis of relay and switching circuits", "year": "1937",
             "firstAuthor": "Shannon", "edition": "", "type": "thesis"},
            {"title": "A symbolic analysis of relay and switching circuits", "year": "1938",
             "firstAuthor": "Shannon", "edition": "", "type": "journalArticle"},
        ]
        confident, reason = merge_confidence(group)
        self.assertFalse(confident)
        self.assertIn("item types", reason)

    def test_webpage_and_blogpost_are_the_same_thing_imported_twice(self):
        group = [
            {"title": "First digital computer, by country", "year": "2020",
             "firstAuthor": "Doiron", "edition": "", "type": "webpage"},
            {"title": "First digital computer, by country", "year": "2020",
             "firstAuthor": "Doiron", "edition": "", "type": "blogPost"},
        ]
        self.assertTrue(merge_confidence(group)[0])

    def test_missing_metadata_does_not_veto(self):
        group = [
            {"title": "Digitalization", "year": "", "firstAuthor": "", "edition": ""},
            {"title": "Digitalization", "year": "2016", "firstAuthor": "Brennen", "edition": ""},
        ]
        self.assertTrue(merge_confidence(group)[0])


class TagsFromCollectionPathTests(unittest.TestCase):
    RULES = [
        {"match": "infodemia|infodemic", "tags": ["#infodemia"]},
        {"match": "digitalizacion", "tags": ["#digitalización"]},
        {"match": "estado del arte|marco teorico", "tags": ["~teoría"]},
    ]
    CONTAINERS = ["Investigacion", "Articulos", "@Digitalización", "@Tesis. Digitalización societal"]

    def test_a_leaf_topic_is_picked_up(self):
        tags = tags_for_path("Investigacion / Articulos / Infodemia en Twitter",
                             self.RULES, self.CONTAINERS)
        self.assertEqual(tags, {"#infodemia"})

    def test_accents_and_case_do_not_matter(self):
        self.assertEqual(tags_for_path("X / INFODEMIA", self.RULES), {"#infodemia"})

    def test_container_segments_do_not_tag_the_whole_branch(self):
        # The real regression: with the root branch counted, every item under
        # "@Digitalización" got #digitalización — 1318 of 3019 items.
        tags = tags_for_path("@Digitalización / IA y educación", self.RULES, self.CONTAINERS)
        self.assertNotIn("#digitalización", tags)

    def test_a_genuine_mention_below_the_container_still_tags(self):
        tags = tags_for_path("@Digitalización / @Tesis. Digitalización societal / "
                             "Z. Archivo / Marco teórico / Digitalización",
                             self.RULES, self.CONTAINERS)
        self.assertEqual(tags, {"#digitalización", "~teoría"})

    def test_a_path_made_only_of_containers_falls_back_to_itself(self):
        tags = tags_for_path("@Digitalización", self.RULES, self.CONTAINERS)
        self.assertEqual(tags, {"#digitalización"})

    def test_several_rules_can_fire_at_once(self):
        tags = tags_for_path("Infodemia en Twitter / Estado del arte", self.RULES)
        self.assertEqual(tags, {"#infodemia", "~teoría"})

    def test_a_bad_regex_is_reported_not_swallowed(self):
        with self.assertRaises(ValueError):
            tags_for_path("anything", [{"match": "[unclosed", "tags": ["#x"]}])


if __name__ == "__main__":
    unittest.main()
