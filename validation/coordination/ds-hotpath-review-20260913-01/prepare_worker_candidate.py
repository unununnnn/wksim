#!/usr/bin/env python3
"""Pure preparation + equivalence checks for the ONE wksim #84 hot-path candidate.

Candidate (the only one; byte-identical by construction):
    Simulator/wksim_core/worker.py::encoded()
binds a single json.JSONEncoder at module scope instead of rebuilding a
JSONEncoder on every call through json.dumps(..., separators, allow_nan=False).
Exactly two source edits, both shown in patch-prep-report.json.

Safety properties:
  * the archived source is opened read-only; only its SHA-256 is compared;
  * outputs are written only into --out-dir (this review's assigned scope);
  * no production/private file is created or modified, no checkout is touched;
  * no child process, socket, model, ROS node, SITL or native library is used;
  * the candidate is prepared as .py.txt and is never imported as a package;
  * a run is refused unless each pinned SHA-256 matches the reviewed bytes.

No performance conclusion is drawn anywhere in this tool: the encoder deltas it
consumes come from a Windows host and are explicitly not an upper bound on WSL.
"""
import argparse
import ast
import hashlib
import json
import os
import sys

# Pinned archived bytes of the terminated diagnostic flight
# Ubuntu-22.04 /root/wksim-release-acceptance-fe3/validation/joint-public-flight-rfw9nmbb
# epoch 9b18d3d1322749db8e7dfccd7891b885.
PINNED = {
    'source__Simulator__wksim_core__worker.py.txt':
        '0becd1f3214b53c6169fb61ae010a969fb57a4ccbe26fb3ed3c3652c26ef7fab',
    'source__Simulator__wksim_core__joint.py.txt':
        '3d6056b85a399cdcc2a0078815990f051d12475b7b319e753009aeeecdbfc8fa',
    'source__tools__run_joint_flight.py.txt':
        '3bc281ea28b3787c0372a2c5cc57889aeb1d28bb16f4e85fcbdbd66d8d069932',
    'source__Simulator__wksim_runtime__joint_rate.py.txt':
        '0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4',
    'source__Simulator__wksim_runtime__joint_rate_probe.py.txt':
        'a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653',
    'source__tools__group_work_timing.py.txt':
        'a14d5e9c3c7e7c234972a8632d8da800ea9a91646f6b50e252675b38d30752db',
}
WORKER = 'source__Simulator__wksim_core__worker.py.txt'
JOINT = 'source__Simulator__wksim_core__joint.py.txt'
RUNNER = 'source__tools__run_joint_flight.py.txt'

BASELINE_FUNCTION = ('def encoded(value):\n'
                     "    return json.dumps(value, separators=(',', ':'), allow_nan=False)\n")
CANDIDATE_FUNCTION = ('def encoded(value):\n'
                      '    return _ENCODER.encode(value)\n')
CANDIDATE_CONSTANT = (
    '# One bound encoder replaces a per-call JSONEncoder construction inside\n'
    "# json.dumps(..., separators=(',', ':'), allow_nan=False). Settings, exception\n"
    '# behaviour and output bytes are identical to the previous call.\n'
    "_ENCODER = json.JSONEncoder(separators=(',', ':'), allow_nan=False)\n")
ANCHOR_HINT = 'REQUEST_LIMIT = 4096\nRESPONSE_LIMIT = 65536\n'

HOT_SITES = [
    (293, 'receive_workers', 'parent builds one outgoing request frame per channel per tick'),
    (231, '_worker_loop', 'worker serializes the response row per step tick'),
    (235, '_worker_loop', 'worker serializes the evidence header per step tick'),
]
COLD_SITES = [27, 242, 243, 248]


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_pinned(name, raw):
    if name not in PINNED:
        raise ValueError('unpinned input: %s' % name)
    actual = sha256(raw)
    if actual != PINNED[name]:
        raise ValueError('pinned source mismatch for %s: %s != %s' % (name, actual, PINNED[name]))
    return actual


def read_pinned(archive):
    found = {}
    for name in PINNED:
        with open(os.path.join(archive, name), 'rb') as handle:
            raw = handle.read()
        verify_pinned(name, raw)
        found[name] = raw
    return found


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError('anchor not unique for %s (count=%d)' % (label, text.count(old)))
    return text.replace(old, new, 1)


def build_worker_candidate(worker_raw, name=WORKER):
    verify_pinned(name, worker_raw)
    text = worker_raw.decode('utf-8')
    candidate = replace_once(text, ANCHOR_HINT, ANCHOR_HINT + '\n' + CANDIDATE_CONSTANT,
                             'module constants')
    candidate = replace_once(candidate, BASELINE_FUNCTION, CANDIDATE_FUNCTION, 'encoded()')
    ast.parse(candidate)
    restored = replace_once(candidate, ANCHOR_HINT + '\n' + CANDIDATE_CONSTANT, ANCHOR_HINT,
                            'constants reversal')
    restored = replace_once(restored, CANDIDATE_FUNCTION, BASELINE_FUNCTION, 'function reversal')
    if restored.encode('utf-8') != worker_raw:
        raise ValueError('candidate patch changed unrelated bytes')
    if candidate.count(CANDIDATE_CONSTANT) != 1 or candidate.count(CANDIDATE_FUNCTION) != 1:
        raise ValueError('candidate patch did not apply exactly once')
    return candidate.encode('utf-8')


def module_api(raw):
    tree = ast.parse(raw.decode('utf-8'))
    api = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('_'):
                api[node.name] = dict(kind='function', positional=len(node.args.args),
                                      kwonly=len(node.args.kwonlyargs))
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith('_'):
                api[node.name] = dict(kind='class',
                                      methods=sorted(m.name for m in node.body
                                                     if isinstance(m, ast.FunctionDef)))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith('_'):
                    api[target.id] = dict(kind='constant')
    return api


def load_module(namespace, raw, relative):
    import types
    package = types.ModuleType('wksim_pkg_' + namespace)
    package.__path__ = []
    sys.modules[package.__name__] = package
    for suffix, names in relative.items():
        stub = types.ModuleType(package.__name__ + '.' + suffix)
        for attribute in names:
            setattr(stub, attribute, type(attribute, (), {}))
        sys.modules[stub.__name__] = stub
    module = types.ModuleType(package.__name__ + '.worker')
    module.__package__ = package.__name__
    module.__file__ = '<%s/worker.py>' % package.__name__
    exec(compile(raw.decode('utf-8'), module.__file__, 'exec'), module.__dict__)
    return module


def load_worker(raw, namespace):
    return load_module(namespace, raw, {'model': ['Model'],
                                        'ap_json': ['decode_servos', 'sensor_fields',
                                                    'sensor_message'],
                                        'px4_mavlink': ['Sender', 'actuator_commands',
                                                        'gps_arguments']})


def state_values(seed=12345, count=120):
    value = seed
    out = []
    for _ in range(count):
        value = (1103515245 * value + 12345) % (1 << 31)
        out.append((value / (1 << 31)) * 40.0 - 20.0)
    return out


def corpus():
    state = state_values()
    cases = {}
    cases['step_request'] = dict(version=1, epoch='9b18d3d1322749db8e7dfccd7891b885',
                                 tick=131760, commands=[(i % 17) / 17 for i in range(16)])
    cases['step_request_terrain'] = dict(version=1, epoch='9b18d3d1322749db8e7dfccd7891b885',
                                         tick=131760, commands=[(i % 17) / 17 for i in range(16)],
                                         terrain=[float(i) / 1000 for i in range(15)])
    cases['state_response'] = dict(version=1, epoch='9b18d3d1322749db8e7dfccd7891b885',
                                   tick=131760, state=state)
    cases['initial_response'] = dict(version=1, epoch='9b18d3d1322749db8e7dfccd7891b885',
                                     tick=0, state=state, initial=True)
    cases['snapshot_response'] = dict(version=1, epoch='9b18d3d1322749db8e7dfccd7891b885',
                                      tick=0, state=None)
    cases['extras_row'] = dict(commands=[0.0] * 16, input='{"version":1}\n',
                               request=dict(version=1, epoch='9b18d3d1322749db8e7dfccd7891b885',
                                            tick=1, commands=[0.5] * 16))
    cases['extras_row_terrain'] = dict(commands=[1.0] * 16, input='{"version":1}\n',
                                       terrain=[0.25] * 15, request=dict(version=1, tick=7))
    cases['empty_containers'] = dict(a=[], b={}, c=[[], {}], d='')
    cases['negatives_and_edges'] = dict(zero=-0.0, neg=-1.5e-9, big=2 ** 63 - 1,
                                        small=-(2 ** 63), flag=True, none=None,
                                        tiny=5e-324, huge=1.7976931348623157e308)
    cases['text_escapes'] = dict(quote='"', backslash='\\', newline='\n', tab='\t',
                                 control='\x00\x01\x1f', unicode='\u4e2d\u6587\U0001f680',
                                 solidus='/', del_='\x7f')
    cases['key_order'] = dict(z=1, a=2, m=3, b=4)
    cases['nested'] = dict(outer=dict(inner=[dict(deep=[1, 2, {'x': 'y'}])]))
    return cases


def equality_checks(baseline, candidate):
    results = []
    for name, value in sorted(corpus().items()):
        try:
            expected, outcome = baseline.encoded(value), 'value'
        except BaseException as error:  # noqa: BLE001
            expected, outcome = (type(error).__name__, str(error)), 'raise'
        try:
            actual, got = candidate.encoded(value), 'value'
        except BaseException as error:  # noqa: BLE001
            actual, got = (type(error).__name__, str(error)), 'raise'
        same = outcome == got and expected == actual
        results.append(dict(case=name, outcome=outcome, identical=same,
                            expected=expected if outcome == 'raise' else '<text>',
                            actual=actual if got == 'raise' else '<text>'))
        if not same:
            raise AssertionError('encoded() differs for %s: %r != %r' % (name, expected, actual))

    def raises(module, value, expected_type):
        try:
            module.encoded(value)
        except BaseException as error:  # noqa: BLE001
            return type(error) is expected_type, '%s: %s' % (type(error).__name__, error)
        return False, 'no exception'

    for name, value, kind in [('nan_float', float('nan'), ValueError),
                              ('inf_float', float('inf'), ValueError),
                              ('neg_inf_nested', dict(state=[1.0, float('-inf')]), ValueError),
                              ('bytes_object', b'raw', TypeError),
                              ('set_object', {1, 2}, TypeError),
                              ('custom_object', object(), TypeError),
                              ('tuple_key', {(1, 2): 'x'}, TypeError)]:
        left, right = raises(baseline, value, kind), raises(candidate, value, kind)
        same = left == right and left[0]
        results.append(dict(case='failure/' + name, outcome=kind.__name__, identical=same,
                            expected=left[1], actual=right[1]))
        if not same:
            raise AssertionError('failure semantics differ for %s: %r != %r' % (name, left, right))

    circular = {}
    circular['self'] = circular
    left, right = raises(baseline, circular, ValueError), raises(candidate, circular, ValueError)
    same = left == right and left[0]
    results.append(dict(case='failure/circular', outcome='ValueError', identical=same,
                        expected=left[1], actual=right[1]))
    if not same:
        raise AssertionError('circular-reference semantics differ: %r != %r' % (left, right))
    return results


def worker_call_counts(sources):
    """Re-derive per-tick call counts from the pinned bytes, not from memory."""
    lines = sources[WORKER].decode('utf-8').split('\n')
    joint = sources[JOINT].decode('utf-8')
    runner = sources[RUNNER].decode('utf-8')
    sites = {}
    for number, function, role in HOT_SITES:
        text = lines[number - 1]
        if text.count('encoded(') != 1:
            raise ValueError('line %d is not a single encoded() call: %r' % (number, text))
        sites[str(number)] = dict(line=number, text=text.strip(), function=function, role=role)
    all_sites = [index + 1 for index, line in enumerate(lines) if 'encoded(' in line]
    expected = sorted([number for number, _, _ in HOT_SITES] + COLD_SITES)
    if sorted(all_sites) != expected:
        raise ValueError('unexpected encoded() line set: %r' % (all_sites,))
    for number in COLD_SITES:
        if 'encoded(' not in lines[number - 1]:
            raise ValueError('cold line %d is not an encoded() call' % number)

    worker_set = "inputs = dict(arducopter=self.pending_ap['commands'], px4=self.px_commands)"
    batch = 'responses = receive_workers(requests, self.clock.epoch, health=self.health)'
    loop = 'for name, commands in inputs.items():'
    advance = '        states = advance()'
    main_loop = '    while clock.tick < MAX_TICKS:'
    for label, text, anchor in (('parent worker set', joint, worker_set),
                                ('batching call', joint, batch),
                                ('channel loop', joint, loop),
                                ('per-tick advance', runner, advance),
                                ('main loop', runner, main_loop)):
        if text.count(anchor) != 1:
            raise ValueError('anchor not unique: %s (count=%d)' % (label, text.count(anchor)))
    if joint.count('receive_workers(') + runner.count('receive_workers(') != 1:
        raise ValueError('unexpected receive_workers call count')

    channels = 2
    per_worker = 2
    return dict(
        parent_channels=channels,
        receive_workers_calls_per_tick=1,
        parent_request_frames_per_tick=channels,
        child_calls_per_worker_per_tick=per_worker,
        worker_processes=channels,
        whole_system_encoded_calls_per_tick=channels + channels * per_worker,
        sites=sites,
        all_encoded_lines=all_sites,
        cold_path_lines=COLD_SITES,
        cold_path_note=('lines 27/242/243/248 are one-time setup or the tick-zero sidecar '
                        'branch and are never counted as per-tick work'),
        anchors=dict(parent_worker_set=worker_set, batching_call=batch, channel_loop=loop,
                     per_tick_advance=advance, main_loop=main_loop),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--report-name', default='patch-prep-report.json')
    parser.add_argument('--candidate-name', default='worker-candidate.py.txt')
    parser.add_argument('--reports', default='group-work-timing.jsonl')
    parser.add_argument('--result', default='result.json')
    parser.add_argument('--op-cost', default='op-cost-host.json')
    args = parser.parse_args(argv)

    sources = read_pinned(args.archive)
    candidate_raw = build_worker_candidate(sources[WORKER])
    counts = worker_call_counts(sources)
    baseline = load_worker(sources[WORKER], 'baseline')
    candidate = load_worker(candidate_raw, 'candidate')
    equality = equality_checks(baseline, candidate)
    if module_api(sources[WORKER]) != module_api(candidate_raw):
        raise AssertionError('public module API changed')
    if candidate.encoded.__code__.co_names != ('_ENCODER', 'encode'):
        raise AssertionError('candidate encoded() does not call the bound encoder')
    if baseline.encoded.__code__.co_names != ('json', 'dumps'):
        raise AssertionError('unexpected baseline encoded() body')
    if not (candidate.REQUEST_LIMIT == baseline.REQUEST_LIMIT == 4096):
        raise AssertionError('REQUEST_LIMIT changed')
    if not (candidate.RESPONSE_LIMIT == baseline.RESPONSE_LIMIT == 65536):
        raise AssertionError('RESPONSE_LIMIT changed')

    with open(os.path.join(args.archive, args.result), encoding='utf-8') as handle:
        archived_result = json.load(handle)
    recorder = archived_result['group_work_timing']
    archived_counts = recorder['counts']
    if archived_counts['reports_dropped'] != (archived_counts['over_budget_groups']
                                             - archived_counts['reports_emitted']):
        raise ValueError('archived drop accounting does not add up')
    if archived_counts['diagnostic_errors'] != 0:
        raise ValueError('archived recorder reported diagnostic errors')
    with open(os.path.join(args.archive, args.reports), encoding='utf-8') as handle:
        retained = [json.loads(line) for line in handle if line.strip()]
    if len(retained) != archived_counts['reports_emitted']:
        raise ValueError('retained report count differs from result.json')
    if any(r['classification'] != 'diagnostic_only' or r['census'] is not True for r in retained):
        raise ValueError('retained reports are not census diagnostic_only rows')

    op_cost = None
    if args.op_cost:
        op_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.op_cost)
        if os.path.isfile(op_path):
            with open(op_path, encoding='utf-8') as handle:
                op_cost = json.load(handle)

    os.makedirs(args.out_dir, exist_ok=True)
    candidate_path = os.path.join(args.out_dir, args.candidate_name)
    expected_sha = sha256(candidate_raw)
    if os.path.exists(candidate_path):
        with open(candidate_path, 'rb') as handle:
            existing = sha256(handle.read())
        if existing != expected_sha:
            raise FileExistsError('%s exists with different bytes (%s != %s); remove it and re-run'
                                  % (candidate_path, existing, expected_sha))
        reused = True
    else:
        with open(candidate_path, 'xb') as handle:
            handle.write(candidate_raw)
        reused = False

    report = dict(
        kind='wksim.hotpath-patch-prep.v3',
        classification='diagnostic_only',
        full_acceptance=False,
        assigned_scope='validation/coordination/ds-hotpath-review-20260913-01',
        archive=os.path.abspath(args.archive),
        candidate_source='Simulator/wksim_core/worker.py::encoded',
        candidate_edits=[
            dict(anchor='REQUEST_LIMIT/RESPONSE_LIMIT block',
                 insert=CANDIDATE_CONSTANT),
            dict(anchor='def encoded(value)', replace_from=BASELINE_FUNCTION,
                 replace_to=CANDIDATE_FUNCTION),
        ],
        edits_applied=2,
        pinned_sha256={name: PINNED[name] for name in sorted(PINNED)},
        baseline_sha256=sha256(sources[WORKER]),
        candidate_sha256=expected_sha,
        candidate_path=os.path.abspath(candidate_path),
        candidate_reused_byte_identical=reused,
        executed_candidate=False,
        touched_production_files=False,
        touched_private_files=False,
        static_call_counts=counts,
        equivalence=dict(
            corpus_cases=len(equality),
            all_identical=all(entry['identical'] for entry in equality),
            cases=equality,
            falsifying_condition=('any value for which _ENCODER.encode() differs from '
                                  'json.dumps(value, separators=(",", ":"), allow_nan=False) '
                                  'in returned text, exception type or exception message; '
                                  'the 20-case corpus plus exception battery is the executed '
                                  'attempt, no further fuzz is claimed here'),
            public_api_unchanged=True,
            preserved_by_construction=[
                'clock reads: no time.monotonic/time.monotonic_ns call is touched',
                'native protocol ordering: no wait_ap/wait_px4/select path is touched',
                'backpressure: os.write/os.set_blocking/BlockingIOError path untouched',
                'deadlines: every timeout/deadline expression untouched',
                'exceptions: identical ValueError/TypeError/RecursionError text and type',
            ],
        ),
        archived_recorder=dict(counts=archived_counts, report_limit=recorder['report_limit'],
                               census=recorder['census'], valid=recorder['valid']),
        performance=dict(
            conclusion=None,
            reason=('no performance conclusion is drawn. The only encoder numbers available '
                    'were measured on the Windows DSH host (op-cost-host.json) and are not an '
                    'upper bound on WSL/Linux savings; the WSL measurement needed to bound '
                    'them was not performed and would require native execution, which is out '
                    'of scope.'),
            consumed_op_cost=op_cost,
            qualification=('under the idealised assumption of zero work outside the measured '
                           'steps and zero release jitter, the frozen no-catch-up rule gives '
                           'next_start >= previous_start + period, so start drift would recur '
                           'as D_next = D_current + max(0, W - period) rather than '
                           'max(0, D_current + W - period). Real observed start deltas already '
                           'contain step work, out-of-step work and release jitter, so no '
                           'quantitative decision is made here; the main session owns it.'),
        ),
        reclaimed_history=dict(
            rejected='joint-rate-candidate.py.txt.rejected (a projected_lateness/no-catch-up '
                     'recurrence candidate withdrawn by the reviewer: it allowed catch-up and is '
                     'not the frozen rule)',
            live_spin_tests_removed=True,
            note='retained as rejected history only; never apply it to any checkout',
        ),
        limitations=[
            'byte equality is necessary but not sufficient for any rate claim; no flight ran',
            'encoder deltas measured on the Windows host are not an upper bound on WSL and the '
            'candidate is therefore not claimed to save anything on the target host',
            'the archived census retains 16 of 18 over-budget groups '
            '(reports_emitted=16, reports_dropped=2, report_limit=16, an explicit bound); the '
            'total excess is a lower bound and no dropped group is reconstructed',
            'wall and thread-CPU samples inside a wait bracket are taken sequentially, so the '
            'difference is not rigorous off-CPU attribution and no off-CPU cause is claimed',
            'this tool never applies the candidate to any production or private checkout',
        ],
    )
    report_path = os.path.join(args.out_dir, args.report_name)
    with open(report_path, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(ok=True,
                          baseline_sha256=report['baseline_sha256'],
                          candidate_sha256=report['candidate_sha256'],
                          edits_applied=report['edits_applied'],
                          corpus_cases=len(equality),
                          all_identical=report['equivalence']['all_identical'],
                          encoded_calls_per_tick=counts['whole_system_encoded_calls_per_tick'],
                          archived_counts=archived_counts,
                          performance_conclusion=report['performance']['conclusion'],
                          report=os.path.abspath(report_path),
                          candidate=os.path.abspath(candidate_path)), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
