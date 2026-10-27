"""Normalize one demonstrated LibreOffice Title Slide placeholder for research.

Only change a sole title placeholder when ctrTitle is absent. This is not a
general template normalizer or a guarantee of Office consumer compatibility.
"""
import argparse
import json
import zipfile
from xml.dom import minidom

NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'


def normalize(source, target):
    changed = []
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(
            target, 'w', zipfile.ZIP_DEFLATED) as output:
        for info in archive.infolist():
            data = archive.read(info.filename)
            if info.filename.startswith('ppt/slideLayouts/') and info.filename.endswith('.xml'):
                doc = minidom.parseString(data)
                common = doc.getElementsByTagNameNS(NS, 'cSld')
                placeholders = doc.getElementsByTagNameNS(NS, 'ph')
                if (common and common[0].getAttribute('name') == 'Title Slide'
                        and not any(p.getAttribute('type') == 'ctrTitle' for p in placeholders)):
                    titles = [p for p in placeholders if p.getAttribute('type') == 'title']
                    if len(titles) == 1:
                        titles[0].setAttribute('type', 'ctrTitle')
                        data = doc.toxml(encoding='UTF-8')
                        changed.append(info.filename)
            output.writestr(info, data)
    return {'changed_parts': changed}


