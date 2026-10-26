"""The packaged EPUB → PDF helper must prepare the book Calibre converts: one file per
chapter, notes linked both ways, and the reviewed tree in the navigation."""
import importlib.util
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'skill/references/epub_to_pdf.py'
spec = importlib.util.spec_from_file_location('epub_to_pdf_skill', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

BREAK = '<div style="page-break-before: always;"/>'
FILES = {
    'part.html': '<p style="text-align: center">Part One</p>' + BREAK,
    'label.html': '<p style="text-align: center">CHAPTER 1</p>' + BREAK,
    'ch1.html': '<h2>Disks</h2><p>Drives shrank from 8 to 5,25 inches (see Figure 1.7) as analysts1 noted.</p>'
                '<p>Three steps:</p><p>1. Measure.</p><p>2. Compare.</p><p>Then decide.2</p>' + BREAK,
    'ch1-s1.html': '<h2 id="top">Summary</h2><p>Back to <a href="ch1.html">the start</a>.</p>'
                   '<p>1. First note.</p><p>2. Second note.</p>' + BREAK,
    'ch2.html': '<h2>Ending</h2><p>No sections here, but a call3 all the same.</p><p>3. Third note.</p>',
}
TREE = [{'title': 'Part One', 'href': 'Text/part.html', 'children': [
    {'title': 'Chapter 1. Disks', 'href': 'Text/ch1.html', 'children': [
        {'title': 'Summary', 'href': 'Text/ch1-s1.html#top'}]},
    {'title': 'Chapter 2. Ending', 'href': 'Text/ch2.html'}]}]


class EpubToPdfSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / 'book.epub'
        self.build(FILES)
        self.toc = self.base / 'toc.json'
        self.toc.write_text(json.dumps(TREE))

    def build(self, files):
        self.source.unlink(missing_ok=True)
        items = ''.join('<item id="f%d" href="Text/%s" media-type="application/xhtml+xml"/>' % (i, n)
                        for i, n in enumerate(files))
        refs = ''.join('<itemref idref="f%d"/>' % i for i in range(len(files)))
        flat = ''.join('<navPoint id="n%d"><navLabel><text>%s</text></navLabel><content src="Text/%s"/></navPoint>'
                       % (i, n, n) for i, n in enumerate(files))
        with zipfile.ZipFile(self.source, 'w') as z:
            z.writestr('mimetype', 'application/epub+zip')
            z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
            z.writestr('OEBPS/content.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><metadata/>'
                       '<manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>%s</manifest>'
                       '<spine toc="ncx">%s</spine></package>' % (items, refs))
            z.writestr('OEBPS/toc.ncx', '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><head/><navMap>%s</navMap></ncx>' % flat)
            for name, body in files.items():
                z.writestr('OEBPS/Text/' + name, '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
                           '<body>%s</body></html>' % body)

    def prepare(self):
        before = self.source.read_bytes()
        output = self.base / 'prepared.epub'
        report = helper.prepare(self.source, output, self.toc)
        self.assertEqual(self.source.read_bytes(), before)
        return report, zipfile.ZipFile(output)

    def doc(self, z, name):
        return z.read('OEBPS/Text/' + name).decode()

    def test_chapters_start_files_and_sections_join_them(self):
        report, z = self.prepare()
        self.assertTrue(report.startswith('2 files merged'), report)
        self.assertEqual(z.infolist()[0].filename, 'mimetype')
        texts = sorted(n.rsplit('/', 1)[-1] for n in z.namelist() if n.startswith('OEBPS/Text/'))
        # The unreferenced label page joins the chapter it announces, not the part;
        # chapter 2 has no sections but is a sibling of one that does.
        self.assertEqual(texts, ['ch2.html', 'label.html', 'part.html'])
        opf = z.read('OEBPS/content.opf').decode()
        self.assertEqual(re.findall(r'href="Text/([^"]+)"', opf), ['part.html', 'label.html', 'ch2.html'])
        merged = self.doc(z, 'label.html')
        self.assertNotIn('page-break-before', merged)
        self.assertIn('href="label.html#_merged_2"', merged)  # the in-book link follows its target
        self.assertIn('page-break-before', self.doc(z, 'part.html'))  # untouched: it absorbed nothing

    def test_reviewed_tree_reaches_the_navigation(self):
        _, z = self.prepare()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'out.epub'
            path.write_bytes(Path(z.filename).read_bytes())
            with zipfile.ZipFile(path) as archive:
                tree = helper.epub_toc.read_tree(helper.epub_toc.Book(archive))
        self.assertEqual([n['title'] for n in helper.epub_toc.walk(tree)],
                         ['Part One', 'Chapter 1. Disks', 'Summary', 'Chapter 2. Ending'])
        self.assertEqual(tree[0]['children'][0]['href'], 'Text/label.html#_merged_2')
        self.assertEqual(tree[0]['children'][0]['children'][0]['href'], 'Text/label.html#top')

    def test_notes_are_linked_both_ways_without_false_calls(self):
        report, z = self.prepare()
        self.assertTrue(report.endswith('3 of 3 notes linked'), report)
        chapter = self.doc(z, 'label.html')
        self.assertIn('analysts<sup class="note-call"><a id="call-1-1" href="#note-1-1">1</a></sup> noted', chapter)
        self.assertIn('decide.<sup class="note-call"><a id="call-1-2" href="#note-1-2">2</a></sup>', chapter)
        self.assertIn('5,25 inches (see Figure 1.7)', chapter)
        self.assertIn('<p>1. Measure.</p>', chapter)  # a numbered list in the body is not a note
        self.assertIn('id="note-1-1" class="note note-first"><a class="note-number" href="#call-1-1">1.</a> First', chapter)
        self.assertIn('href="#call-4-3">3.</a>', self.doc(z, 'ch2.html'))

    def test_notes_without_calls_are_left_alone(self):
        self.build(dict(FILES, **{'ch1.html': FILES['ch1.html'].replace('analysts1', 'analysts').replace('decide.2', 'decide.')}))
        report, z = self.prepare()
        # Chapter 1 is rejected, so chapter 2's run, starting at 3, continues nothing.
        self.assertTrue(report.endswith('0 of 0 notes linked'), report)
        self.assertNotIn('note-number', self.doc(z, 'label.html'))

    def test_contents_page_is_rebuilt_from_the_tree(self):
        doc = ET.fromstring('<html xmlns="http://www.w3.org/1999/xhtml"><body><h2>Contents</h2>'
                            '<p><a href="part.html">Part One</a></p><p><a href="ch2.html">Chapter 2</a></p>'
                            '<p>Not a link list.</p></body></html>')
        helper.rebuild_contents(doc, TREE, 'OEBPS/Text/contents.html', 'OEBPS')
        out = ET.tostring(doc, encoding='unicode')
        self.assertEqual(out.count('class="toc-item'), 4)
        self.assertIn('toc-level-2', out)
        self.assertIn('Not a link list.', out)


if __name__ == '__main__':
    unittest.main()
