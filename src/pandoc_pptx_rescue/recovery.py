"""Recover exact missing reference parts without replacing generated content."""
from .package import (CT, Unsupported, check_parts, content_types, edges, missing,
                      rel_path, type_for)


def recover(reference, original):
    if missing(reference):
        raise Unsupported('incomplete_reference', 'Reference itself has missing internal targets')
    parts, added = dict(original), set()
    before = missing(parts)
    while True:
        pending = missing(parts)
        if not pending:
            break
        for edge in pending:
            name = edge['target']
            if name in parts:
                continue
            if name not in reference:
                raise Unsupported('missing_source', 'Reference cannot supply missing part: ' + name)
            parts[name] = reference[name]
            added.add(name)
            rel = rel_path(name)
            if rel in reference:
                if rel in parts and parts[rel] != reference[rel]:
                    raise Unsupported('dependency_collision', 'Relationship collision: ' + rel)
                if rel not in parts:
                    parts[rel] = reference[rel]
                    added.add(rel)
        check_parts(parts)
    for edge in edges(parts):
        if edge['source'] in added and edge['target'] not in added:
            name = edge['target']
            if name not in reference or parts[name] != reference[name]:
                raise Unsupported('dependency_collision', 'Restored relationship targets changed asset: ' + name)
    doc, defaults, overrides = content_types(parts)
    _, ref_defaults, ref_overrides = content_types(reference)
    additions = []
    for name in sorted(added):
        expected = type_for(name, ref_defaults, ref_overrides)
        actual = type_for(name, defaults, overrides)
        if expected is None:
            raise Unsupported('missing_content_type', 'Reference has no content type for: ' + name)
        if actual != expected:
            if '/' + name in overrides:
                raise Unsupported('content_type_collision', 'Conflicting content type for: ' + name)
            prefix = doc.documentElement.prefix
            element = doc.createElementNS(CT, (prefix + ':' if prefix else '') + 'Override')
            element.setAttribute('PartName', '/' + name)
            element.setAttribute('ContentType', expected)
            doc.documentElement.appendChild(element)
            overrides['/' + name] = expected
            additions.append(name)
    if additions:
        parts['[Content_Types].xml'] = doc.toxml(encoding='UTF-8')
    for name in parts:
        if name != '[Content_Types].xml' and type_for(name, defaults, overrides) is None:
            raise Unsupported('missing_content_type', 'No content type for package part: ' + name)
    check_parts(parts)
    return parts, {'missing_before': before, 'missing_after': missing(parts),
                   'restored_parts': sorted(added), 'content_type_overrides_added': additions,
                   'changed_generated_parts': [name for name in original if parts[name] != original[name]],
                   'restored_parts_match_reference': all(parts[name] == reference[name] for name in added)}
