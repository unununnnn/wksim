"""Narrow, offline parameter codecs; the owning runner supplies current authority.

No transport, discovery, retry or process ownership is implemented here. Call
check_current() immediately before actual publication as well as using these
builders. The runner must serialize operations, correlate ROS futures, drain PX4
input before requests, enforce timeouts and replace transports on generation
changes. PARAM_VALUE has no request ID and is not COMMAND_ACK: a matching value
is only an observation, never proof that a particular write caused it.
"""
from dataclasses import dataclass
import math
import re
import struct
import time


class ParameterError(ValueError):
    """Invalid local request, expired authority, or unexpected native reply."""


@dataclass(frozen=True)
class ParameterContext:
    operation_id: str
    run_id: str
    control_epoch: str
    native_generation: int

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip()
               for v in (self.operation_id, self.run_id)):
            raise ParameterError('operation_id and run_id must be nonempty strings')
        if not isinstance(self.control_epoch, str) or not re.fullmatch('[0-9a-f]{32}', self.control_epoch):
            raise ParameterError('control_epoch must be the session UUID hex string')
        if type(self.native_generation) is not int or self.native_generation < 0:
            raise ParameterError('native_generation must be a nonnegative integer')


@dataclass(frozen=True)
class GroundState:
    context: ParameterContext
    observed_at: float  # monotonic seconds; oldest required native/physics sample
    disarmed: bool
    grounded: bool
    active_task: bool


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_value(stack, name, value):
    """Validate a requested value against the explicit product allowlist."""
    allowed = {'arducopter': ('WP_SPD', 10), 'px4': ('MPC_XY_CRUISE', 1)}
    if stack not in allowed or name != allowed[stack][0]:
        raise ParameterError('parameter is not allowlisted for this stack')
    if not _finite(value):
        raise ParameterError('value must be a finite number, excluding bool')
    upper = 10.0 if stack == 'arducopter' else 5.0
    if not 3.0 <= value <= upper:
        raise ParameterError(f'value must be within [3, {upper:g}] m/s')
    scaled = value * allowed[stack][1]
    if not math.isclose(scaled, round(scaled), rel_tol=0, abs_tol=1e-12):
        raise ParameterError('value violates the supported parameter increment')
    return float(value)


def float32_value(value):
    """Exact native REAL32 storage widened to Python float; no tolerance."""
    if not _finite(value):
        raise ParameterError('value must be finite numeric data')
    try:
        return struct.unpack('<f', struct.pack('<f', value))[0]
    except (OverflowError, struct.error) as error:
        raise ParameterError('value cannot be stored as float32') from error


def restore_request_value(stack, name, original):
    """Find an allowed grid request with identical original float32 bits.

    Reject non-float32 originals as well: a double must not silently lose data.
    Enumerating this tiny fixed grid avoids rounding an off-grid original.
    """
    validate_value(stack, name, 4.0)
    stored = float32_value(original)
    if stored != original:
        raise ParameterError('original is not an exact native float32 value')
    bits = struct.pack('<f', stored)
    candidates = (n / 10 for n in range(30, 101)) if stack == 'arducopter' else range(3, 6)
    for candidate in candidates:
        if struct.pack('<f', candidate) == bits:
            return validate_value(stack, name, candidate)
    raise ParameterError('original has no lossless allowed restore request')


class ParameterProtocol:
    def __init__(self, stack, name, context, state_provider, *, max_age=0.5,
                 clock=time.monotonic, dialect=None, peer=None,
                 target_system=None, target_component=None):
        validate_value(stack, name, 4.0)
        if not isinstance(context, ParameterContext) or not callable(state_provider):
            raise ParameterError('a fixed context and current-state provider are required')
        if not _finite(max_age) or max_age <= 0:
            raise ParameterError('max_age must be finite and positive')
        if stack == 'px4':
            if dialect is None or peer is None:
                raise ParameterError('PX4 requires an injected verified dialect and fixed peer')
            if any(type(v) is not int or not 1 <= v <= 255
                   for v in (target_system, target_component)):
                raise ParameterError('PX4 requires explicit non-broadcast system/component')
        self.stack, self.name, self.context = stack, name, context
        self._state_provider, self._clock, self._max_age = state_provider, clock, max_age
        self._dialect, self._peer = dialect, peer
        self._system, self._component = target_system, target_component
        self._invalidated = False
        self._last_now = None
        self.check_current()

    def check_current(self):
        """Recheck at send/receive time; authority failure permanently closes this op.

        The provider must read runner-owned state, including native disarmed and
        physical grounded evidence, not echo a caller's requested booleans.
        """
        if self._invalidated:
            raise ParameterError('operation has been invalidated')
        try:
            state, now = self._state_provider(), self._clock()
            if (not _finite(now)
                    or (self._last_now is not None and now < self._last_now)):
                raise ParameterError('invalid or regressing monotonic clock')
            self._last_now = now
            if not isinstance(state, GroundState) or state.context != self.context:
                raise ParameterError('operation/run/epoch/native generation changed')
            if (not _finite(state.observed_at)
                    or not 0 <= now - state.observed_at <= self._max_age):
                raise ParameterError('ground state is stale or from the future')
            if state.disarmed is not True or state.grounded is not True or state.active_task is not False:
                raise ParameterError('fresh disarmed/grounded/no-active-task state required')
        except Exception:
            self._invalidated = True
            raise
        return state

    def _check(self, stack):
        self.check_current()
        if self.stack != stack:
            raise ParameterError('wrong native protocol for this stack')

    def ap_get_request(self):
        self._check('arducopter')
        from rcl_interfaces.srv import GetParameters
        return GetParameters.Request(names=[self.name])

    def ap_set_request(self, value):
        self._check('arducopter')
        value = validate_value(self.stack, self.name, value)
        from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
        from rcl_interfaces.srv import SetParameters
        return SetParameters.Request(parameters=[Parameter(
            name=self.name, value=ParameterValue(
                type=ParameterType.PARAMETER_DOUBLE, double_value=value))])

    def ap_set_result(self, response):
        """Return native success/reason; successful=True still needs a new GET."""
        self._check('arducopter')
        from rcl_interfaces.srv import SetParameters
        if not isinstance(response, SetParameters.Response) or len(response.results) != 1:
            raise ParameterError('expected exactly one native SetParameters result')
        result = response.results[0]
        return result.successful, result.reason

    def ap_get_value(self, response, *, expected=None):
        self._check('arducopter')
        from rcl_interfaces.msg import ParameterType
        from rcl_interfaces.srv import GetParameters
        if not isinstance(response, GetParameters.Response) or len(response.values) != 1:
            raise ParameterError('expected exactly one native GetParameters value')
        value = response.values[0]
        if value.type == ParameterType.PARAMETER_NOT_SET:
            raise ParameterError('native parameter is NOT_SET')
        if value.type != ParameterType.PARAMETER_DOUBLE:
            raise ParameterError('native parameter is not DOUBLE')
        return self._value(value.double_value, expected)

    def px4_read_message(self):
        self._check('px4')
        return self._dialect.MAVLink_param_request_read_message(
            self._system, self._component, self.name.encode('ascii'), -1)

    def px4_set_message(self, value):
        self._check('px4')
        value = validate_value(self.stack, self.name, value)
        return self._dialect.MAVLink_param_set_message(
            self._system, self._component, self.name.encode('ascii'), value,
            self._dialect.MAV_PARAM_TYPE_REAL32)

    def px4_value(self, message, *, peer, context, expected=None):
        """Validate an already decoded message from this operation's transport.

        context is local receive-envelope metadata, not a MAVLink field. The
        caller must not relabel buffered old-generation packets with new context.
        """
        self._check('px4')
        if context != self.context or peer != self._peer:
            raise ParameterError('wrong receive context or peer')
        if not isinstance(message, self._dialect.MAVLink_param_value_message):
            raise ParameterError('expected native PARAM_VALUE, not COMMAND_ACK')
        if message.get_srcSystem() != self._system or message.get_srcComponent() != self._component:
            raise ParameterError('wrong native system/component')
        if message.param_id != self.name or message.param_type != self._dialect.MAV_PARAM_TYPE_REAL32:
            raise ParameterError('wrong native parameter name/type')
        return self._value(message.param_value, expected)

    def _value(self, value, expected):
        # Reads report storage faithfully, including values outside write policy.
        # The runner decides before modifying whether it can restore this value.
        if not _finite(value):
            raise ParameterError('native parameter value is not finite numeric data')
        actual = float(value)
        if expected is not None:
            expected = validate_value(self.stack, self.name, expected)
            if actual != float32_value(expected):
                raise ParameterError('native parameter value differs from requested value')
        return actual
