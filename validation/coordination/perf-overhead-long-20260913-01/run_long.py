"""Main-owned 360-second paired synthetic recorder-overhead measurement."""
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
    'analyze_overhead.py': driver / 'analyze_overhead.py',
    'wksim_perf_stream.c': recorder / 'wksim_perf_stream.c',
    'wksim_perf_stream.h': recorder / 'wksim_perf_stream.h',
    'perf_stream_consumer.py': consumer / 'perf_stream_consumer.py',
}
source_sha256 = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for name, path in paths.items()}
assert source_sha256 == {
    'bench_overhead.c': 'e51535a4dfce2107dbc9f8f3f30e68ee094a3a38bb72d1158160fede969df2c7',
    'analyze_overhead.py': '9da94c6fb9980953550e141797f6c56ae4f9e8482b641365db08518f68dd277e',
    'wksim_perf_stream.c': 'aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2',
    'wksim_perf_stream.h': 'ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823',
    'perf_stream_consumer.py': 'dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc',
}
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
work = pathlib.Path(tempfile.mkdtemp(prefix='wksim-overhead-long-', dir='/root'))
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
    'directory': str(work), 'boot_id': boot,
    'source_sha256': payload['source_sha256'], 'commands': [], 'checks': [],
    'started_unix': time.time(),
}

def invoke(name, argv, timeout):
    process = subprocess.Popen(
        argv, cwd=work, env=clean_env, start_new_session=True,
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
build = invoke('build-shared-recorder', flags + [
    '-shared', '-fPIC', '-o', 'libwksim_perf_stream.so', 'wksim_perf_stream.c'], 30)
bench = invoke('build-bench', flags + [
    '-o', 'bench', 'bench_overhead.c', '-L.', '-Wl,-rpath,' + str(work),
    '-lwksim_perf_stream'], 30)
check('builds_exit_zero', build['exit_code'] == bench['exit_code'] == 0,
      [build['exit_code'], bench['exit_code']])

duration = '360000000000'
period = '8000000'
disabled_dir = work / 'disabled'
enabled_dir = work / 'enabled'
disabled_dir.mkdir()
enabled_dir.mkdir()
disabled = invoke('disabled-360s', ['./bench', duration, period, 'disabled',
                  str(disabled_dir)], 390)
enabled = invoke('enabled-360s', ['./bench', duration, period, 'enabled',
                 str(enabled_dir)], 390)
analysis = invoke('analyze-pair', ['python3', '-B', 'analyze_overhead.py',
                  str(disabled_dir), str(enabled_dir), str(work / 'overhead-long.json')], 30)
consumer_run = invoke('consume-enabled', [
    'python3', '-B', 'perf_stream_consumer.py', '--raw', str(enabled_dir / 'switch.raw'),
    '--metadata', str(enabled_dir / 'switch.meta.json'), '--output',
    str(enabled_dir / 'decoded.json'), '--require-kernel-counter'], 60)

check('long_rows_exit_zero', disabled['exit_code'] == enabled['exit_code'] == 0,
      [disabled['exit_code'], enabled['exit_code']])
check('analyzer_exit_zero', analysis['exit_code'] == 0, analysis['stderr'])
check('strict_consumer_exit_zero', consumer_run['exit_code'] == 0, consumer_run['stdout'])
if disabled['exit_code'] == enabled['exit_code'] == 0:
    base = json.loads((disabled_dir / 'result.json').read_text())
    variant = json.loads((enabled_dir / 'result.json').read_text())
    check('whole_requested_workload', base['requested_duration_ns'] ==
          variant['requested_duration_ns'] == 360000000000
          and base['requested_period_ns'] == variant['requested_period_ns'] == 8000000
          and base['iterations'] == variant['iterations'] == 45000,
          {'base': [base['requested_duration_ns'], base['requested_period_ns'], base['iterations']],
           'variant': [variant['requested_duration_ns'], variant['requested_period_ns'],
                       variant['iterations']]})
    check('body_checksum_identical', base['measurement']['body_checksum'] ==
          variant['measurement']['body_checksum'],
          [base['measurement']['body_checksum'], variant['measurement']['body_checksum']])

out['ended_unix'] = time.time()
out['boot_after'] = pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
check('same_boot', out['boot_after'] == boot, [boot, out['boot_after']])
check('all_process_groups_empty', all(row['pgid_empty'] and not row['timed_out']
      for row in out['commands']),
      [{'name': row['name'], 'pgid_empty': row['pgid_empty'],
        'timed_out': row['timed_out']} for row in out['commands']])
file_paths = [
    disabled_dir / 'result.json', disabled_dir / 'timing.csv',
    enabled_dir / 'result.json', enabled_dir / 'timing.csv',
    enabled_dir / 'switch.raw', enabled_dir / 'switch.meta.json',
    work / 'overhead-long.json',
]
out['linux_files'] = {
    str(path.relative_to(work)): {
        'bytes': path.stat().st_size,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    } for path in file_paths if path.exists()
}
decoded = enabled_dir / 'decoded.json'
if decoded.exists():
    out['decoded_not_copied'] = {
        'path': str(decoded), 'bytes': decoded.stat().st_size,
        'sha256': hashlib.sha256(decoded.read_bytes()).hexdigest(),
    }
out['ok'] = all(item['ok'] for item in out['checks'])
out['artifacts'] = {
    str(path.relative_to(work)): base64.b64encode(path.read_bytes()).decode('ascii')
    for path in file_paths if path.exists()
}
print(json.dumps(out))
'''
encoded_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii')
script = ('import base64,json\npayload=json.loads(base64.b64decode(' +
          repr(encoded_payload) + '))\n' + linux)
result = subprocess.run(
    ['wsl.exe', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'python3', '-'],
    input=script, capture_output=True, text=True, timeout=900)
(root / 'stdout.txt').write_text(result.stdout, encoding='utf-8')
(root / 'stderr.txt').write_text(result.stderr, encoding='utf-8')
assert result.returncode == 0, (result.stdout[-4000:], result.stderr[-4000:])
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
assert captured_files == receipt['linux_files']
receipt.update({
    'source_checkout': str(repo), 'source_head': source_head,
    'architecture_ancestor_exit_code': ancestor.returncode,
    'work_class': 'new-development: whole-duration synthetic perf diagnostic',
    'architecture_acceptance': False, 'full_acceptance': False,
    'captured_files': captured_files,
})
(root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
assert receipt['ok'], receipt['checks']
print(json.dumps({'ok': True, 'directory': receipt['directory'],
                  'elapsed_seconds': receipt['ended_unix'] - receipt['started_unix'],
                  'captured_files': len(captured_files)}))
