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
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_core.model import Model
from Simulator.wksim_runtime.evidence import json_identity

EXPECTED_BUILD_SOURCES=frozenset({'Exp1_MinModelTemp.cpp','Exp1_MinModelTemp.h','rtwtypes.h',
    'rtw_continuous.h','rtw_solver.h','model.cpp'})
COLD_ROOT=Path('/root')
COLD_PREFIX='wksim-codegen-e0-build-'


class AdmissionError(ValueError):
    """Input rejected before any output directory, cold directory or compiler run."""


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,allow_nan=False)


def read_regular(path,label):
    """Read a non-symlinked regular file once, returning its bytes."""
    path=Path(path)
    if path.is_symlink():raise AdmissionError(f'{label} is a symlink: {path}')
    if not path.is_file():raise AdmissionError(f'{label} is not a regular file: {path}')
    try:return path.read_bytes()
    except OSError as exc:raise AdmissionError(f'{label} cannot be read: {exc}') from exc


def load_build_manifest(build_manifest):
    """Read the build manifest once and bind its identity to those exact bytes."""
    data=read_regular(build_manifest,'build manifest')
    try:manifest=json.loads(data.decode('utf-8'))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise AdmissionError(f'build manifest is unreadable or malformed JSON: {exc}') from exc
    if not isinstance(manifest,dict):raise AdmissionError('build manifest root must be a JSON object')
    return manifest,hashlib.sha256(data).hexdigest()


def resolve_build_root(root):
    """Bound a staged root to /root, following symlinks to their real directory."""
    if root.is_symlink():
        raise AdmissionError(f'staged parent is a symlink: {root} -> {root.resolve()}')
    if not root.is_dir():
        raise AdmissionError(f'staged parent is not a directory: {root}')
    if root.parent!=COLD_ROOT or not root.name.startswith(COLD_PREFIX):
        raise AdmissionError(f'staged parent escapes the frozen build root: {root}')
    resolved=root.resolve()
    if resolved!=root:
        raise AdmissionError(f'staged parent is a non-canonical path: {root} -> {resolved}')
    return resolved


def source_root(sources):
    """Resolve the single staged root and bind every key to its own filename."""
    if not isinstance(sources,dict):raise AdmissionError('staged_sources must be a JSON object')
    if set(sources)!=EXPECTED_BUILD_SOURCES:
        raise AdmissionError(f'staged_sources set differs from the six expected sources: '
            f'missing={sorted(EXPECTED_BUILD_SOURCES-set(sources))} extra={sorted(set(sources)-EXPECTED_BUILD_SOURCES)}')
    parents=set()
    for name,row in sources.items():
        if not isinstance(row,dict):raise AdmissionError(f'staged_sources.{name} must be a JSON object')
        value=row.get('wsl_staged_path')
        if not isinstance(value,str) or not value.startswith('/') or not value:
            raise AdmissionError(f'staged_sources.{name}.wsl_staged_path must be an absolute POSIX path')
        if '\x00' in value:raise AdmissionError(f'staged_sources.{name}.wsl_staged_path contains a NUL byte')
        if Path(value).name!=name:
            raise AdmissionError(f'staged_sources.{name} filename does not match its key: {Path(value).name}')
        parents.add(Path(value).parent)
    if len(parents)!=1:
        raise AdmissionError(f'sources do not share exactly one staged parent: {sorted(str(item) for item in parents)}')
    return resolve_build_root(parents.pop())


def read_verified_sources(sources):
    """Read all six sources into memory and verify every hash. Nothing is written.

    This is the whole verification pass: if any source is missing, linked or
    disagrees with its recorded identity, the caller fails before the first
    snapshot byte exists.  The total size is small, so holding the bytes is
    cheaper than a second read.
    """
    verified={}
    for name,row in sources.items():
        data=read_regular(row['wsl_staged_path'],f'staged source {name}')
        digest=hashlib.sha256(data).hexdigest()
        if digest!=row.get('sha256'):
            raise AdmissionError(f'staged source hash differs for {name}: expected {row.get("sha256")} observed {digest}')
        verified[name]=(data,digest)
    return verified


def write_snapshot_sources(snapshot,verified):
    """Write the already-verified bytes, re-hashing each copy as it lands."""
    for name,(data,digest) in verified.items():
        (snapshot/name).write_bytes(data)
        if sha(snapshot/name)!=digest:
            raise AdmissionError(f'snapshot copy is not byte-identical for {name}')
    return {name:digest for name,(_,digest) in verified.items()}


def check_library_identity(original,summary_path):
    """Bind the original library, its recorded hash and its size before any write."""
    summary_path=Path(summary_path)
    if summary_path.is_symlink() or not summary_path.is_file():
        raise AdmissionError(f'summary.json is not a regular file beside the build manifest: {summary_path}')
    try:summary=json.loads(summary_path.read_text(encoding='utf-8'))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:
        raise AdmissionError(f'summary.json is unreadable or malformed JSON: {exc}') from exc
    recorded=summary.get('library_sha256') if isinstance(summary,dict) else None
    if not isinstance(recorded,str) or len(recorded)!=64:
        raise AdmissionError('summary.json.library_sha256 must be a 64-character hex digest')
    library=original/'libwksim_e0.so'
    if library.is_symlink() or not library.is_file():
        raise AdmissionError(f'original library is not a regular file: {library}')
    observed=sha(library)
    if observed!=recorded:
        raise AdmissionError(f'original library hash differs from summary.json: expected {recorded} observed {observed}')
    size=int(summary.get('library_size_bytes',library.stat().st_size))
    if size!=library.stat().st_size:
        raise AdmissionError(f'original library size differs from summary.json: expected {size} observed {library.stat().st_size}')
    return summary,library,observed


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
    output=Path(output)
    # --- Admission: nothing is created, compiled or loaded before this passes. --
    # Any existing output path is a rejected input, including an empty
    # directory, so mkdir(exist_ok=False) can never fail after the snapshot.
    if output.is_symlink():raise AdmissionError(f'output is a symlink: {output}')
    if output.exists():raise AdmissionError(f'output path already exists: {output}')
    build_manifest=Path(build_manifest)
    manifest,manifest_sha256=load_build_manifest(build_manifest)
    sources=manifest['staged_sources']
    original=source_root(sources)
    # Read-only: all six sources into memory, every hash checked, library bound.
    verified_sources=read_verified_sources(sources)
    original_summary,original_library,original_library_sha256=check_library_identity(
        original,build_manifest.parent/'summary.json')
    original_library_bytes=read_regular(original_library,'original library')
    if hashlib.sha256(original_library_bytes).hexdigest()!=original_library_sha256:
        raise AdmissionError('original library changed after its identity was verified')
    # Freeze the exact sequence and gates before compiling or loading either library.
    contract=dict(version=1,ticks=1000,dt_s=.001,
        inputs=[dict(first=1,last=100,first_four=0.),dict(first=101,last=600,first_four=.5),
            dict(first=601,last=1000,first_four=.45)],other_twelve=0.,
        output_count=120,clock_absolute_error_s=1e-8,repeat_comparison='exact same inputs/build semantics',
        scope='freshly generated 11.8 cold rebuild and lifecycle; not 11.0 or G6 equivalence',
        build_manifest_sha256=manifest_sha256,validator_sha256=sha(__file__))
    # --- Everything above was read-only.  The first write happens below. ------
    # The snapshot is private to this run.  Any failure before the run completes
    # removes it again; nothing outside the snapshot is ever cleaned up here.
    output=output.resolve()
    snapshot=Path(tempfile.mkdtemp(prefix='wksim-validate-e0-lifecycle-'))
    try:
        shutil.copyfile(build_manifest,snapshot/'build-manifest.json')
        if sha(snapshot/'build-manifest.json')!=manifest_sha256:
            raise AdmissionError('snapshot build manifest is not byte-identical to the verified manifest')
        checked=write_snapshot_sources(snapshot,verified_sources)
        (snapshot/'libwksim_e0.so').write_bytes(original_library_bytes)
        output.mkdir(parents=True,exist_ok=False)
        write(output/'contract.json',contract)
        cold=Path('/root')/('wksim-codegen-e0-cold-'+uuid.uuid4().hex[:12]);cold.mkdir(mode=0o700)
        for name in sorted(checked):shutil.copyfile(snapshot/name,cold/name)
        library=cold/'libwksim_e0.so'
        command=['g++','-std=c++17','-O2','-fno-fast-math','-fPIC','-shared','-Wl,--no-undefined',
            '-I',str(cold),str(cold/'Exp1_MinModelTemp.cpp'),str(cold/'model.cpp'),'-o',str(library)]
        with (output/'build.log').open('x') as log:
            compiled=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        write(output/'build.json',dict(command=command,returncode=compiled.returncode,cold_directory=str(cold),input_sha256=checked))
        if compiled.returncode:raise RuntimeError('Cold build failed; original log retained')
        assert all(sha(cold/name)==value for name,value in checked.items())
        assert sha(library)==original_library_sha256,'Same compiler/input bytes produced a different binary'
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
    except BaseException:
        # Failed runs clean up only their own snapshot; other files are untouched.
        shutil.rmtree(snapshot,ignore_errors=True)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path);parser.add_argument('--probe',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.probe:probe(args.probe,args.output)
    elif args.manifest:run(args.manifest,args.output)
    else:parser.error('Select --manifest or --probe')
