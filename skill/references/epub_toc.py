#!/usr/bin/env python3
"""Inspect or write an EPUB navigation tree. Python stdlib; never edits the input.

python3 epub_toc.py book.epub > toc.json
python3 epub_toc.py book.epub --headings > headings.json
python3 epub_toc.py book.epub --from toc.json --dry-run
python3 epub_toc.py book.epub --from toc.json [--depth 2] -o book-with-toc.epub

JSON: [{"title": "Part I", "href": "Text/part.xhtml", "children": [...]}]
All hrefs are relative to the OPF directory, with optional #fragment. --headings
lists every heading per spine file with an href to use in the tree: its own id,
or a proposed one ("#toc-...") that writing the tree adds to that heading.
--depth keeps only the first N levels of the tree written or printed.
"""
import argparse
import io
import json
import os
import posixpath
import re
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.sax.saxutils import quoteattr

OPF = 'http://www.idpf.org/2007/opf'
XHTML = 'http://www.w3.org/1999/xhtml'
EPUB = 'http://www.idpf.org/2007/ops'
NCX = 'http://www.daisy.org/z3986/2005/ncx/'
XML_ID = '{http://www.w3.org/XML/1998/namespace}id'
HEADINGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')


def text(element):
    return ' '.join(''.join(element.itertext()).split())


def prune(nodes, depth):
    """A copy of the tree keeping only its first `depth` levels (None keeps all)."""
    if depth is None:
        return nodes
    return [dict(node, children=prune(node.get('children') or [], depth - 1) if depth > 1 else [])
            for node in nodes]


def headings(root):
    """(element, level, title, id) for every heading of a content document. A
    heading without an id gets a stable proposal, unique in the file, which
    anchor_headings() writes when a tree points at it."""
    taken = {e.get('id') or e.get(XML_ID) for e in root.iter()} - {None}
    found = []
    for element in root.iter():
        tag = element.tag.rsplit('}', 1)[-1] if isinstance(element.tag, str) else ''
        title = text(element) if tag in HEADINGS else ''
        if not title:
            continue
        ident = element.get('id') or element.get(XML_ID)
        if not ident:
            ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
            base = 'toc-' + (re.sub(r'[^a-z0-9]+', '-', ascii_title.lower()).strip('-')[:48] or 'heading')
            ident, n = base, 2
            while ident in taken:
                ident, n = '%s-%d' % (base, n), n + 1
            taken.add(ident)
        found.append((element, int(tag[1]), title, ident))
    return found


def anchor_headings(nodes, docs, opf_dir):
    """Add the proposed ids that `nodes` point at; return the documents changed."""
    proposals, changed = {}, set()
    for node in walk(nodes):
        url = urlsplit(node['href'])
        name = posixpath.normpath(posixpath.join(opf_dir, unquote(url.path)))
        if not url.fragment or name not in docs:
            continue
        if name not in proposals:
            proposals[name] = {ident: element for element, _, _, ident in headings(docs[name])}
        element = proposals[name].get(unquote(url.fragment))
        if element is not None and not (element.get('id') or element.get(XML_ID)):
            element.set('id', unquote(url.fragment))
            changed.add(name)
    return changed


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get('children', []))


def rebase(href, origin, destination):
    url = urlsplit(href)
    if url.scheme or url.netloc or url.query:
        raise ValueError('Navigation targets must be local EPUB paths: ' + href)
    target = posixpath.normpath(posixpath.join(origin, unquote(url.path)))
    relative = quote(posixpath.relpath(target, destination), safe='/')
    return relative + ('#' + url.fragment if url.fragment else '')


def serialize(root, source):
    # ElementTree invents prefixes (ns0:package, html:nav ns1:type); readers that match
    # `epub:type` or an unprefixed root literally then miss the navigation. Reuse the
    # document's own prefixes.
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(source), events=('start-ns',)):
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:  # an `ns0`-style prefix; ElementTree's own naming applies
            pass
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def register_item(opf, attrs, spine_toc=None):
    # Patch the package as text: re-serializing it would rename its prefixes and drop
    # comments, and the default and `opf:` prefixes often share one namespace.
    manifest = re.search(rb'</([\w.-]+:)?manifest\s*>', opf)
    prefix = manifest.group(1) or b''
    item = '<%sitem %s/>' % (prefix.decode(), ' '.join('%s=%s' % (k, quoteattr(v)) for k, v in attrs.items()))
    opf = opf[:manifest.start()] + item.encode() + opf[manifest.start():]
    if spine_toc:
        def retarget(match):
            tag = re.sub(rb'\s+toc\s*=\s*("[^"]*"|\'[^\']*\')', b'', match.group(0))
            return re.sub(rb'^(<(?:[\w.-]+:)?spine)', rb'\1 toc="' + spine_toc.encode() + b'"', tag)
        opf = re.sub(rb'<(?:[\w.-]+:)?spine\b[^>]*>', retarget, opf, count=1)
    return opf


def toc_nav(root):
    for node in root.iter('{%s}nav' % XHTML):
        if 'toc' in node.get('{%s}type' % EPUB, '').split() or node.get('role') == 'doc-toc':
            return node
    raise ValueError('The EPUB navigation document has no toc nav element')


def read_ncx(root, origin, opf_dir):
    def read(parent):
        return [{'title': text(p.find('{*}navLabel/{*}text')),
                 'href': rebase(p.find('{*}content').get('src'), origin, opf_dir),
                 'children': read(p)} for p in parent.findall('{*}navPoint')]
    return read(root.find('{*}navMap'))


def read_nav(root, origin, opf_dir):
    def read(ol):
        nodes = []
        for li in ol.findall('{*}li'):
            label = li.find('{*}a')
            if label is None:
                raise ValueError('A nav grouping has no link; supply an explicit reviewed JSON plan')
            nested = li.find('{*}ol')
            nodes.append({'title': text(label), 'href': rebase(label.get('href'), origin, opf_dir),
                          'children': read(nested) if nested is not None else []})
        return nodes
    ol = toc_nav(root).find('{*}ol')
    if ol is None:
        raise ValueError('The toc nav element has no list; supply a reviewed JSON plan')
    return read(ol)


def validate(nodes, archive, opf_dir):
    if not isinstance(nodes, list) or not nodes:
        raise ValueError('Expected a non-empty JSON array of entries')
    cache = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get('title'), str) or not node['title'].strip():
            raise ValueError('Every entry needs a non-empty title')
        if not isinstance(node.get('href'), str) or not node['href']:
            raise ValueError('Every entry needs an href')
        href = node['href']
        rebase(href, opf_dir, opf_dir)
        url = urlsplit(href)
        target = posixpath.normpath(posixpath.join(opf_dir, unquote(url.path)))
        if target.startswith('../') or target.startswith('/') or target not in archive.namelist():
            raise ValueError('Missing or unsafe navigation target: ' + href)
        if url.fragment:
            if target not in cache:
                data = archive.read(target)
                try:
                    root = ET.fromstring(data)
                    cache[target] = ({e.get('id') or e.get(XML_ID) for e in root.iter()}
                                     | {ident for _, _, _, ident in headings(root)})
                except ET.ParseError:  # e.g. &nbsp; without a DTD; the ids are still there
                    cache[target] = {m.decode('utf-8', 'replace') for m in
                                     re.findall(rb'\s(?:xml:)?id\s*=\s*["\']([^"\']+)', data)}
            if unquote(url.fragment) not in cache[target]:
                raise ValueError('Missing fragment: ' + href)
        if node.get('children'):
            validate(node['children'], archive, opf_dir)
        elif 'children' in node and not isinstance(node['children'], list):
            raise ValueError('children must be an array')


def write_ncx(root, nodes, opf_dir, directory):
    navmap = root.find('{*}navMap')
    if navmap is None:
        navmap = ET.SubElement(root, '{%s}navMap' % NCX)
    navmap.clear()
    count, depth = 0, 1
    def add(parent, entries, level):
        nonlocal count, depth
        depth = max(depth, level)
        for entry in entries:
            count += 1
            point = ET.SubElement(parent, '{%s}navPoint' % NCX, {'id': f'toc-{count}', 'playOrder': str(count)})
            ET.SubElement(ET.SubElement(point, '{%s}navLabel' % NCX), '{%s}text' % NCX).text = entry['title']
            ET.SubElement(point, '{%s}content' % NCX, {'src': rebase(entry['href'], opf_dir, directory)})
            if entry.get('children'):
                add(point, entry['children'], level + 1)
    add(navmap, nodes, 1)
    for meta in root.findall('.//{*}meta'):
        if meta.get('name') == 'dtb:depth':
            meta.set('content', str(depth))


def write_nav(root, nodes, opf_dir, directory):
    nav = toc_nav(root)
    old = nav.find('{*}ol')
    position = list(nav).index(old) if old is not None else len(nav)
    if old is not None:
        nav.remove(old)
    def add(parent, entries):
        ol = ET.SubElement(parent, '{%s}ol' % XHTML)
        for entry in entries:
            li = ET.SubElement(ol, '{%s}li' % XHTML)
            ET.SubElement(li, '{%s}a' % XHTML, {'href': rebase(entry['href'], opf_dir, directory)}).text = entry['title']
            if entry.get('children'):
                add(li, entry['children'])
        return ol
    container = ET.Element('container')
    nav.insert(position, add(container, nodes))


class Book:
    """The package and navigation documents of an open EPUB archive."""

    def __init__(self, archive):
        container = ET.fromstring(archive.read('META-INF/container.xml'))
        self.opf_name = container.find('.//{*}rootfile').get('full-path')
        self.opf_dir = posixpath.dirname(self.opf_name)
        self.package = ET.fromstring(archive.read(self.opf_name))
        self.documents, self.kinds, self.sources = {}, {}, {}
        for item in self.package.find('{*}manifest'):
            kind = 'ncx' if item.get('media-type') == 'application/x-dtbncx+xml' else 'nav' if 'nav' in item.get('properties', '').split() else None
            if kind:
                name = self.path(item.get('href'))
                self.sources[name] = archive.read(name)
                self.documents[name] = ET.fromstring(self.sources[name])
                self.kinds[name] = kind

    def path(self, href):
        return posixpath.normpath(posixpath.join(self.opf_dir, unquote(href)))


def read_tree(book):
    if not book.documents:
        raise ValueError('No navigation found. Supply a reviewed JSON tree')
    name = next((n for n in book.documents if book.kinds[n] == 'nav'), next(iter(book.documents)))
    reader = read_nav if book.kinds[name] == 'nav' else read_ncx
    return reader(book.documents[name], posixpath.dirname(name), book.opf_dir)


def apply_tree(archive, book, nodes, opf=None):
    """Write `nodes` into every navigation document, creating one if the EPUB has
    none. Returns the changed files; `opf` is the package text to patch, if not
    the archive's own."""
    changes = {}
    if not book.documents:
        # Create the navigation format appropriate for this EPUB version.
        package, opf_dir = book.package, book.opf_dir
        if package.get('version', '2').startswith('3'):
            name = posixpath.join(opf_dir, '_agent-nav.xhtml')
            source = ('<html xmlns="%s" xmlns:epub="%s"><head><title>Contents</title></head>'
                      '<body><nav epub:type="toc"/></body></html>' % (XHTML, EPUB)).encode()
            root = ET.fromstring(source)
            attrs = {'id': '_agent_nav', 'href': '_agent-nav.xhtml', 'media-type': 'application/xhtml+xml', 'properties': 'nav'}
            kind = 'nav'
        else:
            name = posixpath.join(opf_dir, '_agent-toc.ncx')
            source = ('<ncx xmlns="%s" version="2005-1"/>' % NCX).encode()
            root = ET.fromstring(source)
            head = ET.SubElement(root, '{%s}head' % NCX)
            identifier = package.find('.//{http://purl.org/dc/elements/1.1/}identifier')
            ET.SubElement(head, '{%s}meta' % NCX, {'name': 'dtb:uid', 'content': text(identifier) if identifier is not None else 'epub-toc'})
            ET.SubElement(head, '{%s}meta' % NCX, {'name': 'dtb:depth', 'content': '1'})
            title = package.find('.//{http://purl.org/dc/elements/1.1/}title')
            ET.SubElement(ET.SubElement(root, '{%s}docTitle' % NCX), '{%s}text' % NCX).text = text(title) if title is not None else 'Contents'
            attrs = {'id': '_agent_toc', 'href': '_agent-toc.ncx', 'media-type': 'application/x-dtbncx+xml'}
            kind = 'ncx'
        if name in archive.namelist() or any(item.get('id') == attrs['id'] for item in package.find('{*}manifest')):
            raise ValueError('Reserved navigation name/id already exists')
        changes[book.opf_name] = register_item(opf or archive.read(book.opf_name), attrs, attrs['id'] if kind == 'ncx' else None)
        book.documents[name], book.kinds[name], book.sources[name] = root, kind, source
    for name, root in book.documents.items():
        writer = write_nav if book.kinds[name] == 'nav' else write_ncx
        writer(root, nodes, book.opf_dir, posixpath.dirname(name))
        changes[name] = serialize(root, book.sources[name])
    return changes


def write_epub(archive, changes, output, removed=()):
    """Publish a copy of `archive` with `changes` at `output`, which must not exist."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix='.epub')
    os.close(fd)
    changes = dict(changes)
    try:
        with zipfile.ZipFile(temporary, 'w') as epub:
            epub.writestr('mimetype', archive.read('mimetype'), compress_type=zipfile.ZIP_STORED)
            for item in archive.infolist():
                if item.filename != 'mimetype' and item.filename not in removed:
                    epub.writestr(item, changes.pop(item.filename, archive.read(item.filename)))
            for name, data in changes.items():
                epub.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        # Exclusive publication protects a file created while conversion ran.
        os.link(temporary, output)
    finally:
        os.unlink(temporary)


def list_headings(archive, book):
    by_id = {item.get('id'): item for item in book.package.find('{*}manifest')}
    listing = []
    for ref in book.package.find('{*}spine'):
        item = by_id.get(ref.get('idref'))
        if item is None or item.get('media-type') != 'application/xhtml+xml':
            continue
        name = book.path(item.get('href'))
        href = quote(posixpath.relpath(name, book.opf_dir))
        found = [{'level': level, 'title': title, 'href': href + '#' + quote(ident)}
                 for _, level, title, ident in headings(ET.fromstring(archive.read(name)))]
        if found:
            listing.append({'href': href, 'headings': found})
    return listing


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('epub', type=Path)
    parser.add_argument('--from', dest='plan', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--headings', action='store_true', help='list every heading per spine file, with an href')
    parser.add_argument('--depth', type=int, help='keep only the first N levels')
    args = parser.parse_args()
    if args.depth is not None and args.depth < 1:
        parser.error('--depth must be at least 1')
    if args.output and not args.plan:
        parser.error('--output requires --from')
    if args.plan and not (args.output or args.dry_run):
        parser.error('Writing requires a distinct --output; preview with --dry-run')
    if args.output and (args.output.resolve() == args.epub.resolve() or args.output.exists()):
        parser.error('Output must be a new file, different from the input')
    with zipfile.ZipFile(args.epub) as archive:
        book = Book(archive)
        if args.headings:
            print(json.dumps(list_headings(archive, book), ensure_ascii=False, indent=2))
            return
        nodes = json.loads(args.plan.read_text(encoding='utf-8')) if args.plan else read_tree(book)
        validate(nodes, archive, book.opf_dir)
        nodes = prune(nodes, args.depth)
        if not args.plan or args.dry_run:
            print(json.dumps(nodes, ensure_ascii=False, indent=2))
            return
        names = {book.path(urlsplit(node['href']).path) for node in walk(nodes) if urlsplit(node['href']).fragment}
        docs = {name: ET.fromstring(archive.read(name)) for name in names}
        changes = {name: serialize(docs[name], archive.read(name))
                   for name in anchor_headings(nodes, docs, book.opf_dir)}
        changes.update(apply_tree(archive, book, nodes))
        write_epub(archive, changes, args.output)
    print(str(args.output))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from error
