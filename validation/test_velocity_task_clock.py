"""Run the real velocity profile against a clock-separated, no-I/O task fixture."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from Simulator.wksim_runtime.task import Task


class Message(NS):
    SET_PX4_MODE=1
    ARMING=0
    SET_CONTROL_MODE=3
    MOVE=4
    LAND=3
    XYZ_VEL=2


class ProfileFixture:
    Setup=Cmd=Message
    uav_id=1
    flight_stack='px4'
    def __init__(self,shared_clock):
        self.use_sim_time=shared_clock
        self.boot,self.wall=10.,100.
        self.rate=0.
        self.yaw_checks=0
        self.state=NS(uav_id=1,connected=True,odom_valid=True,armed=False,
            header=NS(frame_id='map',stamp=NS(sec=10,nanosec=0)),
            position=[0.,0.,0.],velocity=[0.,0.,0.],attitude=[0.,0.,0.])
        self.setup_pub=self.command_pub=NS(get_subscription_count=lambda:1)
        self.received={'state':self.wall}
    def fresh(self):return True
    def arm_ready(self,unused):return True
    def task_time(self):return self.boot if self.use_sim_time else self.wall
    def wait(self,label,predicate,timeout=20):
        self.received['state']=self.wall+1
        if not predicate():raise RuntimeError(label)
    def send(self,msg,label,timeout=10):
        if hasattr(msg,'cmd'):
            if msg.cmd==Message.ARMING:self.state.armed=True
            if msg.cmd==Message.SET_CONTROL_MODE:self.state.position[2]=3.
        elif msg.agent_cmd==Message.LAND:
            self.state.armed=False;self.state.position[2]=0.
        else:
            self.state.velocity=list(msg.velocity_ref)
            self.rate=msg.yaw_rate_ref
    def dwell(self,label,predicate,seconds):
        for _ in range(int(seconds)):
            self.boot+=1.;self.wall+=1./3
            self.state.header.stamp.sec=int(self.boot)
            self.state.attitude[2]+=self.rate
            if label=='yaw_rate_tracking':self.yaw_checks+=1
            if not predicate():raise RuntimeError(label+' rejected a correctly scaled native motion')


class MotionClockTests(unittest.TestCase):
    def test_native_boot_and_shared_ros_motion_ignore_threefold_wall_rate(self):
        for shared in (False,True):
            with self.subTest(shared_clock=shared):
                fixture=ProfileFixture(shared)
                with patch('Simulator.wksim_runtime.task.time.monotonic',side_effect=lambda:fixture.wall):
                    Task.execute_velocity_yaw(fixture)
                self.assertEqual(fixture.yaw_checks,4)
                self.assertFalse(fixture.state.armed)


if __name__=='__main__':unittest.main()
