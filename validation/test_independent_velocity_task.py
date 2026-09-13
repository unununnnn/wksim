"""No transport: preparation must be continuously stable before audited hold."""
import math
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from Simulator.wksim_runtime.task import Task
from tools.validate_independent_velocity import IndependentVelocityTask


class Command(NS):
    MOVE=4;XYZ_VEL=2;XYZ_VEL_BODY=4


class SettlingTests(unittest.TestCase):
    def test_angle_preparation_restarts_after_a_condition_relapse(self):
        task=IndependentVelocityTask.__new__(IndependentVelocityTask)
        task.flight_stack='px4';task.Cmd=Command
        state=NS(position=[0.,0.,3.],velocity=[0.,0.,0.],attitude=[0.,0.,.6],
                 header=NS(stamp=NS(sec=10,nanosec=0)))
        task.latest={'state':state};task.fresh=lambda:True
        def send(owner,message,label):
            velocity=message.velocity_ref
            if message.move_mode==4:
                c,s=math.cos(state.attitude[2]),math.sin(state.attitude[2])
                velocity=[c*velocity[0]-s*velocity[1],s*velocity[0]+c*velocity[1],velocity[2]]
            state.velocity=velocity
        checks=[]
        def wait(label,predicate,timeout):
            self.assertEqual((label,timeout),('angle_hold_settled',12))
            for boot,speed in ((10.,.2),(10.5,.26),(10.6,.2),(11.8,.2),(12.1,.2)):
                state.header.stamp=NS(sec=int(boot),nanosec=round((boot-int(boot))*1e9))
                state.velocity=[speed,0.,0.]
                checks.append(predicate())
            self.assertEqual(checks,[False,False,False,False,True])
        task.wait=wait
        task.dwell=lambda label,predicate,seconds:self.assertTrue(predicate(),label)
        with patch.object(Task,'send',send):
            task.extra_profiles()
        self.assertEqual(len(checks),5)


if __name__=='__main__':unittest.main()
