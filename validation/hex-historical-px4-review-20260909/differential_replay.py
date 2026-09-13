"""Finite retained-packet replay: no model, listener, FC, ROS, or native library."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.audit_hex_live import windows_raw
from tools import hex_physics
from Simulator.wksim_core import px4_mavlink as current

RUN = '/root/wksim-hex-flight-px4-03/hex-px4-03'
run = windows_raw(RUN+'/result.json').parent if sys.platform == 'win32' else Path(RUN)
old_path = run/'run-source/Simulator/wksim_core/px4_mavlink.py'
new_path = ROOT/'Simulator/wksim_core/px4_mavlink.py'
OLD = '08b3d5fbf6754822572240ceb6beb289341bd0c6653455a35b60b3fb3d85ab3d'
NEW = 'e8c903f2b4c84a261adf6f512c8437c51364143dc048d1ac2cb873e7cfb53260'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert digest(old_path) == OLD
assert digest(new_path) == NEW
assert digest(run/'run-source/tools/hex_physics.py') == digest(ROOT/'tools/hex_physics.py')
spec = importlib.util.spec_from_file_location('Simulator.wksim_core.review_historical_px4', old_path)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
old_tree, new_tree = ast.parse(old_path.read_text()), ast.parse(new_path.read_text())
for name in ('actuator_commands', 'gps_arguments'):
    a = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    b = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    assert ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False), name
# Extract precisely the archived nested send function; do not replace its body.
serve = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'serve')
send = next(n for n in ast.walk(serve) if isinstance(n, ast.FunctionDef) and n.name == 'send_sensors')
exec(compile(ast.Module(body=[send], type_ignores=[]), str(old_path), 'exec'), old.__dict__)


class Wire:
    def __init__(self):
        self.frames = []
    def sendall(self, packet):
        self.frames.append(bytes(packet))


class RecordingOnly:
    def actuator(self, *args, **kwargs):
        pass


left, right = Wire(), Wire()
old.protocol = old.mavlink.MAVLink(old.Sender(left), srcSystem=254, srcComponent=51)
new_protocol = current.mavlink.MAVLink(current.Sender(right), srcSystem=254, srcComponent=51)
old.model = SimpleNamespace(ticks=0)
parser = current.mavlink.MAVLink(None)
counts = dict(actual_actuator_packets=0, actual_sensor_groups=0, duplicate_send_probes=0)
packet_hash = hashlib.sha256()
group_hash = hashlib.sha256()
quad_old, quad_new = old.actuator_commands, current.actuator_commands
with hex_physics.bind(old, object, RecordingOnly()), hex_physics.bind(current, object, RecordingOnly()):
    with (run/'physics-1ms.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            if row['kind'] == 'actuator':
                raw = bytes.fromhex(row['packet_hex'])
                messages = parser.parse_buffer(raw)
                assert len(messages) == 1 and messages[0].get_type() == 'HIL_ACTUATOR_CONTROLS'
                message = messages[0]
                assert bytes(message.get_msgbuf()) == raw
                assert quad_old(message) == quad_new(message)
                assert old.actuator_commands(message) == current.actuator_commands(message) == hex_physics.actuator_commands(message)
                packet_hash.update(raw)
                counts['actual_actuator_packets'] += 1
            if row['kind'] != 'step' or row['substep'] != row['group_steps']-1:
                continue
            state, tick = row['output120'], row['tick']
            assert old.gps_arguments(state) == current.gps_arguments(state)
            old.model.ticks = tick
            old.send_sensors(state)
            current.send_sensors(new_protocol, state, tick)
            assert left.frames == right.frames
            for frame in left.frames:
                group_hash.update(frame)
            left.frames.clear(); right.frames.clear()
            counts['actual_sensor_groups'] += 1
            if tick % 100 == 0:
                # Exercise original duplicate resend branch on an unchanged real state.
                old.send_sensors(state)
                current.send_sensors(new_protocol, state, tick)
                assert left.frames == right.frames
                left.frames.clear(); right.frames.clear()
                counts['duplicate_send_probes'] += 1
print(json.dumps(dict(passed=True, old_sha256=OLD, current_sha256=NEW,
    raw_sha256=digest(run/'physics-1ms.jsonl'), counts=counts,
    captured_actuator_bytes_sha256=packet_hash.hexdigest(),
    matched_default_sensor_frame_bytes_sha256=group_hash.hexdigest(),
    exact_function_ast=['actuator_commands', 'gps_arguments'],
    actual_serve_called=False, model_loaded=False, gnss_gate_enabled=False,
    scope='Actual retained packet/state replay through old/new decoding and default sensor serialization; recording transport only'), indent=2))
