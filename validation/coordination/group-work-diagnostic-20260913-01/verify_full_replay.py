"""Replay the real integration fixture's raw rows through the real routing (v2).

AST-extracts ONLY record/record_rate from runner-candidate-v2.py.txt (never
imports or executes the runner). The input is the ACTUAL captured stream of
group-work-timing-fixture.json (runs.census_true): the pre-end rate rows
(rate_request/rate_anchor/rate_group_start), then ALL original wire rows in
their original order (sensor/actuator every tick, PX4 sensor+actuator+barrier at
tick 44, step, and the two diagnostic kinds), then rate_group_end. Only
kind/epoch/tick and the original wall/issued timestamps are stripped; the real
routing regenerates them from a fake clock. StringIO replaces the wire/rate/
group-report files. Nothing is rebuilt from the expected report and no rows are
invented. Pure memory: socket/subprocess entry points are rigged to raise for
the whole replay. Writes one NEW result JSON (verify-full-replay-v2.json) and
never overwrites any existing record.
"""
import ast
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from tools.group_work_timing import GroupWorkTiming

ROUTING = HERE / 'runner-candidate-v2.py.txt'
FIXTURE = ROOT / 'validation/coordination/group-work-timing-integration-20260913/group-work-timing-fixture.json'
EXPECTED = HERE / 'producer-recorder-replay.json'  # coordinator's independent expectation
DIAGNOSTIC_KINDS = ('diagnostic_step_cpu_timing', 'diagnostic_native_input_timing')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
run = fixture['runs']['census_true']
original_wire = run['wire']          # full captured stream, 23 rows
original_rate = run['rate_rows']     # rate_request, rate_anchor, group start/end
expected = json.loads(EXPECTED.read_text(encoding='utf-8'))['census_true']

# AST-extract only the two routing functions; the runner is never imported.
parsed = ast.parse(ROUTING.read_text(encoding='utf-8'))
nodes = []
for name in ('record_rate', 'record'):
    matches = [node for node in ast.walk(parsed)
               if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(matches) == 1
    nodes += matches


def forbidden(name):
    def stub(*args, **kwargs):
        raise AssertionError(name + ' must not be called')
    return stub


class FakeTime:
    def __init__(self):
        self.wall_reads = 0
        self.ns_reads = 0

    def monotonic(self):
        self.wall_reads += 1
        return 2.0

    def monotonic_ns(self):
        self.ns_reads += 1
        return 2_000_000_000


fake_time = FakeTime()
clock = types.SimpleNamespace(epoch='fixture-epoch-group-work-timing', tick=None)
group_stream = io.StringIO()


def emit_group_work(report):
    group_stream.write(json.dumps(report, separators=(',', ':'), allow_nan=False) + '\n')


recorder = GroupWorkTiming(emit=emit_group_work, census=True)
namespace = dict(json=json, clock=clock, started=1.0, time=fake_time,
                 wire=io.StringIO(), rate_log=io.StringIO(),
                 diagnostic_identity=None, group_work_recorder=recorder,
                 add_timing_probe_identity=forbidden('add_timing_probe_identity'))
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROUTING), 'exec'), namespace)

guards = [patch.object(socket, 'socket', side_effect=AssertionError('socket forbidden')),
          patch.object(socket, 'create_connection', side_effect=AssertionError('socket forbidden')),
          patch.object(subprocess, 'Popen', side_effect=AssertionError('subprocess forbidden')),
          patch.object(subprocess, 'run', side_effect=AssertionError('subprocess forbidden')),
          patch.object(subprocess, 'call', side_effect=AssertionError('subprocess forbidden'))]
for guard in guards:
    guard.start()
try:
    # Pre-end rate rows, then the complete original wire order, then the end row.
    for row in original_rate[:-1]:
        clock.tick = row['tick']
        fields = {k: v for k, v in row.items()
                  if k not in ('kind', 'epoch', 'tick', 'issued_monotonic_ns')}
        namespace['record_rate'](row['kind'], **fields)
    for row in original_wire:
        clock.tick = row['tick']
        data = {k: v for k, v in row.items() if k not in ('kind', 'epoch', 'tick', 'wall')}
        namespace['record'](row['kind'], **data)
    end = original_rate[-1]
    assert end['kind'] == 'rate_group_end'
    clock.tick = end['tick']
    namespace['record_rate'](end['kind'], **{k: v for k, v in end.items()
                             if k not in ('kind', 'epoch', 'tick', 'issued_monotonic_ns')})
finally:
    for guard in guards:
        guard.stop()

summary = recorder.finish()
wire_rows = [json.loads(line) for line in namespace['wire'].getvalue().splitlines()]
rate_rows = [json.loads(line) for line in namespace['rate_log'].getvalue().splitlines()]
reports = [json.loads(line) for line in group_stream.getvalue().splitlines()]

# The ordinary wire stream must survive untouched: every sensor/actuator/barrier/
# step row, same order, same decoded fields (the wall timestamp is regenerated).
original_ordinary = [{k: v for k, v in row.items() if k != 'wall'}
                     for row in original_wire if row['kind'] not in DIAGNOSTIC_KINDS]
replayed_ordinary = [{k: v for k, v in row.items() if k != 'wall'} for row in wire_rows]
assert replayed_ordinary == original_ordinary
assert not any(row['kind'] in DIAGNOSTIC_KINDS for row in wire_rows)
# Every rate row survives on the rate log with fields intact (issued time regenerated).
assert [{k: v for k, v in row.items() if k != 'issued_monotonic_ns'} for row in rate_rows] == \
       [{k: v for k, v in row.items() if k != 'issued_monotonic_ns'} for row in original_rate]
# The recorder result, against the coordinator's independent expectation.
assert len(reports) == 1
report = reports[0]
assert report['work_ns'] == 9710000 == run['work_ns']
assert report['work_decomposition']['closes'] is True
assert len(report['step_windows']) == 4
assert len(report['visible_native_waits']) == 5
assert all(wait['stage_verified'] for wait in report['visible_native_waits'])
assert report == expected['report']
summary_wire = json.loads(json.dumps(summary))
if summary_wire != expected['summary']:
    diff = {key: (summary_wire.get(key), expected['summary'].get(key))
            for key in set(summary_wire) | set(expected['summary'])
            if summary_wire.get(key) != expected['summary'].get(key)}
    raise AssertionError('summary differs from independent expectation: ' + json.dumps(diff, indent=2))
assert summary['valid'] is True
assert summary['counts'] == dict(groups_complete=1, groups_incomplete=0,
                                 over_budget_groups=1, reports_emitted=1,
                                 reports_dropped=0, diagnostic_errors=0)
assert fake_time.wall_reads == len(wire_rows) == len(original_ordinary) == 15
assert fake_time.ns_reads == len(rate_rows) == len(original_rate) == 4

result = dict(schema='wksim.group-work-full-replay.v2', classification='diagnostic_only',
    full_acceptance=False, supersedes='verify-full-replay.json',
    routing_functions_extracted=['record_rate', 'record'], runner_imported=False,
    input_fixture='group-work-timing-integration-20260913/group-work-timing-fixture.json:runs.census_true',
    input_rows=dict(original_wire=len(original_wire), original_rate=len(original_rate)),
    output_rows=dict(ordinary_wire=len(wire_rows), rate_log=len(rate_rows),
                     group_reports=len(reports)),
    diagnostics_routed_to_recorder_only=sum(
        row['kind'] in DIAGNOSTIC_KINDS for row in original_wire),
    group_work_closes_9710000ns=True, four_cpu_windows=True,
    native_waits_inside_native_inputs_stage=True,
    ordinary_wire_rows_byte_fields_equal=True, rate_rows_fields_equal=True,
    no_rows_invented_or_dropped=True,
    report_and_summary_match_independent_expectation=True, finish_summary_valid=True,
    fake_clock_reads=dict(wall=fake_time.wall_reads, ns=fake_time.ns_reads),
    socket_subprocess_guards_not_triggered=True,
    source_sha256={'runner-candidate-v2.py.txt': sha256(ROUTING),
                   'group-work-timing-fixture.json': sha256(FIXTURE),
                   'producer-recorder-replay.json': sha256(EXPECTED),
                   'tools/group_work_timing.py': sha256(ROOT / 'tools/group_work_timing.py'),
                   'verify_full_replay.py': sha256(HERE / 'verify_full_replay.py')},
    scope='In-memory replay of the real captured fixture stream through the real '
          'extracted routing into the real recorder; no flight, no native code, '
          'no acceptance claim')
with (HERE / 'verify-full-replay-v2.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
