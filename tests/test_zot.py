"""Tests for the zotero-agent package — stdlib only (unittest), with a fake
in-process Zotero server for the HTTP paths. Run from the repo root:

    python -m unittest discover -s tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

os.environ["ZOTERO_AGENT_NO_AUDIT"] = "1"  # don't touch ~/.local/state during tests

from fake_zotero import FakeZotero  # noqa: E402

from zotero_agent import audit, cli, http, jslib, resolve  # noqa: E402
from zotero_agent.commands import features, read, write  # noqa: E402
from zotero_agent.term import ZotError, set_verbosity  # noqa: E402

set_verbosity(quiet=True)


def _args(**kw):
    from zotero_agent.mcp_server import _Args
    return _Args(**kw)


class TestParser(unittest.TestCase):
    def test_every_subcommand_has_a_func(self):
        parser = cli.build_parser()
        for cmd in ["search", "get", "add", "dedupe", "tag", "set", "move",
                    "collection", "annotations", "stats", "bib", "export",
                    "note", "backup", "lint", "exec", "ping", "init",
                    "apply", "undo", "enrich", "mcp"]:
            args = parser.parse_args([cmd] + _dummy_args(cmd))
            self.assertTrue(callable(args.func), "%s has no func" % cmd)

    def test_json_and_yes_are_global(self):
        parser = cli.build_parser()
        args = parser.parse_args(["stats", "--yes", "-q", "--json"])
        self.assertTrue(args.yes and args.quiet and args.json)

    def test_version_flag(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--version"])


def _dummy_args(cmd):
    return {
        "search": ["q"], "get": ["K"], "add": ["doi", "10.x/y"], "tag": ["add", "t", "K"],
        "set": ["title", "v", "K"], "move": ["Col", "K"], "collection": ["Name"],
        "annotations": ["K"], "bib": ["K"], "export": ["Col"], "note": ["K"],
        "exec": ["return 1;"], "apply": ["edits.jsonl"], "undo": [], "enrich": ["--field", "doi"],
    }.get(cmd, [])


class TestResolveKey(unittest.TestCase):
    def test_zotero_key_passthrough(self):
        from unittest import mock
        with mock.patch.object(resolve, "bbt_rpc") as rpc:
            self.assertEqual(resolve.resolve_key({}, "AB12CD34"), "AB12CD34")
            rpc.assert_not_called()

    def test_citekey_resolves_via_bbt(self):
        from unittest import mock
        with mock.patch.object(resolve, "bbt_rpc", return_value=[
            {"citekey": "smith2020", "id": "http://zotero.org/users/1/items/WD7FCHBW"}
        ]):
            self.assertEqual(resolve.resolve_key({}, "smith2020"), "WD7FCHBW")

    def test_at_prefix_forces_citekey(self):
        from unittest import mock
        with mock.patch.object(resolve, "bbt_rpc", return_value=[
            {"citation-key": "AB12CD34", "id": "http://zotero.org/users/1/items/ZZZZ0000"}
        ]) as rpc:
            self.assertEqual(resolve.resolve_key({}, "@AB12CD34"), "ZZZZ0000")
            rpc.assert_called_once()

    def test_keys_from_args(self):
        self.assertEqual(resolve.keys_from(["A", "B"]), ["A", "B"])


class TestJsLib(unittest.TestCase):
    def test_scope_switches_on_collection(self):
        self.assertIn("getChildItems", jslib.scope_js("MyColl"))
        self.assertIn("new Zotero.Search", jslib.scope_js(None))

    def test_resolve_collection_js_quotes_arg(self):
        js = jslib.resolve_collection_js("O'Brien's list")
        self.assertIn("collection not found", js)
        self.assertNotIn("O'Brien's list;", js)  # value is repr-quoted, not bare

    def test_field_alias(self):
        self.assertEqual(jslib.field_name("abstract"), "abstractNote")
        self.assertEqual(jslib.field_name("DOI"), "DOI")

    def test_write_regex(self):
        self.assertTrue(jslib.WRITE_RE.search("await item.saveTx();"))
        self.assertTrue(jslib.WRITE_RE.search("await Zotero.Items.merge(a,b)"))
        self.assertIsNone(jslib.WRITE_RE.search("return item.getField('title');"))


class TestFeaturesPure(unittest.TestCase):
    def test_tag_normalization_folds_case(self):
        plan = features.plan_tag_normalization(["Machine Learning", "machine learning", "ML"])
        self.assertEqual(plan.get("machine learning"), "Machine Learning")
        self.assertNotIn("ML", plan)

    def test_tag_normalization_respects_explicit_map(self):
        plan = features.plan_tag_normalization(["ai"], {"ai": "Artificial Intelligence"})
        self.assertEqual(plan["ai"], "Artificial Intelligence")

    def test_openalex_abstract_reconstruction(self):
        work = {"abstract_inverted_index": {"Hello": [0], "world": [1], "again": [2]}}
        self.assertEqual(features._openalex_abstract(work), "Hello world again")

    def test_load_edits_parses_jsonl(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write('{"key":"ABCD1234","set":{"date":"2020"}}\n')
            fh.write("# a comment\n\n")
            fh.write('{"key":"EFGH5678","addTags":["x"]}\n')
            path = fh.name
        edits = features._load_edits(path)
        os.unlink(path)
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[0]["key"], "ABCD1234")

    def test_load_edits_rejects_missing_key(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write('{"set":{"date":"2020"}}\n')
            path = fh.name
        with self.assertRaises(ZotError):
            features._load_edits(path)
        os.unlink(path)


class TestPagination(unittest.TestCase):
    def test_api_list_stops_at_limit(self):
        page = [{"data": {"key": "K%d" % i}} for i in range(25)]
        with FakeZotero(lists={"items": page}, totals={"items": 100}) as srv:
            cfg = {"base": srv.base, "userID": 1, "token": "testtoken"}
            items, total = http.api_list(cfg, "items", want_all=False, limit=25)
        self.assertEqual(len(items), 25)
        self.assertEqual(total, 100)


class TestIntegration(unittest.TestCase):
    def test_post_code_roundtrip_and_token(self):
        with FakeZotero(token="tok") as srv:
            good = http.post_code({"base": srv.base, "token": "tok"}, "return 1 + 1;")
            self.assertTrue(good["ok"])
            self.assertEqual(good["result"], 2)
            bad = http.post_code({"base": srv.base, "token": "WRONG"}, "return 1+1;")
            self.assertFalse(bad["ok"])

    def test_search_prints_items(self):
        page = [{"data": {"key": "AAAA1111", "itemType": "book", "title": "Deep Work", "date": "2016"}}]
        with FakeZotero(token="t", lists={"items": page}, totals={"items": 1}) as srv:
            buf = io.StringIO()
            with redirect_stdout(buf):
                read.cmd_search(_args(query="work", base=srv.base, token="t", user_id=1))
            self.assertIn("Deep Work", buf.getvalue())

    def test_missing_builds_correct_scope_and_parses(self):
        # bridge returns a canned missing-field result for any code containing 'miss'
        result = {"field": "DOI", "total": 3, "missing": 1,
                  "items": [{"key": "K1", "type": "article", "title": "No DOI"}]}
        with FakeZotero(token="t", bridge_results={"var miss": result}) as srv:
            buf = io.StringIO()
            with redirect_stdout(buf):
                read.cmd_missing(_args(field="doi", base=srv.base, token="t", collection=None))
            self.assertIn("No DOI", buf.getvalue())
            self.assertIn("var miss", srv.last_code)


class TestDryRunNeverWrites(unittest.TestCase):
    """Regression guard for the Zotero-7 dry-run write leak: a dry-run must post
    NO code to the bridge, so it can never persist a change."""

    def test_apply_dry_run_posts_no_code(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write('{"key":"ABCD1234","set":{"date":"2021"},"addTags":["review"]}\n')
            path = fh.name
        try:
            with FakeZotero(token="t") as srv:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    features.cmd_apply(_args(file=path, dry_run=True, base=srv.base,
                                             token="t", user_id=1, json=False))
                self.assertIsNone(srv.last_code)  # nothing was executed
                self.assertIn("DRY-RUN", buf.getvalue())
                self.assertIn("ABCD1234", buf.getvalue())
        finally:
            os.unlink(path)

    def test_apply_edits_data_dry_run_posts_no_code(self):
        with FakeZotero(token="t") as srv:
            with mock.patch("zotero_agent.config.require_config",
                            return_value={"base": srv.base, "token": "t", "userID": 1}):
                res = features.apply_edits_data(
                    [{"key": "ABCD1234", "set": {"date": "2021"}}], dry_run=True)
            self.assertIsNone(srv.last_code)
            self.assertTrue(res.get("dryRun"))
            self.assertEqual(res["edits"], 1)

    def test_enrich_dry_run_scans_but_never_applies(self):
        scan = {"field": "DOI", "total": 1, "missing": 1,
                "items": [{"key": "ABCD1234", "title": "A paper", "type": "article"}]}
        with FakeZotero(token="t", bridge_results={"var miss": scan}) as srv:
            with mock.patch.object(features, "_crossref_lookup",
                                   return_value={"DOI": "10.1/x"}):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    features.cmd_enrich(_args(field="doi", source="crossref", collection=None,
                                              dry_run=True, delay=0, base=srv.base,
                                              token="t", user_id=1))
        # exactly one bridge call — the scan — and never the apply body
        self.assertEqual(len(srv.last_codes), 1)
        self.assertIn("var miss", srv.last_codes[0])
        self.assertNotIn("var edits=", srv.last_codes[0])
        self.assertIn("DRY-RUN", buf.getvalue())


class TestApplyUndoRoundtrip(unittest.TestCase):
    def test_apply_snapshots_then_undo_restores(self):
        tmp = tempfile.mkdtemp()
        snap_item = {"key": "ABCD1234", "itemType": "book", "title": "T", "tags": []}
        bridge = {
            "toJSON": lambda code: {"ABCD1234": snap_item},   # snapshot
            "var edits=": {"applied": 1, "errors": []},        # apply
            "fromJSON": {"restored": 1, "errors": []},          # undo
        }
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write('{"key":"ABCD1234","set":{"date":"2021"}}\n')
            path = fh.name
        try:
            with mock.patch.object(features, "UNDO_DIR", tmp), \
                 FakeZotero(token="t", bridge_results=bridge) as srv:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    features.cmd_apply(_args(file=path, dry_run=False, base=srv.base,
                                             token="t", user_id=1, json=False))
                self.assertIn("Applied 1 edit", buf.getvalue())
                # a snapshot was written, and it came before the apply
                snaps = [f for f in os.listdir(tmp) if f.endswith(".json")]
                self.assertEqual(len(snaps), 1)
                self.assertLess(srv.last_codes.index([c for c in srv.last_codes if "toJSON" in c][0]),
                                srv.last_codes.index([c for c in srv.last_codes if "var edits=" in c][0]))

                buf = io.StringIO()
                with redirect_stdout(buf):
                    features.cmd_undo(_args(op="last", keep=False, base=srv.base,
                                            token="t", user_id=1))
                self.assertIn("Restored 1 item", buf.getvalue())
                # snapshot consumed
                self.assertEqual([f for f in os.listdir(tmp) if f.endswith(".json")], [])
        finally:
            os.unlink(path)


class TestWriteCommandsPostExpectedJs(unittest.TestCase):
    def _cfg(self, srv):
        return dict(base=srv.base, token="t", user_id=1, yes=True, json=False)

    def test_set_injects_field_and_value(self):
        with FakeZotero(token="t", bridge_results={
                "it.setField(field, value)": {"field": "title", "items": 1, "errors": []}}) as srv:
            buf = io.StringIO()
            with redirect_stdout(buf):
                write.cmd_set(_args(field="title", value="New Title", keys=["ABCD1234"],
                                    **self._cfg(srv)))
            self.assertIn("Set title on 1 item", buf.getvalue())
            self.assertIn("'New Title'", srv.last_code)

    def test_tag_add_injects_tag(self):
        with FakeZotero(token="t", bridge_results={
                "it.addTag(tag)": {"action": "add", "tag": "review", "items": 1}}) as srv:
            buf = io.StringIO()
            with redirect_stdout(buf):
                write.cmd_tag(_args(action="add", tag="review", keys=["ABCD1234"],
                                    **self._cfg(srv)))
            self.assertIn("Added tag 'review' on 1 item", buf.getvalue())
            self.assertIn("'review'", srv.last_code)

    def test_move_injects_collection(self):
        with FakeZotero(token="t", bridge_results={
                "addToCollection": {"collection": "My Col", "key": "COLL0001", "moved": 1}}) as srv:
            buf = io.StringIO()
            with redirect_stdout(buf):
                write.cmd_move(_args(collection="My Col", keys=["ABCD1234"], **self._cfg(srv)))
            self.assertIn("Added 1 item(s) to 'My Col'", buf.getvalue())
            self.assertIn("'My Col'", srv.last_code)


class TestMcpRunWrapper(unittest.TestCase):
    def test_run_parses_json_output(self):
        from zotero_agent.mcp_server import _run
        page = [{"data": {"key": "AAAA1111", "itemType": "book", "title": "Deep Work"}}]
        with FakeZotero(token="t", lists={"items": page}, totals={"items": 1}) as srv:
            result = _run(read.cmd_search, query="work", base=srv.base, token="t", user_id=1)
        self.assertIn("Deep Work", json.dumps(result))

    def test_run_maps_zoterror_to_error_dict(self):
        from zotero_agent.mcp_server import _run

        def boom(args):
            raise ZotError("boom")

        self.assertEqual(_run(boom), {"error": "boom"})


class TestAuditLog(unittest.TestCase):
    def test_record_writes_jsonl_and_rotates(self):
        tmp = tempfile.mkdtemp()
        apath = os.path.join(tmp, "audit.jsonl")
        with mock.patch.object(audit, "STATE_DIR", tmp), \
             mock.patch.object(audit, "AUDIT_PATH", apath), \
             mock.patch.dict(os.environ, {"ZOTERO_AGENT_NO_AUDIT": "0"}):
            audit.record("apply", "await item.saveTx();", {"ok": True, "result": {"applied": 1}})
            with open(apath, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["label"], "apply")
            self.assertTrue(entry["ok"])
            self.assertEqual(len(entry["codeSHA256"]), 16)

            # a second call with a tiny rotation threshold moves the old log aside
            with mock.patch.object(audit, "MAX_BYTES", 1):
                audit.record("undo", "it.fromJSON({});", {"ok": True, "result": {"restored": 1}})
            self.assertTrue(os.path.exists(apath))
            self.assertTrue(os.path.exists(apath + ".1"))


if __name__ == "__main__":
    unittest.main()
