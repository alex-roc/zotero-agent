"""Backup pruning: what a snapshot directory is allowed to forget.

`zot backup` copies the whole of `zotero.sqlite` — 300-400 MB on a working
library — and for a long time nothing removed the old copies, so the directory
grew about a gigabyte on a day with three backups. Pruning is therefore
irreversible work running on every backup, which is exactly the kind of rule
that belongs in a pure function with tests.

The rule is *newest per day, last N days* — not "the last N snapshots". The
distinction is the whole point: the real directory that motivated this held
three copies made within six hours of each other, and a count-based rule would
have kept those three and thrown away every restore point older than that day.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zotero_agent.commands.admin import BACKUP_RE, _prune_backups  # noqa: E402


def _dir_with(names, size=64):
    d = tempfile.mkdtemp()
    for name in names:
        with open(os.path.join(d, name), "w") as fh:
            fh.write("x" * size)
    return d


class BackupNameTests(unittest.TestCase):
    def test_snapshot_and_its_companions_are_recognised(self):
        for name in ("zotero-20260823-190310.sqlite",
                     "zotero-20260823-190310.sqlite-wal",
                     "zotero-20260823-190310.sqlite-shm"):
            self.assertTrue(BACKUP_RE.match(name), name)

    def test_anything_else_is_not_a_snapshot(self):
        # the directory is the user's; only our own filenames are ours to delete
        for name in ("notes.txt", "zotero.sqlite", "zotero-2026-08-23.sqlite",
                     "zotero-20260823.sqlite", "backup-20260823-190310.sqlite"):
            self.assertIsNone(BACKUP_RE.match(name), name)


class PruneTests(unittest.TestCase):
    # the real directory that motivated this: 10 snapshots, 3 of them same-day
    REAL = ["zotero-20260823-190310.sqlite", "zotero-20260823-123417.sqlite",
            "zotero-20260823-121119.sqlite", "zotero-20260822-145525.sqlite",
            "zotero-20260822-131924.sqlite", "zotero-20260822-090408.sqlite",
            "zotero-20260820-103135.sqlite", "zotero-20260819-205919.sqlite",
            "zotero-20260817-222926.sqlite", "zotero-20260817-210920.sqlite"]

    def test_keeps_the_newest_of_each_of_the_last_three_days(self):
        d = _dir_with(self.REAL)
        _prune_backups(d, 3)
        self.assertEqual(sorted(os.listdir(d)), [
            "zotero-20260820-103135.sqlite",
            "zotero-20260822-145525.sqlite",
            "zotero-20260823-190310.sqlite",
        ])

    def test_coverage_spans_days_not_hours(self):
        # the count-based rule would have kept three copies of one afternoon
        d = _dir_with(self.REAL)
        _prune_backups(d, 3)
        days = {n[7:15] for n in os.listdir(d)}
        self.assertEqual(len(days), 3)

    def test_companions_follow_their_snapshot(self):
        d = _dir_with(["zotero-20260823-190310.sqlite",
                       "zotero-20260823-190310.sqlite-wal",
                       "zotero-20260823-120000.sqlite",
                       "zotero-20260823-120000.sqlite-wal",
                       "zotero-20260823-120000.sqlite-shm"])
        _prune_backups(d, 1)
        self.assertEqual(sorted(os.listdir(d)), ["zotero-20260823-190310.sqlite",
                                                 "zotero-20260823-190310.sqlite-wal"])

    def test_foreign_files_are_never_touched(self):
        d = _dir_with(self.REAL + ["README.md", "zotero.sqlite"])
        _prune_backups(d, 1)
        left = set(os.listdir(d))
        self.assertIn("README.md", left)
        self.assertIn("zotero.sqlite", left)

    def test_zero_days_disables_pruning(self):
        d = _dir_with(self.REAL)
        removed, freed = _prune_backups(d, 0)
        self.assertEqual(removed, [])
        self.assertEqual(freed, 0)
        self.assertEqual(len(os.listdir(d)), len(self.REAL))

    def test_fewer_days_than_asked_for_is_not_an_error(self):
        d = _dir_with(["zotero-20260823-190310.sqlite"])
        removed, _ = _prune_backups(d, 3)
        self.assertEqual(removed, [])
        self.assertEqual(os.listdir(d), ["zotero-20260823-190310.sqlite"])

    def test_reports_what_it_freed(self):
        d = _dir_with(self.REAL, size=100)
        removed, freed = _prune_backups(d, 3)
        self.assertEqual(len(removed), 7)
        self.assertEqual(freed, 700)

    def test_pruning_twice_is_a_no_op(self):
        d = _dir_with(self.REAL)
        _prune_backups(d, 3)
        removed, freed = _prune_backups(d, 3)
        self.assertEqual((removed, freed), ([], 0))


if __name__ == "__main__":
    unittest.main()
