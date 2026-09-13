"""Pure preparation of one private diagnostic runner; never imports or runs it."""
from pathlib import Path
import ast
import hashlib
import json
import sys

EXPECTED = 'f5411627c2758f31d86da16b0bf38c469dda6fe4f03b89806bcb543db04ed63a'

def patch(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('private runner source differs')
    text = raw.decode('utf-8')
    changes = []

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('runner anchor not unique: ' + old[:70])
        changes.append((old, new))
        text = text.replace(old, new, 1)

    anchor = 'def run(args):\n'
    replace(anchor, anchor + '''    requested_group_work = getattr(args, 'group_work_timing', False)
    if type(requested_group_work) is not bool:
        raise ValueError('group-work timing flag must be a plain bool')
    if requested_group_work:
        conflicts = ('pause_probe', 'repeat_paused_clock', 'scene_lifecycle',
                     'scene_lease_loss', 'native_state_trace', 'probe_land_freshness',
                     'model_promotion_flight', 'early_work_timing', 'planner_release_proof')
        if args.task_profile != MIXED_PROFILE or getattr(args, 'dds_loss', None) or any(getattr(args, name, False) for name in conflicts):
            raise ValueError('group-work timing requires the standalone MIXED diagnostic')
''')
    anchor = '    validate_spin_cpu_request(args.task_profile, spin_cpu, timing_probe)\n'
    replace(anchor, anchor + '''    group_work = getattr(args, 'group_work_timing', False)
    group_work_file = None
    group_work_recorder = None
    if group_work:
        if args.task_profile != MIXED_PROFILE or timing_probe or spin_cpu or getattr(args, 'early_work_timing', False):
            raise ValueError('group-work timing requires MIXED alone, without other timing probes')
        from group_work_timing import GroupWorkTiming
        import inspect
        if 'timing_census' not in inspect.signature(JointPhysics).parameters:
            raise ValueError('group-work timing requires the reviewed census producer')
        def emit_group_work(report):
            if group_work_file is None:
                raise RuntimeError('group-work output is not open')
            group_work_file.write(json.dumps(report, separators=(',', ':'), allow_nan=False)+'\\n')
        group_work_recorder = GroupWorkTiming(emit=emit_group_work, census=True)
        if not callable(getattr(group_work_recorder, 'finish', None)):
            raise ValueError('group-work recorder requires explicit finish')
''')
    anchor = "    result['async_model_evidence_requested'] = async_model_evidence\n"
    replace(anchor, anchor + "    if group_work:\n        result['group_work_timing'] = dict(classification='diagnostic_only', initialized=True, full_acceptance=False)\n")
    anchor = "    result['source_sha256'] = {name:digest(REPO/name) for name in sources}\n"
    replace(anchor, "    if group_work:\n        sources.append('tools/group_work_timing.py')\n" + anchor)
    anchor = "                rate_log = resources.enter_context((live/'rate.jsonl').open('x', buffering=65536))\n"
    replace(anchor, "                if group_work:\n                    group_work_file = resources.enter_context((live/'group-work-timing.jsonl').open('x', buffering=65536))\n" + anchor)
    anchor = "                        issued_monotonic_ns=time.monotonic_ns(), **fields), separators=(',', ':'))+'\\n')\n"
    replace(anchor, anchor + "                    if group_work_recorder is not None:\n                        group_work_recorder.observe(dict(kind=kind, epoch=clock.epoch, tick=clock.tick, **fields))\n")
    anchor = "            def record(kind, **data):\n"
    replace(anchor, anchor + "                if group_work_recorder is not None and kind in ('diagnostic_step_cpu_timing', 'diagnostic_native_input_timing'):\n                    group_work_recorder.observe(dict(kind=kind, epoch=clock.epoch, tick=clock.tick, **data))\n                    return\n")
    anchor = "                                          wall=time.monotonic()-started,**data),separators=(',',':'),allow_nan=False)+'\\n')\n"
    replace(anchor, anchor + "                if group_work_recorder is not None and kind == 'step':\n                    group_work_recorder.observe(dict(kind=kind, epoch=clock.epoch, tick=clock.tick, **data))\n")
    anchor = '            physics = JointPhysics(resources, clock, workers, physics_health, record)\n'
    replace(anchor, "            if group_work:\n                physics = JointPhysics(resources, clock, workers, physics_health, record, timing_census=True)\n            else:\n    " + anchor)
    anchor = "        result['unowned_ap_after']=json_identity(828)\n"
    replace(anchor, "        if group_work_recorder is not None:\n            group_work_recorder.finish()\n            result['group_work_timing'] = group_work_recorder.summary()\n" + anchor)
    anchor = "        result['flight_completed'] = result['status']=='pass'\n"
    replace(anchor, "        if group_work and result['status'] == 'pass':\n            result['status'] = 'observed'\n" + anchor)
    anchor = "    runner.add_argument('--rate-spin-cpu-timing', action='store_true',\n"
    replace(anchor, "    runner.add_argument('--group-work-timing', action='store_true', help='MIXED-only bounded work-overrun diagnostic; never formal evidence')\n" + anchor)
    ast.parse(text)
    restored = text
    for old, new in reversed(changes):
        if restored.count(new) != 1:
            raise ValueError('reverse anchor not unique')
        restored = restored.replace(new, old, 1)
    if restored.encode('utf-8') != raw:
        raise ValueError('runner patch changed unrelated bytes')
    return text.encode('utf-8')

if __name__ == '__main__':
    source, output = map(Path, sys.argv[1:])
    raw = source.read_bytes()
    changed = patch(raw)
    with output.open('xb') as stream:
        stream.write(changed)
    print(json.dumps(dict(input_sha256=hashlib.sha256(raw).hexdigest(),
        output_sha256=hashlib.sha256(changed).hexdigest(),
        ast_parse=True, reverse_restoration=True, executed=False)))
