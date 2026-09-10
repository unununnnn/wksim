"""Cold-build verified generated e0 inputs and compare independent native lifecycles.

No MATLAB process, code generation, flight, or equivalence-to-Simulink claim.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_core.model import Model
from Simulator.wksim_runtime.evidence import json_identity


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,allow_nan=False)


def probe(library,output):
    output.mkdir()
    identity=json_identity(os.getpid())
    mappings=[]
    for reset in (0,1):
        with Model(library) as model,(output/f'cycle-{reset}.jsonl').open('x') as stream:
            mappings.append(Path('/proc/self/maps').read_text())
            for tick in range(1,1001):
                level=0. if tick<=100 else .5 if tick<=600 else .45
                commands=[level]*4+[0.]*12
                values=model.step(commands)
                assert len(values)==120 and all(math.isfinite(value) for value in values)
                stream.write(json.dumps(dict(tick=tick,commands=commands,output=values),
                    separators=(',',':'),allow_nan=False)+'\n')
    write(output/'process.json',dict(identity=identity,library=str(library),library_sha256=sha(library),
        maps=mappings,cycles=[sha(output/f'cycle-{i}.jsonl') for i in (0,1)]))


def run(build_manifest,output):
    if sys.platform!='linux':raise ValueError('Run in Ubuntu-22.04 with /usr/bin/python3')
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(build_manifest.read_text())
    sources=manifest['staged_sources']
    expected={'Exp1_MinModelTemp.cpp','Exp1_MinModelTemp.h','rtwtypes.h','rtw_continuous.h','rtw_solver.h','model.cpp'}
    assert set(sources)==expected
    parents={Path(row['wsl_staged_path']).parent for row in sources.values()}
    assert len(parents)==1
    original=parents.pop().resolve()
    assert original.parent==Path('/root') and original.name.startswith('wksim-codegen-e0-build-')
    original_library=original/'libwksim_e0.so'
    original_summary=json.loads((build_manifest.parent/'summary.json').read_text())
    assert sha(original_library)==original_summary['library_sha256']
    # Freeze the exact sequence and gates before compiling or loading either library.
    write(output/'contract.json',dict(version=1,ticks=1000,dt_s=.001,
        inputs=[dict(first=1,last=100,first_four=0.),dict(first=101,last=600,first_four=.5),
            dict(first=601,last=1000,first_four=.45)],other_twelve=0.,
        output_count=120,clock_absolute_error_s=1e-8,repeat_comparison='exact same inputs/build semantics',
        scope='freshly generated 11.8 cold rebuild and lifecycle; not 11.0 or G6 equivalence',
        build_manifest_sha256=sha(build_manifest),validator_sha256=sha(__file__)))
    cold=Path('/root')/('wksim-codegen-e0-cold-'+uuid.uuid4().hex[:12]);cold.mkdir(mode=0o700)
    checked={}
    for name,row in sources.items():
        source=Path(row['wsl_staged_path'])
        assert not source.is_symlink() and sha(source)==row['sha256']
        shutil.copyfile(source,cold/name)
        assert sha(cold/name)==row['sha256'];checked[name]=row['sha256']
    library=cold/'libwksim_e0.so'
    command=['g++','-std=c++17','-O2','-fno-fast-math','-fPIC','-shared','-Wl,--no-undefined',
        '-I',str(cold),str(cold/'Exp1_MinModelTemp.cpp'),str(cold/'model.cpp'),'-o',str(library)]
    with (output/'build.log').open('x') as log:
        compiled=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    write(output/'build.json',dict(command=command,returncode=compiled.returncode,cold_directory=str(cold),input_sha256=checked))
    if compiled.returncode:raise RuntimeError('Cold build failed; original log retained')
    assert all(sha(cold/name)==value for name,value in checked.items())
    assert sha(library)==original_summary['library_sha256'],'Same compiler/input bytes produced a different binary'
    dependencies=subprocess.run(['ldd',str(library)],capture_output=True,text=True,timeout=10,check=True).stdout
    (output/'ldd.txt').write_text(dependencies)
    assert 'not found' not in dependencies.lower()
    assert not any(word in dependencies.lower() for word in ('matlab','simulink','libmw','mcr','gazebo','libgz'))
    runs=[]
    for name,path in (('original',original_library),('cold',library)):
        directory=output/name
        argv=[sys.executable,'-B',str(Path(__file__).resolve()),'--probe',str(path),'--output',str(directory)]
        with (output/(name+'.log')).open('x') as log:
            child=subprocess.Popen(argv,env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1'),
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            owner=json_identity(child.pid)
            try:code=child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.terminate();child.wait(timeout=10);raise
        run=dict(name=name,command=argv,identity=owner,returncode=code)
        runs.append(run);write(output/(name+'-exit.json'),run)
        assert code==0
    # Re-read every raw row independently of Model.step's own clock/finite guards.
    raw=[]
    for name in ('original','cold'):
        for cycle in (0,1):
            rows=[json.loads(line) for line in (output/name/f'cycle-{cycle}.jsonl').read_text().splitlines()]
            assert len(rows)==1000
            for tick,row in enumerate(rows,1):
                expected_level=0. if tick<=100 else .5 if tick<=600 else .45
                assert row['tick']==tick and row['commands']==[expected_level]*4+[0.]*12
                assert len(row['output'])==120 and all(math.isfinite(x) for x in row['output'])
                assert abs(row['output'][2]-tick/1000)<=1e-8
            raw.append(rows)
        process=json.loads((output/name/'process.json').read_text())
        for maps in process['maps']:
            assert not any(word in maps.lower() for word in ('matlab','simulink','libmw','mcr','copterSim.exe'.lower(),'libgz'))
    assert all(rows==raw[0] for rows in raw[1:]),'Native cold reset/rebuild outputs differ'
    assert runs[0]['identity']['pid']!=runs[1]['identity']['pid']
    write(output/'audit.json',dict(status='pass',schema='wksim.generated-e0-lifecycle.v1',runs=runs,
        ticks_per_cycle=1000,cycles=4,compared_values=4*1000*120,clock_tolerance_s=1e-8,
        library_sha256=sha(library),cold_library=str(library),source_sha256=checked,
        raw_sha256={f'{name}/cycle-{cycle}.jsonl':sha(output/name/f'cycle-{cycle}.jsonl')
            for name in ('original','cold') for cycle in (0,1)},
        limitation='Independent Linux reconstruction and reset only; no flight or MATLAB numeric oracle'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path);parser.add_argument('--probe',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.probe:probe(args.probe,args.output)
    elif args.manifest:run(args.manifest,args.output)
    else:parser.error('Select --manifest or --probe')
