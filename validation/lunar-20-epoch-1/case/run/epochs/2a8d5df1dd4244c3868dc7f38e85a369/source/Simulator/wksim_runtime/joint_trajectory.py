"""Fixed formal trajectory transport and common-start contract."""
import json
import math
import re

from .evidence import write_json
from .joint_config import FIXED_TASKS

RECORDER = 'wksim_joint_supervisor'


def supported_actions(task_type, actions):
    if task_type in FIXED_TASKS:
        return [action for action in actions if action in ('start-task', 'stop', 'cold-reset')]
    return actions


def validate_initialized(record, settings):
    fixed = settings['task_type'] in FIXED_TASKS
    expected = dict(version=1,run_id=settings['run_id'],epoch=settings['epoch'],stack=settings['stack'],
                    token=settings['token'],control_subscriptions=[2,2] if fixed else [1,1])
    graph = record.get('request_graph')
    if fixed:
        if not isinstance(graph, dict) or set(graph) != {'setup', 'command'}:
            raise ValueError('Missing fixed task transport graph')
        for endpoints in graph.values():
            if (len(endpoints) != 2 or {e['node_name'] for e in endpoints} != {
                    'wksim_joint_'+settings['stack']+'_control', RECORDER}
                    or len({e['endpoint_gid'] for e in endpoints}) != 2
                    or any(e['node_namespace'] != '/' or not re.fullmatch('[0-9a-f]+', e['endpoint_gid'])
                           or int(e['endpoint_gid'], 16) == 0 for e in endpoints)):
                raise ValueError('Fixed task transport endpoints differ')
        expected['request_graph'] = graph
    if record != expected:
        raise ValueError('Staged task transport identity differs')


def coordinate_legs(task_group, run_id, epoch, tick):
    """Called only after the operator start/go, on complete four-tick boundaries."""
    if tick % 4:
        return
    if not (task_group/'go.json').is_file():
        raise FileNotFoundError('Trajectory coordination requires an explicit formal go')
    for leg in (1, 2):
        path = task_group/f'pv-go-{leg}.json'
        ready_paths = {stack:task_group/stack/f'pv-ready-{leg}.json' for stack in ('arducopter','px4')}
        if path.exists() or not all(p.is_file() for p in ready_paths.values()):
            continue
        initial_go = json.loads((task_group/'go.json').read_text())
        if initial_go['run_id'] != run_id or initial_go['epoch'] != epoch:
            raise ValueError('Trajectory start lacks the current formal task go')
        offers = {stack:json.loads(p.read_text()) for stack,p in ready_paths.items()}
        tokens = set()
        if leg == 2:
            previous = json.loads((task_group/'pv-go-1.json').read_text())
            tokens.update(row['token'] for row in previous['tasks'].values())
        for stack, uid in (('arducopter',1),('px4',2)):
            initial = json.loads((task_group/stack/'ready.json').read_text())
            offer = offers[stack]
            if (initial != initial_go['tasks'][stack] or initial['epoch'] != epoch or initial['run_id'] != run_id
                    or offer['version'] != 1 or offer['profile'] != FIXED_TASKS[0] or offer['leg'] != leg
                    or offer['run_id'] != run_id or offer['scene_epoch'] != epoch or offer['uav_id'] != uid
                    or offer['control_epoch'] != initial['control_epoch']
                    or not re.fullmatch('[0-9a-f]{32}',offer['token']) or offer['token'] in tokens
                    or len(offer['position']) != 3 or not all(math.isfinite(v) for v in (*offer['position'],offer['yaw']))):
                raise ValueError('P+V readiness identity differs')
            tokens.add(offer['token'])
        write_json(path,dict(version=1,profile=FIXED_TASKS[0],run_id=run_id,scene_epoch=epoch,
            leg=leg,issued_tick=tick,start_ns=(tick+1000)*1_000_000,tasks=offers))
