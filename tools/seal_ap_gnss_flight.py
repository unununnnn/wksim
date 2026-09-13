"""Seal the complete candidate source delta and built DDS artifacts; no flight."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot

BASE=Path('/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json')
BASE_SHA='f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a'
COMMIT='1511f27194f1dcc3728270883047bdf022b3fd53'
CHANGED={'libraries/SITL/SIM_JSON.cpp','libraries/SITL/SIM_GPS.cpp','libraries/SITL/SIM_WksimGNSS.h'}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(root):
    root=root.resolve(strict=True)
    if root.parent!=Path('/root') or not root.name.startswith('wksim-ap-gnss-flight-'):
        raise ValueError('Invalid candidate root')
    if digest(BASE)!=BASE_SHA:raise ValueError('Baseline manifest differs')
    baseline=json.loads(BASE.read_text())
    record=json.loads((root/'scheduled-build.json').read_text())
    if record['build_exit']!=0 or not record['source_unchanged']:raise ValueError('Unsuccessful/unsealed build')
    if digest(root/'identity.json')!=record['identity_sha256']:raise ValueError('Build identity changed')
    for name,checksum in record['sources_sha256'].items():
        if digest(REPO/name)!=checksum:raise ValueError('Build source changed: '+name)
    source=source_snapshot(root/'src',commit=COMMIT)
    before=baseline['source']['files'];after=source['files']
    delta={name for name in set(before)|set(after) if before.get(name)!=after.get(name)}
    if delta!=CHANGED or source['deleted_tracked']!=baseline['source']['deleted_tracked']:
        raise ValueError('Unexpected native source delta: '+repr(sorted(delta)))
    identity=json.loads((root/'identity.json').read_text())
    binary=root/'build/sitl/bin/arducopter'
    if digest(binary)!=identity['binary_sha256']:raise ValueError('Built binary changed')
    generated=root/'build/sitl/libraries/AP_DDS/generated'
    artifacts={str(p.relative_to(root)):digest(p) for p in generated.rglob('*') if p.is_file()}
    if not artifacts:raise ValueError('DDS generated artifacts missing')
    result=dict(schema='wksim.ap-gnss-flight-seal.v1',root=str(root),baseline_manifest_sha256=BASE_SHA,
        scheduled_build_sha256=digest(root/'scheduled-build.json'),source=source,
        source_delta=sorted(delta),binary_sha256=digest(binary),generated_sha256=artifacts,
        build_log_sha256=digest(root/'build.log'),configure_log_sha256=digest(root/'configure.log'),
        sealer_sha256=digest(__file__),flown=False,production_admitted=False)
    with (root/'flight-seal.json').open('x') as output:json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(dict(manifest=str(root/'flight-seal.json'),sha256=digest(root/'flight-seal.json'),
                         source_files=len(after),changed=result['source_delta'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    seal(parser.parse_args().root)
