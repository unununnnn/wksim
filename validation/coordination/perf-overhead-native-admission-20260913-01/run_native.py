"""Main-owned bounded native admission for the synthetic perf overhead driver."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess


root = Path(__file__).resolve().parent
repo = root.parents[2]
assert not (root / 'receipt.json').exists()
ancestor = subprocess.run([
    'git', '-C', str(repo), 'merge-base', '--is-ancestor',
    'f333316e6efa6b299b4288a9d91fb2bccedfb9d6', 'HEAD'
])
assert ancestor.returncode == 0
source_head = subprocess.check_output(
    ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()

precheck_source = root.parent / 'perf-counter-integration-20260913-01' / 'run_checks.py'
tree = ast.parse(precheck_source.read_text(encoding='utf-8'))
pre = next(ast.literal_eval(node.value) for node in tree.body
           if isinstance(node, ast.Assign)
           and isinstance(node.targets[0], ast.Name)
           and node.targets[0].id == 'pre')
checks = []
for distro in ('Ubuntu-22.04', 'RflySim-20.04'):
    result = subprocess.run(
        ['wsl.exe', '-d', distro, '-u', 'root', '--', 'python3', '-'],
        input=pre, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    check = json.loads([line for line in result.stdout.splitlines()
                        if line.startswith('{')][-1])
    assert not check['found'], check
    checks.append(check)
(root / 'prechecks.json').write_text(json.dumps(checks, indent=2) + '\n', encoding='utf-8')

driver = root.parent / 'ds-perf-overhead-driver-20260913-01'
recorder = root.parent / 'ds-perf-stream-recorder-20260913-01'
consumer = root.parent / 'ds-perf-stream-consumer-20260913-01'
paths = {
    'bench_overhead.c': driver / 'bench_overhead.c',
    'fault_inject.c': driver / 'fault_inject.c',
    'analyze_overhead.py': driver / 'analyze_overhead.py',
    'test_analyze_overhead.py': driver / 'test_analyze_overhead.py',
    'wksim_perf_stream.c': recorder / 'wksim_perf_stream.c',
    'wksim_perf_stream.h': recorder / 'wksim_perf_stream.h',
    'perf_stream_consumer.py': consumer / 'perf_stream_consumer.py',
}
source_sha256 = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for name, path in paths.items()}
assert source_sha256['wksim_perf_stream.c'] == (
    'aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2')
assert source_sha256['wksim_perf_stream.h'] == (
    'ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823')
assert source_sha256['perf_stream_consumer.py'] == (
    'dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc')
sources = {name: base64.b64encode(path.read_bytes()).decode('ascii')
           for name, path in paths.items()}
snapshot = root / 'sources'
snapshot.mkdir()
(snapshot / '.gitattributes').write_text('* -text\n', encoding='utf-8')
for name, encoded in sources.items():
    (snapshot / name).write_bytes(base64.b64decode(encoded))

payload = {'checks': checks, 'sources': sources, 'source_sha256': source_sha256}
linux = r'''
import base64
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import tempfile
import time

boot = pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert all(check['boot_id'] == boot and not check['found']
           and 0 <= time.time() - check['checked_unix'] <= 60
           for check in payload['checks'])
work = pathlib.Path(tempfile.mkdtemp(prefix='wksim-overhead-native-', dir='/root'))
for name, encoded in payload['sources'].items():
    (work / name).write_bytes(base64.b64decode(encoded))
assert {name: hashlib.sha256((work / name).read_bytes()).hexdigest()
        for name in payload['sources']} == payload['source_sha256']
(work / 'home').mkdir()
clean_env = {
    'HOME': str(work / 'home'),
    'LANG': 'C',
    'LC_ALL': 'C',
    'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
}
out = {
    'directory': str(work),
    'boot_id': boot,
    'source_sha256': payload['source_sha256'],
    'commands': [],
    'checks': [],
}

def invoke(name, argv, timeout=20, extra_env=None):
    env = dict(clean_env)
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        argv, cwd=work, env=env, start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    try:
        os.killpg(process.pid, 0)
        pgid_empty = False
    except ProcessLookupError:
        pgid_empty = True
    row = {
        'name': name, 'argv': argv, 'pid': process.pid,
        'exit_code': process.returncode, 'timed_out': timed_out,
        'pgid_empty': pgid_empty, 'stdout': stdout, 'stderr': stderr,
    }
    out['commands'].append(row)
    return row

def check(name, condition, detail):
    out['checks'].append({'name': name, 'ok': bool(condition), 'detail': detail})

flags = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread', '-I.']
builds = [
    invoke('build-shared-recorder', flags + ['-shared', '-fPIC', '-o',
           'libwksim_perf_stream.so', 'wksim_perf_stream.c']),
    invoke('build-bench', flags + ['-o', 'bench', 'bench_overhead.c', '-L.',
           '-Wl,-rpath,' + str(work), '-lwksim_perf_stream']),
    invoke('build-bench-fault', flags + ['-o', 'bench-fault', 'bench_overhead.c',
           'fault_inject.c', '-L.', '-Wl,-rpath,' + str(work), '-lwksim_perf_stream',
           '-Wl,--wrap=clock_gettime', '-Wl,--wrap=getrusage', '-Wl,--wrap=fclose',
           '-Wl,--wrap=wksim_perf_stop']),
    invoke('inspect-exports', ['nm', '-D', '--defined-only', 'libwksim_perf_stream.so']),
]
check('builds_exit_zero', all(row['exit_code'] == 0 for row in builds),
      [row['exit_code'] for row in builds])

duration = '320000000'
period = '8000000'
case_specs = [
    ('smoke-disabled', './bench', 'disabled', {}),
    ('smoke-enabled', './bench', 'enabled', {}),
    ('fault-baseline', './bench-fault', 'enabled', {}),
    ('fault-clock-start-begin', './bench-fault', 'enabled',
     {'WKSIM_FI_CLOCK_FAIL_AT': '1', 'WKSIM_FI_TRACE_STOP': '1'}),
    ('fault-clock-after-start', './bench-fault', 'enabled',
     {'WKSIM_FI_CLOCK_FAIL_AT': '2', 'WKSIM_FI_TRACE_STOP': '1'}),
    ('fault-cpu-baseline', './bench-fault', 'enabled',
     {'WKSIM_FI_GETRUSAGE_FAIL_AT': '1', 'WKSIM_FI_GETRUSAGE_FAIL_WHO': 'process',
      'WKSIM_FI_TRACE_STOP': '1'}),
    ('fault-cpu-closing', './bench-fault', 'enabled',
     {'WKSIM_FI_GETRUSAGE_FAIL_AT': '3', 'WKSIM_FI_GETRUSAGE_FAIL_WHO': 'process',
      'WKSIM_FI_TRACE_STOP': '1'}),
    ('fault-fclose', './bench-fault', 'disabled', {'WKSIM_FI_FCLOSE_FAIL_AT': '2'}),
    ('fault-stop-report', './bench-fault', 'enabled',
     {'WKSIM_FI_STOP_REPORT_FAILURE': '1'}),
]
cases = {}
if all(row['exit_code'] == 0 for row in builds):
    for name, binary, mode, extra_env in case_specs:
        directory = work / name
        directory.mkdir()
        cases[name] = invoke(name, [binary, duration, period, mode, str(directory)],
                             timeout=10, extra_env=extra_env)

    analysis = invoke('analyze-smoke', ['python3', '-B', 'analyze_overhead.py',
                      str(work / 'smoke-disabled'), str(work / 'smoke-enabled'),
                      str(work / 'overhead-smoke.json')])
    consumers = []
    for name in ('smoke-enabled', 'fault-baseline', 'fault-stop-report'):
        directory = work / name
        consumers.append(invoke(
            'consume-' + name,
            ['python3', '-B', 'perf_stream_consumer.py', '--raw',
             str(directory / 'switch.raw'), '--metadata',
             str(directory / 'switch.meta.json'), '--output',
             str(directory / 'decoded.json'), '--require-kernel-counter']))

    check('success_cases_exit_zero', all(cases[name]['exit_code'] == 0
          for name in ('smoke-disabled', 'smoke-enabled', 'fault-baseline')),
          {name: cases[name]['exit_code'] for name in
           ('smoke-disabled', 'smoke-enabled', 'fault-baseline')})
    check('fault_cases_exit_nonzero', all(cases[name]['exit_code'] != 0
          for name in cases if name.startswith('fault-') and name != 'fault-baseline'),
          {name: row['exit_code'] for name, row in cases.items() if name.startswith('fault-')})
    traced = ('fault-clock-start-begin', 'fault-clock-after-start',
              'fault-cpu-baseline', 'fault-cpu-closing')
    check('post_start_failures_reach_stop', all('wksim_perf_stop called' in cases[name]['stderr']
          for name in traced), {name: cases[name]['stderr'] for name in traced})
    check('failed_instrumentation_has_no_summary', all(
          not (work / name / 'result.json').exists()
          and not (work / name / 'timing.csv').exists() for name in traced), traced)
    fclose_stderr = cases['fault-fclose']['stderr']
    check('both_closes_observed', 'fclose call 1 observed' in fclose_stderr
          and 'fclose call 2 observed' in fclose_stderr and 'csv_close' in fclose_stderr,
          fclose_stderr)
    stop_dir = work / 'fault-stop-report'
    check('consumed_stop_failure_rejected', cases['fault-stop-report']['exit_code'] != 0
          and (stop_dir / 'switch.raw').exists() and (stop_dir / 'switch.meta.json').exists()
          and not (stop_dir / 'result.json').exists() and not (stop_dir / 'timing.csv').exists()
          and 'successful stop reports failure with consumed handle' in
          cases['fault-stop-report']['stderr'], cases['fault-stop-report']['stderr'])
    check('analyzer_exit_zero', analysis['exit_code'] == 0, analysis)
    check('strict_consumers_exit_zero', all(row['exit_code'] == 0 for row in consumers),
          {row['name']: row['exit_code'] for row in consumers})
    base = json.loads((work / 'smoke-disabled' / 'result.json').read_text())
    enabled = json.loads((work / 'smoke-enabled' / 'result.json').read_text())
    check('paired_workload_identical', base['iterations'] == enabled['iterations'] == 40
          and base['measurement']['body_checksum'] == enabled['measurement']['body_checksum'],
          {'iterations': [base['iterations'], enabled['iterations']],
           'body_checksum': [base['measurement']['body_checksum'],
                             enabled['measurement']['body_checksum']]})

out['boot_after'] = pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
check('same_boot', out['boot_after'] == boot, [boot, out['boot_after']])
check('all_process_groups_empty', all(row['pgid_empty'] and not row['timed_out']
      for row in out['commands']),
      [{'name': row['name'], 'pgid_empty': row['pgid_empty'],
        'timed_out': row['timed_out']} for row in out['commands']])
out['ok'] = all(item['ok'] for item in out['checks'])
artifacts = {}
for path in work.rglob('*'):
    if path.is_file() and path.name in {
            'result.json', 'timing.csv', 'switch.raw', 'switch.meta.json',
            'decoded.json', 'overhead-smoke.json'}:
        artifacts[str(path.relative_to(work))] = base64.b64encode(path.read_bytes()).decode('ascii')
out['artifacts'] = artifacts
print(json.dumps(out))
'''
script = 'import base64,json\npayload=json.loads(base64.b64decode(' + repr(
    base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii')) + '))\n' + linux
result = subprocess.run(
    ['wsl.exe', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'python3', '-'],
    input=script, capture_output=True, text=True, timeout=60)
(root / 'stdout.txt').write_text(result.stdout, encoding='utf-8')
(root / 'stderr.txt').write_text(result.stderr, encoding='utf-8')
assert result.returncode == 0, (result.stdout, result.stderr)
receipt = json.loads([line for line in result.stdout.splitlines()
                      if line.startswith('{')][-1])
artifacts = receipt.pop('artifacts')
capture = root / 'capture'
capture.mkdir()
captured_files = {}
for relative, encoded in artifacts.items():
    path = capture / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(encoded)
    path.write_bytes(data)
    captured_files[relative] = {
        'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
    }
receipt.update({
    'source_checkout': str(repo),
    'source_head': source_head,
    'architecture_ancestor_exit_code': ancestor.returncode,
    'work_class': 'new-development: synthetic perf diagnostic admission',
    'architecture_acceptance': False,
    'full_acceptance': False,
    'captured_files': captured_files,
})
(root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
assert receipt['ok'], receipt['checks']
print(json.dumps({'ok': receipt['ok'], 'directory': receipt['directory'],
                  'commands': len(receipt['commands']),
                  'captured_files': len(captured_files)}))
