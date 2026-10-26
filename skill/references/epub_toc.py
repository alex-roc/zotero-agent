#!/usr/bin/env python3
"""Inspect or write an EPUB navigation tree. Python stdlib; never edits the input.

python3 epub_toc.py book.epub > toc.json
python3 epub_toc.py book.epub --from toc.json --dry-run
python3 epub_toc.py book.epub --from toc.json -o book-with-toc.epub

JSON: [{"title": "Part I", "href": "Text/part.xhtml", "children": [...]}]
All hrefs are relative to the OPF directory, with optional #fragment.
"""
import argparse
import io
import json
import os
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.sax.saxutils import quoteattr

OPF = 'http://www.idpf.org/2007/opf'
XHTML = 'http://www.w3.org/1999/xhtml'
EPUB = 'http://www.idpf.org/2007/ops'
NCX = 'http://www.daisy.org/z3986/2005/ncx/'


def text(element):
    return ' '.join(''.join(element.itertext()).split())


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
                    cache[target] = {e.get('id') or e.get('{http://www.w3.org/XML/1998/namespace}id')
                                     for e in ET.fromstring(data).iter()}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('epub', type=Path)
    parser.add_argument('--from', dest='plan', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.output and not args.plan:
        parser.error('--output requires --from')
    if args.plan and not (args.output or args.dry_run):
        parser.error('Writing requires a distinct --output; preview with --dry-run')
    if args.output and (args.output.resolve() == args.epub.resolve() or args.output.exists()):
        parser.error('Output must be a new file, different from the input')
    with zipfile.ZipFile(args.epub) as archive:
        container = ET.fromstring(archive.read('META-INF/container.xml'))
        opf_name = container.find('.//{*}rootfile').get('full-path')
        opf_dir = posixpath.dirname(opf_name)
        package = ET.fromstring(archive.read(opf_name))
        manifest = package.find('{*}manifest')
        documents = {}
        kinds = {}
        sources = {}
        for item in manifest:
            kind = 'ncx' if item.get('media-type') == 'application/x-dtbncx+xml' else 'nav' if 'nav' in item.get('properties', '').split() else None
            if kind:
                name = posixpath.normpath(posixpath.join(opf_dir, unquote(item.get('href'))))
                sources[name] = archive.read(name)
                documents[name] = ET.fromstring(sources[name])
                kinds[name] = kind
        if args.plan:
            nodes = json.loads(args.plan.read_text(encoding='utf-8'))
        elif documents:
            name = next((n for n in documents if kinds[n] == 'nav'), next(iter(documents)))
            reader = read_nav if kinds[name] == 'nav' else read_ncx
            nodes = reader(documents[name], posixpath.dirname(name), opf_dir)
        else:
            raise ValueError('No navigation found. Supply a reviewed JSON tree with --from')
        validate(nodes, archive, opf_dir)
        if not args.plan or args.dry_run:
            print(json.dumps(nodes, ensure_ascii=False, indent=2))
            return
        changes = {}
        if not documents:
            # Create the navigation format appropriate for this EPUB version.
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
            if name in archive.namelist() or any(item.get('id') == attrs['id'] for item in manifest):
                raise ValueError('Reserved navigation name/id already exists')
            changes[opf_name] = register_item(archive.read(opf_name), attrs, attrs['id'] if kind == 'ncx' else None)
            documents[name], kinds[name], sources[name] = root, kind, source
        for name, root in documents.items():
            writer = write_nav if kinds[name] == 'nav' else write_ncx
            writer(root, nodes, opf_dir, posixpath.dirname(name))
            changes[name] = serialize(root, sources[name])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=args.output.parent, suffix='.epub')
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, 'w') as output:
                output.writestr('mimetype', archive.read('mimetype'), compress_type=zipfile.ZIP_STORED)
                for item in archive.infolist():
                    if item.filename != 'mimetype':
                        output.writestr(item, changes.pop(item.filename, archive.read(item.filename)))
                for name, data in changes.items():
                    output.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            # Exclusive publication protects a file created while conversion ran.
            os.link(temporary, args.output)
        finally:
            os.unlink(temporary)
    print(str(args.output))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from error
