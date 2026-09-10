"""Joint ArUco tracking task: bound seam records to public commands, per stack.

One worker per stack (joint_runtime spawns one joint_task per stack with the
fixed arducopter→uav1 / px4→uav2 mapping). Only the selected stack's worker —
the one whose uav_id owns the bound camera — constructs the frozen
ArucoTrackingSeam + ArucoCommandAdapter and may publish visual MOVE commands;
the peer takes off, holds, and lands on the same episode end step. No visual
MOVE exists before the trusted binding is loaded.

Identity sources are explicit: binding.json and observation.json must be
regular files inside the configured scene_directory (symlinks and oversized
files are rejected; packet-provided paths are never trusted), the binding
carries the frozen profile SHA, and the profile dict in aruco_settings must
equal the frozen profile file content. Timing uses only the joint ROS clock:
raw clock nanoseconds floored to 1ms authority steps; wall time never
advances the scene.

An independent raw node is drained explicitly and never added to an executor.
Its public request endpoints participate in the exact transport graph check.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import time

from Simulator.wksim_runtime.aruco_task import ArucoCommandAdapter
from Simulator.wksim_runtime.aruco_tracking_input import ArucoTrackingSeam, MAX_STEP
from Simulator.wksim_perception.target_intent import TargetIntentConfig
from .task import Task, grounded


PROFILE_PATH = Path(__file__).with_name('aruco-tracking-v1.json')
BINDING_SCHEMA = 'wksim.aruco-binding.v1'
OBSERVATION_SCHEMA = 'wksim.aruco-observation.v1'
STACK_UAV = {'arducopter': 1, 'px4': 2}  # joint_runtime.py:245 fixed mapping.
MAX_FILE_BYTES = 65536
VISUAL_LABEL_PREFIX = 'aruco-tracking-'
_HEX32 = re.compile(r'[0-9a-f]{32}')
_HEX64 = re.compile(r'[0-9a-f]{64}')


def load_frozen_profile(path=PROFILE_PATH):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _hex(value, name, pattern=_HEX32):
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f'{name} identity is invalid')
    return value


def _run_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) is None:
        raise ValueError('run_id identity is invalid')
    return value


def _int(value, name, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _step(value, name):
    return _int(value, name, 0, MAX_STEP)


def _stepish(value, name, high=MAX_STEP):
    """Consumer metadata carries decimal strings; accept both, never bool."""
    if isinstance(value, str) and re.fullmatch(r'0|[1-9][0-9]{0,18}', value):
        value = int(value)
    return _int(value, name, 0, high)


def read_bounded_json(path):
    """Read one small JSON file; symlinks, non-files and oversize are refused."""
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError(f'{path} must be a regular file, not a link')
    if info.st_size > MAX_FILE_BYTES:
        raise ValueError(f'{path} exceeds the {MAX_FILE_BYTES}-byte bound')
    text = Path(path).read_text(encoding='utf-8')
    return text, json.loads(text)


def validate_aruco_settings(value):
    """Explicit per-run wiring; every field required, no defaults invented."""
    if not isinstance(value, dict):
        raise ValueError('aruco_settings must be a dict')
    keys = {'profile', 'scene_directory', 'binding_path', 'observation_path',
            'selected_stack', 'instance_id', 'generation'}
    if set(value) != keys:
        raise ValueError('aruco_settings fields differ: ' + str(sorted(set(value) ^ keys)))
    profile, profile_sha = load_frozen_profile()
    if value['profile'] != profile:
        raise ValueError('aruco profile differs from the frozen aruco-tracking-v1.json content')
    scene = Path(value['scene_directory'])
    out = {'profile': copy.deepcopy(profile), 'profile_sha256': profile_sha,
           'scene_directory': scene, 'selected_stack': value['selected_stack'],
           'instance_id': _hex(value['instance_id'], 'instance_id'),
           'generation': _int(value['generation'], 'generation', 1, 2**31 - 1)}
    if out['selected_stack'] not in STACK_UAV:
        raise ValueError('selected_stack must be one of the two joint stacks')
    for key in ('binding_path', 'observation_path'):
        path = Path(value[key])
        resolved = path.resolve() if path.is_absolute() else (scene / path).resolve()
        if not resolved.is_relative_to(scene.resolve()) or resolved == scene.resolve():
            raise ValueError(key + ' must name a file inside the current scene_directory')
        out[key] = resolved
    total = sum(profile['scene'][k] for k in
                ('initial_steps', 'moving_steps', 'occluded_steps', 'recovery_steps'))
    out['episode_steps'] = total
    return out


def validate_binding(data, settings, *, run_id, scene_epoch, now_step):
    """One trusted binding; identity comes from run state, never from targets."""
    if not isinstance(data, dict) or data.get('schema') != BINDING_SCHEMA:
        raise ValueError('binding schema differs')
    if (_run_id(data.get('run_id')) != run_id or
            _hex(data.get('epoch'), 'epoch') != scene_epoch or
            _hex(data.get('instance_id'), 'instance_id') != settings['instance_id']):
        raise ValueError('binding identity differs from the current run/scene')
    _hex(data.get('stream_id'), 'stream_id')
    if _int(data.get('generation'), 'generation', 1, 2**31 - 1) != settings['generation']:
        raise ValueError('binding generation differs from the admitted scene generation')
    camera = data.get('camera')
    if (not isinstance(camera, dict)
            or not isinstance(camera.get('vehicle_id'), int) or isinstance(camera.get('vehicle_id'), bool)
            or camera.get('vehicle_id') not in (1, 2)
            or camera.get('vehicle_id') != STACK_UAV[settings['selected_stack']]
            or camera.get('sensor_id') != settings['profile']['camera']['sensor_id']):
        raise ValueError('binding camera differs from the selected stack camera')
    if data.get('profile_sha256') != settings['profile_sha256']:
        raise ValueError('binding profile hash differs from the frozen profile')
    now_step = _step(now_step, 'now_step')
    first_step = _step(data.get('first_step'), 'first_step')
    if first_step > now_step:
        raise ValueError('binding first_step is in the authority future')
    episode_end = first_step + settings['episode_steps']
    if episode_end > MAX_STEP:
        raise ValueError('episode end step exceeds the authority step budget')
    authority = {
        'schema': 'wksim.aruco-joint-authority.v1',
        'kind': 'joint_scene',
        'run_id': run_id,
        'epoch': scene_epoch,
        'instance_id': settings['instance_id'],
        'generation': data['generation'],
        'stream_id': data['stream_id'],
        'authority_step': first_step,
        'camera': {'vehicle_id': camera['vehicle_id'], 'sensor_id': camera['sensor_id']},
        'vehicles': {stack: {'uav_id': uid, 'run_id': run_id, 'epoch': scene_epoch}
                     for stack, uid in STACK_UAV.items()},
    }
    return {'authority': authority, 'first_step': first_step, 'stream_id': data['stream_id'],
            'episode_end_step': episode_end}


class JointArUcoTask(Task):
    """Joint-scene ArUco tracking; reuses Task send/pump/state/setup unchanged."""

    def __init__(self, directory, health, phase, flight_stack, *, aruco_settings, **kwargs):
        self.aruco = validate_aruco_settings(aruco_settings)
        self.directory = Path(directory)
        self.scene_epoch = kwargs.get('scene_epoch')
        if not isinstance(self.scene_epoch, str) or _HEX32.fullmatch(self.scene_epoch) is None:
            raise ValueError('JointArUcoTask requires the hex32 joint scene epoch')
        if kwargs.get('use_sim_time') is not True or kwargs.get('protocol') != 'session_v1':
            raise ValueError('JointArUcoTask requires session_v1 on the joint ROS clock')
        uav_id = kwargs.get('uav_id', 1)
        if flight_stack not in STACK_UAV or STACK_UAV[flight_stack] != uav_id:
            raise ValueError('flight_stack contradicts the fixed joint uav_id mapping')
        super().__init__(directory, health, phase, flight_stack, **kwargs)
        self.selected = self.uav_id == STACK_UAV[self.aruco['selected_stack']]
        self.binding = None
        self.seam = None
        self.adapter = None
        self._last_sequence = None
        self._last_observation_raw = None
        self._last_frame_id = None
        self._last_record = None
        self._last_clock_ns = None
        self._episode_completed = False
        self.observation_links = []
        self.raw_capture = None
        try:
            self._open_raw_capture()
        except BaseException:
            super().close()
            raise

    @property
    def recorder_name(self):
        return 'wksim_aruco_raw_'+self.flight_stack

    def _open_raw_capture(self):
        from .aruco_raw_capture import ArucoRawCapture, ChannelSpec, build_default_aruco_channels
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from prometheus_control.frames import topic
        from prometheus_msgs.msg import TextInfo
        from wksim_msgs.msg import SessionState
        channels = build_default_aruco_channels(self.uav_id, self.flight_stack)
        passive = QoSProfile(depth=200, reliability=ReliabilityPolicy.BEST_EFFORT)
        native = [(self.topic_root+'v2/state', SessionState), (self.topic_root+'text_info', TextInfo)]
        if self.flight_stack == 'arducopter':
            from ardupilot_msgs.msg import GlobalPosition, WksimState, Status
            native += [('/ap/cmd_gps_pose', GlobalPosition), ('/ap/wksim/local_state_v1', WksimState), ('/ap/status', Status)]
        else:
            from px4_msgs.msg import TrajectorySetpoint, VehicleLocalPosition, VehicleStatus, VehicleControlMode, VehicleCommand
            native += [(topic('/wksim_px4_21', direction, name, cls), cls) for direction, name, cls in (
                ('in', 'trajectory_setpoint', TrajectorySetpoint), ('out', 'vehicle_local_position', VehicleLocalPosition),
                ('in', 'vehicle_command', VehicleCommand), ('out', 'vehicle_status', VehicleStatus),
                ('out', 'vehicle_control_mode', VehicleControlMode))]
        channels += [ChannelSpec(name, cls, passive) for name, cls in native]
        self.raw_capture = ArucoRawCapture(self.directory/'aruco-raw-dds.jsonl', run_id=self.run_id,
            epoch=self.scene_epoch, stack=self.flight_stack, uav_id=self.uav_id, channels=channels,
            # The independent auditor deserializes retained CDR. Building a
            # second full diagnostic object here adds CPU and log traffic to
            # every sample without adding evidence to that raw byte stream.
            ros=self.ros, node_name=self.recorder_name)

    def request_graph_ready(self):
        expected = {'wksim_joint_'+self.flight_stack+'_control', self.recorder_name}
        observations = {}
        for kind, publisher in (('setup', self.setup_pub), ('command', self.command_pub)):
            endpoints = self.node.get_subscriptions_info_by_topic(self.topic_root+'v2/'+kind)
            if (publisher.get_subscription_count() != 2 or len(endpoints) != 2
                    or {info.node_name for info in endpoints} != expected
                    or any(info.node_namespace != '/' or not any(info.endpoint_gid) for info in endpoints)
                    or len({bytes(info.endpoint_gid) for info in endpoints}) != 2):
                return False
            observations[kind] = [dict(node_name=info.node_name, node_namespace=info.node_namespace,
                                       endpoint_gid=bytes(info.endpoint_gid).hex()) for info in endpoints]
        self.aruco_request_graph = observations
        return True

    def pump(self):
        self.raw_capture.drain()
        super().pump()
        self.raw_capture.drain()

    def close(self):
        try:
            if self.raw_capture is not None:
                self.raw_capture.close()
        finally:
            super().close()

    # The profile acceptance timeout applies only to visual tracking commands;
    # every other call keeps the Task default/explicit timeouts unchanged.
    def send(self, msg, label, timeout=None):
        if timeout is None and label.startswith(VISUAL_LABEL_PREFIX):
            timeout = self.aruco['profile']['mission']['command_acceptance_timeout_s']
        if timeout is None:
            super().send(msg, label)
        else:
            super().send(msg, label, timeout)

    def _authority_step(self):
        """Current joint authority step: raw clock ns floored to 1ms."""
        now_ns = self.node.get_clock().now().nanoseconds
        if not isinstance(now_ns, int) or isinstance(now_ns, bool) or now_ns < 0:
            raise RuntimeError('Joint ROS clock returned a non-integer time')
        if self._last_clock_ns is not None and now_ns < self._last_clock_ns:
            raise RuntimeError('Joint ROS clock moved backwards')
        self._last_clock_ns = now_ns
        step = now_ns // 1_000_000
        if step > MAX_STEP:
            raise RuntimeError('Joint authority step outside the scene budget')
        return step

    def _takeoff_prefix(self):
        """The exact verified public prefix of Task.execute: hold/prearm/arm/
        COMMAND_CONTROL/3m takeoff/stable hover. No command_id is spent here."""
        self.wait('public_control_ready', lambda: self.fresh() and
                  self.request_graph_ready(), 55)
        if not grounded(self.state, self.uav_id):
            raise RuntimeError('Task requires initial disarmed ground state')
        self.active = True
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
        if self.flight_stack == 'px4':
            mode_completed_at = time.monotonic()
            self.wait('native_prearm_health_ready', lambda: self.arm_ready(mode_completed_at), 55)
        self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
        self.wait('armed', lambda: self.state.armed)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'task_control_ready', 40)
        self.wait('takeoff_reached', lambda: self.state.position[2] >= 2.5, 25)
        self.dwell('hold_completed', lambda: abs(self.state.position[2] - 3) <= 0.6
                   and max(abs(x) for x in self.state.attitude[:2]) <= 0.35,
                   self.aruco['profile']['mission']['initial_hold_s'])
        self._hover_position = tuple(self.state.position)

    def _write_ready(self):
        from .evidence import write_json
        write_json(self.directory / 'tracking-ready.json', dict(
            version=1, run_id=self.run_id, scene_epoch=self.scene_epoch,
            control_epoch=self.epoch, uav_id=self.uav_id, selected=self.selected,
            stack=self.flight_stack, authority_tick=self._authority_step()))

    def _load_binding(self):
        _, data = read_bounded_json(self.aruco['binding_path'])
        self.binding = validate_binding(data, self.aruco, run_id=self.run_id,
                                        scene_epoch=self.scene_epoch,
                                        now_step=self._authority_step())
        if not self.selected:
            return  # The peer learns first_step only; it never builds a seam.
        controller = self.aruco['profile']['controller']
        config = TargetIntentConfig(tuple(controller['desired_body_flu_m']),
                                    controller['gain_per_s'], controller['max_speed_mps'])
        self.seam = ArucoTrackingSeam(config, authority=self.binding['authority'])
        # The verified prefix spends no public command_id; the host high-water is 0.
        self.adapter = ArucoCommandAdapter(self, self.seam, scene_epoch=self.scene_epoch,
                                           last_command_id=0)

    def _validate_observation(self, data, now_step):
        if not isinstance(data, dict) or data.get('schema') != OBSERVATION_SCHEMA:
            raise ValueError('observation schema differs')
        binding = self.binding
        if (_run_id(data.get('run_id')) != self.run_id or
                _hex(data.get('epoch'), 'epoch') != self.scene_epoch or
                _hex(data.get('instance_id'), 'instance_id') != self.aruco['instance_id'] or
                _int(data.get('generation'), 'generation', 1, 2**31 - 1) != self.aruco['generation'] or
                _hex(data.get('stream_id'), 'stream_id') != binding['stream_id']):
            raise ValueError('observation identity differs from the trusted binding')
        sequence = _int(data.get('sequence'), 'sequence', 1, 2**63 - 1)
        if self._last_sequence is not None and sequence < self._last_sequence:
            raise ValueError('observation sequence regressed')
        capture_step = _step(data.get('capture_step'), 'capture_step')
        if capture_step > now_step:
            raise ValueError('observation capture step is in the future')
        frame_id = _int(data.get('frame_id'), 'frame_id', 0, 2**63 - 1)
        if self._last_frame_id is not None and frame_id <= self._last_frame_id:
            raise ValueError('observation frame_id regressed or repeated')
        _hex(data.get('image_sha256'), 'image_sha256', _HEX64)
        target = data.get('target')
        if target is not None:
            if not isinstance(target, dict):
                raise ValueError('observation target must be the Consumer output or null')
            # The Consumer target belongs to exactly this capture.
            if _stepish(target.get('step'), 'target.step') != capture_step:
                raise ValueError('target step differs from the observation capture step')
            if _stepish(target.get('frame_id'), 'target.frame_id', 2**63 - 1) != frame_id:
                raise ValueError('target frame_id differs from the observation frame')
        return sequence, capture_step, frame_id, target

    def _check_envelope(self):
        mission = self.aruco['profile']['mission']
        state = self.state
        if not self.fresh():
            raise RuntimeError('Public state invalid during tracking')
        if (math.hypot(state.position[0] - self._hover_position[0],
                       state.position[1] - self._hover_position[1]) > mission['maximum_position_radius_m']
                or not mission['altitude_min_m'] <= state.position[2] <= mission['altitude_max_m']
                or max(abs(x) for x in state.attitude[:2]) > mission['maximum_tilt_rad']):
            raise RuntimeError('ArUco tracking envelope exceeded')

    def _tracking_step(self, now_step):
        """One authority step. A byte-identical resident latest file (same
        sequence, unchanged content) is not a new frame: the seam is not fed
        and no MOVE is resent; the adapter still re-checks the cached record
        for expiry at the current step. Same sequence with changed content is
        tampering. A missing file with no cached record is an explicit HOLD —
        a leftover MOVE never persists."""
        if self._episode_completed:
            raise RuntimeError('Episode completed; replaying the tracking loop is rejected')
        if self.seam is None or self.adapter is None:
            raise RuntimeError('No trusted binding; visual MOVE is forbidden before binding')
        self._check_envelope()
        path = self.aruco['observation_path']
        new_frame = False
        if path.is_file():
            raw, data = read_bounded_json(path)
            sequence = data.get('sequence') if isinstance(data, dict) else None
            if sequence is not None and sequence == self._last_sequence:
                if raw != self._last_observation_raw:
                    raise ValueError('observation content changed without a new sequence')
            else:
                sequence, capture_step, frame_id, target = self._validate_observation(data, now_step)
                new_frame = True
        if new_frame:
            record = self.seam.update(copy.deepcopy(target), authority_step=now_step)
            self._last_record = record
            self._last_sequence = sequence
            self._last_frame_id = frame_id
            self._last_observation_raw = raw
            action = self.adapter.process(record, authority_step=now_step)
            self.observation_links.append(dict(
                sequence=sequence, capture_step=capture_step, frame_id=frame_id,
                image_sha256=data['image_sha256'], authority_step=now_step,
                action=action['action'], command_id=action['command_id']))
        elif self._last_record is not None:
            self.adapter.process(self._last_record, authority_step=now_step)
        else:
            # No observation file yet and no cached target: explicit HOLD.
            record = self.seam.update(None, authority_step=now_step)
            self._last_record = record
            self.adapter.process(record, authority_step=now_step)

    def _final_hold(self, now_step):
        if self.adapter is not None and self.adapter._last_sent != 'hover':
            record = self.seam.update(None, authority_step=now_step)
            self.adapter.process(record, authority_step=now_step)

    def _land_tail(self):
        if self.adapter is not None:
            high_water = max((a['command_id'] for a in self.adapter.actions
                              if a['command_id'] is not None), default=0)
        else:
            high_water = 0
        self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=high_water + 1), 'land_accepted')
        self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id), 30)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
        completed_at = time.monotonic()
        self.wait('normal_stop_ready', lambda: self.fresh() and grounded(self.state, self.uav_id)
                  and self.received.get('state', 0) > completed_at)

    def execute(self):
        self._takeoff_prefix()
        self._write_ready()
        # The Windows driver writes binding.json once, from run state + the
        # post-enable new stream + the first scene manifest.
        self.wait('aruco_binding_ready', lambda: self.aruco['binding_path'].is_file(),
                  self.aruco['profile']['mission']['binding_timeout_s'])
        self._load_binding()
        end_step = self.binding['episode_end_step']
        while True:
            self.pump()
            now_step = self._authority_step()
            if now_step >= end_step:
                break
            if self.selected:
                self._tracking_step(now_step)
            else:
                self._check_envelope()
        self._episode_completed = True
        if self.selected:
            self._final_hold(self._authority_step())
        self._land_tail()

    def report(self):
        capture = None
        if self.raw_capture is not None:
            self.raw_capture.drain()
            capture = self.raw_capture.close()
            if capture['status'] != 'complete':
                raise RuntimeError('Raw capture did not close cleanly: '+str(capture))
        return dict(Task.report(self), aruco=dict(
            selected=self.selected, profile_sha256=self.aruco['profile_sha256'],
            binding=(None if self.binding is None else
                     {k: self.binding[k] for k in ('first_step', 'stream_id', 'episode_end_step')}),
            observation_links=self.observation_links,
            adapter_actions=None if self.adapter is None else self.adapter.actions,
            raw_capture=capture))
