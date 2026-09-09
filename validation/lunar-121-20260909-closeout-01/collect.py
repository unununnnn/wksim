"""Read-only #121 readiness review; no FC/model/ROS launch or flight acceptance."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def save(name, value):
    with (HERE / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(name, argv, *, timeout=120):
    record = dict(argv=argv, cwd=str(ROOT), started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    with (HERE / (name + '.stdout.log')).open('xb') as stdout, (HERE / (name + '.stderr.log')).open('xb') as stderr:
        try:
            result = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=timeout)
            record['returncode'] = result.returncode
        except subprocess.TimeoutExpired:
            record.update(returncode=None, timeout_s=timeout)
    record['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save(name + '.command.json', record)
    print(name, record.get('returncode'), flush=True)
    if record.get('returncode') != 0:
        raise RuntimeError(name + ' did not complete successfully; original output retained')


run('issue-121', ['gh', 'issue', 'view', '121', '--repo', 'unununnnn/wksim', '--json', 'number,state,title,body,labels,comments'])
run('dependencies', ['gh', 'api', 'repos/unununnnn/wksim/issues/121/dependencies/blocked_by'])
for number in (22, 45, 109, 110):
    run('issue-' + str(number), ['gh', 'issue', 'view', str(number), '--repo', 'unununnnn/wksim', '--json', 'number,state,body'])
run('head', ['git', 'rev-parse', 'HEAD'])
run('branch', ['git', 'branch', '--show-current'])
modules = ['validation.test_gnss_event', 'validation.test_gnss_px4_injection', 'validation.test_wksim_core.ProtocolTests']
run('windows-tests', [sys.executable, '-B', '-m', 'unittest', *modules, '-v'])
run('wsl-tests', ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', '--', '/usr/bin/python3', '-B', '-m', 'unittest', *modules, '-v'])

ground = ROOT / 'validation/45-ap-gnss-candidate/wksim-ap-gnss-109-ground-05'
sys.path.insert(0, str(ROOT / 'validation/45-ap-gnss-candidate'))
from probe import audit
save('ap-ground-reaudit.json', audit(ground))
# Existing #109 mutations run only on temporary copies of sealed ground records.
with tempfile.TemporaryDirectory(prefix='wksim-121-audit-') as scratch:
    out = Path(scratch) / 'mutations'
    run('ap-ground-mutations', [sys.executable, '-B', 'validation/45-ap-gnss-candidate/check_audit.py', str(ground), str(out)])
    save('ap-ground-mutations.json', json.loads((out / 'tests.json').read_text()))

run('wsl-resource-identities', ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'sha256sum',
    '/root/wksim-ap-gnss-109-20260909-05/build/sitl/bin/arducopter',
    '/root/wksim-ap-gnss-109-20260909-05/src/libraries/SITL/SIM_WksimGNSS.h',
    '/root/wksim-ap-gnss-109-20260909-05/src/libraries/SITL/SIM_JSON.cpp',
    '/root/wksim-ap-gnss-109-20260909-05/src/libraries/SITL/SIM_GPS.cpp',
    '/root/wksim-ap-gnss-109-20260909-05/src/libraries/SITL/SIM_GPS_UBLOX.cpp'])
build = ROOT / 'validation/45-ap-gnss-candidate/wksim-ap-gnss-109-20260909-05/identity.json'
identity = json.loads(build.read_text())
expected = {'arducopter': identity['binary_sha256'], **identity['candidate']}
actual = {}
for line in (HERE / 'wsl-resource-identities.stdout.log').read_text(encoding='utf-8').splitlines():
    checksum, path = line.split(maxsplit=1)
    actual[Path(path.strip()).name] = checksum
save('resource-comparison.json', dict(expected=expected, actual=actual, ok=expected == actual))
if expected != actual:
    raise RuntimeError('Current AP candidate differs from archived identity')

owned = ['Simulator/wksim_runtime/gnss_task.py', 'Simulator/wksim_runtime/gnss-flight-v1.json',
         'tools/run_gnss_flight.py', 'tools/run-gnss-flight.sh', 'tools/audit_gnss_flight.py',
         'validation/test_gnss_flight.py', 'validation/test_gnss_audit.py', 'docs/plan/45-gnss-runbook.md']
save('deliverable-inventory.json', {name: dict(exists=(ROOT/name).is_file(),
    sha256=digest(ROOT/name) if (ROOT/name).is_file() else None) for name in owned})
inputs = ['docs/2026-09-09-gnss-event-report.md', 'docs/plan/45-ap-gnss-native-contract.md',
    'Simulator/wksim_core/gnss_event.py', 'Simulator/wksim_core/px4_mavlink.py',
    'Simulator/wksim_core/ap_json.py', 'validation/45-ap-gnss-candidate/SIM_WksimGNSS.h',
    'validation/45-ap-gnss-candidate/probe.py', 'validation/45-ap-gnss-candidate/check_audit.py',
    'validation/test_gnss_event.py', 'validation/test_gnss_px4_injection.py',
    str(build.relative_to(ROOT))]
inputs += [str((ground/name).relative_to(ROOT)) for name in ('manifest.json', 'ground.parm', 'native.tsv', 'wire.jsonl', 'audit.json')]
save('input-sha256.json', {name: digest(ROOT/name) for name in inputs})
run('processes-after', ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'ps', '-eo', 'pid,ppid,etimes,args'])
save('readiness.json', dict(schema='wksim.gnss.readiness-review.v1', status='blocked', flight_started=False,
    dependencies_closed=True, runtime_preflight_passed=False, full_flight_audit_passed=False,
    blockers=['AP candidate fixes outage at startup ticks [4000,6000) and rejects tick >60000; no post-readiness plan interface.',
              'GNSS-specific physical envelope, validity-loss/recovery windows and native failsafe policy need an explicit reviewed contract; #22 covers Agent link only.',
              'Seven runtime/config/audit/test deliverables are absent; no executable dual-stack flight entry.'],
    verified_scope='Existing PX4 send-boundary tests and archived AP ground raw audit only.'))
save('artifact-sha256.json', {p.name: digest(p) for p in HERE.iterdir() if p.is_file()})
