"""Bounded Linux real-SITL gate through the formal entry; no diagnostic commands."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]


def identity(pid):
    text = Path(f'/proc/{pid}/stat').read_text()
    return dict(pid=pid, start_ticks=text[text.rindex(')') + 2:].split()[19],
                cmdline=Path(f'/proc/{pid}/cmdline').read_bytes().decode().replace('\0', ' '))


def sample(directory):
    path = directory / 'truth.jsonl'
    if not path.exists():
        return None
    with path.open('rb') as source:
        source.seek(max(0, path.stat().st_size - 16384))
        lines = source.read().split(b'\n')
    for line in reversed(lines[1:-1]):
        try:
            return json.loads(line)['time']
        except (ValueError, KeyError):
            continue


def group_members(groups):
    members = []
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            value = path.read_text()
            fields = value[value.rindex(')') + 2:].split()
            if int(fields[2]) in groups:
                members.append(int(path.parent.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control-protocol', choices=('session_v1', 'legacy_v1'), default='session_v1')
    args = parser.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='product-isolation-', dir=REPO / 'validation'))
    report = dict(status='failed', scope='two independent experiments, not a joint scene',
                  original_before=identity(828), samples=[], launches={})
    report['validator_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    children, logs = {}, []
    token = uuid.uuid4().hex[:10]
    configs, dirs = {}, {}

    def launch(label, config, root):
        path = evidence / (label + '.json')
        path.write_text(json.dumps(config, indent=2) + '\n')
        argv = ['bash', str(REPO / 'tools/run-wksim.sh'), str(path), '--output-root', str(root)]
        log = (evidence / (label + '.log')).open('x')
        logs.append(log)
        child = subprocess.Popen(argv, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
        children[label] = child
        report['launches'][label] = dict(argv=argv, pid=child.pid, started=time.time())
        return child

    print(str(evidence), flush=True)
    try:
        for stack in ('arducopter', 'px4'):
            suffix = '-session' if args.control_protocol == 'session_v1' else ''
            config = json.loads((REPO / f'Simulator/wksim_runtime/examples/{stack}{suffix}.json').read_text())
            config['run_id'] = 'isolation-' + stack + '-' + token
            configs[stack] = config
            dirs[stack] = evidence / 'runs' / config['run_id']
            launch(stack, config, evidence / 'runs')
        deadline = time.monotonic() + 220
        refused = False
        stopped = None
        progress_after_stop = False
        while time.monotonic() < deadline:
            values = {stack: sample(path) for stack, path in dirs.items()}
            alive = {stack: children[stack].poll() is None for stack in dirs}
            report['samples'].append(dict(wall=time.time(), times=values, alive=alive,
                                          original=identity(828)))
            if all(alive.values()) and all(v is not None for v in values.values()) and not refused:
                duplicate = launch('duplicate', configs['px4'], evidence / 'different-root')
                assert duplicate.wait(timeout=15) == 2, 'Duplicate run_id was not refused'
                assert 'resource conflict' in (evidence / 'duplicate.log').read_text()
                assert not (evidence / 'different-root' / configs['px4']['run_id']).exists()
                report['startup_refusal'] = dict(wall=time.time(), survivor_times=values)
                refused = True
            if stopped is None and sum(alive.values()) == 1:
                survivor = next(s for s in dirs if alive[s])
                ended = next(s for s in dirs if not alive[s])
                result = json.loads((dirs[ended] / 'result.json').read_text())
                assert result['status'] == 'pass' and result['stop_kind'] == 'landed_stop', result.get('error')
                stopped = dict(ended=ended, survivor=survivor, time=values[survivor], wall=time.time())
                report['normal_stop'] = stopped
            if stopped and values[stopped['survivor']] > stopped['time'] + 1:
                progress_after_stop = True
            if not any(alive.values()):
                break
            time.sleep(0.3)
        else:
            raise TimeoutError('Acceptance watchdog')
        results = {s: json.loads((p / 'result.json').read_text()) for s, p in dirs.items()}
        report['results'] = {s: str(p / 'result.json') for s, p in dirs.items()}
        assert all(r['status'] == 'pass' and r['children_reaped'] and not r['cleanup_errors'] for r in results.values()), results
        assert refused and progress_after_stop, 'Missing overlap/refusal/post-stop progress'
        assert len({r['resources']['network_namespace'] for r in results.values()}) == 2
        assert len({r['resources']['ipc_namespace'] for r in results.values()}) == 2
        assert len({r['resources']['shm_device'] for r in results.values()}) == 2
        report['remaining_owned_processes'] = group_members({c['pgid'] for r in results.values() for c in r['children'].values()})
        assert not report['remaining_owned_processes'], 'Owned descendants survived cleanup'
        assert report['original_before'] == identity(828)
        report['status'] = 'pass'
    except Exception as error:
        report['error'] = str(error)
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()  # formal runtime's failed isolated teardown
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    report['cleanup_timeout'] = child.pid
        for log in logs:
            log.close()
        report['original_after'] = identity(828)
        (evidence / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(dict(status=report['status'], evidence=str(evidence), error=report.get('error'))), flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
