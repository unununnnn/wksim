"""Stage immutable e0 inputs and inspect executable XML before a bounded MATLAB probe.

Default only prepares evidence. --run explicitly executes load/update, never sim/codegen.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp')
EXPECTED = {
    'MulticopterModel.zip': 'd528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed',
    'Exp1_MinModelTemp.slx': 'c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392',
    'Exp1_MinModelTemp_init.m': '9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def inspect(path):
    result = {'path': str(path), 'sha256': digest(path), 'callbacks': [], 'references': [], 'masks': []}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith('.xml'):
                continue
            root = ET.fromstring(archive.read(name))
            for node in root.iter():
                key = node.get('Name', node.tag)
                value = node.text or ''
                if value.strip() and (key.endswith('Fcn') or 'Initialization' in key or 'Callback' in key):
                    result['callbacks'].append({'member': name, 'key': key, 'text': value})
                if key == 'SourceBlock':
                    result['references'].append(value)
                if node.tag in ('Mask', 'MaskParameter'):
                    result['masks'].append({'member': name, 'xml': ET.tostring(node, encoding='unicode')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--matlab', type=Path, default=Path('D:/matlab/install date/bin/matlab.exe'))
    args = parser.parse_args()
    out = ROOT / 'validation/model-reference-readiness-20260909'
    if args.attempt > 1:
        out = out / f'attempt-{args.attempt:02d}'
    if (out / 'matlab-console.log').exists():
        raise RuntimeError('Refusing to overwrite previous runtime evidence; use a new --attempt')
    out.mkdir(parents=True, exist_ok=True)
    private = out / 'staged-model'
    private.mkdir(exist_ok=True)
    manifest = []
    for name, expected in EXPECTED.items():
        source = SOURCE / name
        actual = digest(source)
        if actual != expected:
            raise RuntimeError(f'Source identity mismatch: {source}: {actual}')
        target = private / name
        if target.exists() and digest(target) != actual:
            raise RuntimeError(f'Private input changed: {target}')
        shutil.copyfile(source, target)
        manifest.append({'source': str(source), 'private': str(target), 'sha256': actual})
    audit = inspect(private / 'Exp1_MinModelTemp.slx')
    libraries = sorted({ref.split('/')[0] for ref in audit['references']})
    # Locate only installed toolbox model files; no vendor path or startup registration.
    toolbox = args.matlab.parent.parent / 'toolbox'
    files_by_name = {}
    for directory, _, files in os.walk(toolbox):
        for filename in files:
            if filename.endswith(('.slx', '.mdl')):
                files_by_name.setdefault(Path(filename).stem, []).append(Path(directory) / filename)
    deps = []
    pending = list(libraries)
    seen = set()
    while pending:
        lib = pending.pop()
        if lib in seen or lib == '$bdroot':
            continue
        seen.add(lib)
        for path in files_by_name.get(lib, []):
            item = {'path': str(path), 'sha256': digest(path)}
            if path.suffix == '.slx':
                item['xml_audit'] = inspect(path)
                pending.extend(ref.split('/')[0] for ref in item['xml_audit']['references'])
                for cb in item['xml_audit']['callbacks']:
                    pending.extend(re.findall(r"load_system\('([^']+)'\)", cb['text']))
            else:
                item['text'] = path.read_text(encoding='utf-8', errors='replace')
            deps.append(item)
    write(out / 'source-manifest.json', manifest)
    write(out / 'static-audit.json', audit)
    write(out / 'installed-library-audit.json', deps)
    write(out / 'static-library-resolution.json', {'requested_roots': sorted(seen), 'missing': sorted(seen - files_by_name.keys() - {'$bdroot'})})
    (out / 'init-reviewed.txt').write_text((private / 'Exp1_MinModelTemp_init.m').read_bytes().decode('gb18030'), encoding='utf-8')
    shutil.copyfile(ROOT / 'tools/probe_model_reference_readiness.m', private / 'probe_model_reference_readiness.m')
    write(out / 'probe-identity.json', {p.name: digest(p) for p in (Path(__file__), private / 'probe_model_reference_readiness.m')})
    for name in ('temp', 'pref', 'cache', 'codegen'):
        (out / name).mkdir(exist_ok=True)
    argv = [str(args.matlab), '-wait', '-sd', str(private), '-batch', 'probe_model_reference_readiness']
    write(out / 'command.json', {'argv': argv, 'cwd': str(private), 'environment_overrides': {k: str(out / v) for k, v in [('TEMP', 'temp'), ('TMP', 'temp'), ('MATLAB_PREFDIR', 'pref')]}, 'run_requested': args.run})
    if args.run:
        env = os.environ.copy()
        env.update(TEMP=str(out / 'temp'), TMP=str(out / 'temp'), MATLAB_PREFDIR=str(out / 'pref'))
        env.pop('MATLABPATH', None)
        with (out / 'matlab-console.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(argv, cwd=private, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        write(out / 'process.json', {'exit_code': result.returncode})
        post_inputs = [{'path': x[key], 'sha256': digest(x[key]), 'unchanged': digest(x[key]) == x['sha256']}
                       for x in manifest for key in ('source', 'private')]
        write(out / 'post-source-manifest.json', post_inputs)
        readiness = out / 'readiness.json'
        data = {}
        if readiness.exists():
            data = json.loads(readiness.read_text(encoding='utf-8'))
            actual_paths = sorted({x['resolved_path'] for x in data['dependencies']})
            write(out / 'effective-dependency-hashes.json', [{'path': p, 'sha256': digest(p) if Path(p).is_file() else None} for p in actual_paths])
        post_libraries = [{'path': x['path'], 'sha256': digest(x['path']), 'unchanged': digest(x['path']) == x['sha256']} for x in deps]
        write(out / 'post-library-hashes.json', post_libraries)
        ready = (result.returncode == 0 and data.get('status') == 'ready'
                 and all(x['unchanged'] for x in post_inputs+post_libraries))
        write(out / 'preflight-result.json', {'status': 'ready' if ready else 'blocked',
              'matlab_exit_code': result.returncode, 'cli_exit_code': 0 if ready else 1})
        raise SystemExit(0 if ready else 1)
    print(json.dumps({'prepared': str(out), 'library_roots': libraries, 'installed_files': len(deps), 'callbacks': audit['callbacks']}, indent=2))


if __name__ == '__main__':
    main()
