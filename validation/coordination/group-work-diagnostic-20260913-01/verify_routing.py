"""Execute extracted logging functions only, with memory-only dependencies."""
from pathlib import Path
import ast
import copy
import io
import json
import types

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2] / 'validation/33-formal-promotion/spin-v2-0fsmugd1/source__tools__run_joint_flight.py.txt'

class ClockReads:
    def __init__(self):
        self.reads = []
    def monotonic(self):
        self.reads.append('wall')
        return 2.0
    def monotonic_ns(self):
        self.reads.append('ns')
        return 2_000_000_000

class Observer:
    def __init__(self):
        self.rows = []
    def observe(self, row):
        self.rows.append(copy.deepcopy(row))

def functions(path, observer):
    parsed = ast.parse(path.read_text(encoding='utf-8'))
    nodes = []
    for name in ('record_rate', 'record'):
        matches = [node for node in ast.walk(parsed) if isinstance(node, ast.FunctionDef) and node.name == name]
        assert len(matches) == 1
        nodes += matches
    namespace = dict(json=json, clock=types.SimpleNamespace(epoch='epoch', tick=44),
        started=1.0, time=ClockReads(), wire=io.StringIO(), rate_log=io.StringIO(),
        diagnostic_identity=None, group_work_recorder=observer)
    # Only these two function definitions are compiled. No runner import or I/O setup.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace

events = [('sensor', {'stack': 'arducopter', 'packet_hex': '00'}),
          ('step', {'model_ticks': {'arducopter': 44, 'px4': 44}}),
          ('diagnostic_step_cpu_timing', {'wall_start_ns': 1, 'wall_end_ns': 2}),
          ('diagnostic_native_input_timing', {'waits': []}),
          ('diagnostic_gc_timing', {'generation': 0})]
old = functions(SOURCE, None)
new = functions(HERE / 'runner-candidate.py.txt', None)
for kind, fields in events:
    old['record'](kind, **fields)
    new['record'](kind, **fields)
for kind in ('rate_group_start', 'rate_group_end'):
    old['record_rate'](kind, start_tick=40, end_tick=44)
    new['record_rate'](kind, start_tick=40, end_tick=44)
assert old['wire'].getvalue() == new['wire'].getvalue()
assert old['rate_log'].getvalue() == new['rate_log'].getvalue()
assert old['time'].reads == new['time'].reads

observer = Observer()
enabled = functions(HERE / 'runner-candidate.py.txt', observer)
for kind, fields in events:
    enabled['record'](kind, **fields)
enabled['record_rate']('rate_group_start', start_tick=40, end_tick=44)
wire_kinds = [json.loads(row)['kind'] for row in enabled['wire'].getvalue().splitlines()]
assert wire_kinds == ['sensor', 'step', 'diagnostic_gc_timing']
assert [row['kind'] for row in observer.rows] == ['step', 'diagnostic_step_cpu_timing',
                                              'diagnostic_native_input_timing', 'rate_group_start']
assert enabled['time'].reads == ['wall', 'wall', 'wall', 'ns']
result = dict(default_wire_and_rate_bytes_unchanged=True, default_clock_reads_unchanged=True,
    census_diagnostics_routed_to_memory=True, ordinary_wire_and_gc_preserved=True,
    runner_imported=False, sockets_or_processes_created=False,
    scope='Extracted logging-function integration only; no collector or flight acceptance')
with (HERE / 'routing-check.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
