"""Bounded OPC parsing, not an Office conformance validator."""
from dataclasses import dataclass
import posixpath
import re
import stat
from urllib.parse import unquote, urlsplit
from xml.dom import minidom
import zipfile
import zlib

REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


class Unsupported(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 64 * 1024 * 1024
    expanded_bytes: int = 128 * 1024 * 1024
    part_bytes: int = 32 * 1024 * 1024
    xml_bytes: int = 8 * 1024 * 1024
    entries: int = 4096
    depth: int = 100
    xml_nodes: int = 250000


LIMITS = Limits()


def part_name(name):
    if (not name or '\\' in name or '\x00' in name or name.startswith('/')
            or any(c in ('', '.', '..') for c in name.split('/'))):
        raise Unsupported('unsafe_part_path', 'Unsafe package part path: ' + repr(name))
    return name


def xml(data, name):
    if len(data) > LIMITS.xml_bytes:
        raise Unsupported('xml_limit', 'XML part exceeds 8 MiB: ' + name)
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise Unsupported('xml_encoding', 'Only UTF-8 XML is supported: ' + name) from exc
    if re.search(r'<!\s*(DOCTYPE|ENTITY)\b', text, re.I):
        raise Unsupported('xml_declaration', 'DTD/entity declarations are unsupported: ' + name)
    try:
        doc = minidom.parseString(text)
    except Exception as exc:
        raise Unsupported('invalid_xml', 'Cannot parse XML: ' + name) from exc
    stack, count = [(doc.documentElement, 1)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if depth > LIMITS.depth or count > LIMITS.xml_nodes:
            raise Unsupported('xml_complexity', 'XML structure exceeds limits: ' + name)
        stack.extend((child, depth + 1) for child in node.childNodes
                     if child.nodeType == child.ELEMENT_NODE)
    return doc


def check_parts(parts):
    if len(parts) > LIMITS.entries or sum(map(len, parts.values())) > LIMITS.expanded_bytes:
        raise Unsupported('package_limit', 'Expanded package exceeds configured limits')
    for name, data in parts.items():
        part_name(name)
        if len(data) > LIMITS.part_bytes:
            raise Unsupported('part_limit', 'Part exceeds 32 MiB: ' + name)
        if name.startswith('_xmlsignatures/') or name.lower().endswith('vbaproject.bin'):
            raise Unsupported('signed_or_macro_package', 'Signed or VBA packages are unsupported')
        if name.endswith(('.xml', '.rels')):
            xml(data, name)
    for name in ('[Content_Types].xml', '_rels/.rels', 'ppt/presentation.xml'):
        if name not in parts:
            raise Unsupported('not_pptx', 'Required PPTX part missing: ' + name)


def load(path):
    if path.stat().st_size > LIMITS.archive_bytes:
        raise Unsupported('archive_limit', 'Archive exceeds 64 MiB')
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > LIMITS.entries:
                raise Unsupported('entry_limit', 'Archive exceeds 4096 entries')
            parts, seen, total = {}, set(), 0
            for info in infos:
                part_name(info.filename.rstrip('/'))
                if info.filename in seen:
                    raise Unsupported('duplicate_part', 'Duplicate ZIP part: ' + info.filename)
                seen.add(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise Unsupported('zip_feature', 'Symlink/encrypted ZIP entries are unsupported')
                if info.is_dir():
                    continue
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise Unsupported('zip_compression', 'Unsupported ZIP compression')
                total += info.file_size
                if info.file_size > LIMITS.part_bytes or total > LIMITS.expanded_bytes:
                    raise Unsupported('package_limit', 'Declared expanded ZIP size exceeds limits')
                with archive.open(info) as stream:
                    data = stream.read(LIMITS.part_bytes + 1)
                if len(data) > LIMITS.part_bytes or len(data) != info.file_size:
                    raise Unsupported('part_limit', 'Expanded ZIP part exceeds limits')
                parts[info.filename] = data
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise Unsupported('invalid_zip', 'Invalid or unsupported ZIP archive') from exc
    check_parts(parts)
    return parts


def rel_path(owner):
    parent, name = posixpath.split(owner)
    return posixpath.join(parent, '_rels', name + '.rels')


def edges(parts):
    result = []
    for name in sorted(parts):
        if not name.endswith('.rels'):
            continue
        if name == '_rels/.rels':
            parent = ''
        elif '/_rels/' in name:
            parent, filename = name.rsplit('/_rels/', 1)
            if parent + '/' + filename[:-5] not in parts:
                raise Unsupported('orphan_relationship', 'Relationship owner is missing: ' + name)
        else:
            raise Unsupported('relationship_path', 'Unsupported relationship part path: ' + name)
        doc = xml(parts[name], name)
        if (doc.documentElement.namespaceURI != REL
                or doc.documentElement.localName != 'Relationships'):
            raise Unsupported('relationship_xml', 'Unexpected relationship XML root: ' + name)
        ids = set()
        for node in doc.documentElement.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.namespaceURI != REL or node.localName != 'Relationship':
                raise Unsupported('relationship_xml', 'Unexpected relationship element: ' + name)
            identity = node.getAttribute('Id')
            if not identity or identity in ids:
                raise Unsupported('relationship_id', 'Missing/duplicate relationship ID: ' + name)
            ids.add(identity)
            mode = node.getAttribute('TargetMode')
            if mode == 'External':
                continue
            if mode not in ('', 'Internal'):
                raise Unsupported('relationship_mode', 'Unknown relationship target mode: ' + name)
            try:
                uri = urlsplit(node.getAttribute('Target'))
                if uri.scheme or uri.netloc or uri.query or not uri.path:
                    raise ValueError('unsupported URI')
                target = unquote(uri.path, errors='strict')
            except ValueError as exc:
                raise Unsupported('relationship_uri', 'Unsupported internal relationship URI: ' + name) from exc
            target = posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                       else posixpath.join(parent, target))
            part_name(target)
            result.append({'source': name, 'target': target, 'id': identity})
    return result


def missing(parts):
    return [edge for edge in edges(parts) if edge['target'] not in parts]


def content_types(parts):
    doc = xml(parts['[Content_Types].xml'], '[Content_Types].xml')
    if doc.documentElement.namespaceURI != CT or doc.documentElement.localName != 'Types':
        raise Unsupported('content_types', 'Unexpected content-types root')
    defaults, overrides = {}, {}
    for node in doc.documentElement.childNodes:
        if node.nodeType != node.ELEMENT_NODE:
            continue
        if node.namespaceURI != CT or node.localName not in ('Default', 'Override'):
            raise Unsupported('content_types', 'Unsupported content-type declaration')
        key = node.getAttribute('Extension' if node.localName == 'Default' else 'PartName')
        mime = node.getAttribute('ContentType')
        mapping = defaults if node.localName == 'Default' else overrides
        if not key or not mime or key in mapping:
            raise Unsupported('content_types', 'Missing/duplicate content-type declaration')
        mapping[key] = mime
    return doc, defaults, overrides


def type_for(name, defaults, overrides):
    return overrides.get('/' + name) or defaults.get(name.rsplit('.', 1)[-1])


def write(parts, path):
    check_parts(parts)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
