"""Independent review negatives for JointArUcoTask._wait_final_hold_native.

Scope: only the current ~40-line terminal-HOLD wait (post-bc092f4, now gated on
armed + COMMAND_CONTROL). Own harness; no ROS nodes, no simulation, no runtime
edits. The native-holds auditor and the large retained runs are out of scope.
"""
from types import SimpleNamespace as NS
import unittest

from Simulator.wksim_runtime.aruco_joint_task import JointArUcoTask

try:
    from rclpy.serialization import serialize_message
    from wksim_msgs.msg import SessionState
    from prometheus_msgs.msg import UAVControlState, UAVState
    ROS = True
except ImportError:
    ROS = False


@unittest.skipUnless(ROS, 'Needs installed ROS message classes')
class FinalHoldWaitReview(unittest.TestCase):
    OK = (True, False, 2)  # armed, failsafe, COMMAND_CONTROL

    def task(self, stages, stack='px4'):
        task = JointArUcoTask.__new__(JointArUcoTask)
        task.request_id = 90
        task.epoch = 'b' * 32
        task.run_id = 'aruco-review'
        task.flight_stack = stack
        task.uav_id = 1 if stack == 'arducopter' else 2
        task.aruco = {'profile': {'mission': {'command_acceptance_timeout_s': .5}}}
        task.raw_capture = NS(latest_samples={})
        task.fresh = lambda: True
        task.seen = []

        def wait(label, predicate, timeout):
            self.assertEqual(timeout, .5)
            for state_stamp, native_stamp, rid, (armed, failsafe, control) in stages:
                msg = SessionState(version=1, run_id=task.run_id,
                                   control_epoch=task.epoch, sequence=state_stamp,
                                   last_request_id=rid,
                                   state=UAVState(armed=armed),
                                   control=UAVControlState(control_state=control,
                                                           failsafe=failsafe))
                samples = {task.topic_root + 'v2/state':
                           {'source_timestamp': state_stamp,
                            'cdr_hex': serialize_message(msg).hex()}}
                topic = ('/ap/cmd_gps_pose' if stack == 'arducopter'
                         else '/wksim_px4_21/fmu/in/trajectory_setpoint')
                if native_stamp is not None:
                    samples[topic] = {'source_timestamp': native_stamp}
                task.raw_capture.latest_samples = samples
                answer = predicate()
                task.seen.append(answer)
                if answer:
                    return
            raise TimeoutError(label)
        task.wait = wait
        return task

    def test_native_without_a_following_state_cannot_pass(self):
        # A newer native sample (101) exists after the boundary state (100),
        # but no SessionState follows it: the boundary observation alone must
        # never release LAND.
        task = self.task([(100, 101, 90, self.OK)])
        with self.assertRaises(TimeoutError):
            task._wait_final_hold_native()
        self.assertEqual(task.seen, [False])

    def test_unarmed_failsafe_or_non_command_state_cannot_confirm(self):
        # The following state lost armed / failsafe rose / control_state left
        # COMMAND_CONTROL: must not confirm even with a fresh native sample
        # strictly between boundary and that state.
        for bad in ((False, False, 2), (True, True, 2), (True, False, 1)):
            task = self.task([(100, None, 90, self.OK), (103, 101, 90, bad)])
            with self.assertRaises(TimeoutError):
                task._wait_final_hold_native()
            self.assertEqual(task.seen, [False, False])


if __name__ == '__main__':
    unittest.main()
