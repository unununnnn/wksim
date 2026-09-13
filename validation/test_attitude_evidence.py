"""Audit rejection checks; synthetic fixtures never constitute flight evidence."""
import json
import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_attitude_flight import physical_evidence,window,q_from_euler,native_q,q_distance,digest,px4_parameter_value,frozen_command
from tools.audit_attitude_flight import entry_contract,entry_gate_evidence,candidate_parameters,ap_guided_transition,ENTRY_PATH,ENTRY_SHA,REPO


class EvidenceTests(unittest.TestCase):
    def test_ap_old_native_input_only_before_frozen_window(self):
        raw=[({},dict(header=dict(stamp=dict(sec=66,nanosec=76000000),frame_id='map'),
                      orientation=dict(w=1.,x=0.,y=0.,z=0.),normalized_thrust=.31))]
        old=dict(matches_public=False,physical_s=66.087,native_boot_s=66.087,
                 roll_deg=0.,pitch_deg=0.,yaw_deg=90.,normalized_thrust=.31)
        new=dict(old,matches_public=True,physical_s=66.12,native_boot_s=66.12,normalized_thrust=.34)
        self.assertEqual(len(ap_guided_transition([old,new],raw,66.1,66.102)),1)
        # The fixed window never moves to the first match after a bad sample.
        for bad in (dict(old,physical_s=66.1,native_boot_s=66.1),
                    dict(old,physical_s=66.11,native_boot_s=66.11)):
            with self.assertRaisesRegex(ValueError,'inside frozen'):
                ap_guided_transition([bad,new],raw,66.1,66.102)
        with self.assertRaises(ValueError):ap_guided_transition([old,new],[],66.1,66.102)
        with self.assertRaises(ValueError):ap_guided_transition([dict(old,normalized_thrust=.4),new],raw,66.1,66.102)

    def gate_fixture(self):
        contract=json.loads((REPO/ENTRY_PATH).read_text())['px4']
        mode={name:True for name in contract['required_true']}
        mode.update({name:False for name in contract['required_false']});mode['timestamp']=1100000
        q=native_q(q_from_euler(0,0,.2))
        def phase(t,wall,**values):
            return dict(physical_cursor=dict(final_time=t),observed_monotonic_s=wall,**values)
        def raw(t,wall):
            return dict(physical_cursor=dict(final_time=t),monotonic=wall,source_timestamp=123,received_timestamp=456)
        native=dict(native_source_stamp=1050000,physical_time=1.06)
        actual=dict(physical_time=1.14,native_boot_s=1.12,thrust=.5,quaternion=q)
        endpoint=[dict(node='px4',namespace='/',endpoint_gid='0102')]
        phases={
            'hover_candidate_frozen':phase(.98,9.9),
            'level_calibration_entry_preconditioning_begin':phase(1.,10.,physical_start=1.,physical_deadline=3.,
                wall_timeout_seconds=10.,neutral_attitude=[0,0,.2,.5]),
            'level_calibration_entry_neutral_offered':phase(1.,10.01,command_id=1),
            'level_calibration_entry_neutral_native_observed':phase(1.06,10.06,native_target=native),
            'level_calibration_entry_preconditioning_complete':phase(1.2,10.2,offered_native_stamp=1050000,
                control_mode=dict(native_source_stamp=1100000,physical_time=1.1,flags=mode,
                                  source_timestamp=123,received_timestamp=456),
                actual_attitude_target=actual,publisher_endpoints=endpoint),
            'level_calibration_offered':phase(1.2,10.21),
            'level_calibration_native_observed':phase(1.24,10.25,native_target=dict(physical_time=1.24)),
            'level_calibration_begin':phase(1.24,10.26,physical_start=1.24,duration_seconds=2)}
        topic='/wksim_px4_21/fmu/out/vehicle_control_mode'
        data={topic:[(raw(1.1,10.1),mode)],
              '/uav1/prometheus/v2/command':[(raw(1.02,10.02),dict(command=dict(command_id=1,agent_cmd=4,
                  move_mode=7,att_ref=[0,0,.2,.5])))],
              '/wksim_px4_21/fmu/in/vehicle_attitude_setpoint':[(raw(1.06,10.05),
                  dict(timestamp=1050000,q_d=q,thrust_body=[0.,0.,-.5]))],
              '/wksim_px4_21/fmu/in/offboard_control_mode':[(raw(1.06,10.055),dict(timestamp=1050000,
                  attitude=True,position=False,velocity=False,acceleration=False,body_rate=False,
                  thrust_and_torque=False,direct_actuator=False))]}
        recorded=[dict(monotonic=10.14,physical_time=1.14,
            message=dict(mavpackettype='ATTITUDE_TARGET',time_boot_ms=1120,thrust=.5,q=q))]
        states=[dict(time=t/1000,position=(2,3,3),velocity=(0,0,0),attitude=(0,0,.2)) for t in range(1,3201)]
        result=dict(stack='px4',task=dict(attitude_thrust=dict(status='failed',
            calibration=dict(yaw=.2,hover=.5,anchor=(2,3,3)))))
        return dict(result=result,data=data,recorded=recorded,phases=phases,states=states,
                    discovery=[dict(monotonic=9.99,publishers={topic:endpoint})],contract=contract)

    def test_entry_raw_chain(self):
        report=entry_gate_evidence(**self.gate_fixture())
        self.assertEqual(report['stages'][0]['status'],'verified')
        self.assertEqual(report['stages'][1]['status'],'not_reached')

    def test_entry_rejects_fabricated_or_stale_chain(self):
        def complete(v):return v['phases']['level_calibration_entry_preconditioning_complete']
        def native_mode(v):return v['data']['/wksim_px4_21/fmu/out/vehicle_control_mode'][0][1]
        mutations={
            'missing_raw_mode':lambda v:v['data']['/wksim_px4_21/fmu/out/vehicle_control_mode'].clear(),
            'position_control':lambda v:native_mode(v).update(flag_control_position_enabled=True),
            'mode_before_input':lambda v:native_mode(v).update(timestamp=1040000),
            'same_target_stamp':lambda v:v['recorded'][0]['message'].update(time_boot_ms=1100),
            'fabricated_target':lambda v:complete(v)['actual_attitude_target'].update(thrust=.6),
            'wrong_neutral':lambda v:v['data']['/uav1/prometheus/v2/command'][0][1]['command'].update(att_ref=[.1,0,.2,.5]),
            'wrong_ocm':lambda v:v['data']['/wksim_px4_21/fmu/in/offboard_control_mode'][0][1].update(position=True),
            'wall_deadline':lambda v:complete(v).update(observed_monotonic_s=20.),
            'physical_deadline':lambda v:complete(v)['physical_cursor'].update(final_time=3.01),
            'shifted_original_window':lambda v:v['phases']['level_calibration_begin'].update(physical_start=1.1),
            'short_original_window':lambda v:v['phases']['level_calibration_begin'].update(duration_seconds=1.8),
            'unsafe_1ms':lambda v:v['states'][1100].update(attitude=(math.radians(15.01),0,.2)),
            'competing_discovery':lambda v:v['discovery'][0]['publishers']['/wksim_px4_21/fmu/out/vehicle_control_mode'].append(
                dict(node='other',namespace='/',endpoint_gid='0304')),
            'missing_gate':lambda v:v['phases'].pop('level_calibration_entry_preconditioning_begin'),
            'fabricated_completed_run':lambda v:v['result']['task']['attitude_thrust'].update(status='completed_pending_raw_audit')}
        for name,change in mutations.items():
            with self.subTest(name=name):
                value=self.gate_fixture();change(value)
                with self.assertRaises(ValueError):entry_gate_evidence(**value)

    def test_entry_target_timestamp_strict_even_when_report_agrees(self):
        value=self.gate_fixture()
        value['recorded'][0]['message']['time_boot_ms']=1100
        value['phases']['level_calibration_entry_preconditioning_complete']['actual_attitude_target']['native_boot_s']=1.1
        with self.assertRaisesRegex(ValueError,'strictly after'):entry_gate_evidence(**value)

    def test_entry_cannot_choose_older_passing_mode(self):
        value=self.gate_fixture()
        modes=value['data']['/wksim_px4_21/fmu/out/vehicle_control_mode']
        row,mode=copy.deepcopy(modes[0])
        row['monotonic']=10.15;mode['timestamp']=1150000;mode['flag_control_position_enabled']=True
        modes.append((row,mode))
        with self.assertRaisesRegex(ValueError,'older passing'):entry_gate_evidence(**value)

    def test_entry_cannot_select_later_matching_target(self):
        value=self.gate_fixture();earlier=copy.deepcopy(value['recorded'][0])
        earlier['monotonic']=10.13;earlier['message']['time_boot_ms']=1110
        value['recorded'].insert(0,earlier)
        with self.assertRaisesRegex(ValueError,'first eligible'):entry_gate_evidence(**value)

    def test_entry_control_mode_age_is_independent_of_report_flags(self):
        value=self.gate_fixture()
        value['phases']['level_calibration_entry_preconditioning_complete']['physical_cursor']['final_time']=1.86
        with self.assertRaisesRegex(ValueError,'freshness'):entry_gate_evidence(**value)

    def test_entry_contract_cannot_be_removed_or_resealed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'run-source/Simulator/wksim_runtime/attitude_task.py'
            source.parent.mkdir(parents=True);source.write_text('historical task')
            result=dict(task=dict(attitude_thrust={}),source_sha256={})
            self.assertFalse(entry_contract(root,result)['required'])
            source.write_text('ENTRY_CONTRACT_SHA = frozen')
            with self.assertRaises(ValueError):entry_contract(root,result)
            (root/'run-source'/ENTRY_PATH).write_bytes((REPO/ENTRY_PATH).read_bytes())
            result['task']['attitude_thrust']['entry_contract_sha256']=ENTRY_SHA
            result['source_sha256'][ENTRY_PATH]=ENTRY_SHA
            self.assertTrue(entry_contract(root,result)['required'])
            with (root/'run-source'/ENTRY_PATH).open('a') as stream:stream.write(' ')
            with self.assertRaises(ValueError):entry_contract(root,result)

    def test_ap_actual_candidate_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'attitude.parm').write_text('GUID_OPTIONS 8\nGUID_TIMEOUT 3\nLOG_DISARMED 1\nPSC_ANGLE_MAX 10\n')
            (root/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
            (root/'base.parm').write_text('PSC_ANGLE_MAX 0\nATC_ANGLE_MAX 30\n')
            result=dict(experimental_parameters=dict(GUID_OPTIONS=8,GUID_TIMEOUT=3,LOG_DISARMED=1,PSC_ANGLE_MAX=10),
                        children=dict(fc=dict(argv=['fc','--defaults',','.join(str(root/name) for name in
                            ('base.parm','attitude.parm','dds.parm'))])))
            candidate_parameters(root,result)
            bad=copy.deepcopy(result);bad['experimental_parameters']['PSC_ANGLE_MAX']=15
            with self.assertRaises(ValueError):candidate_parameters(root,bad)
            (root/'base.parm').write_text('PSC_ANGLE_MAX 10\n')
            with self.assertRaises(ValueError):candidate_parameters(root,result)

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
