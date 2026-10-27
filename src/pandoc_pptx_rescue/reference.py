"""Guarded normalization of the demonstrated Title Slide placeholder."""
from .package import Unsupported, xml

NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'


def normalize(parts):
    result, changed = dict(parts), []
    for name, data in parts.items():
        if not name.startswith('ppt/slideLayouts/') or not name.endswith('.xml'):
            continue
        doc = xml(data, name)
        common = doc.getElementsByTagNameNS(NS, 'cSld')
        if not common or common[0].getAttribute('name') != 'Title Slide':
            continue
        placeholders = doc.getElementsByTagNameNS(NS, 'ph')
        if any(p.getAttribute('type') == 'ctrTitle' for p in placeholders):
            continue
        titles = [p for p in placeholders if p.getAttribute('type') == 'title']
        if len(titles) != 1:
            raise Unsupported('ambiguous_title', 'Title Slide needs one unambiguous title placeholder: ' + name)
        titles[0].setAttribute('type', 'ctrTitle')
        result[name] = doc.toxml(encoding='UTF-8')
        changed.append(name)
    return result, changed
