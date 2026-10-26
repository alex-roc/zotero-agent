#!/usr/bin/env python3
"""Convert an EPUB to a paginated PDF with Calibre, keeping a reviewed outline.

python3 epub_to_pdf.py book.epub --toc toc.json -o book.pdf
python3 epub_to_pdf.py book.epub --toc toc.json --depth 2 --profile tablet -o book.pdf
python3 epub_to_pdf.py book.epub --toc toc.json --prepare-only prepared.epub

Calibre converts a temporary copy, prepared so that:
- the tree from --toc (JSON as written by epub_toc.py, headings from its
  --headings included; default: the EPUB's own navigation), cut to --depth
  levels, fills the NCX/nav, and so becomes the PDF outline;
- each chapter's spine files are merged, since Calibre starts every file on a page;
- notes typed as plain text (a digit glued to a word, "8. ..." paragraphs closing
  the chapter) become superscript calls linked both ways;
- a visible contents page made of one-link paragraphs is rebuilt from the tree;
- Liberation Serif, which ships with Calibre, is embedded.

Profiles: a4 (A4, 14.4 pt type, 72 pt margins) and tablet (A5, 12 pt, 32 pt).
Width/height in millimetres; type and margins in points. Never edits the input.
"""
import argparse
import copy
import html
import importlib.util
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

_spec = importlib.util.spec_from_file_location('epub_toc', Path(__file__).with_name('epub_toc.py'))
epub_toc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(epub_toc)

OPF = '{http://www.idpf.org/2007/opf}'
PROFILES = {'a4': (210, 297, 14.4, 72), 'tablet': (148, 210, 12, 32)}
FOOTERS = {'es': 'Página {page}', 'pt': 'Página {page}', 'it': 'Pagina {page}', 'de': 'Seite {page}'}
CONTENTS_HEADINGS = ('índice', 'indice', 'índice general', 'contenido', 'contenidos', 'sumario',
                     'contents', 'table of contents')
FORCED_BREAK = re.compile(r'(?:page-)?break-(?:before|after)\s*:\s*(?:always|page|left|right|recto|verso)'
                          r'\s*(?:!important\s*)?;?', re.IGNORECASE)
# A note call is glued to a word or to the punctuation closing it ("análisis8.",
# "previos.17 De", "”.12"), never to a digit, so "1.7" and "5,25" are not calls.
CALL_BEFORE = r'(?:(?<=[^\W\d_])|(?<=[^\W\d_][.,;:!?”’»)\]])|(?<=[”’»)\]][.,;:]))'
NO_CALLS = ('a', 'sup', 'sub', 'script', 'style')
LABEL_CHARS = 40

CSS = '''
body { margin: 0 !important; padding: 0 !important; font-family: "FAMILY", serif !important; font-size: SIZEpt; line-height: 1.4; color: #171717; }
body > br, div.epub-merged > br { display: none; }
p { font-size: SIZEpt; line-height: 1.4; text-align: justify !important; text-indent: 1.5em !important; margin: 0 !important; orphans: 3; widows: 3; }
p[style*="text-align: center"], p[style*="text-align:center"] { text-align: center !important; text-indent: 0 !important; }
h1,h2,h3,h4,h5,h6 { font-family: "FAMILY", serif !important; text-align: left; line-height: 1.22; page-break-after: avoid; margin: 1.3em 0 0.7em 0; text-indent: 0; }
h1 { font-size: 22pt; } h2 { font-size: 19pt; } h3 { font-size: 16pt; } h4 { font-size: 14.5pt; } h5,h6 { font-size: 13pt; }
img { max-width: 100% !important; height: auto !important; object-fit: contain; }
table { width: 100% !important; max-width: 100% !important; table-layout: auto !important; font-size: 10pt; border-collapse: collapse; }
table,td,th { white-space: normal !important; overflow-wrap: anywhere; }
td,th { padding: 0.3em; }
a { color: inherit; text-decoration: none; }
sup.note-call { font-size: 0.68em; line-height: 0; vertical-align: super; }
p.note { font-size: NOTEpt !important; text-indent: 0 !important; margin: 0 0 0.35em 0 !important; }
p.note-first { margin-top: 1.6em !important; }
a.note-number { font-weight: bold; }
div.toc-tree ol { list-style: none !important; margin: 0 !important; padding: 0 !important; }
div.toc-tree ol ol { margin-left: 1.3em !important; }
div.toc-tree li { margin: 0 !important; padding: 0 !important; }
p.toc-item { page-break-inside: avoid !important; break-inside: avoid !important; font-size: TOCpt !important; text-align: left !important; text-indent: 0 !important; line-height: 1.28 !important; margin: 0 0 0.4em 0 !important; }
p.toc-level-0 { font-weight: bold; margin-top: 0.7em !important; }
p.toc-level-0.toc-parent { font-size: SIZEpt !important; margin-top: 1.2em !important; }
p.toc-level-1.toc-parent { font-weight: bold; margin-top: 0.8em !important; }
p.toc-parent { page-break-after: avoid !important; }
'''


def local(node):
    return node.tag.rsplit('}', 1)[-1] if isinstance(node.tag, str) else ''


def namespace(node):
    return node.tag.split('}')[0] + '}' if '}' in node.tag else ''


def merge_chapters(docs, spine, tree, opf_dir, keep_apart=()):
    """Merge each chapter's spine files into its first one.

    A page starts at every top-level entry, and at every entry with children in
    other files, and at its siblings (so a chapter without sections still starts
    one), unless the entry stays in its parent's file: headings inside a file never
    start a page. `"break": true/false` on an entry overrides this for its file.
    Everything else joins the file before it, except a short label page no entry
    points to ("CAPÍTULO 2"), which joins the chapter it announces. Rewrites links,
    paths and the tree's hrefs to the merged files. Returns the absorbed files and
    the titles of the entries that start a page.
    """
    def target(href):
        return posixpath.normpath(posixpath.join(opf_dir, unquote(href.partition('#')[0])))
    starts, referenced, vetoed, titles = set(), set(), set(), []
    def mark(nodes, parent):
        branch = parent is None or any(target(child['href']) != target(node['href'])
                                       for node in nodes for child in node.get('children') or [])
        for node in nodes:
            referenced.add(target(node['href']))
            if node.get('break', branch and (parent is None or target(node['href']) != target(parent['href']))):
                starts.add(target(node['href']))
                titles.append(node['title'])
            elif node.get('break') is False:
                vetoed.add(target(node['href']))
            mark(node.get('children') or [], node)
    mark(tree, None)
    starts -= vetoed
    for name in keep_apart:
        if name in spine:
            starts.add(name)
            if spine.index(name) + 1 < len(spine):
                starts.add(spine[spine.index(name) + 1])
    for name, following in zip(spine, spine[1:], strict=False):
        if (name not in referenced and following in starts and not docs[name].findall('.//{*}img')
                and following not in vetoed and len(epub_toc.text(docs[name].find('{*}body'))) <= LABEL_CHARS):
            starts.discard(following)
            starts.add(name)
    host, current = {}, None
    for name in spine:
        if current is None or name in starts:
            current = name
        host[name] = current
    anchors = {name: '_merged_%d' % i for i, name in enumerate(spine) if host[name] != name}
    # ids must stay unique inside the file that receives them.
    taken, renamed = {}, {}
    for name in spine:
        used = taken.setdefault(host[name], set())
        if name in anchors:
            used.add(anchors[name])
        for node in docs[name].iter():
            value = node.get('id')
            if value is None:
                continue
            new, n = value, 1
            while new in used:
                new, n = '%s-%d' % (value, n), n + 1
            node.set('id', new)
            renamed[(name, value)] = new
            used.add(new)

    def translate(ref, origin, folder, final_folder):
        url = urlsplit(ref)
        if url.scheme or url.netloc:
            return ref
        goal = posixpath.normpath(posixpath.join(folder, unquote(url.path))) if url.path else origin
        fragment = unquote(url.fragment)
        if goal in host:
            if fragment:
                fragment = renamed.get((goal, fragment), fragment)
            elif goal in anchors:
                fragment = anchors[goal]
            goal = host[goal]
        return quote(posixpath.relpath(goal, final_folder)) + ('#' + quote(fragment) if fragment else '')

    for name, doc in docs.items():
        folder, final = posixpath.dirname(name), posixpath.dirname(host.get(name, name))
        for node in doc.iter():
            for attribute in ('href', 'src', '{http://www.w3.org/1999/xlink}href'):
                if node.get(attribute):
                    node.set(attribute, translate(node.get(attribute), name, folder, final))
    for node in epub_toc.walk(tree):
        node['href'] = translate(node['href'], None, opf_dir, opf_dir)

    absorbed = []
    for name in spine:
        if name not in anchors:
            continue
        doc, receiver = docs.pop(name), docs[host[name]]
        body = doc.find('{*}body')
        block = ET.SubElement(receiver.find('{*}body'), namespace(body) + 'div',
                              {'id': anchors[name], 'class': 'epub-merged'})
        block.text = body.text
        block.extend(list(body))
        head, receiver_head = doc.find('{*}head'), receiver.find('{*}head')
        if head is not None and receiver_head is not None:
            sheets = {x.get('href') for x in receiver_head if local(x) == 'link'}
            for x in head:
                if local(x) == 'style' or (local(x) == 'link' and x.get('href') not in sheets):
                    receiver_head.append(x)
        absorbed.append(name)
    # Files often end with their own forced break; inside a merged chapter it would
    # now split sections instead of files.
    for name in {host[x] for x in absorbed}:
        for node in docs[name].iter():
            style = node.get('style')
            if style and 'break' in style:
                node.set('style', FORCED_BREAK.sub('', style).strip())
    return absorbed, titles


def link_notes(docs, spine):
    """Link plain-text notes both ways; return (notes found, calls linked).

    Only a consecutive run of "N. ..." paragraphs that closes a file and starts at 1
    or continues the previous run counts as notes: numbered lists in the body look
    the same. Calls are searched in order; a file where fewer than half are found
    is left untouched. Multi-paragraph notes end the run early.
    """
    expected, notes, linked = 1, 0, 0
    for index, name in enumerate(spine):
        if name not in docs:
            continue
        doc = docs[name]
        run = []
        for p in reversed([p for p in doc.iter() if local(p) == 'p' and epub_toc.text(p)]):
            m = re.match(r'(\d{1,3})\.\s', epub_toc.text(p))
            if not m or (run and int(m.group(1)) != run[-1][0] - 1):
                break
            run.append((int(m.group(1)), p))
        run.reverse()
        if not run or run[0][0] not in (1, expected):
            continue
        backup = copy.deepcopy(doc)
        first = run[0][1]
        ns = namespace(first)
        slots = []  # (node, 'text' | 'tail', parent) in reading order, up to the notes
        def visit(node, first=first, slots=slots):
            if node is first:
                return True
            if local(node) not in NO_CALLS:
                slots.append((node, 'text', None))
                for child in list(node):
                    if visit(child):
                        return True
                    slots.append((child, 'tail', node))
            return False
        visit(doc.find('{*}body'))
        found, start = set(), 0
        for number, _ in run:
            pattern = re.compile(CALL_BEFORE + str(number) + r'(?!\d)(?![.,]\d)')
            for j in range(start, len(slots)):
                node, which, parent = slots[j]
                value = getattr(node, which) or ''
                m = pattern.search(value)
                if not m:
                    continue
                sup = ET.Element(ns + 'sup', {'class': 'note-call'})
                ET.SubElement(sup, ns + 'a', {'id': 'call-%d-%d' % (index, number),
                                              'href': '#note-%d-%d' % (index, number)}).text = str(number)
                sup.tail = value[m.end():]
                setattr(node, which, value[:m.start()])
                if which == 'text':
                    node.insert(0, sup)
                    slots[j] = (sup, 'tail', node)
                else:
                    parent.insert(list(parent).index(node) + 1, sup)
                    slots[j] = (sup, 'tail', parent)
                found.add(number)
                start = j
                break
        if len(found) * 2 < len(run):
            docs[name] = backup
            continue
        for number, p in run:
            p.set('id', 'note-%d-%d' % (index, number))
            p.set('class', (p.get('class', '') + ' note' + (' note-first' if p is first else '')).strip())
            m = re.match(r'\s*%d\.' % number, p.text or '')
            if number in found and m:
                back = ET.Element(ns + 'a', {'class': 'note-number', 'href': '#call-%d-%d' % (index, number)})
                back.text, back.tail = '%d.' % number, p.text[m.end():]
                p.text = p.text[:m.start()]
                p.insert(0, back)
        expected = run[-1][0] + 1
        notes += len(run)
        linked += len(found)
    return notes, linked


def rebuild_contents(doc, tree, name, opf_dir):
    """Replace a visible contents list of one-link paragraphs with the reviewed tree."""
    for parent in list(doc.iter()):
        children = list(parent)
        for i, heading in enumerate(children):
            if local(heading) not in ('h1', 'h2', 'h3', 'h4') or epub_toc.text(heading).casefold() not in CONTENTS_HEADINGS:
                continue
            old = []
            for node in children[i + 1:]:
                if local(node) == 'br':
                    old.append(node)
                    continue
                links = [x for x in node.iter() if local(x) == 'a']
                if local(node) != 'p' or len(links) != 1 or epub_toc.text(node) != epub_toc.text(links[0]):
                    break
                old.append(node)
            if not any(local(x) == 'p' for x in old):
                continue
            ns = namespace(heading)
            box = ET.Element(ns + 'div', {'class': 'toc-tree'})
            def add(container, entries, level, ns=ns):
                ol = ET.SubElement(container, ns + 'ol')
                for entry in entries:
                    if entry['title'].casefold() in ('cover', 'cover page', 'portada'):
                        continue
                    li = ET.SubElement(ol, ns + 'li')
                    kids = entry.get('children') or []
                    p = ET.SubElement(li, ns + 'p', {'class': 'toc-item toc-level-%d' % level + (' toc-parent' if kids else '')})
                    path, hash_, fragment = entry['href'].partition('#')
                    path = posixpath.relpath(posixpath.normpath(posixpath.join(opf_dir, unquote(path))), posixpath.dirname(name))
                    ET.SubElement(p, ns + 'a', {'href': quote(path) + hash_ + fragment}).text = entry['title']
                    if kids:
                        add(li, kids, level + 1)
            add(box, tree, 0)
            for node in old:
                parent.remove(node)
            parent.insert(list(parent).index(heading) + 1, box)
            return


def prepare(epub, output, toc=None, font_dir=None, depth=None):
    """Write the EPUB that Calibre converts; return a report."""
    with zipfile.ZipFile(epub) as archive:
        book = epub_toc.Book(archive)
        if toc is not None:
            tree = json.loads(Path(toc).read_text(encoding='utf-8'))
        else:
            tree = epub_toc.read_tree(book)
            if not any(node.get('children') for node in tree):
                print('Warning: the navigation is flat, so the PDF outline will be too. '
                      'Review a tree with epub_toc.py and pass it with --toc.', file=sys.stderr)
        epub_toc.validate(tree, archive, book.opf_dir)
        package = book.package
        manifest, spine_element = package.find(OPF + 'manifest'), package.find(OPF + 'spine')
        by_id = {item.get('id'): item for item in manifest}
        sources = {book.path(item.get('href')): archive.read(book.path(item.get('href')))
                   for item in manifest if item.get('media-type') == 'application/xhtml+xml'}
        docs = {name: ET.fromstring(data) for name, data in sources.items()}
        spine = [book.path(by_id[ref.get('idref')].get('href')) for ref in spine_element]
        spine = [name for name in spine if name in docs]
        for name in book.documents:
            if name in docs:  # an EPUB 3 nav is also an XHTML document: share one tree
                book.documents[name] = docs[name]
        epub_toc.anchor_headings(tree, docs, book.opf_dir)
        absorbed, starts = merge_chapters(docs, spine, tree, book.opf_dir, keep_apart=book.documents)
        tree = epub_toc.prune(tree, depth)
        for item in list(manifest):
            if book.path(item.get('href')) in absorbed:
                manifest.remove(item)
                spine_element.remove(next(x for x in spine_element if x.get('idref') == item.get('id')))
        notes, linked = link_notes(docs, spine)
        changes = {}
        if font_dir:
            folder = posixpath.join(book.opf_dir, '_epub_to_pdf_fonts')
            rules = []
            for suffix, weight, style in (('Regular', 'normal', 'normal'), ('Bold', 'bold', 'normal'),
                                          ('Italic', 'normal', 'italic'), ('BoldItalic', 'bold', 'italic')):
                file = 'LiberationSerif-%s.ttf' % suffix
                changes[posixpath.join(folder, file)] = (Path(font_dir) / file).read_bytes()
                ET.SubElement(manifest, OPF + 'item', {'id': '_epub_to_pdf_font_' + suffix, 'href': '_epub_to_pdf_fonts/' + file,
                                                      'media-type': 'application/vnd.ms-opentype'})
                rules.append('@font-face { font-family: "Liberation Serif"; src: url("%s"); font-weight: %s; font-style: %s; }'
                             % (file, weight, style))
            sheet = posixpath.join(folder, 'fonts.css')
            changes[sheet] = '\n'.join(rules).encode('utf-8')
            ET.SubElement(manifest, OPF + 'item', {'id': '_epub_to_pdf_fonts', 'href': '_epub_to_pdf_fonts/fonts.css',
                                                  'media-type': 'text/css'})
        for name, doc in docs.items():
            rebuild_contents(doc, tree, name, book.opf_dir)
            head = doc.find('{*}head')
            if font_dir and head is not None:
                ET.SubElement(head, namespace(head) + 'link', {'rel': 'stylesheet', 'type': 'text/css',
                              'href': quote(posixpath.relpath(sheet, posixpath.dirname(name)))})
            changes[name] = epub_toc.serialize(doc, sources[name])
        opf = epub_toc.serialize(package, archive.read(book.opf_name))
        changes[book.opf_name] = opf
        changes.update(epub_toc.apply_tree(archive, book, tree, opf=opf))
        epub_toc.write_epub(archive, changes, Path(output), removed=set(absorbed))
    return ('%d files merged into their chapters; %d of %d notes linked; %d entries start a page:\n  %s'
            % (len(absorbed), linked, notes, len(starts), '\n  '.join(starts)))


def find_calibre(given):
    calibre = given or shutil.which('ebook-convert')
    candidate = Path('/Applications/calibre.app/Contents/MacOS/ebook-convert')
    if not calibre and candidate.is_file():
        calibre = str(candidate)
    return calibre


def language(epub):
    with zipfile.ZipFile(epub) as archive:
        node = epub_toc.Book(archive).package.find('.//{http://purl.org/dc/elements/1.1/}language')
    return (epub_toc.text(node) if node is not None else '').split('-')[0].lower()


def positive(value):
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be greater than zero')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('epub', type=Path)
    parser.add_argument('-o', '--output', type=Path, help='default: next to the EPUB, same name, .pdf')
    parser.add_argument('--toc', type=Path, help='reviewed JSON tree (epub_toc.py format)')
    parser.add_argument('--depth', type=int, help='outline and contents levels to keep (default: all)')
    parser.add_argument('--profile', choices=sorted(PROFILES), default='a4')
    parser.add_argument('--width', type=positive)
    parser.add_argument('--height', type=positive)
    parser.add_argument('--font-size', type=positive, help='points; overrides the profile')
    parser.add_argument('--margin', type=positive, help='points; overrides the profile')
    parser.add_argument('--font', default='Liberation Serif', help='an installed family; the default is embedded from Calibre')
    parser.add_argument('--language', help="the book's language (es, en…) when its metadata is wrong; also picks the footer")
    parser.add_argument('--footer', help='footer text, {page} is the page number; "" for none (default: by book language)')
    parser.add_argument('--calibre', help='path to ebook-convert')
    parser.add_argument('--prepare-only', type=Path, metavar='EPUB', help='write the prepared EPUB here and stop')
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    for key, value in zip(('width', 'height', 'font_size', 'margin'), PROFILES[args.profile], strict=True):
        if getattr(args, key) is None:
            setattr(args, key, value)
    source = args.epub.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.epub':
        parser.error('the input must be an existing .epub')
    if args.depth is not None and args.depth < 1:
        parser.error('--depth must be at least 1')
    if not 6 <= args.font_size <= 40:
        parser.error('--font-size must be between 6 and 40 points')
    if args.margin * 2 >= min(args.width, args.height) * 72 / 25.4:
        parser.error('the margins leave no room for the text')
    calibre = find_calibre(args.calibre)
    font_dir = None
    if args.font == 'Liberation Serif':
        font_dir = Path(calibre).resolve().parent.parent / 'Resources/resources/fonts/liberation' if calibre else None
        if not font_dir or not (font_dir / 'LiberationSerif-Regular.ttf').is_file():
            parser.error("Calibre's Liberation fonts were not found; pass --font with an installed family")
    if args.prepare_only:
        if args.prepare_only.exists():
            parser.error('the prepared EPUB must be a new file')
        print(prepare(source, args.prepare_only, args.toc, font_dir, args.depth), file=sys.stderr)
        print(args.prepare_only)
        return
    if not calibre:
        parser.error('Calibre not found: install it or pass --calibre /path/to/ebook-convert')
    output = (args.output.expanduser().resolve() if args.output else source.with_suffix('.pdf'))
    if output.suffix.lower() != '.pdf':
        parser.error('the output must be a .pdf')
    if output.exists() and not args.overwrite:
        parser.error('the output exists; pass --overwrite to replace it')
    footer = args.footer if args.footer is not None else FOOTERS.get(args.language or language(source), 'Page {page}')
    css = (CSS.replace('FAMILY', args.font).replace('NOTE', '%g' % round(args.font_size * 0.85, 2))
           .replace('TOC', '%g' % round(args.font_size * 0.92, 2)).replace('SIZE', '%g' % args.font_size))
    output.parent.mkdir(parents=True, exist_ok=True)
    # The temporary PDF lives on the output's volume so it can be published atomically.
    with tempfile.TemporaryDirectory(prefix='.epub-to-pdf-', dir=output.parent) as work:
        work = Path(work)
        (work / 'extra.css').write_text(css, encoding='utf-8')
        prepared, pdf = work / 'prepared.epub', work / 'book.pdf'
        print(prepare(source, prepared, args.toc, font_dir, args.depth), file=sys.stderr)
        command = [calibre, str(prepared), str(pdf), '--unit', 'millimeter',
                   '--custom-size', '%gx%g' % (args.width, args.height),
                   '--pdf-page-margin-left', str(args.margin), '--pdf-page-margin-right', str(args.margin),
                   '--pdf-page-margin-top', str(args.margin), '--pdf-page-margin-bottom', str(args.margin),
                   '--pdf-serif-family', args.font, '--pdf-default-font-size', str(round(args.font_size * 96 / 72)),
                   '--disable-font-rescaling', '--minimum-line-height', '140', '--extra-css', str(work / 'extra.css'),
                   '--pdf-page-number-map', 'n + 1', '--preserve-cover-aspect-ratio',
                   # No structure detection: chapters already start their own files, and the
                   # default break before every h1/h2 would split the merged sections again.
                   '--chapter', '/', '--page-breaks-before', '/']
        if args.language:
            command += ['--language', args.language]
        if footer:
            text = html.escape(footer).replace('{page}', '_PAGENUM_')
            command += ['--pdf-footer-template', '<footer><div style="margin:auto; font-family: &quot;%s&quot;, serif; '
                        'font-size:%gpt">%s</div></footer>' % (html.escape(args.font), args.font_size, text)]
        subprocess.run(command, check=True, stdout=sys.stderr)
        with pdf.open('rb') as handle:
            if handle.read(5) != b'%PDF-':
                raise RuntimeError('Calibre did not produce a PDF')
        if output.exists() and not args.overwrite:
            raise FileExistsError('the output was created meanwhile: %s' % output)
        os.replace(pdf, output)
    print(output)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, RuntimeError, ET.ParseError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
