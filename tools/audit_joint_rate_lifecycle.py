"""Offline raw audit of formal rate switches, pause, four ticks and fresh resume."""
import argparse
import json
from pathlib import Path
import sys

from audit_joint_flight import digest, lines, require
from audit_joint_rate import read, schedule
from audit_joint_product import audit_epoch, cdr_string
from audit_joint_product_lifecycle import retained_identity, raw_public
from Simulator.wksim_runtime.joint_actions import validate_request


PASS_TERMINAL_REASONS = frozenset(('set-rate', 'pause', 'resume_confirmed', 'stop'))


def closed_rate_schedule(path, epoch, *, expected_terminal_reasons):
    """Audit the production schedule with failure mode disabled.

    A lifecycle run can only be PASS when its raw schedule closes without a
    rate-unmet row.  The separate failure audit may certify a genuine
    >100 ms fault, but this successful lifecycle audit must never consume that
    escape hatch or relabel it as a completed run.
    """
    require(isinstance(expected_terminal_reasons, (list, tuple))
            and all(isinstance(reason, str) and reason for reason in expected_terminal_reasons),
            'Lifecycle terminal reason contract is missing or malformed')
    try:
        segments = schedule(path, epoch, allow_failure=False)
    except (AssertionError, ValueError) as error:
        raise ValueError('Lifecycle PASS schedule rejected: rate_unmet, >100ms lateness or catch-up: '
                         + str(error)) from error
    require(segments and all('failure' not in segment for segment in segments.values()),
            'Lifecycle schedule contains a failure segment')
    terminal = {}
    for row in lines(path):
        if row.get('kind') == 'rate_segment_end':
            require(row.get('segment_id') not in terminal,
                    'Lifecycle schedule repeats a segment terminal record')
            terminal[row['segment_id']] = row
    require(set(terminal) == set(segments),
            'Lifecycle schedule lacks one terminal record per segment')
    require(len(expected_terminal_reasons) == len(segments),
            'Lifecycle terminal reason count differs from rate segments')
    for (segment_id, segment), expected_reason in zip(segments.items(), expected_terminal_reasons):
        anchor = segment['anchor']
        end = terminal[segment_id]
        require(end.get('completed_groups') == len(segment['groups']),
                'Lifecycle segment summary disagrees with completed groups')
        # A resume_requested anchor is a deliberate transition boundary: the
        # producer closes it at resume_confirmed before another group can run.
        require(segment['groups'] or anchor['anchor'].get('transition') is True,
                'Lifecycle schedule closed a non-transition segment without a group')
        require(end.get('reason') in PASS_TERMINAL_REASONS,
                'Lifecycle segment has an unknown or failure terminal reason')
        require(end.get('reason') == expected_reason,
                f'Lifecycle segment {segment_id} terminal reason does not match production '
                f'close/reanchor operation: expected {expected_reason!r}')
        if anchor['anchor'].get('transition') is True:
            require(end['reason'] == 'resume_confirmed',
                    'Lifecycle transition segment did not close at resume confirmation')
    return segments


def audit(root):
    root = Path(root)
    flow, wrapper, run = [read(root / name) for name in ('flow.json', 'wrapper.json', 'run/result.json')]
    require(flow['mode'] == 'lifecycle' and flow['status'] == 'behavior_pass'
            and flow['result'] == run and run['status'] == 'pass' and len(run['epochs']) == 1,
            'Expected one completed formal lifecycle epoch')
    require(wrapper['driver_returncode'] == wrapper['manager_returncode'] == 0
            and wrapper['driver_source_unchanged'] and not wrapper['remaining_manager_group'],
            'Driver or manager cleanup failed')
    item = run['epochs'][0]; epoch = item['epoch']; run_id = run['run_id']
    directory = root / 'run/epochs' / epoch
    result = retained_identity(directory, item, run_id)
    require(not result.get('faults') and result['flight_completed'], 'Epoch faulted or flight incomplete')
    # audit_epoch calls audit_product_timeline and checks every raw model input,
    # state, native wire packet, unique clock tick and public task request.
    physical = audit_epoch(root / 'run', item, run_id)
    events, _, counts = raw_public(directory, epoch, run_id)
    actions = flow['actions']
    require([a['response']['action'] for a in actions] ==
            ['start-task', 'set-rate', 'set-rate', 'pause', 'step', 'resume', 'stop'], 'Unexpected actions')
    prior = -1
    for action in actions:
        request, response = action['submitted']['request'], action['response']
        validate_request(request, run_id, epoch)
        require(request['command_id'] > prior, 'Nonmonotonic action command ID')
        prior = request['command_id']
        name = f"{prior:020d}-{request['token']}.json"
        require(read(root / 'run/actions' / name) == request
                and read(root / 'run/action-results' / epoch / (request['token'] + '.json')) == response
                and response['state'] == 'completed'
                and all(response[k] == request[k] for k in ('run_id', 'epoch', 'command_id', 'action', 'token')),
                'Action lacks matching original request and completion receipt')
    permissions, acknowledgements = [], []
    for row in lines(directory / 'scene-lifecycle.jsonl'):
        if row['kind'] not in ('permission', 'ack_raw'): continue
        value = cdr_string(row['cdr_hex'])
        require(value['run_id'] == run_id and value['scene_epoch'] == epoch, 'Lifecycle crossed identity')
        (permissions if row['kind'] == 'permission' else acknowledgements).append(value)
    pause, step, resume = actions[3:6]
    frozen = pause['response']['authority']['tick']
    stepped = step['response']['authority']['tick']
    require(stepped == frozen + 4 and frozen % 4 == 0
            and all(a['response']['authority']['phase'] == 'paused' for a in (pause, step)),
            'Step did not end exactly four ticks later, paused')
    matched = {}
    for action, phase in ((pause, 'paused'), (step, 'stepping'), (resume, 'resuming')):
        request = action['submitted']['request']
        request_id = action['response']['authority']['last_request_id']
        candidates = [p for p in permissions if p['phase'] == phase and p['request_id'] == request_id]
        require(candidates and candidates[0]['issued_monotonic_s'] >= request['command_id'] / 1e9,
                'Missing action-correlated permission after original command: ' + phase)
        matched[phase] = candidates
    pause_start = matched['paused'][0]['issued_monotonic_s']
    step_start = matched['stepping'][0]['issued_monotonic_s']
    resume_start = matched['resuming'][0]['issued_monotonic_s']
    require(step_start - pause_start >= 4 and matched['paused'][0]['tick'] == frozen
            and matched['resuming'][0]['tick'] == stepped, 'Pause duration or resume boundary differs')
    exact_steps = []
    for row in lines(directory / 'wire.jsonl'):
        if row['kind'] not in ('step', 'sensor', 'gps'): continue
        wall = row['issued_monotonic_s']
        require(not pause_start <= wall < step_start, 'Physics/sensor advanced during four-second pause')
        if step_start <= wall < resume_start:
            require(frozen < row['tick'] <= stepped, 'Step window advanced outside exact four ticks')
            if row['kind'] == 'step': exact_steps.append(row['tick'])
    require(exact_steps == list(range(frozen + 1, stepped + 1)), 'Missing/extra actual native model steps')
    native_acks = {}
    for action, phase in ((pause, 'paused'), (resume, 'resuming')):
        request_id = action['response']['authority']['last_request_id']
        selected = {}
        for ack in acknowledgements:
            if ack['phase'] != phase or ack['request_id'] != request_id or not ack['ready']: continue
            permission = next((p for p in matched[phase] if p['sequence'] == ack['sequence']), None)
            require(permission is not None and ack['tick'] == permission['tick']
                    and ack['issued_monotonic_s'] >= permission['issued_monotonic_s'],
                    'Ready ACK lacks preceding exact permission sequence')
            if phase == 'resuming' and ack['source_boot_ns'] <= stepped * 1000000: continue
            if phase == 'paused' and ack['issued_monotonic_s'] >= step_start: continue
            require(any(e.get('control_epoch') == ack['control_epoch'] for e in events[ack['uav_id']]),
                    'Lifecycle ACK does not belong to actual public Control')
            selected[ack['uav_id']] = ack
        require(set(selected) == {1, 2}, 'Missing actual dual ready/fresh native-state ACKs: ' + phase)
        native_acks[phase] = selected
    terminal_reasons = []
    for action in actions[1:]:
        name = action['response']['action']
        if name == 'set-rate':
            terminal_reasons.append('set-rate')
        elif name == 'pause':
            terminal_reasons.append('pause')
        elif name == 'resume':
            terminal_reasons.append('resume_confirmed')
        elif name == 'stop':
            terminal_reasons.append('stop')
    segments = closed_rate_schedule(directory / 'rate.jsonl', epoch,
                                    expected_terminal_reasons=terminal_reasons)
    anchors = [s['anchor'] for s in segments.values()]
    require([a['reason'] for a in anchors] == ['synchronized_boundary', 'set-rate', 'set-rate',
            'resume_requested', 'resume_confirmed'], 'Rate anchors crossed expected lifecycle')
    for action, anchor, rate in zip(actions[1:3], anchors[1:3], (1, .5)):
        request, response = action['submitted']['request'], action['response']
        require(request['requested_rate'] == anchor['requested_rate'] == rate
                and anchor['request_id'] == request['token'] and anchor['anchor'] == response['rate']['anchor']
                and anchor['anchor']['tick'] == response['authority']['tick']
                and anchor['anchor']['wall_ns'] >= request['command_id'], 'Rate switch lacks original causality')
    require(anchors[3]['anchor']['tick'] == stepped and anchors[3]['anchor']['transition']
            and anchors[3]['anchor']['wall_ns'] >= resume['submitted']['request']['command_id']
            and anchors[4]['anchor']['tick'] == resume['response']['authority']['tick']
            and not anchors[4]['anchor']['transition']
            and all(a['requested_rate'] == .5 and a['request_id'] == actions[2]['submitted']['request']['token']
                    for a in anchors[3:]), 'Resume used old rate debt or lost requested rate')
    for a in anchors:
        require(a['steady_after_ns'] == a['anchor']['wall_ns'] + 2_000_000_000, 'Changed stabilization boundary')
    return dict(status='pass', epoch=epoch, scope='one retained formal rate/lifecycle behavior epoch',
        executed_source_sha256=result['source_sha256'], physical=physical, public_state_counts=counts,
        pause=dict(tick=frozen, wall_seconds=step_start-pause_start), exact_step_ticks=exact_steps,
        rate_contract=dict(no_catch_up=True, over_100ms='fail_closed', pause_step_ticks=4,
                           worst_lateness_ns=max(segment['worst_ns'] for segment in segments.values())),
        native_control_acks=native_acks,
        rate_segments=[dict(segment_id=s['anchor']['segment_id'], requested_rate=s['anchor']['requested_rate'],
            anchor=s['anchor']['anchor'], completed_groups=len(s['groups']), worst_lateness_ns=s['worst_ns'],
            terminal_reason=terminal_reasons[index])
            for index, s in enumerate(segments.values())],
        limitations=['Retained executed sources only; this does not accept later source edits.',
            'One epoch and a brief 1x switch do not certify 1x throughput or three-epoch rate acceptance.',
            'Ready lifecycle ACKs attest the native-state/control pause/resume handshake; native task command ACKs are separately decoded by the product audit.',
            'No UE, MATLAB, vendor dynamics comparison, overload or current-host live PID verification.'],
        evidence_sha256={p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob('*')) if p.is_file()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.directory.resolve()), 'Output must be outside evidence')
    # Include transitive local Python dependencies actually imported during audit.
    repo = Path(__file__).resolve().parents[1]
    dependencies = {p: digest(p) for folder in ('tools', 'Simulator/wksim_runtime', 'Simulator/wksim_core')
                    for p in (repo / folder).rglob('*.py')}
    try:
        report = audit(args.directory)
    except (OSError, ValueError, KeyError, TypeError, ImportError, AssertionError, StopIteration) as error:
        report = dict(status='failed', error=repr(error))
    loaded = {Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, '__file__', None)}
    selected = {p: sha for p, sha in dependencies.items() if p.resolve() in loaded}
    report['audit_dependencies_sha256'] = {p.relative_to(repo).as_posix(): sha for p, sha in selected.items()}
    report['changed_audit_dependencies'] = [str(p) for p, sha in selected.items() if digest(p) != sha]
    if report['changed_audit_dependencies']: report['status'] = 'failed'
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: report.get(k) for k in ('status', 'epoch', 'pause', 'exact_step_ticks', 'error')}))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
