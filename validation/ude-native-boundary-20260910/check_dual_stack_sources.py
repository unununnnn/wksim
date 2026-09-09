"""Read-only source/protocol comparison. Run only after both owned runs finish.

No online code imports, subprocesses, ROS nodes, model loads or evidence writes.
This checks identity consistency; it does not certify physical flight acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = '4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590'
MODEL = 'cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(root, stack):
    root = root.resolve(strict=True)
    result = read(root/'result.json')
    require(result['stack'] == stack, 'Wrong stack: '+str(root))
    require(result['children_reaped'] is True and result['children']
            and all(v['returncode'] is not None for v in result['children'].values()),
            'Run has no completed owned-child teardown; wait for completion')
    require(digest(root/'pid-protocol.json') == PROTOCOL, 'Frozen UDE protocol mismatch')
    config = read(root/'pid-protocol.json')
    require(config == read(REPO/'Simulator/wksim_runtime/ude-flight-v1.json')
            and digest(REPO/'Simulator/wksim_runtime/ude-flight-v1.json') == PROTOCOL,
            'Current frozen UDE protocol differs')
    require(result['config']['controller'] == 'ude' and result['config']['external_ude'] == config
            and read(root/'config.json') == result['config'], 'Selected UDE configuration mismatch')
    selected = result['admission']['external_ude']
    require(result['admission']['ok'] and selected['protocol_sha256'] == PROTOCOL
            and selected['configuration'] == config
            and selected['implementation'] == 'Simulator.wksim_control.position_ude.PositionUDE',
            'Selected UDE admission mismatch')
    require(config['model']['library_sha256'] == MODEL
            and result['admission']['identities']['model_build']['library_sha256'] == MODEL,
            'Frozen model identity mismatch')
    require(result['source_unchanged'] is True and result['candidate_unchanged'] is True,
            'Run reports changed source/candidate')
    sources = result['source_sha256']
    required = {'Simulator/wksim_runtime/pid_task.py', 'Simulator/wksim_control/position_pid.py',
                'Simulator/wksim_control/position_ude.py', 'Simulator/wksim_runtime/ude-flight-v1.json',
                'tools/run_pid_flight.py', 'tools/pid_physics.py'}
    require(required <= sources.keys(), 'Missing selected runtime source seal')
    retained_root = (root/'run-source').resolve(strict=True)
    for name, sha in sources.items():
        retained = (retained_root/name).resolve(strict=True)
        current = (REPO/name).resolve(strict=True)
        require(retained.is_relative_to(retained_root) and current.is_relative_to(REPO),
                'Escaping source path: '+name)
        require(digest(retained) == sha == digest(current), 'Source mismatch: '+name)
    return dict(stack=stack, run_id=result['run_id'], run_dir=str(root),
                result_sha256=digest(root/'result.json'), protocol_sha256=PROTOCOL,
                model_sha256=MODEL, status=result['status'], safe_landing=result['safe_landing'],
                source_sha256=sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--px4-run-dir', required=True, type=Path)
    parser.add_argument('--arducopter-run-dir', required=True, type=Path)
    args = parser.parse_args()
    report = dict(status='rejected', scope='source/protocol consistency only; no flight acceptance')
    try:
        report['px4'] = inspect(args.px4_run_dir, 'px4')
        report['arducopter'] = inspect(args.arducopter_run_dir, 'arducopter')
        require(report['px4']['source_sha256'] == report['arducopter']['source_sha256'],
                'PX4/AP selected runtime source manifests differ')
        report['status'] = 'source_protocol_consistent'
    except Exception as error:
        report['failure'] = dict(type=type(error).__name__, message=str(error))
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['status'] == 'source_protocol_consistent' else 1


if __name__ == '__main__':
    raise SystemExit(main())
