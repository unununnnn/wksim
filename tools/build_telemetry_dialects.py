"""Generate local MAVLink decoders from the exact pinned FC XML, without pip changes.

Writes only a NEW output directory and its candidate manifest. Installing the
manifest into the runtime is a separate reviewed step; FC checkouts stay intact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

PINS = {
    'px4': ('/root/wksim-dependencies/px4-d6f12ad1', 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4',
            'src/modules/mavlink/mavlink', 'development'),
    'arducopter': ('/root/wksim-ap-dds-yaw-state-4Wr27s/src', '1511f27194f1dcc3728270883047bdf022b3fd53',
                  'modules/mavlink', 'ardupilotmega'),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def xml_inputs(entry):
    root, pending, inputs = entry.parent.resolve(), [entry], {}
    while pending:
        path = pending.pop().resolve()
        if path in inputs:
            continue
        if not path.is_relative_to(root):
            raise ValueError('MAVLink include escapes the reviewed definitions directory')
        inputs[path] = digest(path)
        pending.extend(path.parent / node.text for node in ET.parse(path).getroot().findall('include'))
    return {str(path): value for path, value in sorted(inputs.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new directory; never overwrite a generated decoder')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    manifest = dict(schema_version=1, generated=True, builder_sha256=digest(__file__), dialects={})
    for stack, (location, expected, submodule, dialect) in PINS.items():
        root = Path(location)
        commit = git(root, 'rev-parse', 'HEAD')
        if commit != expected:
            raise ValueError(stack + ': wrong firmware source commit')
        mavroot = root / submodule
        mavcommit = git(mavroot, 'rev-parse', 'HEAD')
        pinned_submodule = git(root, 'ls-tree', 'HEAD', submodule).split()[2]
        if mavcommit != pinned_submodule:
            raise ValueError(stack + ': MAVLink submodule differs from firmware commit')
        entry = mavroot / 'message_definitions/v1.0' / (dialect + '.xml')
        inputs = xml_inputs(entry)
        git_inputs = {}
        for filename in inputs:
            path = Path(filename)
            relative = path.relative_to(mavroot).as_posix()
            committed = subprocess.check_output(['git', '-C', str(mavroot), 'show', 'HEAD:' + relative])
            actual = path.read_bytes()
            if actual.replace(b'\r\n', b'\n') != committed.replace(b'\r\n', b'\n'):
                raise ValueError(stack + ': XML has changes beyond CRLF/LF: ' + relative)
            git_inputs[relative] = dict(committed_sha256=hashlib.sha256(committed).hexdigest(),
                                       exact_bytes=actual == committed, crlf_lf_only=actual != committed)
        target = output / (stack + '.py')
        generator = mavroot / 'pymavlink'
        generator_commit = git(generator, 'rev-parse', 'HEAD')
        if generator_commit != git(mavroot, 'ls-tree', 'HEAD', 'pymavlink').split()[2]:
            raise ValueError(stack + ': generator differs from the pinned MAVLink submodule')
        subprocess.run(['git', '-C', str(generator), 'diff', '--quiet', '--ignore-cr-at-eol', 'HEAD', '--',
                        'generator', 'tools/mavgen.py', '__init__.py'], check=True)
        generator_files = [generator / 'tools/mavgen.py', generator / '__init__.py']
        generator_files += sorted(p for p in (generator / 'generator').rglob('*')
                                  if p.is_file() and p.suffix in ('.py', '.xsd'))
        generator_inputs = {str(p): digest(p) for p in generator_files}
        argv = [sys.executable, str(generator / 'tools/mavgen.py'), '--lang', 'Python3',
                '--wire-protocol', '2.0', '--output', str(target), str(entry)]
        subprocess.run(argv, check=True, env=dict(os.environ, PYTHONPATH=str(mavroot), PYTHONDONTWRITEBYTECODE='1'))
        if inputs != xml_inputs(entry):
            raise RuntimeError(stack + ': XML inputs changed during generation')
        if generator_inputs != {str(p): digest(p) for p in generator_files}:
            raise RuntimeError(stack + ': generator inputs changed')
        manifest['dialects'][stack] = dict(path=str(target), sha256=digest(target), dialect=dialect,
            fc_commit=commit, mavlink_commit=mavcommit, xml_sha256=inputs, xml_git_identity=git_inputs,
            generator_commit=generator_commit, generator_sha256=generator_inputs, argv=argv)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(status='generated', candidate_manifest=str(output / 'manifest.json'))))


if __name__ == '__main__':
    main()
