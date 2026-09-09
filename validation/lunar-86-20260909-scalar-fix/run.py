"""One bounded post-fix attempt; preserve logs and return codes without retry."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUN = 'pid-px4-scalar-fix-20260909-01'
OUTPUT = '/root/wksim-pid-flight-' + RUN
BASE = ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', '--']


def call(name, argv):
    start = time.time()
    with (HERE / (name + '.stdout.log')).open('xb') as out, (HERE / (name + '.stderr.log')).open('xb') as err:
        result = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err)
    (HERE / (name + '.json')).write_text(json.dumps(dict(argv=argv, cwd=str(ROOT),
        started_unix_s=start, ended_unix_s=time.time(), returncode=result.returncode), indent=2)+'\n')
    print(name, result.returncode, flush=True)
    return result.returncode


if __name__ == '__main__':
    sources = ['Simulator/wksim_control/position_pid.py', 'validation/test_pid_flight.py',
               'Simulator/wksim_runtime/pid-flight-v1.json', 'Simulator/wksim_runtime/pid_task.py',
               'tools/run_pid_flight.py', 'tools/run-pid-flight.sh']
    (HERE/'source-sha256.json').write_text(json.dumps({p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
        for p in sources}, indent=2)+'\n')
    setup = 'source /opt/ros/humble/setup.bash; source /root/wksim-ros2-MUlZd0/install/local_setup.bash; '
    if call('tests', BASE + ['bash', '-lc', setup + '/usr/bin/python3 -B -m unittest validation.test_pid_flight validation.test_position_pid -v']):
        raise SystemExit(1)
    flight = BASE + ['bash', 'tools/run-pid-flight.sh', '--stack', 'px4', '--run-id', RUN,
        '--config', 'Simulator/wksim_runtime/pid-flight-v1.json', '--output-root', OUTPUT]
    if call('preflight', flight + ['--preflight']):
        raise SystemExit(1)
    raise SystemExit(call('flight', flight))
