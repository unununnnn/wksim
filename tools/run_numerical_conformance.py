"""Execute only the three frozen #23 cases, retaining all attempts and strict failures."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import traceback
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'Simulator/wksim_core/numerical-conformance-v1.json'
CONTRACT_SHA = '23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0'
BUILD = '/root/wksim-major-recorder-j_3guvtn/build.json'
BUILD_SHA = '6e16102ae1197a899eef554b9c938f5ca32220516fdd8630c7b8b1b19267cce3'
EXE_SHA = 'c685817a974471113793fde3c78eeed26f7c7b56eef1194f9df1fd2ecf7e8d49'
MATLAB = 'D:/matlab/install date/bin/matlab.exe'
WSL = ['wsl.exe', '-d', 'Ubuntu-22.04', '--exec']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned(path, expected):
    require(digest(path) == expected, f'Hash mismatch: {path}')
    return {'path': str(path), 'sha256': expected}


def wsl_path(path):
    return subprocess.check_output(WSL+['wslpath', '-a', '-u', str(path)], text=True).strip()


def target_identity():
    raw = subprocess.check_output(WSL+['cat', BUILD])
    require(hashlib.sha256(raw).hexdigest() == BUILD_SHA, 'Build manifest changed')
    build = json.loads(raw)
    paths = {BUILD: BUILD_SHA, build['executable']: EXE_SHA}
    source = build['source']; directory = build['directory']
    for member, sha in source['members_sha256'].items():
        name = Path(member).name
        if name == 'Exp1_MinModelTemp.cpp':
            name = 'Exp1_MinModelTemp.original.cpp'
        paths[directory+'/'+name] = sha
    paths[directory+'/Exp1_MinModelTemp.cpp'] = source['patched_cpp_sha256']
    paths[directory+'/major_model_recorder.cpp'] = source['driver_sha256']
    paths[directory+'/build_major_model_recorder.py'] = source['builder_sha256']
    output = subprocess.check_output(WSL+['sha256sum', *paths], text=True)
    for line in output.splitlines():
        sha, path = line.split(maxsplit=1)
        require(paths[path] == sha, f'Target identity changed: {path}')
    return build, raw, paths


def run_process(argv, out, prefix, cwd, env=None):
    status = {'argv': argv, 'cwd': str(cwd), 'started_unix_ns': time.time_ns()}
    write(out / (prefix+'-process.json'), status)
    with (out / (prefix+'.stdout.log')).open('wb') as stdout, (out / (prefix+'.stderr.log')).open('wb') as stderr:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr)
        status['pid'] = process.pid
        write(out / (prefix+'-process.json'), status)
        try:
            status['exit_code'] = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            # A timeout is invalid evidence. Explicitly terminate the process tree on Windows.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            status['exit_code'] = process.wait()
            status['timeout'] = True
    status['ended_unix_ns'] = time.time_ns()
    write(out / (prefix+'-process.json'), status)
    return status


def binary_rows(path, columns):
    raw = Path(path).read_bytes()
    require(len(raw) == 501*columns*8, f'Wrong binary length: {path}')
    rows = list(struct.iter_unpack('<'+'d'*columns, raw))
    require(all(math.isfinite(v) for row in rows for v in row), f'Nonfinite binary: {path}')
    return rows


def compare(out, contract, manifest, build):
    for side in ('reference', 'target'):
        p = read(out / (side+'-process.json'))
        require(p.get('exit_code') == 0 and not p.get('timeout'), f'{side} process failed')
    ref = read(out / 'reference.json')
    require(ref['status'] == 'complete', 'Reference incomplete')
    for key in ('case', 'epoch', 'contract_sha256'):
        require(ref[key] == manifest[key], f'Reference identity: {key}')
    inputs = [[float(x) for x in row] for row in list(csv.reader((out/'input.csv').read_text().splitlines()))[1:]]
    require(binary_rows(out/'applied-input.f64', 33) == [tuple(r) for r in inputs], 'Reference parsed input differs')
    records = [json.loads(line) for line in (out/'target.stdout.log').read_text().splitlines()]
    require(len(records) == 503, 'Target record count')
    start, *samples, end = records
    require(all(r['schema_version'] == 1 for r in records), 'Target schema')
    require(start['kind'] == 'major_recorder_start' and start['source'] == build['source'], 'Target source')
    require(start['input_csv'].encode('ascii') == (out/'input.csv').read_bytes(), 'Target raw CSV differs')
    require(start['expected_calls'] == 501 and start['comparison_end_s'] == .5 and start['expected_engine_end_s'] == .501, 'Start schedule')
    require(end['kind'] == 'major_recorder_end' and end['status'] == 'complete', 'Missing complete end')
    require(all(end[k] == 501 for k in ('attempted_calls', 'returned_calls', 'emitted_samples')), 'End counts')
    require(end['comparison_end_s'] == .5 and abs(end['engine_end_s']-.501) <= 1e-12, 'End schedule')
    references = {}
    for name, width in contract['sampling']['array_lengths'].items():
        rows = binary_rows(out/(name+'.f64'), width+1)
        require(all(abs(row[0]-k*.001) <= 1e-12 for k, row in enumerate(rows)), f'{name} time')
        require(all(rows[k][0] < rows[k+1][0] for k in range(500)), f'{name} order')
        references[name] = rows
    for k, sample in enumerate(samples):
        require(sample['kind'] == 'major_recorder_sample' and sample['k'] == k and sample['call_number'] == k+1, 'Sample order')
        require(sample['major_capture_count'] == 1 and sample['step_status'] == 'complete', 'Capture/step status')
        for key, value in [('input_time_s', inputs[k][1]), ('engine_before_s', k*.001), ('engine_after_s', (k+1)*.001)]:
            require(math.isfinite(sample[key]) and abs(sample[key]-value) <= 1e-12, f'Target clock {key}')
        require(sample['inPWMs'] == inputs[k][2:18] and sample['TerrainIn15d'] == inputs[k][18:], 'Applied target inputs')
        for phase in ('major_root_outputs', 'post_step_api'):
            for name, width in contract['sampling']['array_lengths'].items():
                values = sample[phase][name]
                require(len(values) == width and all(type(x) in (int, float) and math.isfinite(x) for x in values), f'{phase} {name} malformed')
    stats = []; failures = []
    groups = contract['observables']
    covered = set()
    for group in groups:
        require(group['rule'] == 'finite_binary64_value_equal' and group['absolute_budget'] == group['relative_budget'] == 0, 'Unsupported frozen comparison')
        name = group['array']
        for index in group['indices']:
            require((name,index) not in covered, 'Duplicate scalar'); covered.add((name,index))
            errors = []; failed = []
            for k, sample in enumerate(samples):
                r = references[name][k][index+1]; x = float(sample['major_root_outputs'][name][index])
                errors.append(abs(x-r))
                if x != r:
                    f = {key: manifest[key] for key in ('case','epoch','contract_sha256')}
                    f.update(array=name,index=index,k=k,reference=r,target=x,reference_hex=r.hex(),target_hex=x.hex(),absolute_error=abs(x-r))
                    failures.append(f); failed.append(f)
            first = failed[0] if failed else {}
            stats.append(dict(case=manifest['case'],array=name,index=index,native_unit=group['native_unit'],
                semantic_status=group['semantic_status'],sample_count=501,failed_count=len(failed),
                max_abs_error=max(errors),rms_error=math.hypot(*errors)/math.sqrt(501),
                first_failure_k=first.get('k'),first_failure_reference=first.get('reference'),first_failure_target=first.get('target')))
    require(len(covered) == 120, 'Scalar coverage')
    write(out/'per-scalar.json',stats)
    with (out/'failures.jsonl').open('w',encoding='utf-8') as f:
        for row in failures:
            f.write(json.dumps(row,allow_nan=False)+'\n')
    return dict(status='numerical_failed' if failures else contract['reporting']['numerical_pass_label'],
        execution_status='valid',scalar_count=120,sample_count=501,comparisons=60120,
        failed_scalars=sum(s['failed_count']>0 for s in stats),failed_values=len(failures),
        physical_accuracy_status='unverified')


def execute_case(base, case, contract):
    out = base/case['id']; out.mkdir()
    stage=out/'staged-model'; stage.mkdir()
    build, build_raw, target_hashes = target_identity()
    shutil.copyfile(CONTRACT,out/'contract.json')
    (out/'build.json').write_bytes(build_raw)
    identities=[]
    for key, name in [('slx','Exp1_MinModelTemp.slx'),('init','Exp1_MinModelTemp_init.m')]:
        item=contract['identity'][key]; source=Path(item['path'])
        identities.append(pinned(source,item['sha256'])); shutil.copyfile(source,stage/name)
        identities.append(pinned(stage/name,item['sha256']))
    for key, name in [('reference_readiness','readiness.json'),('parameter_bindings','parameter-bindings.json'),('effective_dependencies','dependencies.json')]:
        item=contract['identity'][key]; source=ROOT/item['path']
        identities.append(pinned(source,item['sha256'])); shutil.copyfile(source,out/name)
        identities.append(pinned(out/name,item['sha256']))
    item=contract['identity']['archive']; identities.append(pinned(item['path'],item['sha256']))
    with zipfile.ZipFile(item['path']) as archive:
        for member, sha in build['source']['members_sha256'].items():
            require(hashlib.sha256(archive.read(member)).hexdigest()==sha,'Archive member changed')
    identities += [pinned(d['path'],d['sha256']) for d in read(out/'dependencies.json')]
    item=case['input']; source=ROOT/item['path']; identities.append(pinned(source,item['sha256']))
    shutil.copyfile(source,out/'input.csv'); identities.append(pinned(out/'input.csv',item['sha256']))
    identities.append(pinned(out/'contract.json',CONTRACT_SHA))
    for path in [Path(__file__),ROOT/'tools/export_model_reference.m',ROOT/'tools/major_model_recorder.cpp',ROOT/'tools/build_major_model_recorder.py']:
        identities.append(pinned(path,digest(path)))
        target=stage/path.name if path.suffix=='.m' else out/path.name
        shutil.copyfile(path,target); identities.append(pinned(target,digest(path)))
    for folder in ('temp','pref','cache','codegen'): (out/folder).mkdir()
    env=os.environ.copy(); env.pop('MATLABPATH',None)
    overrides={key:str(out/folder) for key,folder in [('TEMP','temp'),('TMP','temp'),('MATLAB_PREFDIR','pref')]}
    env.update(overrides)
    reference_argv=[MATLAB,'-wait','-sd',str(stage),'-batch','export_model_reference']
    target_argv=WSL+[build['executable'],'--record',wsl_path(out/'input.csv')]
    manifest=dict(case=case['id'],epoch=uuid.uuid4().hex,contract_sha256=CONTRACT_SHA,
        frozen_unix_ns=time.time_ns(),input_sha256=item['sha256'],identities=identities,
        target_hashes=target_hashes,build_sha256=BUILD_SHA,reference_argv=reference_argv,target_argv=target_argv,
        reference_cwd=str(stage),target_cwd=str(ROOT),environment_overrides=overrides,
        scope='strict cross-version native conformance, no physical fidelity claim')
    write(out/'manifest.json',manifest)
    print(f"{case['id']}: frozen {manifest['epoch']}; executing reference",flush=True)
    run_process(reference_argv,out,'reference',stage,env)
    print(f"{case['id']}: reference exited; executing target",flush=True)
    run_process(target_argv,out,'target',ROOT)
    try:
        post=[pinned(i['path'],i['sha256']) for i in identities]
        target_identity(); write(out/'post-identities.json',post)
        result=compare(out,contract,manifest,build)
    except Exception as error:
        result=dict(status='invalid_run_not_pass',error=str(error),traceback=traceback.format_exc())
    result.update(case=case['id'],epoch=manifest['epoch'],contract_sha256=CONTRACT_SHA)
    write(out/'result.json',result); print(json.dumps(result),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Execute the frozen cases in fresh processes')
    parser.add_argument('--cases',nargs='+',choices=['C0','C2G','C3G'],default=['C0','C2G','C3G'])
    args=parser.parse_args(); require(args.run,'Use --run to explicitly execute models')
    pinned(CONTRACT,CONTRACT_SHA); contract=read(CONTRACT)
    out=Path(tempfile.mkdtemp(prefix='numerical-conformance-',dir=ROOT/'validation'))
    print(str(out),flush=True); results=[]
    for case in contract['cases']:
        if case['id'] not in args.cases: continue
        try: results.append(execute_case(out,case,contract))
        except Exception as error:
            result=dict(case=case['id'],status='invalid_run_not_pass',error=str(error),traceback=traceback.format_exc())
            write(out/(case['id']+'-preflight-failure.json'),result); results.append(result); print(json.dumps(result),flush=True)
    write(out/'summary.json',results)
    raise SystemExit(2 if any(r['status']=='invalid_run_not_pass' for r in results) else 1 if any(r['status']=='numerical_failed' for r in results) else 0)


if __name__=='__main__':
    main()
