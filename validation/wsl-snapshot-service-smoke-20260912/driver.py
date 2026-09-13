"""Real Windows/WSL ownership exchange with six canaries, never SITL or tracefs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.wsl_snapshot_exchange import (decode_json_strict, make_snapshot_request,
    publish_create_only, verify_snapshot_response_binding)


def identity(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'start_ticks': int(fields[19])}


def linux_canaries(output):
    roles = ('supervisor', 'ap_worker', 'px4_worker', 'ap_fc', 'px4_fc')
    children = {}
    owners = {}
    records = []
    deadline = time.monotonic() + 60
    try:
        for role in roles:
            child = subprocess.Popen([sys.executable, '-B', '-c', 'import sys; sys.stdin.read()'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            children[role] = child
            owners[role] = identity(child.pid)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        ns = Path('/proc/self/ns/pid').stat().st_ino
        run_id, epoch = 'snapshot-canary-' + uuid.uuid4().hex[:12], uuid.uuid4().hex
        for phase in ('pre_bootstrap_leaders', 'post_capture_tasks'):
            request = make_snapshot_request(run_id=run_id, epoch=epoch, boot_id=boot,
                target_pid_ns=ns, collector=identity(os.getpid()), owners=owners, phase=phase)
            raw = publish_create_only(output / (phase + '.request.json'), request)
            reply = output / (phase + '.response.json')
            while not reply.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError('Canary exchange deadline')
                time.sleep(.02)
            response = decode_json_strict(reply.read_bytes())
            verify_snapshot_response_binding(response, expected_request=request, expected_request_bytes=raw)
            leaders = response['snapshot']['leaders']
            targets = dict(owners, collector=identity(os.getpid()))
            for role, expected in targets.items():
                observed = leaders[str(expected['pid'])]
                assert observed['local_tid'] == observed['local_tgid'] == expected['pid']
                assert observed['start_ticks'] == expected['start_ticks']
                assert observed['global_tid'] == observed['global_tgid'] > 0
            assert len({leaders[str(v['pid'])]['global_tid'] for v in targets.values()}) == 6
            records.append({'phase': phase, 'verified_leaders': 6})
    finally:
        exits = {}
        for role, child in children.items():
            child.stdin.close()
            try:
                code = child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                code = child.wait(timeout=5)
            exits[role] = {'identity': owners.get(role), 'returncode': code}
        publish_create_only(output / 'canary-exits.json', {'children': exits})
    assert len(exits) == 5 and all(row['returncode'] == 0 for row in exits.values())
    publish_create_only(output / 'linux-audit.json', {'status': 'pass', 'phases': records,
        'canaries_reaped': 5, 'scope': 'Real ownership/file transport canaries; no FC, model or tracefs'})


def windows_driver():
    from tools.serve_wsl_snapshot_requests import serve_snapshot_requests
    output = Path(__file__).resolve().parent / 'run-01'
    output.mkdir(exist_ok=False)
    def wsl_path(path):
        return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]
    command = ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', '--cd', wsl_path(ROOT), '--',
               'python3', '-B', wsl_path(Path(__file__).resolve()), '--linux', wsl_path(output)]
    with (output / 'linux.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        error = None
        try:
            result = serve_snapshot_requests(output, timeout_s=45, distro='Ubuntu-22.04')
        except Exception as caught:
            error = repr(caught)
            result = {'status': 'failed', 'error': error}
        finally:
            code = child.wait(timeout=65)
    sources = ('tools/wsl_root_task_snapshot.py', 'tools/wsl_snapshot_exchange.py',
               'tools/serve_wsl_snapshot_requests.py')
    report = {'status': 'pass' if error is None and code == 0 else 'failed',
        'command': command, 'linux_returncode': code, 'service': result,
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
        'scope': 'Windows NTFS / WSL mount exchange and real kernel PID ownership; no scheduler or flight acceptance'}
    publish_create_only(output / 'summary.json', report)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--linux':
        linux_canaries(Path(sys.argv[2]))
    else:
        raise SystemExit(windows_driver())
