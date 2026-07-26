"""Tests for the zotero-agent package — stdlib only (unittest), with a fake
in-process Zotero server for the HTTP paths. Run from the repo root:

    python -m unittest discover -s tests
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

os.environ["ZOTERO_AGENT_NO_AUDIT"] = "1"  # don't touch ~/.local/state during tests

from fake_zotero import FakeZotero  # noqa: E402

from zotero_agent import assets, audit, cli, http, jslib, resolve  # noqa: E402
from zotero_agent.commands import admin, features, read, write  # noqa: E402
from zotero_agent.constants import VERSION  # noqa: E402
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


class TestAssets(unittest.TestCase):
    """The skill/plugin assets must be reachable and installable — this is what a
    `uv tool install` user gets, so a packaging regression has to fail here."""

    def test_asset_paths_resolve(self):
        self.assertTrue(os.path.isdir(assets.asset_path("skill")))
        self.assertTrue(os.path.isfile(assets.asset_path("agents-md")))
        self.assertTrue(os.path.isfile(os.path.join(assets.asset_path("skill"), "SKILL.md")))

    def test_the_package_does_not_ship_the_plugin(self):
        """The XPI has exactly one distribution channel (the release asset), so
        no plugin source may sneak into the installable package."""
        self.assertEqual(set(assets._ASSETS), {"skill", "agents-md"})
        self.assertFalse(hasattr(assets, "build_xpi"))

    def test_install_skill_copies_the_skill(self):
        tmp = tempfile.mkdtemp()
        dest = os.path.join(tmp, "skills", "zotero")
        got = assets.install_skill(dest)
        self.assertEqual(got, dest)
        self.assertTrue(os.path.isfile(os.path.join(dest, "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "references", "recipes.md")))
        self.assertFalse(os.path.exists(os.path.join(dest, "scripts")))

    def test_install_skill_refuses_to_clobber_without_force(self):
        tmp = tempfile.mkdtemp()
        dest = os.path.join(tmp, "zotero")
        assets.install_skill(dest)
        with self.assertRaises(ZotError):
            assets.install_skill(dest)
        assets.install_skill(dest, force=True)  # force replaces it
        self.assertTrue(os.path.isfile(os.path.join(dest, "SKILL.md")))

    def test_skill_install_dest_honours_project_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["skill", "install", "--project"])
        self.assertEqual(admin._skill_dest(args),
                         os.path.join(os.getcwd(), ".claude", "skills", "zotero"))
        args = parser.parse_args(["skill", "install"])
        self.assertEqual(admin._skill_dest(args),
                         os.path.expanduser("~/.claude/skills/zotero"))
        args = parser.parse_args(["skill", "install", "--dest", "/tmp/x"])
        self.assertEqual(admin._skill_dest(args), "/tmp/x")

    def test_wheel_force_include_covers_every_skill_file(self):
        """Packaging guard: a new file under skill/ must be added to the wheel's
        force-include list, or PyPI users silently get an incomplete skill."""
        import re
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as fh:
            toml = fh.read()
        block = re.search(r"\[tool\.hatch\.build\.targets\.wheel\.force-include\]\n(.*?)(?=\n\[|\Z)",
                          toml, re.S).group(1)
        declared = set(re.findall(r'^"([^"]+)"\s*=', block, re.M))
        skill_root = os.path.join(root, "skill")
        for dirpath, dirnames, filenames in os.walk(skill_root):
            dirnames[:] = [d for d in dirnames if d not in ("scripts", "evals", "__pycache__")]
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
                covered = any(rel == d or rel.startswith(d + "/") for d in declared)
                self.assertTrue(covered, "%s is not in the wheel's force-include list" % rel)

    def test_skill_agents_md_goes_to_stdout(self):
        parser = cli.build_parser()
        args = parser.parse_args(["skill", "agents-md"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            admin.cmd_skill(args)
        self.assertIn("zot", buf.getvalue())


class TestReadmeCommandTable(unittest.TestCase):
    """The README's "Commands at a glance" table must match the CLI in *both*
    directions: a new command missing from it goes unadvertised, and a retired one
    left in it advertises something that errors out."""

    def test_table_matches_the_parser(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        with open(os.path.join(root, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        table = re.search(r"### Commands at a glance\n(.*?)(?=\n#{2,3} )", readme, re.S)
        self.assertIsNotNone(table, "the 'Commands at a glance' table is gone")
        listed = set(re.findall(r"`([a-z]+)`", table.group(1)))

        parser = cli.build_parser()
        sub = [a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"][0]
        commands = set(sub.choices)
        # The table also names `tag` subactions (add/rm/...); ignore anything that
        # is not a top-level command, and require exact coverage of the rest.
        self.assertEqual(commands - listed, set(), "commands missing from the README table")
        self.assertEqual(listed - commands - {"add", "rm", "rename", "purge", "normalize"}, set(),
                         "README table lists commands the CLI does not have")


class TestVersionIsSingleSourced(unittest.TestCase):
    """The CLI, the plugin and the auto-update manifest are released together and
    must all announce the same version — otherwise Zotero either never offers the
    update, or offers one that disagrees with the installed CLI."""

    _ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

    def _read(self, *parts):
        with open(os.path.join(self._ROOT, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_plugin_manifest_matches_the_package(self):
        manifest = json.loads(self._read("plugin", "zotero-agent-bridge", "manifest.json"))
        self.assertEqual(manifest["version"], VERSION)

    def test_bootstrap_matches_the_package(self):
        import re
        found = re.search(r'\n\s*version:\s*"([^"]+)"', self._read("plugin", "zotero-agent-bridge", "bootstrap.js"))
        self.assertIsNotNone(found, "BRIDGE.version not found in bootstrap.js")
        self.assertEqual(found.group(1), VERSION)

    def test_updates_json_announces_the_current_version(self):
        updates = json.loads(self._read("updates.json"))
        entry = updates["addons"]["zotero-agent-bridge@zotero-agent"]["updates"][0]
        self.assertEqual(entry["version"], VERSION)
        self.assertIn("/releases/download/v%s/" % VERSION, entry["update_link"])
        self.assertTrue(entry["update_link"].endswith("zotero-agent-bridge-%s.xpi" % VERSION))

    def test_manifest_update_url_matches_the_generator(self):
        """Both must name the same file, or the plugin polls a manifest nobody writes."""
        manifest = json.loads(self._read("plugin", "zotero-agent-bridge", "manifest.json"))
        self.assertTrue(manifest["applications"]["zotero"]["update_url"].endswith("/updates.json"))


class TestPluginVersionReporting(unittest.TestCase):
    def test_matching_version_is_reported_plainly(self):
        self.assertEqual(admin._plugin_status(VERSION), VERSION)

    def test_missing_version_means_an_old_plugin(self):
        self.assertIn("unknown", admin._plugin_status(None))

    def test_older_and_newer_plugins_get_the_right_advice(self):
        with mock.patch.object(admin, "VERSION", "0.9.0"):
            # 0.10.0 > 0.9.0 numerically; a string comparison would call it older.
            self.assertIn("newer than this CLI", admin._plugin_status("0.10.0"))
            self.assertIn("older than this CLI", admin._plugin_status("0.8.9"))
            self.assertIn("Check for Updates", admin._plugin_status("0.8.9"))
        with mock.patch.object(admin, "VERSION", "0.10.0"):
            self.assertIn("older than this CLI", admin._plugin_status("0.9.0"))
        with mock.patch.object(admin, "VERSION", "0.2.1"):
            self.assertIn("uv tool upgrade", admin._plugin_status("0.3.0"))

    def test_version_tuple_is_numeric_and_tolerates_suffixes(self):
        self.assertGreater(admin._version_tuple("0.10.0"), admin._version_tuple("0.9.9"))
        self.assertEqual(admin._version_tuple("0.3.0rc1"), (0, 3, 0))

    def test_dev_tree_is_told_apart_from_an_installed_copy(self):
        """Switching an editable install for a released one leaves the version
        identical, so this predicate is the only thing that distinguishes them."""
        from zotero_agent import constants
        self.assertFalse(constants.is_dev_tree(
            "/opt/homebrew/Cellar/zotero-agent/0.4.0/libexec/lib/python3.14/site-packages/zotero_agent"))
        self.assertFalse(constants.is_dev_tree("/usr/lib/python3/dist-packages/zotero_agent"))
        self.assertTrue(constants.is_dev_tree("/Users/me/dev/zotero-agent/src/zotero_agent"))
        # These tests always run from a checkout, so the ambient value must agree.
        self.assertTrue(constants.IS_DEV_TREE)

    def test_ping_reports_which_install_answered(self):
        """`zot ping` is what people paste into bug reports; it has to say where the
        CLI ran from, or a brew/uv/editable mix-up is invisible."""
        with FakeZotero() as srv:
            cfg = {"base": srv.base, "token": "t", "userID": 1}
            with mock.patch.object(admin, "post_code",
                                   return_value={"ok": True, "result": 2, "version": admin.VERSION}), \
                 mock.patch("zotero_agent.config.require_config", return_value=cfg):
                buf = io.StringIO()
                with redirect_stdout(buf), self.assertRaises(SystemExit):
                    admin.cmd_ping(_args())
        out = buf.getvalue()
        self.assertIn("zot source", out)
        self.assertIn("(dev tree)", out)          # the suite runs from a checkout
        self.assertNotIn(os.path.expanduser("~"), out, "the home path should be shown as ~")

    def test_ping_prints_the_plugin_version(self):
        with FakeZotero() as srv:
            cfg = {"base": srv.base, "token": "t", "userID": 1}
            with mock.patch.object(admin, "post_code",
                                   return_value={"ok": True, "result": 2, "version": "9.9.9"}), \
                 mock.patch("zotero_agent.config.require_config", return_value=cfg):
                buf = io.StringIO()
                with redirect_stdout(buf), self.assertRaises(SystemExit) as exit_ctx:
                    admin.cmd_ping(_args())
        self.assertEqual(exit_ctx.exception.code, 0)
        out = buf.getvalue()
        self.assertIn("bridge plugin", out)
        self.assertIn("9.9.9", out)


if __name__ == "__main__":
    unittest.main()
