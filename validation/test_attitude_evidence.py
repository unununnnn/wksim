"""Audit rejection checks; synthetic fixtures never constitute flight evidence."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_attitude_flight import physical_evidence,window,q_from_euler,native_q,q_distance,digest,px4_parameter_value,frozen_command


class EvidenceTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'run-source/tools/attitude_physics.py'
        source.parent.mkdir(parents=True)
        source.write_text('synthetic observer fixture\n')
        records=[dict(kind='start',schema='wksim.attitude.physics.v1',initial_tick=0,dt_s=.001,
                      observer_sha256=digest(source))]
        trace=[]
        for tick in range(1,9):
            state=[0.]*120;state[2]=tick*.001;state[11]=math.pi/2
            command=[.5]*4+[0.]*12
            records.append(dict(kind='step',tick=tick,group=(tick-1)//4+1,substep=(tick-1)%4,
                                group_steps=4,input16=command,output120=state))
            if tick%4==0:
                trace.append(dict(time=state[2],vehicle=state[:60],sensor=state[60:90],controls=command))
        records.append(dict(kind='end',ticks=8,groups=2))
        (root/'truth.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in trace))
        return records

    def run_fixture(self,change=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rows=self.fixture(root)
            if change:change(rows)
            (root/'physics-1ms.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            return physical_evidence(root,'px4')

    def test_complete_groups(self):
        result,states,_,_=self.run_fixture()
        self.assertEqual((result['ticks'],result['groups']),(8,2))
        self.assertEqual(len(window(states,.002,.006)),5)

    def test_missing_tick_rejected(self):
        with self.assertRaises(ValueError):self.run_fixture(lambda rows:rows.pop(3))

    def test_held_input_change_rejected(self):
        def mutate(rows):rows[2]['input16'][0]=.6
        with self.assertRaises(ValueError):self.run_fixture(mutate)

    def test_incomplete_group_rejected(self):
        def mutate(rows):rows[-2]['substep']=1
        with self.assertRaises(ValueError):self.run_fixture(mutate)

    def test_nonfinite_output_rejected(self):
        def mutate(rows):rows[2]['output120'][11]=math.nan
        with self.assertRaises(ValueError):self.run_fixture(mutate)

    def test_relabelled_trace_rejected(self):
        def mutate(rows):rows[4]['output120'][7]=99
        with self.assertRaises(ValueError):self.run_fixture(mutate)

    def test_missing_terminal_rejected(self):
        with self.assertRaises(ValueError):self.run_fixture(lambda rows:rows.pop())

    def test_window_never_fills_missing_data(self):
        _,states,_,_=self.run_fixture()
        with self.assertRaises(ValueError):window(states,.001,.009)

    def test_px4_integer_is_bytewise(self):
        self.assertEqual(px4_parameter_value(dict(param_type=6,param_value=1.401298464324817e-45)),1)
        self.assertEqual(px4_parameter_value(dict(param_type=9,param_value=.5)),.5)
        with self.assertRaises(ValueError):px4_parameter_value(dict(param_type=2,param_value=1.))

    def test_calibration_cannot_relabel_step(self):
        calibration=dict(hover=.5,yaw=.2)
        cmd=dict(agent_cmd=4,move_mode=7,att_ref=[math.radians(5),0.,.2,.5])
        frozen_command('attitude_step',cmd,calibration)
        with self.assertRaises(ValueError):frozen_command('thrust_step',cmd,calibration)

    def test_basis_via_independent_rotation_matrix(self):
        def matrix(q):
            w,x,y,z=q
            return [[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                    [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                    [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
        for angles in ((0,0,0),(.1,-.2,.3),(-.7,.6,-2.9)):
            q=q_from_euler(*angles);rotation=matrix(q);converted=matrix(native_q(q))
            # R_ned_frd = NED<-ENU * R_enu_flu * FLU<-FRD.
            expected=[[rotation[1][j]*(1 if j==0 else -1) for j in range(3)],
                      [rotation[0][j]*(1 if j==0 else -1) for j in range(3)],
                      [-rotation[2][j]*(1 if j==0 else -1) for j in range(3)]]
            self.assertLess(max(abs(a-b) for x,y in zip(converted,expected) for a,b in zip(x,y)),1e-14)
            self.assertEqual(q_distance(q,[-v for v in q]),0)


if __name__=='__main__':unittest.main()
