"""Explicit moving-P+V interruption experiment, not nominal PV acceptance."""
import math
import os
import time

from pv_trajectory_task import PVTask, reference
from Simulator.wksim_runtime.task import grounded
from planner_release_handoff import handoff_and_release


class PlannerReleaseTask(PVTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.release_result = None
        self.release_stop = None

    def execute(self):
        self.prepare()  # Existing arm/takeoff/hold/waypoint contract, unchanged.
        if self.flight_stack == 'px4':
            self.fly_leg(1)  # Companion retains the complete first leg and stop windows.
            self.offer('land_accepted', agent_cmd=self.Cmd.LAND,
                       control_level=self.Cmd.EXIT_ABSOLUTE_CONTROL)
        else:
            self.fly_until_release()
            # Explicit public native LAND after BRAKE, without restarting an old trajectory.
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LAND'),
                      'release_auto_land_confirmed')
        self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id), 30)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'),
                  'ground_hold_completed')
        completed = time.monotonic()
        self.wait('normal_stop_ready', lambda: self.fresh() and grounded(self.state, self.uav_id)
                  and self.received.get('state', 0) > completed)

    def fly_until_release(self):
        position, yaw, start, record = self.begin_leg(1)
        previous = None
        while True:
            elapsed = self.task_time() - start
            if previous is not None and elapsed - previous > .25:
                raise RuntimeError('Trajectory public sampling exceeded 250ms')
            p, v, a, heading = reference(elapsed, position, yaw, 1)
            record['samples'].append(dict(ros_time_s=self.task_time(), elapsed=elapsed,
                                         position=p, velocity=v, acceleration=a, yaw=heading))
            self.offer('release_pv_reference', agent_cmd=self.Cmd.MOVE,
                       move_mode=self.Cmd.TRAJECTORY, position_ref=list(p),
                       velocity_ref=list(v), acceleration_ref=list(a), yaw_ref=heading)
            if elapsed >= 6.0:
                break
            previous = elapsed
            while self.task_time() - start < min(6.0, elapsed + .1):
                self.pump()
                actual = reference(self.task_time() - start, position, yaw, 1)
                if not self.tracked(actual[0], actual[1], actual[3]):
                    raise RuntimeError('Trajectory tracking exceeded frozen bounds')
        if not self.fresh() or math.hypot(*self.state.velocity) <= .25:
            raise RuntimeError('Release proof requires actual movement above the stop threshold')
        self.release_stop = dict(requested_ros_ns=self.node.get_clock().now().nanoseconds,
                                 requested_ros_s=self.task_time(),
                                 anchor=[float(v) for v in self.state.position],
                                 pre_release_velocity=[float(v) for v in self.state.velocity])
        # No further command publication occurs until the helper returns with
        # a verified setup response and the new public request high-water.
        self.phase('release_writer_silent')
        self.release_result = handoff_and_release(
            self, output=self.directory/'planner-release', environment=dict(os.environ),
            mode='BRAKE', expected_native_mode='BRAKE')
        self.release_stop['confirmed_ros_ns'] = self.node.get_clock().now().nanoseconds
        self.release_stop['confirmed_ros_s'] = self.task_time()
        self.phase('release_confirmed')
        self.dwell('release_stop_prepared', self.fresh, 2)
        self.release_stop['hold_start_ros_ns'] = self.node.get_clock().now().nanoseconds
        self.release_stop['hold_start_ros_s'] = self.task_time()
        self.dwell('release_stop_held', lambda: self.fresh()
                   and math.hypot(*self.state.velocity) <= .25
                   and math.dist(self.state.position, self.release_stop['anchor']) <= 1., 4)
        self.release_stop['hold_end_ros_ns'] = self.node.get_clock().now().nanoseconds
        self.release_stop['hold_end_ros_s'] = self.task_time()

    def report(self):
        return dict(super().report(), experiment='planner_public_release',
                    nominal_pv_acceptance=False, release=self.release_result,
                    release_stop=self.release_stop)
