# Copyright 2022 AMOVLAB; wksim migration changes 2026.
# SPDX-License-Identifier: Apache-2.0
"""Prometheus output shaping, independent of a flight stack or transport.

Source: pinned uav_controller.cpp:754-864, 1117-1637; see package README.
Inputs/outputs are FC-local ENU/FLU, SI. Per-axis None means inactive, not zero.
Intentional fixes: no transition output gaps, axis-local hold anchors, isolated
mixed-mode history, and explicit local coordinates for offset GPS/RTK states.
"""
from dataclasses import dataclass
import math
import struct


def scalar(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('Expected a finite scalar') from error
    if not math.isfinite(result):
        raise ValueError('Expected a finite scalar')
    return result


def vector(value, length=3):
    if value is None or len(value) != length:
        raise ValueError(f'Expected {length} components')
    return tuple(scalar(x) for x in value)


def float32(value):
    """Match upstream float configuration/yaw arguments, reject overflow."""
    try:
        return scalar(struct.unpack('<f', struct.pack('<f', scalar(value)))[0])
    except OverflowError as error:
        raise ValueError('Value exceeds float32 range') from error


@dataclass(frozen=True)
class Setpoint:
    kind: str
    position: tuple = (None, None, None)
    velocity: tuple = (None, None, None)
    acceleration: tuple = (None, None, None)
    yaw: float | None = None
    yaw_rate: float | None = None
    quaternion_xyzw: tuple | None = None
    thrust: float | None = None
    global_position: tuple | None = None


class SetpointShaper:
    """Preserve upstream hold/output rules, fixing state transitions explicitly.

    Call shape for every processor step, including None/land, so a terminated
    control session cannot reuse its anchors. Call reset on run/epoch changes.
    The host must supply FC-local position (CommandProcessor.local_position()),
    manage state freshness, and validate native FC capabilities before sending.
    """
    def __init__(self, speed_deadband=.09, yaw_deadband=.0349,
                 hold_gap=.04, hold_gain=1.8, mixed_deadband=.001):
        self.speed_deadband, self.yaw_deadband, self.hold_gap, self.hold_gain = (
            float32(x) for x in (speed_deadband, yaw_deadband, hold_gap, hold_gain))
        self.mixed_deadband = scalar(mixed_deadband)  # Upstream uses a double literal.
        if min(self.speed_deadband, self.yaw_deadband, self.hold_gap,
               self.hold_gain, self.mixed_deadband) <= 0:
            raise ValueError('Shaping thresholds/gain must be positive')
        self.reset()

    def reset(self):
        self.family = None
        self.anchor = None
        self.held = None
        self.held_yaw = None

    def shape(self, reference, local_position):
        if reference is None or reference.kind == 'land':
            self.reset()
            return None if reference is None else Setpoint('land')
        position = vector(local_position)
        kind = reference.kind
        if reference.yaw is not None and reference.yaw_rate is not None:
            raise ValueError('Yaw and yaw rate are mutually exclusive')
        if kind in ('velocity', 'velocity_xy_position_z'):
            velocity = vector(reference.velocity)
            z = vector(reference.position)[2] if kind == 'velocity_xy_position_z' else None
            if reference.yaw_rate is not None:
                rate = float32(reference.yaw_rate)
                self.reset()  # Rate-mode exit must not revive an old hold origin.
                return Setpoint('local', position=(None, None, z),
                                velocity=velocity if z is None else (*velocity[:2], 0.0), yaw_rate=rate)
            yaw = float32(reference.yaw)
            return self._velocity(kind, velocity, z, yaw, position)
        # Validate before resetting a valid hold; malformed references are atomic failures.
        yaw = float32(reference.yaw) if kind != 'attitude' else None
        if kind == 'position':
            result = Setpoint('local', position=vector(reference.position), yaw=yaw)
        elif kind == 'trajectory':
            vector(reference.acceleration)  # Retained reference, not sent by the old output path.
            result = Setpoint('local', position=vector(reference.position),
                              velocity=vector(reference.velocity), yaw=yaw)
        elif kind == 'acceleration':
            result = Setpoint('local', acceleration=vector(reference.acceleration), yaw=yaw)
        elif kind == 'attitude':
            roll, pitch, heading, thrust = vector(reference.attitude, 4)
            if not 0 <= thrust <= 1:
                raise ValueError('Thrust must be in [0, 1]')
            cr, sr = math.cos(roll/2), math.sin(roll/2)
            cp, sp = math.cos(pitch/2), math.sin(pitch/2)
            cy, sy = math.cos(heading/2), math.sin(heading/2)
            result = Setpoint('attitude', quaternion_xyzw=(sr*cp*cy-cr*sp*sy,
                cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy), thrust=thrust)
        elif kind == 'global':
            coordinates = vector(reference.global_position)
            if not (-90 <= coordinates[0] <= 90 and -180 <= coordinates[1] <= 180):
                raise ValueError('Invalid global latitude/longitude')
            result = Setpoint('global', global_position=coordinates, yaw=yaw)
        else:
            raise ValueError(f'Unsupported reference kind: {kind}')
        self.reset()
        return result

    def _velocity(self, family, velocity, z, yaw, position):
        mixed = family == 'velocity_xy_position_z'
        threshold = self.mixed_deadband if mixed else self.speed_deadband
        held = tuple(abs(v) <= threshold for v in velocity)
        if self.family != family:
            anchor = list(position)
            held_yaw = None
        else:
            anchor, held_yaw = self.anchor.copy(), self.held_yaw
            for axis in range(2 if mixed else 3):
                if held[axis] and not self.held[axis]:
                    anchor[axis] = position[axis]
        if not mixed:
            yaw = 0.0 if abs(yaw) <= self.yaw_deadband else yaw
            if held_yaw is None or abs(yaw-held_yaw) > self.yaw_deadband:
                held_yaw = yaw  # Update this tick, without skipping a publication.
            yaw = held_yaw
        def correction(axis):
            error = position[axis] - anchor[axis]
            return -self.hold_gain * error if abs(error) >= self.hold_gap else 0.0
        if held[0] and held[1]:
            result = Setpoint('local', position=(anchor[0], anchor[1], z if mixed else anchor[2] if held[2] else None),
                              velocity=(None, None, None if mixed or held[2] else velocity[2]), yaw=yaw)
        else:
            result = Setpoint('local', position=(None, None, z if mixed else anchor[2] if held[2] else None),
                              velocity=(correction(0) if held[0] else velocity[0],
                                        correction(1) if held[1] else velocity[1],
                                        0.0 if mixed or held[2] else velocity[2]), yaw=yaw)
        if any(value is not None and not math.isfinite(value) for value in result.velocity):
            raise ValueError('Hold correction overflow')
        self.family, self.anchor, self.held, self.held_yaw = family, anchor, held, held_yaw
        return result
