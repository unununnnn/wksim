"""Prepare an isolated AP P+V source candidate. Never build, install or admit it."""
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

BASE = Path('/root/wksim-ap-clock-stop-OXQqdR')
MANIFEST_SHA = 'f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a'
COMMIT = '1511f27194f1dcc3728270883047bdf022b3fd53'
PATCH = REPO / 'Simulator/firmware/ap-pv-candidate/0004-dds-global-position-velocity.patch'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raw = (BASE / 'wksim-build.json').read_bytes()
    if sha(raw) != MANIFEST_SHA:
        raise ValueError('Fixed source manifest changed')
    baseline = json.loads(raw)
    before = source_snapshot(BASE / 'src', commit=COMMIT)
    if before != baseline['source']:
        raise ValueError('Fixed source no longer matches its manifest')
    patch_raw = PATCH.read_bytes()
    candidate = Path(tempfile.mkdtemp(prefix='wksim-ap-pv-', dir='/root'))
    # Preserve source provenance before any candidate mutation.
    (candidate / 'baseline-manifest.json').write_bytes(raw)
    (candidate / 'candidate.patch').write_bytes(patch_raw)
    shutil.copy2(__file__, candidate / 'prepare_ap_pv_candidate.py')
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE / 'src'), str(candidate / 'src')], check=True)
    checkout = candidate / 'src'
    if not (checkout / '.git').is_dir() or (checkout / '.git').resolve() != checkout / '.git':
        raise ValueError('Candidate must own an independent Git directory')
    top = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(top).resolve() != checkout.resolve():
        raise ValueError('Candidate Git operations escape the new checkout')
    if source_snapshot(candidate / 'src', commit=COMMIT) != before:
        raise ValueError('Copied candidate differs from baseline')
    for args in [('--check',), ()]:
        subprocess.run(['git', '-C', str(candidate / 'src'), 'apply', *args,
                        str(candidate / 'candidate.patch')], check=True)
    subprocess.run(['git', '-C', str(candidate / 'src'), 'diff', '--check'], check=True)
    after = source_snapshot(candidate / 'src', commit=COMMIT)
    if source_snapshot(BASE / 'src', commit=COMMIT) != before or sha((BASE / 'wksim-build.json').read_bytes()) != MANIFEST_SHA:
        raise ValueError('Baseline changed during preparation')
    record = dict(schema_version=1, status='source-only-not-built-not-admitted',
                  candidate_root=str(candidate), baseline_root=str(BASE), commit=COMMIT,
                  baseline_manifest_sha256=MANIFEST_SHA, patch_sha256=sha(patch_raw),
                  prepare_sha256=sha(Path(__file__).read_bytes()), source=after)
    manifest = candidate / 'pv-source.json'
    manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(candidate_root=str(candidate), manifest=str(manifest),
                          manifest_sha256=sha(manifest.read_bytes()))))


if __name__ == '__main__':
    main()
