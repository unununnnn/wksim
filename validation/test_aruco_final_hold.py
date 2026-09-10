"""Real-CDR terminal HOLD observation tests; no ROS node or simulation."""
from types import SimpleNamespace as NS
import unittest
from Simulator.wksim_runtime.aruco_joint_task import JointArUcoTask
from tools.audit_aruco_native_holds import state_for_sample, expected_ap, f32, yaw

try:
    from rclpy.serialization import serialize_message
    from wksim_msgs.msg import SessionState
    from prometheus_msgs.msg import UAVControlState, UAVState
    ROS = True
except ImportError:
    ROS = False


class HoldAuditBoundaries(unittest.TestCase):
    def test_native_belongs_to_following_state(self):
        states=['before','reference','after']
        self.assertEqual(state_for_sample([10,20,30],states,19),'reference')
        self.assertEqual(state_for_sample([10,20,30],states,21),'after')
        for stamp in (9,10,20,30,31):
            with self.assertRaises(ValueError): state_for_sample([10,20,30],states,stamp)

    def test_ap_zero_offset_and_altitude_quantization(self):
        self.assertEqual(expected_ap([0,0,0.1],0,(350000000,1390000000)),
                         (35.0,139.0,f32(.1),0.0))

    def test_quaternion_validation(self):
        self.assertEqual(yaw(NS(w=2,x=0,y=0,z=0)),0.0)
        with self.assertRaises(ValueError): yaw(NS(w=0,x=0,y=0,z=0))


@unittest.skipUnless(ROS,'Needs installed ROS message classes')
class FinalHoldNative(unittest.TestCase):
    def task(self, stack, stages, fresh=True, command_control=True):
        task=JointArUcoTask.__new__(JointArUcoTask)
        task.request_id=90;task.epoch='a'*32;task.run_id='aruco-test'
        task.flight_stack=stack;task.uav_id=1 if stack=='arducopter' else 2
        task.aruco={'profile':{'mission':{'command_acceptance_timeout_s':.5}}}
        task.raw_capture=NS(latest_samples={});task.fresh=lambda:fresh
        task.seen=[]
        def wait(label,predicate,timeout):
            self.assertEqual(timeout,.5)
            for state_stamp,native_stamp,rid in stages:
                msg=SessionState(version=1,run_id=task.run_id,control_epoch=task.epoch,
                                 sequence=state_stamp,last_request_id=rid,
                                 state=UAVState(armed=True),
                                 control=UAVControlState(control_state=(UAVControlState.COMMAND_CONTROL
                                                          if command_control else UAVControlState.INIT)))
                samples={task.topic_root+'v2/state':{'source_timestamp':state_stamp,
                          'cdr_hex':serialize_message(msg).hex()}}
                topic='/ap/cmd_gps_pose' if stack=='arducopter' else '/wksim_px4_21/fmu/in/trajectory_setpoint'
                if native_stamp is not None:samples[topic]={'source_timestamp':native_stamp}
                task.raw_capture.latest_samples=samples
                answer=predicate();task.seen.append(answer)
                if answer:return
            raise TimeoutError(label)
        task.wait=wait
        return task

    def test_both_stacks_require_a_later_native_and_following_state(self):
        for stack in ('arducopter','px4'):
            task=self.task(stack,[(100,99,90),(100,101,90),(103,101,90)])
            task._wait_final_hold_native()
            self.assertEqual(task.seen,[False,False,True])

    def test_acceptance_without_execution_cannot_pass(self):
        task=self.task('arducopter',[(100,99,89),(103,101,91)])
        with self.assertRaises(TimeoutError):task._wait_final_hold_native()

    def test_old_native_or_missing_native_cannot_pass(self):
        for stages in ([(100,99,90),(103,99,90)],[(100,None,90),(103,None,90)]):
            task=self.task('px4',stages)
            with self.assertRaises(TimeoutError):task._wait_final_hold_native()

    def test_stale_public_state_cannot_pass(self):
        task=self.task('px4',[(100,99,90),(103,101,90)],fresh=False)
        with self.assertRaises(TimeoutError):task._wait_final_hold_native()

    def test_control_release_cannot_pass(self):
        task=self.task('px4',[(100,99,90),(103,101,90)],command_control=False)
        with self.assertRaises(TimeoutError):task._wait_final_hold_native()


if __name__=='__main__':unittest.main()
