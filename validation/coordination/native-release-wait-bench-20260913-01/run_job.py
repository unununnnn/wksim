"""Run exactly one prechecked, owned job from this experiment's command manifest."""
from pathlib import Path
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

ROOT = Path('/root/wksim-native-release-wait-20260913-01')
key = sys.argv[1]
assert key in ('compile_library', 'compile_clock_cases', 'run_clock_cases', 'run_benchmark')
raw = (ROOT / 'commands.json').read_bytes()
commands = json.loads(raw)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name, expected in commands['source_identities'].items():
    assert sha(ROOT / name) == expected, name
assert not (ROOT / (key + '-result.json')).exists()
started = time.time()
timeout = False
with (ROOT / (key + '.stdout')).open('xb') as stdout, (ROOT / (key + '.stderr')).open('xb') as stderr:
    process = subprocess.Popen(commands[key], cwd=ROOT, stdout=stdout, stderr=stderr, start_new_session=True)
    try:
        code = process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        timeout = True
        os.killpg(process.pid, signal.SIGKILL)  # this job's newly created, still-live group only
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
    pgid=process.pid, remaining=remaining, elapsed_s=time.time() - started,
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    commands_sha256=hashlib.sha256(raw).hexdigest(),
    runner_sha256=sha(Path(__file__)),
    sources_unchanged=all(sha(ROOT / name) == expected for name, expected in commands['source_identities'].items()))
if key == 'compile_library' and code == 0:
    result['library_sha256'] = sha(ROOT / 'native_release_wait.so')
if key == 'compile_clock_cases' and code == 0:
    result['unit_executable_sha256'] = sha(ROOT / 'clock_cases')
with (ROOT / (key + '-result.json')).open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
assert code == 0 and not remaining and result['sources_unchanged']
