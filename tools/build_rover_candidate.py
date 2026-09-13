"""Build ArduRover in an independent candidate copied from retained AP source."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot,sha

BASE=Path('/root/wksim-ap-clock-stop-OXQqdR')
PARENT_SHA='f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a'
COMMIT='1511f27194f1dcc3728270883047bdf022b3fd53'


def build():
    raw=(BASE/'wksim-build.json').read_bytes()
    if sha(raw)!=PARENT_SHA:raise ValueError('Retained AP source receipt changed')
    parent=json.loads(raw)
    if source_snapshot(BASE/'src',commit=COMMIT)!=parent['source']:
        raise ValueError('Retained AP source changed')
    root=Path(tempfile.mkdtemp(prefix='wksim-rover-model-',dir='/root'))
    print(json.dumps({'candidate_root':str(root)}),flush=True)
    shutil.copyfile(__file__,root/'builder.py')
    subprocess.run(['cp','-a','--reflink=auto',str(BASE/'src'),str(root/'src')],check=True)
    source=root/'src'
    configure=['./waf','configure','--board','sitl','--out',str(root/'build')]
    compile_argv=['./waf','rover','-j4']
    record=dict(schema='wksim.rover-candidate.v1',family='ardupilot',firmware_target='rover',
        vehicle_class='ground_vehicle',source_root=str(source),candidate_root=str(root),
        upstream_commit=COMMIT,parent_manifest_sha256=PARENT_SHA,
        configure_argv=configure,build_argv=compile_argv,production_admitted=False,
        control_stage='native_rover',builder_sha256=sha((root/'builder.py').read_bytes()))
    (root/'prepared.json').write_text(json.dumps(record,indent=2)+'\n')
    for argv,name in ((configure,'configure.log'),(compile_argv,'build.log')):
        with (root/name).open('w') as log:
            subprocess.run(argv,cwd=source,stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=root/'build/sitl/bin/ardurover'
    record.update(state='built',binary=str(binary),binary_sha256=sha(binary.read_bytes()),
                  source=source_snapshot(source,commit=COMMIT))
    manifest=root/'candidate.json'
    manifest.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'manifest':str(manifest),'sha256':sha(manifest.read_bytes())}),flush=True)


if __name__=='__main__':build()
