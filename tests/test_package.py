"""Adversarial package and preservation controls; public inputs are separate."""
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from pandoc_pptx_rescue.package import CT, REL, Unsupported, content_types, load, missing, xml
from pandoc_pptx_rescue.recovery import recover
from pandoc_pptx_rescue.reference import normalize


def fixture():
    return {'[Content_Types].xml': (f'<Types xmlns="{CT}">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '</Types>').encode(),
            '_rels/.rels': (f'<Relationships xmlns="{REL}"><Relationship Id="r1" '
                           'Type="officeDocument" Target="ppt/presentation.xml"/></Relationships>').encode(),
            'ppt/presentation.xml': b'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'}


def relationships(target, identity='r1'):
    return (f'<Relationships xmlns="{REL}"><Relationship Id="{identity}" '
            f'Type="asset" Target="{target}"/></Relationships>').encode()


class PackageControls(unittest.TestCase):
    def test_valid_control_preserves_every_existing_part(self):
        original = fixture()
        result, audit = recover(original, original)
        self.assertEqual(result, original)
        self.assertEqual(audit['restored_parts'], [])

    def test_missing_source_fails_instead_of_inventing_data(self):
        original = fixture()
        original['ppt/_rels/presentation.xml.rels'] = relationships('missing.xml')
        with self.assertRaisesRegex(Unsupported, 'cannot supply'):
            recover(fixture(), original)

    def test_transitive_source_restoration_and_content_type_namespace(self):
        original = fixture()
        original['[Content_Types].xml'] = original['[Content_Types].xml'].replace(
            b'<Types ', b'<c:Types ').replace(b'</Types>', b'</c:Types>').replace(
            b'xmlns=', b'xmlns:c=').replace(b'<Default ', b'<c:Default ')
        original['ppt/_rels/presentation.xml.rels'] = relationships('custom.xml')
        reference = fixture()
        reference.update({'ppt/_rels/presentation.xml.rels': relationships('custom.xml'),
                          'ppt/custom.xml': b'<custom/>',
                          'ppt/_rels/custom.xml.rels': relationships('media/asset.foo'),
                          'ppt/media/asset.foo': b'exact source asset'})
        reference['[Content_Types].xml'] = reference['[Content_Types].xml'].replace(
            b'</Types>', b'<Default Extension="foo" ContentType="example/source"/></Types>')
        result, audit = recover(reference, original)
        self.assertEqual(missing(result), [])
        self.assertEqual(len(audit['restored_parts']), 3)
        self.assertEqual(result['ppt/media/asset.foo'], b'exact source asset')
        doc, _, overrides = content_types(result)
        self.assertEqual(overrides['/ppt/media/asset.foo'], 'example/source')
        self.assertEqual(doc.getElementsByTagNameNS(CT, 'Override').length, 1)
        self.assertEqual(audit['changed_generated_parts'], ['[Content_Types].xml'])

    def test_restored_dependency_collision_is_rejected(self):
        original = fixture()
        original.update({'ppt/_rels/presentation.xml.rels': relationships('missing.xml'),
                         'ppt/asset.xml': b'<different/>'})
        reference = fixture()
        reference.update({'ppt/_rels/presentation.xml.rels': relationships('missing.xml'),
                          'ppt/missing.xml': b'<restored/>',
                          'ppt/_rels/missing.xml.rels': relationships('asset.xml'),
                          'ppt/asset.xml': b'<original/>'})
        with self.assertRaisesRegex(Unsupported, 'changed asset'):
            recover(reference, original)

    def test_external_reference_is_preserved_and_never_resolved(self):
        parts = fixture()
        parts['ppt/_rels/presentation.xml.rels'] = (f'<Relationships xmlns="{REL}">'
            '<Relationship Id="r1" Type="url" Target="https://example.invalid/a" TargetMode="External"/>'
            '</Relationships>').encode()
        self.assertEqual(missing(parts), [])
        self.assertEqual(recover(parts, parts)[0], parts)

    def test_encoded_traversal_and_duplicate_ids_rejected(self):
        for data in [relationships('%2e%2e/%2e%2e/outside.xml'),
                     relationships('a.xml').replace(b'</Relationships>',
                         b'<Relationship Id="r1" Type="asset" Target="b.xml"/></Relationships>')]:
            parts = fixture()
            parts['ppt/_rels/presentation.xml.rels'] = data
            with self.assertRaises(Unsupported):
                missing(parts)

    def test_dtd_and_deep_xml_rejected(self):
        for data in [b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>',
                     ('<x>' * 110 + '</x>' * 110).encode()]:
            with self.assertRaises(Unsupported):
                xml(data, 'test.xml')

    def test_duplicate_zip_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.pptx'
            for names in [('a.xml', 'a.xml'), ('../outside.xml',)]:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    with zipfile.ZipFile(path, 'w') as archive:
                        for name in names:
                            archive.writestr(name, '<x/>')
                with self.assertRaises(Unsupported):
                    load(path)

    def test_sole_title_normalization_is_guarded(self):
        parts = fixture()
        name = 'ppt/slideLayouts/slideLayout1.xml'
        parts[name] = b'<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="Title Slide"><p:ph type="title"/></p:cSld></p:sldLayout>'
        result, changed = normalize(parts)
        self.assertEqual(changed, [name])
        self.assertIn(b'type="ctrTitle"', result[name])
        self.assertEqual(normalize(result)[1], [])
        parts[name] = parts[name].replace(b'<p:ph type="title"/>', b'<p:ph type="title"/><p:ph type="title"/>')
        with self.assertRaises(Unsupported):
            normalize(parts)


if __name__ == '__main__':
    unittest.main()
