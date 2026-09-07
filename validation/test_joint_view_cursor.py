"""Archived UI observations cannot move the active view cursor backwards."""
import json
from pathlib import Path
import tempfile
import time
import unittest

from Simulator.wksim_console.visual import View
from validation.test_joint_state_stream import packet


def observation(generation,epoch,sequence):
    data=packet();data.update(generation=generation,epoch=epoch,sequence=sequence,
        display_clock='windows_utc_bound',display_wall_time_s=time.time(),transport_age_bound_s=0)
    ack={k:data[k] for k in ('run_id','instance_id','generation','epoch','sequence','step','sim_time_ns')}
    ack.update(version=3,kind='joint_actor',selected_vehicle_id=1,
        vehicles=[dict(vehicle_id=i,ue_position_cm=[0,0,300],ue_quaternion_xyzw=[0,0,0,1],
                       rotor_rpm=[100,200,300,400],rotor_yaw_deg=[0,0,0,0]) for i in (1,2)],
        observed_vehicles=[dict(vehicle_id=i,step=4,stale=False,visible=True) for i in (1,2)],
        camera_position_cm=[-260,-300,440])
    return dict(packet=data,ack=ack)


class JointViewCursorTests(unittest.TestCase):
    def test_delayed_old_generation_and_sequence_do_not_replace_current(self):
        with tempfile.TemporaryDirectory() as name:
            view=View(Path(name),'joint-test','/tmp/joint-test/state.sock',joint_instance='a'*32)
            view._root.mkdir()
            def append(row):
                with view.readback_path.open('a') as stream:stream.write(json.dumps(row)+'\n')
            append(observation(2,'c'*32,20))
            current,fresh=view._actor();self.assertTrue(fresh)
            self.assertEqual(current['packet']['generation'],2)
            for row in (observation(1,'b'*32,30),observation(2,'c'*32,19)):
                append(row);current,fresh=view._actor();self.assertTrue(fresh)
                self.assertEqual((current['packet']['generation'],current['packet']['sequence']),(2,20))


if __name__=='__main__':unittest.main()
