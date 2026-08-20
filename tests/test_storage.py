"""Shrink's acceptance rule and dedupe's confidence rule.

Both decide whether to do something irreversible — replace a file, merge two
items — so both are pure functions kept away from Ghostscript and Zotero, and
both are tested against the real measurements that motivated them.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zotero_agent.commands import storage  # noqa: E402
from zotero_agent.commands.features import tags_for_path  # noqa: E402
from zotero_agent.commands.storage import is_disposable_orphan  # noqa: E402
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


class DisposableOrphanTests(unittest.TestCase):
    """A parentless attachment is an item, not litter.

    On a real library all 268 parentless attachments were filed in a collection
    and were books — 1.1 GB the first version of this command offered to delete.
    """

    BASE = {"parentKey": None, "collections": 0, "tags": 0, "annotations": 0, "deleted": False}

    def test_a_truly_unclaimed_file_is_disposable(self):
        self.assertTrue(is_disposable_orphan(dict(self.BASE)))

    def test_being_filed_in_a_collection_saves_it(self):
        self.assertFalse(is_disposable_orphan(dict(self.BASE, collections=1)))

    def test_being_tagged_saves_it(self):
        self.assertFalse(is_disposable_orphan(dict(self.BASE, tags=2)))

    def test_being_annotated_saves_it(self):
        self.assertFalse(is_disposable_orphan(dict(self.BASE, annotations=5)))

    def test_having_a_parent_means_it_is_not_an_orphan(self):
        self.assertFalse(is_disposable_orphan(dict(self.BASE, parentKey="ABCD1234")))

    def test_already_trashed_is_left_alone(self):
        self.assertFalse(is_disposable_orphan(dict(self.BASE, deleted=True)))


class ShrinkTargetSelectionTests(unittest.TestCase):
    """Explicit keys must reach the same resolution path every other command uses.

    keys_from() takes only the CLI list; resolving citekeys is a separate step.
    Calling it as keys_from(cfg, keys) raised TypeError, so `zot shrink KEY`
    never worked at all — only the --min-mb sweep was ever exercised.
    """

    ATTS = [
        {"key": "AAAA1111", "parentKey": "PPPP1111", "contentType": "application/pdf",
         "size": 30 * MB, "hasFile": True, "deleted": False, "linked": False},
        {"key": "BBBB2222", "parentKey": None, "contentType": "application/pdf",
         "size": 5 * MB, "hasFile": True, "deleted": False, "linked": False},
        {"key": "CCCC3333", "parentKey": "PPPP3333", "contentType": "text/html",
         "size": 90 * MB, "hasFile": True, "deleted": False, "linked": False},
    ]

    class Args:
        def __init__(self, keys=None, min_mb=25, max_mb=None):
            self.keys = keys or []
            self.min_mb = min_mb
            self.max_mb = max_mb
            self.force = False

    def _patched(self, args):
        with mock.patch.object(storage, "_inventory", return_value=(self.ATTS, 0)), \
             mock.patch.object(storage, "resolve_key", side_effect=lambda cfg, k: k):
            return storage._shrink_targets(None, args)

    def test_an_explicit_attachment_key_selects_that_file(self):
        got = self._patched(self.Args(keys=["AAAA1111"]))
        self.assertEqual([a["key"] for a in got], ["AAAA1111"])

    def test_an_explicit_parent_key_selects_its_attachment(self):
        got = self._patched(self.Args(keys=["PPPP1111"]))
        self.assertEqual([a["key"] for a in got], ["AAAA1111"])

    def test_the_sweep_honours_min_mb_and_skips_non_pdfs(self):
        got = self._patched(self.Args(min_mb=25))
        self.assertEqual([a["key"] for a in got], ["AAAA1111"])

    def test_max_mb_bounds_the_band(self):
        # 10-20 MB band: the 30 MB file is out, so nothing is left.
        got = self._patched(self.Args(min_mb=10, max_mb=20))
        self.assertEqual(got, [])

    def test_an_already_shrunk_file_is_skipped(self):
        # Shrinking is lossy; a second pass would re-encode what was encoded.
        atts = [dict(self.ATTS[0], tagNames=["shrunk"])]
        with mock.patch.object(storage, "_inventory", return_value=(atts, 0)), \
             mock.patch.object(storage, "resolve_key", side_effect=lambda cfg, k: k):
            self.assertEqual(storage._shrink_targets(None, self.Args(min_mb=25)), [])

    def test_force_redoes_an_already_shrunk_file(self):
        atts = [dict(self.ATTS[0], tagNames=["shrunk"])]
        args = self.Args(min_mb=25)
        args.force = True
        with mock.patch.object(storage, "_inventory", return_value=(atts, 0)), \
             mock.patch.object(storage, "resolve_key", side_effect=lambda cfg, k: k):
            self.assertEqual([a["key"] for a in storage._shrink_targets(None, args)],
                             ["AAAA1111"])


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
