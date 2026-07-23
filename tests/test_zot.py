"""Unit tests for the `zot` CLI — stdlib only (unittest + mock), no network.

Run:  python3 -m unittest discover -s tests   (from the repo root)
"""
import importlib.machinery
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

# Load cli/zot (no .py extension) as a module named "zot".
_HERE = os.path.dirname(os.path.abspath(__file__))
_ZOT_PATH = os.path.join(_HERE, "..", "cli", "zot")
_loader = importlib.machinery.SourceFileLoader("zot", _ZOT_PATH)
_spec = importlib.util.spec_from_loader("zot", _loader)
zot = importlib.util.module_from_spec(_spec)
_loader.exec_module(zot)


class TestParser(unittest.TestCase):
    def test_every_subcommand_has_a_func(self):
        parser = zot.build_parser()
        # A representative sample across read / edit / escape / setup.
        for cmd in ["search", "get", "add", "dedupe", "tag", "set", "move",
                    "collection", "annotations", "stats", "bib", "export",
                    "note", "backup", "lint", "exec", "ping", "init"]:
            args = parser.parse_args([cmd] + _dummy_args(cmd))
            self.assertTrue(callable(args.func), "%s has no func" % cmd)

    def test_global_flags_present(self):
        parser = zot.build_parser()
        args = parser.parse_args(["stats", "--yes", "-q"])
        self.assertTrue(args.yes)
        self.assertTrue(args.quiet)


def _dummy_args(cmd):
    return {
        "search": ["q"], "get": ["K"], "add": ["doi", "10.x/y"], "tag": ["add", "t", "K"],
        "set": ["title", "v", "K"], "move": ["Col", "K"], "collection": ["Name"],
        "annotations": ["K"], "bib": ["K"], "export": ["Col"], "note": ["K"],
        "exec": ["return 1;"],
    }.get(cmd, [])


class TestResolveKey(unittest.TestCase):
    def test_zotero_key_passthrough(self):
        # 8-char uppercase alnum → returned as-is, no BBT call.
        with mock.patch.object(zot, "bbt_rpc") as rpc:
            self.assertEqual(zot.resolve_key({}, "AB12CD34"), "AB12CD34")
            rpc.assert_not_called()

    def test_citekey_resolves_via_bbt(self):
        with mock.patch.object(zot, "bbt_rpc", return_value=[
            {"citekey": "smith2020", "id": "http://zotero.org/users/1/items/WD7FCHBW"}
        ]):
            self.assertEqual(zot.resolve_key({}, "smith2020"), "WD7FCHBW")

    def test_at_prefix_forces_citekey(self):
        with mock.patch.object(zot, "bbt_rpc", return_value=[
            {"citation-key": "AB12CD34", "id": "http://zotero.org/users/1/items/ZZZZ0000"}
        ]) as rpc:
            self.assertEqual(zot.resolve_key({}, "@AB12CD34"), "ZZZZ0000")
            rpc.assert_called_once()


class TestPagination(unittest.TestCase):
    def test_api_list_stops_at_limit(self):
        page = [{"data": {"key": "K%d" % i}} for i in range(25)]
        with mock.patch.object(zot, "http_get_full",
                               return_value=(200, {"Total-Results": "100"}, zot.json.dumps(page))):
            items, total = zot.api_list({"base": "x", "userID": 1}, "items", want_all=False, limit=25)
        self.assertEqual(len(items), 25)
        self.assertEqual(total, 100)

    def test_api_list_paginates_all(self):
        calls = {"n": 0}

        def fake(url, timeout=30):
            calls["n"] += 1
            # two full pages of 100, then a short page of 30 → stops
            n = 100 if calls["n"] <= 2 else 30
            body = zot.json.dumps([{"data": {"key": "x"}} for _ in range(n)])
            return 200, {"Total-Results": "230"}, body

        with mock.patch.object(zot, "http_get_full", side_effect=fake):
            items, total = zot.api_list({"base": "x", "userID": 1}, "items", want_all=True)
        self.assertEqual(len(items), 230)
        self.assertEqual(total, 230)


class TestProjectAndAliases(unittest.TestCase):
    def test_project_drops_abstract_unless_full(self):
        res = {"items": [{"title": "t", "abstract": "long..."}]}
        zot._project(res, "concise")
        self.assertNotIn("abstract", res["items"][0])

    def test_project_keeps_abstract_when_full(self):
        res = {"items": [{"title": "t", "abstract": "long..."}]}
        zot._project(res, "full")
        self.assertIn("abstract", res["items"][0])

    def test_field_aliases(self):
        self.assertEqual(zot.FIELD_ALIASES["abstract"], "abstractNote")
        self.assertEqual(zot.FIELD_ALIASES["doi"], "DOI")


class TestWriteSafety(unittest.TestCase):
    def test_confirm_write_passes_with_yes(self):
        args = mock.Mock(yes=True)
        zot.confirm_write(args, "x")  # should not raise

    def test_confirm_write_refuses_non_tty(self):
        args = mock.Mock(yes=False)
        with mock.patch("sys.stdin.isatty", return_value=False), \
             redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                zot.confirm_write(args, "x")
        self.assertEqual(cm.exception.code, zot.EXIT_GENERIC)

    def test_exec_write_regex_matches_savetx(self):
        self.assertTrue(zot.WRITE_RE.search("await item.saveTx();"))
        self.assertTrue(zot.WRITE_RE.search("await Zotero.Items.merge(a,b)"))
        self.assertIsNone(zot.WRITE_RE.search("return item.getField('title');"))


if __name__ == "__main__":
    unittest.main()
