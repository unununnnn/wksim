"""Run one owned job only after matching fresh two-distro prechecks."""
from pathlib import Path
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

ROOT = Path('/root/wksim-release-extension-bench-20260913-01')
EVIDENCE = Path(__file__).resolve().parent
key = sys.argv[1]
if key not in ('compile', 'interface', 'benchmark'):
    raise ValueError('unknown job')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
prechecks = {}
for distro in ('Ubuntu-22.04', 'RflySim-20.04'):
    raw = (EVIDENCE / (key + '-precheck-' + distro + '.json')).read_bytes()
    record = json.loads(raw)
    age = time.time() - record['checked_unix']
    if record['distro'] != distro or record['boot_id'] != boot or record['found'] or not -1 <= age <= 60:
        raise RuntimeError('Precheck no longer valid; refresh both before launch')
    prechecks[distro] = hashlib.sha256(raw).hexdigest()
raw = (ROOT / 'commands.json').read_bytes()
commands = json.loads(raw)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name, expected in commands['source_identities'].items():
    if sha(ROOT / name) != expected:
        raise RuntimeError('staged source changed: ' + name)
if (ROOT / (key + '-result.json')).exists():
    raise FileExistsError('job already has a receipt')
started = time.time()
timeout = False
with (ROOT / (key + '.stdout')).open('xb') as stdout, (ROOT / (key + '.stderr')).open('xb') as stderr:
    process = subprocess.Popen(commands[key], cwd=ROOT, stdout=stdout, stderr=stderr, start_new_session=True)
    try:
        code = process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        timeout = True
        os.killpg(process.pid, signal.SIGKILL)
        code = process.wait()
remaining = []
for item in Path('/proc').iterdir():
    if item.name.isdigit():
        try:
            if os.getpgid(int(item.name)) == process.pid:
                remaining.append(int(item.name))
        except ProcessLookupError:
            pass
result = dict(job=key, argv=commands[key], exit_code=code, timeout=timeout,
    pgid=process.pid, remaining=remaining, elapsed_s=time.time()-started,
    boot_id=boot, precheck_sha256=prechecks, commands_sha256=hashlib.sha256(raw).hexdigest(),
    runner_sha256=sha(Path(__file__)),
    sources_unchanged=all(sha(ROOT/name) == value for name, value in commands['source_identities'].items()))
if key == 'compile' and code == 0:
    result['extension_sha256'] = sha(ROOT / '_wksim_release_wait_native.cpython-310-x86_64-linux-gnu.so')
with (ROOT / (key+'-result.json')).open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
if code != 0 or remaining or not result['sources_unchanged']:
    raise RuntimeError('owned job failed; preserve receipts')
