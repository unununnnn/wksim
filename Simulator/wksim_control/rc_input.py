"""Fail-closed software RC input envelope and world-frame integrator.

The module is deliberately transport-free.  A product node supplies the
publisher identity and receive/operation clocks, then sends its returned
intent through the existing public control path.
"""

import json
import math
import re
from collections.abc import Mapping
from numbers import Real


SOURCE = "wksim-software-rc-v1"
VERSION = 1
CHANNEL_COUNT = 8
MAX_AGE_NS = 1_500_000_000
MAX_DT_NS = 50_000_000
MAX_SEQUENCE = 2**64 - 1
STATES = frozenset(("UNBOUND", "CANDIDATE", "ACTIVE_RC", "REVOKED"))
DEAD_ZONE = 0.05
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
FRAME_KEYS = frozenset(("version", "source", "run_id", "control_epoch", "uav_id", "boot_id",
                        "stream_id", "sequence", "produced_monotonic_ns", "channels_us"))


class RCError(ValueError):
    """Validation error with a stable machine-readable reason."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise RCError(name + "_invalid")
    return value


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise RCError(name + "_invalid")
    return float(value)


def _vector(value, name):
    if isinstance(value, (str, bytes)):
        raise RCError(name + "_invalid")
    try:
        values = tuple(value)
    except TypeError as error:
        raise RCError(name + "_invalid") from error
    if len(values) != 3:
        raise RCError(name + "_invalid")
    return tuple(_finite(item, name) for item in values)


def _json_constant(value):
    raise RCError("json_nonfinite")


def decode_frame(value):
    """Decode strict JSON or return a mapping without changing its values."""
    if isinstance(value, (str, bytes, bytearray)) and len(value.encode('utf-8') if isinstance(value, str) else value) > 4096:
        raise RCError('frame_too_large')
    if isinstance(value, (bytes, bytearray)):
        try:
            value = bytes(value).decode("utf-8")
        except UnicodeDecodeError as error:
            raise RCError("json_utf8_invalid") from error
    if isinstance(value, str):
        try:
            def pairs(items):
                result = {}
                for key, item in items:
                    if key in result:
                        raise RCError("json_duplicate_key")
                    result[key] = item
                return result
            value = json.loads(value, object_pairs_hook=pairs, parse_constant=_json_constant)
        except RCError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RCError("json_invalid") from error
    if not isinstance(value, Mapping):
        raise RCError("frame_object_required")
    return dict(value)


def normalize_channel(pwm):
    """Apply the upstream deadzone, including exact zero at both boundaries."""
    pwm = _integer(pwm, "channel", 1000, 2000)
    value = (pwm - 1500) / 500.0
    if abs(value) <= DEAD_ZONE:
        return 0.0
    return math.copysign((abs(value) - DEAD_ZONE) / (1.0 - DEAD_ZONE), value)


def normalize_channels(channels):
    if not isinstance(channels, (list, tuple)) or len(channels) != CHANNEL_COUNT:
        raise RCError("channels_count_invalid")
    channels = tuple(_integer(item, "channel", 1000, 2000) for item in channels)
    if any(channels[index] != 1000 for index in (4, 6, 7)):
        raise RCError("unsupported_switch")
    if channels[5] not in (1000, 1500, 2000):
        raise RCError("unsupported_mode_switch")
    if channels[0] < 1100 and channels[1] < 1100 and channels[2] < 1100 and channels[3] > 1900:
        raise RCError("unsupported_reboot_gesture")
    return tuple(normalize_channel(item) for item in channels[:4])


def validate_frame(value, *, expected=None, now_ns=None, last_sequence=None, last_produced_ns=None):
    """Validate and normalize one complete eight-channel frame.

    ``expected`` may contain run_id, control_epoch, uav_id, boot_id and
    stream_id.  Receive-time freshness is checked only when ``now_ns`` is
    supplied; this keeps the function deterministic for offline tests.
    """
    frame = decode_frame(value)
    if set(frame) != FRAME_KEYS:
        raise RCError("frame_fields_invalid")
    if type(frame["version"]) is not int or frame["version"] != VERSION:
        raise RCError("version_invalid")
    if frame["source"] != SOURCE:
        raise RCError("source_invalid")
    if not isinstance(frame["run_id"], str) or not RUN_ID.fullmatch(frame["run_id"]):
        raise RCError("run_id_invalid")
    if not isinstance(frame["control_epoch"], str) or not HEX32.fullmatch(frame["control_epoch"]):
        raise RCError("control_epoch_invalid")
    if type(frame["uav_id"]) is not int or not 1 <= frame["uav_id"] <= 255:
        raise RCError("uav_id_invalid")
    for name in ("boot_id", "stream_id"):
        if not isinstance(frame[name], str) or not HEX32.fullmatch(frame[name].lower()):
            raise RCError(name + "_invalid")
        frame[name] = frame[name].lower()
    _integer(frame["sequence"], "sequence", 1, MAX_SEQUENCE)
    _integer(frame["produced_monotonic_ns"], "produced_monotonic_ns", 1, MAX_SEQUENCE)
    if expected is not None:
        for name in ("run_id", "control_epoch", "uav_id", "boot_id", "stream_id"):
            if name in expected and frame[name] != expected[name]:
                raise RCError("wrong_" + name)
    if last_sequence is not None and frame["sequence"] <= last_sequence:
        raise RCError("sequence_not_increasing")
    if last_produced_ns is not None and frame["produced_monotonic_ns"] <= last_produced_ns:
        raise RCError("produced_time_not_increasing")
    if now_ns is not None:
        _integer(now_ns, "now_monotonic_ns", 1, MAX_SEQUENCE)
        age = now_ns - frame["produced_monotonic_ns"]
        if age < 0:
            raise RCError("produced_time_in_future")
        if age > MAX_AGE_NS:
            raise RCError("input_expired")
    normalized = normalize_channels(frame["channels_us"])
    frame["normalized"] = normalized
    frame["channels_us"] = tuple(frame["channels_us"])
    return frame


class RCInput:
    """One stream-bound RC integrator; all state is discarded on revoke/reset."""

    def __init__(self, expected):
        if not isinstance(expected, Mapping):
            raise RCError("identity_invalid")
        self.expected = dict(expected)
        # Validate identity once using a harmless envelope-shaped check.
        for name in ("run_id", "control_epoch", "boot_id"):
            if not isinstance(self.expected.get(name), str):
                raise RCError("identity_invalid")
        if not RUN_ID.fullmatch(self.expected["run_id"]):
            raise RCError("identity_invalid")
        if not HEX32.fullmatch(self.expected["control_epoch"].lower()) or not HEX32.fullmatch(self.expected["boot_id"].lower()):
            raise RCError("identity_invalid")
        if type(self.expected.get("uav_id")) is not int or not 1 <= self.expected["uav_id"] <= 255:
            raise RCError("identity_invalid")
        self.expected["control_epoch"] = self.expected["control_epoch"].lower()
        self.expected["boot_id"] = self.expected["boot_id"].lower()
        self.state = "UNBOUND"
        self.owner_gid = None
        self.stream_id = None
        self.sequence = None
        self.produced_ns = None
        self.received_ns = None
        self.last_step_ns = None
        self._first_step = False
        self.target = None
        self.last_rejection = None
        self._retired_streams = set()

    def _frame_expected(self):
        expected = dict(self.expected)
        if self.stream_id is not None:
            expected["stream_id"] = self.stream_id
        return expected

    @staticmethod
    def _gid(gid):
        if isinstance(gid, bytearray):
            gid = bytes(gid)
        if not isinstance(gid, (str, bytes)) or not gid:
            raise RCError("publisher_gid_invalid")
        return gid

    @staticmethod
    def _neutral(frame):
        return not any(frame['normalized']) and frame["channels_us"][5] == 1500

    def _record_rejection(self, reason):
        self.last_rejection = reason
        return dict(accepted=False, state=self.state, reason=reason)

    def bind(self, value, publisher_gid, *, now_ns):
        """Bind a fresh stream as a candidate; this does not produce output."""
        gid = self._gid(publisher_gid)
        if self.state not in ("UNBOUND",):
            return self._record_rejection("already_bound")
        try:
            frame = validate_frame(value, expected=self.expected, now_ns=now_ns)
            if frame["stream_id"] in self._retired_streams:
                raise RCError("retired_stream")
            if not self._neutral(frame):
                raise RCError("bind_requires_neutral_candidate")
        except RCError as error:
            return self._record_rejection(error.reason)
        self.owner_gid = gid
        self.stream_id = frame["stream_id"]
        self.state = "CANDIDATE"
        self.sequence, self.produced_ns, self.received_ns = frame["sequence"], frame["produced_monotonic_ns"], now_ns
        self._frame = frame
        return dict(accepted=True, state=self.state, reason="candidate_bound", sequence=self.sequence)

    def receive(self, value, publisher_gid, *, received_ns):
        """Cache only a valid frame from the already-bound publisher/stream."""
        try:
            gid = self._gid(publisher_gid)
        except RCError as error:
            return self._record_rejection(error.reason)
        if self.state not in ('CANDIDATE', 'ACTIVE_RC'):
            return self._record_rejection("stream_unbound")
        if gid != self.owner_gid:
            return self._record_rejection("publisher_not_owner")
        try:
            frame = validate_frame(value, expected=self._frame_expected(), now_ns=received_ns,
                                   last_sequence=self.sequence, last_produced_ns=self.produced_ns)
            if received_ns < self.received_ns:
                raise RCError("receive_time_regressed")
        except RCError as error:
            # The owner cannot extend its own lifetime with malformed input.
            if not (error.reason.startswith('wrong_') or error.reason in (
                    'sequence_not_increasing', 'produced_time_not_increasing')):
                self.revoke(error.reason)
            return self._record_rejection(error.reason)
        self._frame = frame
        self.sequence, self.produced_ns, self.received_ns = frame["sequence"], frame["produced_monotonic_ns"], received_ns
        return dict(accepted=True, state=self.state, sequence=self.sequence)

    def activate(self, *, now_ns, position, yaw, setup_id=None, operation_ns=None):
        """Turn a neutral candidate into active RC control after explicit setup."""
        if self.state != "CANDIDATE":
            return self._record_rejection("candidate_required")
        if setup_id is not None:
            _integer(setup_id, "setup_id", 1, MAX_SEQUENCE)
        try:
            position = _vector(position, "position")
            yaw = _finite(yaw, "yaw")
            _integer(now_ns, "now_monotonic_ns", 1, MAX_SEQUENCE)
            if now_ns < self.received_ns:
                raise RCError("operation_time_regressed")
            if now_ns - self.received_ns > MAX_AGE_NS or now_ns - self.produced_ns > MAX_AGE_NS:
                raise RCError("input_expired")
            if position[2] < .2:
                raise RCError('airborne_position_required')
            if not self._neutral(self._frame):
                raise RCError("candidate_not_neutral")
        except RCError as error:
            return self._record_rejection(error.reason)
        self.state = "ACTIVE_RC"
        self.target = dict(position=position, yaw=yaw)
        self.last_step_ns = now_ns if operation_ns is None else _integer(operation_ns, 'operation_ns', 1, MAX_SEQUENCE)
        self._first_step = True
        return dict(accepted=True, state=self.state, setup_id=setup_id)

    def step(self, *, now_ns, running=True, operation_mode="running", operation_ns=None):
        """Integrate one fresh frame in public ENU coordinates."""
        if type(running) is not bool or not isinstance(operation_mode, str):
            raise RCError("operation_state_invalid")
        if self.state != "ACTIVE_RC":
            return None
        if not running or operation_mode != "running":
            self.revoke("operation_paused")
            return None
        _integer(now_ns, "now_monotonic_ns", 1, MAX_SEQUENCE)
        operation_ns = now_ns if operation_ns is None else _integer(operation_ns, 'operation_ns', 1, MAX_SEQUENCE)
        if operation_ns < self.last_step_ns:
            self.revoke("operation_time_regressed")
            return None
        if now_ns - self.received_ns > MAX_AGE_NS or now_ns - self.produced_ns > MAX_AGE_NS:
            self.revoke("input_expired")
            return None
        channels = self._frame["channels_us"]
        if channels[4] != 1000 or channels[6] != 1000 or channels[7] != 1000:
            self.revoke("unsupported_switch")
            return None
        if channels[5] == 1000:
            self.revoke("channel_release")
            return None
        dt_ns = 0 if self._first_step else operation_ns - self.last_step_ns
        if dt_ns > MAX_DT_NS:
            self.revoke("dt_exceeded")
            return None
        dt = dt_ns / 1e9
        d1, d2, d3, d4 = self._frame["normalized"] if channels[5] == 1500 else (0., 0., 0., 0.)
        self.target["y"] = self.target["position"][1] - d1 * 1.5 * dt
        self.target["x"] = self.target["position"][0] + d2 * 1.5 * dt
        self.target["z"] = max(.2, self.target["position"][2] + d3 * 1.3 * dt)
        self.target["position"] = (self.target.pop("x"), self.target.pop("y"), self.target.pop("z"))
        self.target["yaw"] -= d4 * 1.5 * dt
        self.last_step_ns = operation_ns
        self._first_step = False
        return dict(state=self.state, sequence=self.sequence, stream_id=self.stream_id,
                    dt_s=dt, position=list(self.target["position"]), yaw=self.target["yaw"],
                    normalized=list(self._frame["normalized"]), intent="rc" if channels[5] == 1500 else 'command')

    def command_handoff_ready(self, now_ns):
        return (self.state == 'ACTIVE_RC' and self._frame['channels_us'][5] == 2000
                and not any(self._frame['normalized'])
                and 0 <= now_ns - self.received_ns <= MAX_AGE_NS
                and 0 <= now_ns - self.produced_ns <= MAX_AGE_NS)

    def revoke(self, reason="revoked"):
        if not isinstance(reason, str) or not reason:
            raise RCError("reason_invalid")
        if self.stream_id is not None:
            self._retired_streams.add(self.stream_id)
        self.state = "REVOKED"
        self.last_rejection = reason
        self.owner_gid = None
        self.stream_id = None
        self.sequence = self.produced_ns = self.received_ns = self.last_step_ns = None
        self._first_step = False
        self.target = None
        self._frame = None
        return dict(state=self.state, reason=reason)

    def reset(self):
        """Clear the stream and return to UNBOUND; retired stream IDs stay retired."""
        if self.stream_id is not None:
            self._retired_streams.add(self.stream_id)
        self.state = "UNBOUND"
        self.owner_gid = None
        self.stream_id = None
        self.sequence = self.produced_ns = self.received_ns = self.last_step_ns = None
        self._first_step = False
        self.target = None
        self._frame = None
        self.last_rejection = None
        return dict(state=self.state, retired_streams=sorted(self._retired_streams))


def bind(rc, *args, **kwargs):
    return rc.bind(*args, **kwargs)


def receive(rc, *args, **kwargs):
    return rc.receive(*args, **kwargs)


def step(rc, *args, **kwargs):
    return rc.step(*args, **kwargs)


def revoke(rc, *args, **kwargs):
    return rc.revoke(*args, **kwargs)
