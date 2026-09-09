"""Finite, offline review probe. No ROS/native process or source mutation."""
import hashlib
import json
import math
import time
from pathlib import Path
import sys
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_runtime.pid_task import PIDTask, CONFIG_PATH, load_config


def task(target_stamp, samples, stack='arducopter', wall_age=0, physical_age=0):
    value = object.__new__(PIDTask)
    value.pid_config = load_config(CONFIG_PATH)
    value.flight_stack = stack
    value.latest = {'state': NS(header=NS(stamp=NS(sec=1, nanosec=80000000)))}
    value.pid_pending = dict(request_id=21, command_id=11, events_start=0,
        targets_start=0, samples_start=0, physical_time=1.04-physical_age,
        wall=time.monotonic()-wall_age, thrust=.32,
        quaternion_xyzw=[0., 0., 0., 1.],
        quaternion_ned=[math.sqrt(.5), 0., 0., math.sqrt(.5)],
        native_state_stamp_s=1.04)
    value.pending_request_id = 21
    value.events = [dict(event='command_accepted', request_id=21, command_id=11)]
    value.native_targets = [dict(thrust=.32, quaternion_xyzw=[0., 0., 0., 1.],
        native_source_stamp=round(target_stamp*1e6))]
    value.native_samples = [dict(native_boot_s=stamp, thrust=.32, quaternion=q)
                            for stamp, q in samples]
    value.read_truth = lambda: {'time': 1.04}
    value.cursor = lambda: {}
    value.record = lambda *args, **kwargs: None
    return value


q = [math.sqrt(.5), 0., 0., math.sqrt(.5)]
result = {'source_sha256': hashlib.sha256(
    (ROOT/'Simulator/wksim_runtime/pid_task.py').read_bytes()).hexdigest()}
result['old_target_0_90_and_old_samples_0_91_0_92_release_request_from_1_04'] = task(.90, [(.91, q), (.92, q)]).check_pending()
result['current_target_and_two_matching_samples_release'] = task(1.04, [(1.05, q), (1.06, q)]).check_pending()
result['duplicate_timestamps_release'] = task(1.04, [(1.05, q), (1.05, q)]).check_pending()
result['sample_after_current_state_releases'] = task(1.04, [(1.09, q), (1.10, q)]).check_pending()
shaped = [math.sqrt(.5), .001, 0., math.sqrt(.5)]
result['AP_shaped_quaternion_with_matching_thrust_releases'] = task(1.04, [(1.05, shaped), (1.06, shaped)]).check_pending()
for key, kwargs in [('physical_timeout', {'physical_age': .201}), ('wall_timeout', {'wall_age': 2.01})]:
    try:
        task(1.04, [(1.05, q), (1.06, q)], **kwargs).check_pending()
        result[key] = 'NO_EXCEPTION'
    except TimeoutError as error:
        result[key] = str(error)
print(json.dumps(result, indent=2))
