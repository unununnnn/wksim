# SPDX-License-Identifier: Apache-2.0
"""Explicit ENU/FLU <-> NED/FRD boundaries; no transport or implicit units."""
import math

from .shaping import scalar, vector


def wrap_pi(angle):
    angle = scalar(angle)
    return math.atan2(math.sin(angle), math.cos(angle))


def ned_axes(values):
    """Self-inverse ENU/NED conversion; inactive axes become wire NaNs."""
    if len(values) != 3:
        raise ValueError('Expected three axes')
    x, y, z = (math.nan if v is None else scalar(v) for v in values)
    return (y, x, -z)


def unit_quaternion(values):
    """Hamilton WXYZ. Reject missing/non-finite orientation, never synthesize it."""
    values = vector(values, 4)
    norm = math.hypot(*values)
    if norm < 1e-9 or not math.isfinite(norm):
        raise ValueError('Invalid orientation quaternion')
    return tuple(v / norm for v in values)


def ned_frd_quaternion(values):
    """Self-inverse ENU/FLU <-> NED/FRD, Hamilton WXYZ in/out."""
    w, x, y, z = unit_quaternion(values)
    k = math.sqrt(0.5)
    return (k * (w + z), k * (x + y), k * (x - y), k * (w - z))


def euler(values):
    w, x, y, z = unit_quaternion(values)
    return (math.atan2(2 * (w*x + y*z), 1 - 2 * (x*x + y*y)),
            math.asin(max(-1.0, min(1.0, 2 * (w*y - z*x)))),
            math.atan2(2 * (w*z + x*y), 1 - 2 * (y*y + z*z)))


def set_orientation(state, values):
    w, x, y, z = unit_quaternion(values)
    state.attitude_q.w, state.attitude_q.x, state.attitude_q.y, state.attitude_q.z = w, x, y, z
    state.attitude = [float(v) for v in euler((w, x, y, z))]


def stamp_us(header, timestamp):
    header.stamp.sec, remaining = divmod(int(timestamp), 1_000_000)
    header.stamp.nanosec = remaining * 1000


def topic(prefix, direction, name, message_type):
    version = getattr(message_type, 'MESSAGE_VERSION', 0)
    return f'{prefix}/fmu/{direction}/{name}' + (f'_v{version}' if version else '')
