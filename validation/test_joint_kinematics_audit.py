"""Keep audit velocity aligned with the actual model sensor ABI."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_joint_flight import kinematics
from Simulator.wksim_core.ap_json import sensor_message


class KinematicsTests(unittest.TestCase):
    def test_velocity_is_sensor_velocity_not_attitude(self):
        state=[0.]*120
        state[3:6]=[.1,.2,.3];state[6:9]=[1.,2.,-3.];state[9:12]=[1.5,2.5,3.5]
        sensor=json.loads(sensor_message(state))
        self.assertEqual(kinematics(state),sensor['position']+sensor['velocity'])
        self.assertNotEqual(kinematics(state)[3:],state[9:12])


if __name__=='__main__':unittest.main()
