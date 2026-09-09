"""Prepare an independent attitude source candidate; no build, overlay install or admission."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot, sha

BASE = Path('/root/wksim-ap-mixed-fhuf05l9')
BASE_SHA = '1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c'
COMMIT = '1511f27194f1dcc3728270883047bdf022b3fd53'
PATCH = REPO/'patches/arducopter/0006-dds-attitude-thrust.patch'


def baseline():
    raw = (BASE/'mixed-build.json').read_bytes()
    if sha(raw) != BASE_SHA:
        raise ValueError('Mixed build manifest changed')
    build = json.loads(raw)
    raw_source = (BASE/'mixed-source.json').read_bytes()
    if sha(raw_source) != build['source_manifest_sha256']:
        raise ValueError('Mixed source manifest changed')
    source = json.loads(raw_source)['source']
    if source_snapshot(BASE/'src', commit=COMMIT) != source:
        raise ValueError('Mixed source differs from sealed manifest')
    if sha((BASE/'build/sitl/bin/arducopter').read_bytes()) != build['artifacts']['build/sitl/bin/arducopter']:
        raise ValueError('Mixed binary differs from sealed manifest')
    return source


def prepare():
    before = baseline()
    root = Path(tempfile.mkdtemp(prefix='wksim-ap-attitude-', dir='/root'))
    (root/'baseline-mixed-build.json').write_bytes((BASE/'mixed-build.json').read_bytes())
    (root/'candidate.patch').write_bytes(PATCH.read_bytes())
    shutil.copy2(__file__, root/'prepare_ap_attitude_candidate.py')
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE/'src'), str(root/'src')], check=True)
    source = root/'src'
    if not (source/'.git').is_dir() or (source/'.git').resolve() != source/'.git':
        raise ValueError('Candidate must own its Git directory')
    top = subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(top).resolve() != source or source_snapshot(source, commit=COMMIT) != before:
        raise ValueError('Candidate source copy escaped or differs from mixed baseline')
    for options in (('--check', '--whitespace=error'), ('--whitespace=error',)):
        subprocess.run(['git', '-C', str(source), 'apply', *options, str(root/'candidate.patch')], check=True)
    # Candidate-only hardware definition: original macro/default stays closed.
    (root/'attitude-extra.hwdef').write_text('define AP_DDS_WKSIM_ATTITUDE_ENABLED 1\n')
    after = source_snapshot(source, commit=COMMIT)
    if baseline() != before:
        raise ValueError('Mixed baseline changed during preparation')
    record = dict(schema_version=1, status='source-only-not-built-not-admitted',
        profile='attitude_thrust_v1', candidate_root=str(root), baseline_root=str(BASE), commit=COMMIT,
        baseline_manifest_sha256=BASE_SHA, patch_sha256=sha(PATCH.read_bytes()),
        prepare_sha256=sha(Path(__file__).read_bytes()),
        extra_hwdef_sha256=sha((root/'attitude-extra.hwdef').read_bytes()), source=after,
        production_admitted=False, flown=False)
    manifest = root/'attitude-source.json'
    with manifest.open('x') as stream:
        stream.write(json.dumps(record, indent=2, sort_keys=True)+'\n')
    return dict(candidate_root=str(root), manifest=str(manifest), manifest_sha256=sha(manifest.read_bytes()))


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(prepare()))
