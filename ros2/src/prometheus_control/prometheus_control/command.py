# Copyright 2022 AMOVLAB; wksim migration changes 2026.
# SPDX-License-Identifier: Apache-2.0
"""Prometheus command acceptance and desired-state calculation, without I/O.

Source: Modules/uav_control/src/uav_controller.cpp at
5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce, especially lines 441-649,
717-752, 866-892 and 1044-1105. ROS1 source remains untouched.
This is NOT the transport/output shaping, PID/UDE/NE, RC, or task-node port.
"""
from copy import deepcopy
from dataclasses import dataclass
import math

from prometheus_msgs.msg import UAVCommand as Cmd, UAVControlState as Control, UAVState


@dataclass(frozen=True)
class Acceptance:
    accepted: bool
    reason: str = ''
    stop_control: bool | None = None


@dataclass(frozen=True)
class Desired:
    """Resolved reference in local ENU/FLU, SI; global altitude is home-relative.

    Inactive references are None, never stale values from an earlier mode.
    A landing request is distinct from a streamed setpoint.
    """
    kind: str
    position: tuple | None = None
    velocity: tuple | None = None
    acceleration: tuple | None = None
    yaw: float | None = None
    yaw_rate: float | None = None
    attitude: tuple | None = None
    global_position: tuple | None = None


def finite(values):
    return all(math.isfinite(float(x)) for x in values)


def rotate_xy(vector, yaw):
    x, y = vector[:2]
    return (x * math.cos(yaw) - y * math.sin(yaw),
            x * math.sin(yaw) + y * math.cos(yaw))


class CommandProcessor:
    """Own command priority, home/hover capture and body-reference latching.

    The host must supply fresh state, manage wall-clock timeouts and validate
    flight-stack capabilities BEFORE acceptance. No flight-stack mode changes
    or synthetic acknowledgements are performed here.
    """
    BODY = (Cmd.XYZ_POS_BODY, Cmd.XYZ_VEL_BODY, Cmd.XY_VEL_Z_POS_BODY)
    VELOCITY = (Cmd.XYZ_VEL, Cmd.XYZ_VEL_BODY, Cmd.XY_VEL_Z_POS, Cmd.XY_VEL_Z_POS_BODY)

    def __init__(self, takeoff_height=1.0, enable_external_control=False,
                 fence=((-100.0, 100.0),) * 3):
        if not math.isfinite(takeoff_height) or takeoff_height <= 0:
            raise ValueError('takeoff_height must be finite and positive')
        if len(fence) != 3 or any(len(b) != 2 or not finite(b) or b[0] >= b[1] for b in fence):
            raise ValueError('fence must contain three finite increasing bounds')
        self.takeoff_height = float(takeoff_height)
        self.enable_external_control = bool(enable_external_control)
        self.fence = tuple(tuple(b) for b in fence)
        self.state = UAVState()
        self.position = (0.0, 0.0, 0.0)
        self.yaw = 0.0
        self.offset = (0.0, 0.0)
        self.home = None
        self.hover = None
        self.control_state = Control.INIT
        self.failsafe = False
        self.command = Cmd(agent_cmd=Cmd.INIT_POS_HOVER)
        self.previous_agent = None
        self.last_command_id = 0
        self.body_reference = None

    def local_position(self):
        return (self.position[0] - self.offset[0], self.position[1] - self.offset[1], self.position[2])

    def update_state(self, state):
        q = state.attitude_q
        if not finite((*state.position, *state.velocity, q.w, q.x, q.y, q.z)):
            raise ValueError('State contains non-finite pose/velocity')
        norm = math.hypot(q.w, q.x, q.y, q.z)
        if not math.isfinite(norm) or norm < 1e-9:
            raise ValueError('State quaternion is zero')
        w, x, y, z = (v / norm for v in (q.w, q.x, q.y, q.z))
        self.position = tuple(float(v) for v in state.position)
        self.yaw = math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
        if state.armed and not self.state.armed:
            self.home = self.local_position()
        if not state.armed and self.state.armed:
            # Disarming ends this control session; old motion cannot resume on re-arm.
            self.control_state = Control.INIT
            self.command = Cmd(agent_cmd=Cmd.INIT_POS_HOVER)
            self.previous_agent, self.body_reference, self.hover = None, None, None
        self.state = deepcopy(state)

    def set_offset(self, x, y):
        if self.state.location_source not in (UAVState.GPS, UAVState.RTK):
            return Acceptance(False, 'offset_requires_gps_or_rtk')
        if not finite((x, y)):
            return Acceptance(False, 'non_finite_offset')
        self.offset = (float(x), float(y))
        return Acceptance(True)

    def enter_control(self, mode, *, initial_hover=None):
        """Enter control, optionally holding a once-captured airborne pose.

        The host captures this reference only for a fresh explicit takeover.
        Repeating setup must neither recapture it nor replay an old command.
        Ground takeoff keeps the upstream INIT_POS_HOVER behavior.
        """
        if mode not in (Control.INIT, Control.RC_POS_CONTROL, Control.COMMAND_CONTROL, Control.LAND_CONTROL):
            return Acceptance(False, 'unknown_control_state')
        if mode != Control.INIT and not self.state.armed:
            return Acceptance(False, 'not_armed')
        if mode in (Control.RC_POS_CONTROL, Control.COMMAND_CONTROL) and (
                not self.state.connected or not self.state.odom_valid):
            return Acceptance(False, 'state_not_ready')
        if mode == self.control_state:
            return Acceptance(True)  # Repeated setup must not recapture hover/restart takeoff.
        if initial_hover is not None:
            if (mode != Control.COMMAND_CONTROL or not isinstance(initial_hover, Desired)
                    or initial_hover.kind != 'position' or initial_hover.position is None
                    or len(initial_hover.position) != 3 or initial_hover.yaw is None
                    or not finite((*initial_hover.position, initial_hover.yaw))
                    or any(getattr(initial_hover, field) is not None for field in
                           ('velocity', 'acceleration', 'yaw_rate', 'attitude', 'global_position'))):
                return Acceptance(False, 'invalid_initial_hover')
        self.control_state = mode
        self.command = Cmd(agent_cmd=Cmd.INIT_POS_HOVER)
        self.previous_agent, self.body_reference = None, None
        if initial_hover is not None:
            self.hover = Desired('position', position=tuple(float(v) for v in initial_hover.position),
                                 yaw=float(initial_hover.yaw))
            self.command = Cmd(agent_cmd=Cmd.CURRENT_POS_HOVER)
            self.previous_agent = Cmd.CURRENT_POS_HOVER
        if mode == Control.RC_POS_CONTROL:
            self.hover = Desired('position', position=self.local_position(), yaw=self.yaw)
        return Acceptance(True)

    def accept(self, command):
        if self.control_state != Control.COMMAND_CONTROL:
            self.command = Cmd(agent_cmd=Cmd.INIT_POS_HOVER)
            return Acceptance(False, 'not_command_control')
        if command.control_level not in (Cmd.DEFAULT_CONTROL, Cmd.ABSOLUTE_CONTROL, Cmd.EXIT_ABSOLUTE_CONTROL):
            return Acceptance(False, 'unknown_control_level')
        if self.command.control_level == Cmd.ABSOLUTE_CONTROL and command.control_level == Cmd.DEFAULT_CONTROL:
            return Acceptance(False, 'absolute_control_active', True)
        if command.agent_cmd not in (Cmd.INIT_POS_HOVER, Cmd.CURRENT_POS_HOVER, Cmd.LAND, Cmd.MOVE):
            return Acceptance(False, 'unsupported_agent_command')
        if command.agent_cmd == Cmd.MOVE:
            mode = command.move_mode
            if mode not in range(Cmd.XYZ_POS, Cmd.LAT_LON_ALT + 1):
                return Acceptance(False, 'unsupported_move_mode')
            if mode == Cmd.XYZ_ATT and not self.enable_external_control:
                # Deliberate improvement over upstream's silent takeoff-hover fallback.
                return Acceptance(False, 'external_attitude_disabled')
            numbers = (*command.position_ref, *command.velocity_ref, *command.acceleration_ref,
                       command.yaw_ref, command.yaw_rate_ref, *command.att_ref,
                       command.latitude, command.longitude, command.altitude)
            if not finite(numbers):
                return Acceptance(False, 'non_finite_command')
            if mode == Cmd.XYZ_ATT and not 0 <= command.att_ref[3] <= 1:
                return Acceptance(False, 'invalid_thrust')
            if mode == Cmd.LAT_LON_ALT and not (-90 <= command.latitude <= 90 and -180 <= command.longitude <= 180):
                return Acceptance(False, 'invalid_global_coordinate')
            if mode in self.BODY and command.command_id <= self.last_command_id:
                # Do not re-anchor duplicate/out-of-order relative commands.
                return Acceptance(False, 'body_command_id_not_increasing')
        stop = None
        if command.control_level == Cmd.ABSOLUTE_CONTROL and command.agent_cmd == Cmd.CURRENT_POS_HOVER:
            stop = True
        elif self.command.control_level == Cmd.ABSOLUTE_CONTROL and command.control_level == Cmd.EXIT_ABSOLUTE_CONTROL:
            stop = False
        self.command = deepcopy(command)
        self.body_reference = None
        self.last_command_id = max(self.last_command_id, command.command_id)
        return Acceptance(True, stop_control=stop)

    def safety_flag(self, *, sim_mode=True, rc_age=0.0):
        # Same precedence as upstream check_failsafe; the host supplies the time base.
        if not self.state.connected:
            return -1
        if not sim_mode and (not math.isfinite(rc_age) or rc_age > 1.5):
            return 3
        if any(p < low or p > high for p, (low, high) in zip(self.position, self.fence)):
            return 1
        return 0 if self.state.odom_valid else 2

    def step(self, *, sim_mode=True, rc_age=0.0):
        if self.control_state == Control.INIT:
            return None
        if self.control_state in (Control.RC_POS_CONTROL, Control.COMMAND_CONTROL):
            flag = self.safety_flag(sim_mode=sim_mode, rc_age=rc_age)
            self.failsafe = flag != 0
            if flag == -1:
                return None  # Host/FC own loss policy; never fabricate a landing ACK.
            if flag > 0:
                self.control_state = Control.LAND_CONTROL
        if self.control_state == Control.LAND_CONTROL:
            return Desired('land')
        if self.control_state == Control.RC_POS_CONTROL:
            return self.hover  # RC stick integration is a separate, not-yet-ported layer.
        cmd = self.command
        if cmd.agent_cmd == Cmd.INIT_POS_HOVER:
            if self.home is None:
                raise RuntimeError('No observed arming origin')
            result = Desired('position', position=(*self.home[:2], self.home[2] + self.takeoff_height), yaw=0.0)
        elif cmd.agent_cmd == Cmd.CURRENT_POS_HOVER:
            if self.previous_agent != Cmd.CURRENT_POS_HOVER:
                self.hover = Desired('position', position=self.local_position(), yaw=self.yaw)
            result = self.hover
        elif cmd.agent_cmd == Cmd.LAND:
            self.control_state = Control.LAND_CONTROL
            result = Desired('land')
        else:
            if cmd.move_mode in self.BODY and self.body_reference is not None:
                result = self.body_reference
            else:
                result = self.resolve_move(cmd)
                if cmd.move_mode in self.BODY:
                    self.body_reference = result
        self.previous_agent = cmd.agent_cmd
        self.last_command_id = max(self.last_command_id, cmd.command_id)
        return result

    def resolve_move(self, cmd):
        mode = cmd.move_mode
        p, v, a = (tuple(float(x) for x in values) for values in (cmd.position_ref, cmd.velocity_ref, cmd.acceleration_ref))
        yaw = float(cmd.yaw_ref) + (self.yaw if mode in self.BODY else 0.0)
        rate = float(cmd.yaw_rate_ref) if cmd.yaw_rate_mode and mode in self.VELOCITY else None
        yaw = None if rate is not None else yaw
        if mode == Cmd.XYZ_POS_BODY:
            xy = rotate_xy(p, self.yaw)
            p = (self.position[0] + xy[0], self.position[1] + xy[1], self.position[2] + p[2])
        elif mode in (Cmd.XYZ_VEL_BODY, Cmd.XY_VEL_Z_POS_BODY):
            v = (*rotate_xy(v, self.yaw), v[2])
            if mode == Cmd.XY_VEL_Z_POS_BODY:
                p = (0.0, 0.0, self.position[2] + p[2])
        if mode in (Cmd.XYZ_POS, Cmd.XYZ_POS_BODY, Cmd.TRAJECTORY):
            p = (p[0] - self.offset[0], p[1] - self.offset[1], p[2])
            return Desired('trajectory' if mode == Cmd.TRAJECTORY else 'position', position=p,
                           velocity=v if mode == Cmd.TRAJECTORY else None,
                           acceleration=a if mode == Cmd.TRAJECTORY else None, yaw=yaw)
        if mode in (Cmd.XYZ_VEL, Cmd.XYZ_VEL_BODY):
            return Desired('velocity', velocity=v, yaw=yaw, yaw_rate=rate)
        if mode in (Cmd.XY_VEL_Z_POS, Cmd.XY_VEL_Z_POS_BODY):
            # Upstream forgot to update yaw_rate_des in these two modes; use this command.
            return Desired('velocity_xy_position_z', position=(0.0, 0.0, p[2]), velocity=(*v[:2], 0.0), yaw=yaw, yaw_rate=rate)
        if mode == Cmd.XYZ_ATT:
            return Desired('attitude', attitude=tuple(float(x) for x in cmd.att_ref))
        if mode == Cmd.LAT_LON_ALT:
            return Desired('global', global_position=(cmd.latitude, cmd.longitude, cmd.altitude), yaw=yaw)
        raise ValueError('Unexpected move mode after validation')
