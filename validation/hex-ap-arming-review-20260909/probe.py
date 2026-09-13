"""Offline actual HexTask parameter guard; no ROS client/node or native process."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace as N
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_runtime.hex_task import HexTask
from tools.hex_launch_plan import launch_plan
from tools.build_hex_model_candidate import canonical, sha


def probe(parameters, responses):
    task = object.__new__(HexTask)
    task.flight_stack = 'arducopter'
    task.epoch, task.native_generation, task.peer = 'offline', 4, ('127.0.0.1', 1)
    task.budget = dict(parameter_total_timeout_s=dict(arducopter=45), parameter_read_timeout_s=10)
    task.parameters, task.hex_result = parameters, dict(parameter_readback={})
    task.ground_current = task.public_graph_ready = lambda: True
    records = []
    task.record = lambda kind, **fields: records.append(dict(kind=kind, **fields))
    task.convert = lambda response: dict(values=[vars(p) for p in response.values])
    task.mark = lambda label: None
    def wait(label, predicate, *args):
        assert predicate(), label
    task.wait = wait
    client = N(service_is_ready=lambda: True, call_async=lambda request:
               N(done=lambda: True, result=lambda: N(values=[N(**responses[request.names[0]])])))
    task.node = N(create_client=lambda *a: client, destroy_client=lambda c: None)
    modules = {'rcl_interfaces':N(), 'rcl_interfaces.srv':N(GetParameters=N(Request=lambda **k:N(**k))),
               'rclpy':N(), 'rclpy.serialization':N(serialize_message=lambda value:b'offline')}
    error = None
    with patch.dict(sys.modules,modules):
        try:
            task.ground_parameters()
        except RuntimeError as exception:
            error = str(exception)
    return dict(error=error, readback=task.hex_result['parameter_readback'])


# Actual retained response shape: type 0 is authoritative; integer_value=1000
# is stale service storage from SIM_RATE_HZ and must never be treated as a value.
old = probe({'ARMING_CHECK':1}, {'ARMING_CHECK':dict(type=0,integer_value=1000,double_value=0.)})
assert old['error'] == 'Native parameter unavailable: ARMING_CHECK' and old['readback'] == {}
new = probe({'ARMING_SKIPCHK':0}, {'ARMING_SKIPCHK':dict(type=2,integer_value=0,double_value=0.)})
assert new['error'] is None and new['readback'] == {'ARMING_SKIPCHK':0}
disabled = probe({'ARMING_SKIPCHK':0}, {'ARMING_SKIPCHK':dict(type=2,integer_value=-1,double_value=0.)})
assert disabled['error'] == 'Native AP parameter differs: ARMING_SKIPCHK'
plan = launch_plan()
original = plan.pop('plan_identity')
plan['ap_parameters'] = {('ARMING_SKIPCHK' if k=='ARMING_CHECK' else k): (0 if k=='ARMING_CHECK' else v)
                         for k,v in plan['ap_parameters'].items()}
plan['ap_parameter_file'] = ''.join(f'{k} {v}\n' for k,v in plan['ap_parameters'].items())
proposal = 'sha256:'+sha(canonical(plan).encode())
summary = dict(scope='Offline actual method with mocked DDS; no proposed contract applied',
               old_unavailable=old, proposed_available_fixture=new, disabled_checks_rejected=disabled,
               current_plan_identity=original, hypothetical_global_replacement_plan_identity=proposal,
               warning='Global replacement changes PX4 cold-reset identity too; do not apply silently')
print(json.dumps(summary,indent=2))
Path(__file__).with_name('probe-result.json').write_text(json.dumps(summary,indent=2)+'\n')
