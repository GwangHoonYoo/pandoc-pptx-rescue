"""Agent-readable, atomic build CLI for the tested Pandoc 3.13 workflow."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from . import __version__
from .package import Unsupported, load, missing, write
from .recovery import recover
from .reference import normalize


class BuildFailure(RuntimeError):
    pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(args):
    source, reference, output = (Path(x).absolute() for x in
                                 (args.input, args.reference, args.output))
    if output.exists() or output.is_symlink():
        raise Unsupported('output_exists', 'Choose a new output path; existing files are preserved')
    if not source.is_file() or not reference.is_file():
        raise Unsupported('missing_input', 'Markdown and reference must be existing local files')
    if source.stat().st_size > 10 * 1024 * 1024:
        raise Unsupported('markdown_limit', 'Markdown exceeds 10 MiB')
    input_hashes = {'markdown': digest(source), 'reference': digest(reference)}
    reference_parts = load(reference)
    if missing(reference_parts):
        raise Unsupported('incomplete_reference', 'Reference itself has missing internal targets')
    normalized, changed = normalize(reference_parts)
    with tempfile.TemporaryDirectory(prefix='pandoc-pptx-rescue-') as temporary:
        temp = Path(temporary)
        with (temp / 'version.log').open('w') as log:
            try:
                version = subprocess.run([args.pandoc, '--version'], stdout=log,
                                         stderr=log, timeout=10)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise Unsupported('pandoc_unavailable', 'Cannot execute the supplied Pandoc binary') from exc
        first_line = (temp / 'version.log').read_text(errors='replace').splitlines()
        if version.returncode or not first_line or first_line[0].strip() != 'pandoc 3.13':
            raise Unsupported('pandoc_version', 'This release supports exactly Pandoc 3.13')
        temp_reference, generated = temp / 'reference.pptx', temp / 'generated.pptx'
        write(normalized, temp_reference)
        command = [args.pandoc, str(source), '--from=markdown', '--to=pptx',
                   '--reference-doc=' + str(temp_reference), '--output=' + str(generated)]
        with (temp / 'pandoc.log').open('w') as log:
            try:
                process = subprocess.run(command, cwd=source.parent, stdout=log,
                                         stderr=log, timeout=60)
            except subprocess.TimeoutExpired as exc:
                raise BuildFailure('Pandoc exceeded the 60-second build limit') from exc
        if process.returncode or not generated.is_file():
            detail = (temp / 'pandoc.log').read_bytes()[:2048].decode('utf-8', errors='replace').strip()
            raise BuildFailure('Pandoc conversion failed; no output was published. ' + detail)
        repaired, audit = recover(normalized, load(generated))
        if digest(source) != input_hashes['markdown'] or digest(reference) != input_hashes['reference']:
            raise BuildFailure('Input changed during build; no output was published')
        if not output.parent.is_dir():
            raise Unsupported('output_directory', 'Output parent directory must already exist')
        fd, path = tempfile.mkstemp(prefix='.pptx-rescue-', suffix='.tmp', dir=output.parent)
        os.close(fd)
        staged = Path(path)
        try:
            write(repaired, staged)
            if missing(load(staged)):
                raise BuildFailure('Final package still has missing internal targets')
            with staged.open('rb') as handle:
                os.fsync(handle.fileno())
            output_hash = digest(staged)
            try:
                os.link(staged, output)
            except FileExistsError as exc:
                raise Unsupported('output_exists', 'Output appeared during build; it was preserved') from exc
        finally:
            staged.unlink(missing_ok=True)
        log_text = (temp / 'pandoc.log').read_bytes()[:65536].decode('utf-8', errors='replace')
    return {'status': 'written', 'output': str(output), 'output_sha256': output_hash,
            'input_sha256': input_hashes, 'pandoc_version': '3.13',
            'reference_parts_normalized': changed, **audit, 'pandoc_log': log_text,
            'scope': 'Reference dependency recovery and guarded title placeholder normalization; '
                     'not a full Office validator or Microsoft PowerPoint compatibility guarantee.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Recover missing PPTX reference dependencies while building with Pandoc 3.13.')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('build', help='Build Markdown with an exact local PPTX reference')
    command.add_argument('input')
    command.add_argument('--reference', required=True)
    command.add_argument('--output', required=True)
    command.add_argument('--pandoc', default='pandoc', help='Pandoc executable name or absolute path')
    command.add_argument('--format', choices=('human', 'json'), default='human')
    args = parser.parse_args(argv)
    try:
        if '/' in args.pandoc:
            args.pandoc = str(Path(args.pandoc).absolute())
        result, code = build(args), 0
    except Unsupported as exc:
        result, code = {'status': 'unsupported', 'error': {'code': exc.code, 'message': str(exc)}, 'output_written': False}, 2
    except (BuildFailure, OSError, ValueError) as exc:
        result, code = {'status': 'failed', 'error': {'code': 'build_failed', 'message': str(exc)}, 'output_written': False}, 1
    if args.format == 'json':
        print(json.dumps(result, indent=2))
    elif code:
        print(result['status'] + ': ' + result['error']['message'])
    else:
        print('Wrote ' + result['output'])
        print('Restored reference parts: ' + str(len(result['restored_parts'])))
        print('Normalized title layouts: ' + str(len(result['reference_parts_normalized'])))
        print('Missing internal targets: ' + str(len(result['missing_before'])) + ' -> 0')
        if result['pandoc_log'].strip():
            print('Pandoc log: ' + result['pandoc_log'].strip())
        print(result['scope'])
    return code
