"""The packaged EPUB helper must preserve content and both navigation formats."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'skill/references/epub_toc.py'
spec = importlib.util.spec_from_file_location('epub_toc_skill', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class EpubTocSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.plan = [{'title': 'Part', 'href': 'Text/chapter.xhtml', 'children': [
            {'title': 'Chapter 1', 'href': 'Text/chapter.xhtml#section', 'children': []}]}]
        self.plan_path = self.base / 'plan.json'
        self.plan_path.write_text(json.dumps(self.plan))

    def fixture(self, version='3.0', navigation=True, both=False):
        files = {'META-INF/container.xml': '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
                 'OEBPS/Text/chapter.xhtml': '<html xmlns="http://www.w3.org/1999/xhtml"><body><h1 id="section">Chapter</h1><p>Keep this intact.</p></body></html>'}
        items = '<item id="chapter" href="Text/chapter.xhtml" media-type="application/xhtml+xml"/>'
        if navigation and (version.startswith('2') or both):
            items += '<item id="ncx" href="nav/toc.ncx" media-type="application/x-dtbncx+xml"/>'
            files['OEBPS/nav/toc.ncx'] = '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><head/><navMap><navPoint id="n"><navLabel><text>Old</text></navLabel><content src="../Text/chapter.xhtml"/></navPoint></navMap></ncx>'
        if navigation and version.startswith('3'):
            items += '<item id="nav" href="nav/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            files['OEBPS/nav/nav.xhtml'] = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol><li><a href="../Text/chapter.xhtml">Old</a></li></ol></nav><nav epub:type="landmarks"><ol><li><a href="../Text/chapter.xhtml">Start</a></li></ol></nav></body></html>'
        files['OEBPS/content.opf'] = f'<package xmlns="{helper.OPF}" version="{version}"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Fixture</dc:title><dc:identifier>fixture</dc:identifier></metadata><manifest>{items}</manifest><spine><itemref idref="chapter"/></spine></package>'
        source = self.base / 'input.epub'
        with zipfile.ZipFile(source, 'w') as z:
            z.writestr('mimetype', 'application/epub+zip')
            for name, content in files.items():
                z.writestr(name, content)
        return source

    def run_helper(self, source, *args):
        return subprocess.run([sys.executable, str(HELPER), str(source), *map(str, args)], capture_output=True, text=True)

    def write(self, source):
        output = self.base / 'output.epub'
        before = source.read_bytes()
        result = self.run_helper(source, '--from', self.plan_path, '-o', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(json.loads(self.run_helper(output).stdout), self.plan)
        with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
            self.assertEqual(a.read('OEBPS/Text/chapter.xhtml'), b.read('OEBPS/Text/chapter.xhtml'))
            self.assertEqual(b.infolist()[0].filename, 'mimetype')
            self.assertEqual(b.infolist()[0].compress_type, zipfile.ZIP_STORED)
        return output

    def test_epub2_round_trip(self):
        self.write(self.fixture('2.0'))

    def test_epub3_and_ncx_stay_in_sync_and_landmarks_survive(self):
        output = self.write(self.fixture(both=True))
        with zipfile.ZipFile(output) as z:
            ncx = ET.fromstring(z.read('OEBPS/nav/toc.ncx'))
            self.assertEqual(helper.read_ncx(ncx, 'OEBPS/nav', 'OEBPS'), self.plan)
            nav = ET.fromstring(z.read('OEBPS/nav/nav.xhtml'))
            landmarks = [n for n in nav.iter('{%s}nav' % helper.XHTML) if n.get('{%s}type' % helper.EPUB) == 'landmarks']
            self.assertEqual(len(landmarks), 1)
            self.assertEqual(helper.text(landmarks[0]), 'Start')
            # Readers match these literally, so ElementTree's ns0:/html: prefixes must not leak.
            self.assertIn(b'<nav epub:type="toc">', z.read('OEBPS/nav/nav.xhtml'))
            self.assertTrue(z.read('OEBPS/nav/toc.ncx').startswith(b"<?xml version='1.0' encoding='utf-8'?>\n<ncx "))
        with zipfile.ZipFile(self.base / 'input.epub') as a, zipfile.ZipFile(output) as b:
            self.assertEqual(a.read('OEBPS/content.opf'), b.read('OEBPS/content.opf'))

    def test_create_missing_epub2_navigation(self):
        output = self.write(self.fixture('2.0', navigation=False))
        with zipfile.ZipFile(output) as z:
            opf = ET.fromstring(z.read('OEBPS/content.opf'))
            self.assertEqual(opf.find('{*}spine').get('toc'), '_agent_toc')
            self.assertIn(b'<package xmlns=', z.read('OEBPS/content.opf'))

    def test_create_missing_epub3_navigation(self):
        self.write(self.fixture(navigation=False))

    def test_fragment_found_despite_html_entities(self):
        source = self.fixture()
        with zipfile.ZipFile(source) as z:
            files = {i.filename: z.read(i.filename) for i in z.infolist()}
        files['OEBPS/Text/chapter.xhtml'] = files['OEBPS/Text/chapter.xhtml'].replace(b'Keep', b'Keep&nbsp;')
        source.unlink()
        with zipfile.ZipFile(source, 'w') as z:
            for name, content in files.items():
                z.writestr(name, content)
        result = self.run_helper(source, '--from', self.plan_path, '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_writing_anchors_a_listed_heading(self):
        source = self.fixture()
        heading = self.run_helper(source, '--headings')
        self.assertEqual(json.loads(heading.stdout)[0]['headings'][0]['href'], 'Text/chapter.xhtml#section')
        with zipfile.ZipFile(source) as z:
            files = {i.filename: z.read(i.filename) for i in z.infolist()}
        files['OEBPS/Text/chapter.xhtml'] = files['OEBPS/Text/chapter.xhtml'].replace(b'</body>', b'<h2>Late Section</h2></body>')
        source.unlink()
        with zipfile.ZipFile(source, 'w') as z:
            for name, content in files.items():
                z.writestr(name, content)
        listed = json.loads(self.run_helper(source, '--headings').stdout)[0]['headings'][1]
        self.assertEqual(listed['href'], 'Text/chapter.xhtml#toc-late-section')
        self.plan[0]['children'].append({'title': 'Late', 'href': listed['href']})
        self.plan_path.write_text(json.dumps(self.plan))
        output = self.base / 'output.epub'
        result = self.run_helper(source, '--from', self.plan_path, '-o', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(output) as z:
            self.assertIn(b'<h2 id="toc-late-section">Late Section</h2>', z.read('OEBPS/Text/chapter.xhtml'))
        shallow = json.loads(self.run_helper(output, '--depth', '1').stdout)
        self.assertEqual(shallow, [{'title': 'Part', 'href': 'Text/chapter.xhtml', 'children': []}])

    def test_bad_fragment_rejected_without_output(self):
        source = self.fixture()
        self.plan[0]['href'] = 'Text/chapter.xhtml#absent'
        self.plan_path.write_text(json.dumps(self.plan))
        output = self.base / 'output.epub'
        result = self.run_helper(source, '--from', self.plan_path, '-o', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing fragment', result.stderr)
        self.assertFalse(output.exists())

    def test_dry_run_and_overwrite_refusal(self):
        source = self.fixture()
        before = source.read_bytes()
        result = self.run_helper(source, '--from', self.plan_path, '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.plan)
        result = self.run_helper(source, '--from', self.plan_path, '-o', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
