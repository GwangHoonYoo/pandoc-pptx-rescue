"""Bounded research probe, not a general OOXML repair utility.

Compare Pandoc's output with its exact reference package, then restore missing
relationship dependencies from that reference. Never overwrite existing parts.
This does not establish PowerPoint rendering or complete document fidelity.
"""
import argparse
import hashlib
import json
import posixpath
import zipfile
from pathlib import Path
from xml.dom import minidom
import xml.etree.ElementTree as ET

REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def missing(parts):
    result = []
    for name, data in sorted(parts.items()):
        if not name.endswith('.rels'):
            continue
        base = '' if name == '_rels/.rels' else name.rsplit('/_rels/', 1)[0]
        for rel in ET.fromstring(data).findall(REL + 'Relationship'):
            if rel.get('TargetMode') == 'External':
                continue
            target = rel.attrib['Target']
            resolved = posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                         else posixpath.join(base, target))
            if resolved not in parts:
                result.append({'source': name, 'target': resolved})
    return result


def load(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def probe(reference, source, output):
    ref, original = load(reference), load(source)
    parts, added = dict(original), []
    before = missing(parts)
    for _ in range(30):
        pending = missing(parts)
        if not pending:
            break
        changed = False
        for item in pending:
            target = item['target']
            if target in parts or target not in ref:
                continue
            parts[target] = ref[target]
            added.append(target)
            changed = True
            parent, name = posixpath.split(target)
            rel = posixpath.join(parent, '_rels', name + '.rels')
            if rel in ref and rel not in parts:
                parts[rel] = ref[rel]
                added.append(rel)
        if not changed:
            break
    # Copy content-type declarations only for restored parts. Keep original
    # namespace prefixes rather than reserializing the whole package via ET.
    types = minidom.parseString(parts['[Content_Types].xml'])
    ref_types = minidom.parseString(ref['[Content_Types].xml'])
    registered = {node.getAttribute('PartName') for node in
                  types.getElementsByTagName('Override')}
    for node in ref_types.getElementsByTagName('Override'):
        name = node.getAttribute('PartName')
        if name.lstrip('/') in added and name not in registered:
            types.documentElement.appendChild(types.importNode(node, True))
            registered.add(name)
    if added:
        parts['[Content_Types].xml'] = types.toxml(encoding='UTF-8')
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    after = load(output)
    return {'reference': str(reference), 'input': str(source), 'output': str(output),
            'before_missing': before, 'added_parts': sorted(added),
            'after_missing': missing(after),
            'changed_existing_parts': [n for n in original if original[n] != after[n]],
            'restored_reference_bytes_equal': all(after[n] == ref[n] for n in added),
            'output_sha256': hashlib.sha256(Path(output).read_bytes()).hexdigest(),
            'scope': 'ZIP/XML relationships and exact source-part recovery only; '
                     'no native PowerPoint/LibreOffice rendering or full-fidelity claim.'}


