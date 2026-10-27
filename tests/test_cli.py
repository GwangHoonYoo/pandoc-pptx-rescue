"""Atomic failure controls using a simulated converter, not native Office tests."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pandoc_pptx_rescue import cli
from pandoc_pptx_rescue.package import write
from test_package import fixture


class AtomicControls(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, reference, output = root / 'input.md', root / 'ref.pptx', root / 'output.pptx'
            source.write_text('# Input')
            write(fixture(), reference)

            def converter(command, **kwargs):
                if '--version' in command:
                    kwargs['stdout'].write('pandoc 3.13\n')
                    return SimpleNamespace(returncode=0)
                if mode == 'converter-failure':
                    kwargs['stdout'].write('test conversion failure')
                    return SimpleNamespace(returncode=1)
                dest = Path(next(x.split('=', 1)[1] for x in command if x.startswith('--output=')))
                write(fixture(), dest)
                if mode == 'input-change':
                    source.write_text('# Concurrently changed')
                return SimpleNamespace(returncode=0)

            def racing_link(_source, destination):
                Path(destination).write_bytes(b'created by concurrent writer')
                raise FileExistsError('race')

            capture = io.StringIO()
            with patch.object(cli.subprocess, 'run', side_effect=converter), contextlib.redirect_stdout(capture):
                if mode == 'output-race':
                    with patch.object(cli.os, 'link', side_effect=racing_link):
                        code = cli.main(['build', str(source), '--reference', str(reference),
                                         '--output', str(output), '--format', 'json'])
                else:
                    code = cli.main(['build', str(source), '--reference', str(reference),
                                     '--output', str(output), '--format', 'json'])
            result = json.loads(capture.getvalue())
            self.assertFalse(list(root.glob('.pptx-rescue-*')))
            if mode == 'output-race':
                self.assertEqual(code, 2)
                self.assertEqual(result['error']['code'], 'output_exists')
                self.assertEqual(output.read_bytes(), b'created by concurrent writer')
            else:
                self.assertEqual(code, 1)
                self.assertFalse(output.exists())
            self.assertFalse(result['output_written'])

    def test_atomic_output_race_preserves_other_writer(self):
        self.exercise('output-race')

    def test_converter_failure_has_no_partial_output(self):
        self.exercise('converter-failure')

    def test_input_change_aborts_publication(self):
        self.exercise('input-change')


if __name__ == '__main__':
    unittest.main()
