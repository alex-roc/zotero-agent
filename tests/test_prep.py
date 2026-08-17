"""Unit tests for the `zot pdf-prep` arithmetic.

Everything here runs without PyMuPDF, without OCRmyPDF and without a PDF: the
decisions that can go wrong — where the gutter is, which pages to trust, which
languages to hand tesseract — are pure functions over an ink profile, and that
is precisely why they live apart from the I/O.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zotero_agent.pdf import prep  # noqa: E402


def raster(columns, height=4):
    """A greyscale buffer whose column `i` is dark iff columns[i] is truthy."""
    row = bytes(0 if dark else 255 for dark in columns)
    return row * height, len(columns), height


def profile_with_gap(width, gap_start, gap_end, level=0.5):
    return [0.0 if gap_start <= i < gap_end else level for i in range(width)]


class ColumnInk(unittest.TestCase):
    def test_counts_dark_pixels_per_column(self):
        samples, width, height = raster([0, 1, 0, 0])
        profile = prep.column_ink(samples, width, height, row_step=1)
        self.assertEqual(profile, [0.0, 1.0, 0.0, 0.0])

    def test_row_step_samples_rows_without_changing_the_fraction(self):
        samples, width, height = raster([0, 1, 0, 0], height=8)
        self.assertEqual(prep.column_ink(samples, width, height, row_step=4),
                         prep.column_ink(samples, width, height, row_step=1))

    def test_empty_raster_is_not_an_error(self):
        self.assertEqual(prep.column_ink(b"", 0, 0), [])


class GutterFromProfile(unittest.TestCase):
    def test_finds_a_centred_gap(self):
        cut, valley = prep.gutter_from_profile(profile_with_gap(200, 95, 105))
        self.assertAlmostEqual(cut, 0.5, delta=0.02)
        self.assertGreater(valley, 0.02)

    def test_finds_an_offset_gap(self):
        cut, _valley = prep.gutter_from_profile(profile_with_gap(200, 110, 122))
        self.assertAlmostEqual(cut, 0.58, delta=0.02)

    def test_prefers_the_widest_valley_not_the_first(self):
        # A narrow column gap (the space between two text columns) sits left of
        # a wide one (the real gutter); the wide one must win.
        profile = profile_with_gap(200, 70, 74)
        for i in range(100, 116):
            profile[i] = 0.0
        cut, _valley = prep.gutter_from_profile(profile)
        self.assertAlmostEqual(cut, 0.54, delta=0.02)

    def test_uniform_ink_has_no_gutter(self):
        cut, valley = prep.gutter_from_profile([0.5] * 200)
        self.assertIsNone(cut)
        self.assertEqual(valley, 0.0)

    def test_ignores_gaps_outside_the_central_band(self):
        # A wide blank margin at the edge is not a gutter.
        cut, _valley = prep.gutter_from_profile(profile_with_gap(200, 0, 40))
        self.assertTrue(cut is None or 0.3 < cut < 0.7)


class ChooseGutter(unittest.TestCase):
    def test_median_of_confident_pages(self):
        samples = [(0.50, 0.05, 0.06), (0.51, 0.05, 0.06), (0.49, 0.05, 0.06)]
        cut, confidence, used = prep.choose_gutter(samples)
        self.assertAlmostEqual(cut, 0.50, places=3)
        self.assertEqual(confidence, 1.0)
        self.assertEqual(used, 3)

    def test_blank_pages_are_excluded(self):
        # The blank page's cut is nonsense; including it would drag the median.
        samples = [(0.50, 0.05, 0.06), (0.51, 0.05, 0.06), (0.40, 0.30, 0.001)]
        cut, _confidence, used = prep.choose_gutter(samples)
        self.assertEqual(used, 2)
        self.assertAlmostEqual(cut, 0.505, places=3)

    def test_disagreement_lowers_confidence(self):
        samples = [(0.50, 0.05, 0.06), (0.42, 0.05, 0.06),
                   (0.58, 0.05, 0.06), (0.50, 0.05, 0.06)]
        _cut, confidence, _used = prep.choose_gutter(samples)
        self.assertLess(confidence, 0.6)

    def test_nothing_usable(self):
        cut, confidence, used = prep.choose_gutter([(None, 0.0, 0.0)])
        self.assertIsNone(cut)
        self.assertEqual((confidence, used), (0.0, 0))


class ParsePages(unittest.TestCase):
    def test_numbers_and_ranges(self):
        self.assertEqual(prep.parse_pages("1,4-6", 10), {1, 4, 5, 6})

    def test_reversed_range_still_works(self):
        self.assertEqual(prep.parse_pages("6-4", 10), {4, 5, 6})

    def test_clamped_to_the_document(self):
        self.assertEqual(prep.parse_pages("9-12", 10), {9, 10})

    def test_empty(self):
        self.assertEqual(prep.parse_pages("", 10), set())
        self.assertEqual(prep.parse_pages(None, 10), set())

    def test_rejects_nonsense(self):
        with self.assertRaises(ValueError):
            prep.parse_pages("one", 10)


class PickLanguage(unittest.TestCase):
    available = ["eng", "spa", "por", "osd"]

    def test_explicit_request_wins(self):
        self.assertEqual(prep.pick_language("deu", "es", self.available), "deu")

    def test_item_language_is_used_alone(self):
        self.assertEqual(prep.pick_language(None, "es", self.available), "spa")
        self.assertEqual(prep.pick_language(None, "Spanish", self.available), "spa")

    def test_unknown_language_falls_back_to_the_pair(self):
        self.assertEqual(prep.pick_language(None, "", self.available), "spa+eng")

    def test_unavailable_language_pack_is_dropped(self):
        self.assertEqual(prep.pick_language(None, "", ["eng", "osd"]), "eng")


class OcrCommand(unittest.TestCase):
    def test_carries_language_profile_and_paths(self):
        command = prep.ocr_command("in.pdf", "out.pdf", "spa", profile="balanced")
        self.assertEqual(command[:3], ["ocrmypdf", "-l", "spa"])
        self.assertEqual(command[-2:], ["in.pdf", "out.pdf"])
        self.assertIn("--deskew", command)
        self.assertIn("--clean", command)

    def test_skip_text_is_always_present(self):
        # Mixed PDFs (typed pages bound with scanned plates) make OCRmyPDF exit
        # with an error unless it is told what to do about existing text.
        self.assertIn("--skip-text", prep.ocr_command("a", "b", "eng"))

    def test_quality_profile_oversamples(self):
        command = prep.ocr_command("a", "b", "eng", profile="quality")
        self.assertIn("--oversample", command)
        self.assertIn("300", command)

    def test_rotate_is_opt_in(self):
        self.assertNotIn("--rotate-pages", prep.ocr_command("a", "b", "eng"))
        self.assertIn("--rotate-pages", prep.ocr_command("a", "b", "eng", rotate=True))


class SampleIndices(unittest.TestCase):
    def test_short_documents_are_sampled_whole(self):
        self.assertEqual(prep.sample_indices(5, 24), [0, 1, 2, 3, 4])

    def test_long_documents_skip_the_covers(self):
        indices = prep.sample_indices(300, 24)
        self.assertLessEqual(len(indices), 24)
        self.assertGreaterEqual(min(indices), 30)
        self.assertLess(max(indices), 270)


if __name__ == "__main__":
    unittest.main()
