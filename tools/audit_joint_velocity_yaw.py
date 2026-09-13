"""Offline formal #22 audit. A physical-window pass never clears a run fault."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.joint_evidence import verify_tasks
from Simulator.wksim_runtime.velocity_evidence import require


def read(path):
    return json.loads(path.read_text())


def audit(root):
    result = read(root/'result.json')
    epoch, run_id = result['epoch'], result['run_id']
    report = dict(status='failed', epoch=epoch, run_id=run_id,
                  recorded_status=result['status'], recorded_faults=result.get('faults', []),
                  recorded_error=result.get('error'), physical_windows=None)
    try:
        require(len(result['tasks']) == 2, 'Expected exactly one dual-stack task group')
        control_epochs = set()
        for name, task in result['tasks'].items():
            stack = task['stack']
            group = name.removeprefix(stack+'-task-')
            directory = root/'tasks'/group/stack
            require(read(directory/'result.json') == task, 'Retained task report differs')
            config = read(directory/'task-config.json')
            ready = read(directory/'ready.json')
            offer = read(directory.parent/'go.json')
            require(config['task_type'] == 'public_velocity_yaw' and config['mode'] == 'initial'
                    and config['run_id'] == task['run_id'] == run_id
                    and config['epoch'] == task['scene_epoch'] == epoch
                    and config['uav_id'] == task['uav_id'] and config['stack'] == stack,
                    'Task configuration identity differs')
            require(offer['run_id'] == run_id and offer['epoch'] == epoch and offer['tasks'][stack] == ready
                    and ready['token'] == config['token'] and ready['uav_id'] == task['uav_id']
                    and ready['control_epoch'] == task['task']['control_epoch'], 'Ready/go identity differs')
            control_epochs.add(ready['control_epoch'])
            child = result['children'][name]
            require(child['returncode'] == 0 and child['argv'][-1].replace('\\', '/').endswith(
                    '/tasks/'+group+'/'+stack+'/task-config.json'), 'Task did not exit normally or identity differs')
            require(task['status'] == 'pass', 'Task did not complete')
        require(len(control_epochs) == 2, 'Control epochs are not distinct')
        starts = [a for a in result['action_results'] if a['action'] == 'start-task']
        require(len(starts) == 1 and starts[0]['state'] == 'completed'
                and starts[0]['run_id'] == run_id and starts[0]['epoch'] == epoch
                and starts[0]['token'] and starts[0]['command_id'] > 0, 'Start action identity differs')
        stop = result['stop_request']
        require(stop['action'] == 'stop' and stop['run_id'] == run_id and stop['epoch'] == epoch
                and stop['command_id'] > starts[0]['command_id'] and stop['token'] != starts[0]['token'],
                'Stop action identity differs')
        proof = verify_tasks(root, epoch, result['authority']['tick'], result['tasks'], 'public_velocity_yaw')
        require(proof is not None, 'Missing dual-stack physical proof')
        report['physical_windows'] = dict(status='pass', proof=proof)
        require(result['status'] == 'stopped'
                and not result.get('cleanup_errors') and not result.get('changed_sources')
                and not result['authority'].get('fault'), 'Run fault/retirement/cleanup prevents acceptance')
        require(all(child['returncode'] == 0 for name, child in result['children'].items()
                    if name.endswith(('-model', '-control'))), 'Model/control did not exit normally')
        report['status'] = 'pass'
    except (KeyError, ValueError, OSError) as error:
        report['error'] = str(error)
    report['result_sha256'] = hashlib.sha256((root/'result.json').read_bytes()).hexdigest()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Formal epoch directory')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit(args.directory)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
