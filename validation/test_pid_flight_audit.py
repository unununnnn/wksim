"""Synthetic adversarial evidence, explicitly not a native flight oracle.

python -B -m unittest validation.test_pid_flight_audit -v
"""
import copy
from dataclasses import asdict
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_pid_flight as audit
from Simulator.wksim_runtime.pid_task import event_for, PIDLoop, reference
from Simulator.wksim_control.position_pid import PIDState

CONFIG = json.loads((audit.REPO/'Simulator/wksim_runtime/pid-flight-v1.json').read_text())


class ProgressEncodingTests(unittest.TestCase):
    def test_optional_telemetry_encoding_only(self):
        optional = ('range', 'rel_alt', 'battery_state', 'battery_percetage')
        raw = dict(phases=[dict(state=dict(position=[1., 2., 3.],
            **dict.fromkeys(optional, float('nan'))))], pid_updates=3)
        encoded = copy.deepcopy(raw)
        for key in optional:
            encoded['phases'][0]['state'][key] = {'nonfinite_number': 'nan'}
        self.assertTrue(audit.same_progress(encoded, raw))
        self.assertTrue(math.isnan(raw['phases'][0]['state']['range']))
        for key, value in (('range', 1.), ('range', float('inf')), ('position', [1., 2., float('nan')])):
            changed = copy.deepcopy(raw)
            changed['phases'][0]['state'][key] = value
            self.assertFalse(audit.same_progress(encoded, changed))
        changed = copy.deepcopy(encoded)
        changed['pid_updates'] = 4
        self.assertFalse(audit.same_progress(encoded, changed))
        bad = dict(phases=[dict(state=dict(position=[float('nan'), 2., 3.]))])
        self.assertFalse(audit.same_progress(bad, bad))


def event_fixture():
    event = event_for(CONFIG, 'fixture', 0)
    raw = (json.dumps(event, sort_keys=True, separators=(',', ':'))+'\n').encode()
    return event, raw, audit.event_check(event, raw, 'fixture')


def physical_fixture():
    event, raw, sha = event_fixture()
    rows = [dict(kind='start', run_id='fixture', schema='wksim.pid.physics.v1', initial_tick=0,
                 dt_s=.001, mass_kg=1.515, library_sha256=audit.MODEL, protocol_sha256=audit.PROTOCOL)]
    packets = []
    for tick in range(3000):
        pwm = [1500]*4+[0]*12
        p = dict(protocol='AP_JSON_SERVO16', packet_hex=struct.pack('<HHI16H',18458,1000,tick,*pwm).hex(),
                 frame=tick, rate_hint=1000, pwm16=pwm, decoded_input16=[.5]*4+[0.]*12)
        packets.append(p)
        v = [0.]*120; v[2] = (tick+1)*.001
        active = 2000 <= tick < 3000
        rows.append(dict(kind='step', run_id='fixture', interval_tick=tick, tick=tick+1,
            group=tick+1, substep=0, group_steps=1, output120=v, raw_actuator_packet=p,
            input16=p['decoded_input16'], original_decoded_input16=p['decoded_input16'],
            applied_input16=[.485 if active else .5]*4+[0.]*12,
            disturbance_active=active, disturbance_event_sha256=sha, disturbance_revoked=False))
    rows.append(dict(kind='end', run_id='fixture', ticks=3000, groups=3000,
                     disturbance_applied_ticks=1000, disturbance_event_sha256=sha, disturbance_revoked=False))
    return rows, packets, event, sha


def trace_fixture():
    result = dict(run_id='fixture', stack='px4', task=dict(control_epoch='epoch'))
    phases = {}; rows = []; data = {'/uav1/prometheus/v2/command': [], '/uav1/prometheus/v2/state': [],
                                    '/uav1/prometheus/text_info': []}
    loop = PIDLoop(CONFIG, 'px4', .5)
    for i, kind in enumerate(('point', 'circle', 'disturbance')):
        origin = 10.+30*i; now = origin+.02
        state = PIDState((2.,3.,3.), (0.,0.,0.), (1.,0.,0.,0.))
        loop.reset('takeover_'+kind, origin)
        row = loop.update(now, state, reference(CONFIG, kind, .02), active=True)
        rid = cid = i+1
        cmd = dict(command_id=cid, agent_cmd=4, move_mode=7,
                   att_ref=[*row['output']['roll_pitch_yaw_enu_rad'], row['normalized_collective']])
        public = dict(version=1, run_id='fixture', control_epoch='epoch', request_id=rid, command=cmd)
        row.update(stage=kind, run_id='fixture', protocol_sha256=audit.PROTOCOL, model_identity='sha256:'+audit.MODEL,
                   mass_kg=1.515, calibration=.5, control_epoch='epoch', native_generation=1,
                   physical_time=now, reference_origin_physical_s=origin, public_request_id=rid,
                   public_command_id=cid, public_move_mode=7, public_envelope=copy.deepcopy(public))
        raw = dict(monotonic=now)
        data['/uav1/prometheus/v2/command'].append((raw, public))
        s = dict(header=dict(stamp=dict(sec=int(now), nanosec=round((now-int(now))*1e9))),
                 position=list(state.position_enu), velocity=list(state.velocity_enu),
                 attitude_q=dict(zip(('w','x','y','z'),state.attitude_flu_to_enu)),
                 armed=True, connected=True, odom_valid=True, mode='OFFBOARD')
        data['/uav1/prometheus/v2/state'].append((dict(monotonic=origin),
            dict(run_id='fixture', control_epoch='epoch', native_generation=1, state=s, control=dict(control_state=2))))
        data['/uav1/prometheus/text_info'].append((raw, dict(message=json.dumps(dict(event='command_accepted',
            run_id='fixture', control_epoch='epoch', request_id=rid, command_id=cid)))))
        phases['pid_'+kind+'_begin'] = dict(physical_start=origin, native_boot_s=origin, observed_monotonic_s=origin)
        phases['pid_'+kind+'_end'] = dict(physical_cursor=dict(final_time=origin+1), observed_monotonic_s=origin+1,
                                         native_boot_s=now+.01)
        rows.append(json.loads(json.dumps(row)))
    return rows, phases, result, data


class PIDFlightAuditTests(unittest.TestCase):
    def test_ap_native_execution_and_position_override(self):
        from pymavlink import mavutil
        rows, phases, result, data = trace_fixture(); result['stack']='arducopter'
        for r in rows: r['native_thrust_convention']=r['normalized_collective']
        for _, s in data['/uav1/prometheus/v2/state']: s['state']['mode']='GUIDED'
        matched, _ = audit.trace_audit(CONFIG,rows,phases,result,.5,data)
        targets=[]; native=[]
        class Message:
            def __init__(self,kind,value): self.kind,self.value=kind,value
            def get_type(self): return self.kind
            def to_dict(self): return self.value
        class Log:
            def __init__(self): self.rows=iter(native)
            def recv_match(self,**kwargs): return next(self.rows,None)
            def close(self): pass
        states=[dict(position=(2,3,3),velocity=(0,0,0))]*72000
        originals=[[.5]*4+[0]*12]*72000
        for row,raw,public in matched:
            t=row['native_state_stamp_s']+.01
            r,p,y,u=public['command']['att_ref']; q=audit.wire.q_from_euler(r,p,y)
            targets.append((dict(monotonic=raw['monotonic']+.01),dict(
                header=dict(stamp=dict(sec=int(t),nanosec=round((t-int(t))*1e9)),frame_id='map'),
                orientation=dict(zip(('w','x','y','z'),q)),normalized_thrust=u)))
            native.append(Message('GUIA',dict(TimeUS=round(t*1e6),Roll=math.degrees(r),Pitch=-math.degrees(p),
                Yaw=90-math.degrees(y),Thrust=u,ClimbRt=0,RollRt=0,PitchRt=0,YawRt=0)))
            native.append(Message('RCOU',dict(TimeUS=round(t*1e6),C1=1500,C2=1500,C3=1500,C4=1500)))
            native.append(Message('SIM2',dict(TimeUS=round(t*1e6),PE=2,PN=3,PD=-3,VE=0,VN=0,VD=0)))
        data['/ap/wksim/attitude_target_v1']=targets
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'test.BIN').touch()
            with patch.object(mavutil,'mavlink_connection',side_effect=lambda *a:Log()):
                value=audit.native_audit(root,result,data,matched,phases,states,originals)
                self.assertEqual(len(value['request_associations']),3)
                native.append(Message('GUIP',dict(TimeUS=10030000)))
                with self.assertRaisesRegex(ValueError,'position loop override'):
                    audit.native_audit(root,result,data,matched,phases,states,originals)

    def test_same_run_calibration_and_changed_hover(self):
        samples=[dict(physical_time=1+i*.1,native_boot_s=1+i*.1,thrust=.5,quaternion=[1,0,0,0]) for i in range(31)]
        recorded=[dict(message=dict(mavpackettype='ATTITUDE_TARGET',time_boot_ms=round(s['native_boot_s']*1000),
                                    thrust=s['thrust'],q=s['quaternion']),physical_time=s['physical_time'],monotonic=4)
                  for s in samples]
        # Native millisecond conversion is authoritative, not the float fixture generator.
        for s,r in zip(samples,recorded): s['native_boot_s']=r['message']['time_boot_ms']/1000
        cal=dict(stack='px4',mass_kg=1.515,model_identity='sha256:'+audit.MODEL,samples=samples,hover=.5,frozen_at_physical_time=4.)
        resolved=dict(configuration=CONFIG,protocol_sha256=audit.PROTOCOL,controller='pid',calibration=cal)
        result=dict(stack='px4',task=dict(external_pid=dict(calibration=cal)))
        phases=dict(hover_observation_begin=dict(physical_start=1.),
            hover_observation_end=dict(physical_cursor=dict(final_time=4.),observed_monotonic_s=4.),
            pid_level_calibration_begin=dict(physical_start=5.),
            pid_level_calibration_end=dict(physical_cursor=dict(final_time=7.)),
            pid_level_calibration_offered=dict(physical_cursor=dict(final_time=4.9)),
            pid_point_begin=dict(physical_start=8.))
        states=[dict(time=i/1000,position=(2,3,3),velocity=(0,0,0),attitude=(0,0,0)) for i in range(1,8001)]
        self.assertEqual(audit.calibration(CONFIG,resolved,result,recorded,phases,states)['hover'],.5)
        cal['hover']=.531
        with self.assertRaisesRegex(ValueError,'median differs'): audit.calibration(CONFIG,resolved,result,recorded,phases,states)
        cal['hover']=.5; recorded[0]['message']['thrust']=.4
        with self.assertRaisesRegex(ValueError,'samples missing'): audit.calibration(CONFIG,resolved,result,recorded,phases,states)

    def test_native_px4_association_and_override_negatives(self):
        from Simulator.wksim_runtime.attitude_task import MODE_TRUE, MODE_FALSE
        rows, phases, result, data = trace_fixture()
        matched, _ = audit.trace_audit(CONFIG,rows,phases,result,.5,data)
        targets = []; logged = []; modes = []; offboard = []; motors = []
        for row, raw, public in matched:
            t = round((row['native_state_stamp_s']+.01)*1e6)
            r,p,y,u = public['command']['att_ref']; q = audit.wire.native_q(audit.wire.q_from_euler(r,p,y))
            target = dict(timestamp=t, q_d=q, thrust_body=[0.,0.,-u])
            targets.append((dict(monotonic=raw['monotonic']+.01),target))
            logged.append(dict(timestamp=t, q_d=q, **{'thrust_body[2]':-u}))
            modes.append(({},dict(timestamp=t-1, **{k:True for k in MODE_TRUE}, **{k:False for k in MODE_FALSE})))
            offboard.append(({},dict(timestamp=t, attitude=True, position=False, velocity=False, acceleration=False,
                                    body_rate=False, thrust_and_torque=False, direct_actuator=False)))
            motors.append(dict(timestamp=t, output=[1500]*4))
        data['/in/vehicle_attitude_setpoint'] = targets
        data['/in/offboard_control_mode'] = offboard
        data['/out/vehicle_control_mode'] = modes
        originals = [[.5]*4+[0]*12]*72000
        native = dict(vehicle_attitude_setpoint=logged,actuator_outputs=motors)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'test.ulg').touch()
            with patch.object(audit.wire,'ulog',return_value=(native,dict(dropout_durations_ms=[]))):
                report = audit.native_audit(root,result,data,matched,phases,[],originals)
                self.assertEqual(len(report['request_associations']),3)
                modes[0][1]['flag_control_position_enabled'] = True
                with self.assertRaisesRegex(ValueError,'loop override'):
                    audit.native_audit(root,result,data,matched,phases,[],originals)
                modes[0][1]['flag_control_position_enabled'] = False
                logged.pop()
                with self.assertRaisesRegex(ValueError,'No native execution log'):
                    audit.native_audit(root,result,data,matched,phases,[],originals)
                targets[0][1]['thrust_body'][2] = -.1
                with self.assertRaisesRegex(ValueError,'No distinct native attitude CDR'):
                    audit.native_audit(root,result,data,matched,phases,[],originals)

    def test_px4_real_mavlink_frame_crc_and_decode(self):
        from pymavlink.dialects.v20 import common
        encoder = common.MAVLink(None,srcSystem=22,srcComponent=1)
        msg = common.MAVLink_hil_actuator_controls_message(4000,[.5]*4+[0.]*12,128,0)
        raw = msg.pack(encoder)
        parsed = common.MAVLink(None).parse_buffer(raw)[0]
        packet = dict(protocol='MAVLink_HIL_ACTUATOR_CONTROLS', packet_hex=raw.hex(),
                      message=parsed.to_dict(), decoded_input16=[.5]*4+[0.]*12)
        values, time = audit.decode_packet(packet,'px4')
        self.assertEqual(time,4000); self.assertEqual(values[:4],[.5]*4)
        bad = bytearray(raw); bad[-1] ^= 1; packet['packet_hex']=bad.hex()
        with self.assertRaises(Exception): audit.decode_packet(packet,'px4')

    def test_full_fixed_windows_and_final_dwell(self):
        phases = {}; states = []
        event = event_for(CONFIG,'fixture',56000)
        for kind, origin, end in (('point',1.,11.),('circle',20.,44.),('disturbance',50.,67.)):
            phases['pid_'+kind+'_begin'] = dict(physical_start=origin,settle_s=CONFIG[kind]['settle_s'],measured_external_pid=True)
            phases['pid_'+kind+'_end'] = dict(physical_cursor=dict(final_time=end),measured_external_pid=True)
        phases['pid_disturbance_event_frozen'] = dict(event=event,physical_cursor=dict(final_time=56.))
        for i in range(1,67001):
            time=i/1000; kind='circle' if 20 <= time <= 44 else 'point'
            ref = audit.desired(CONFIG,kind,time-20)
            states.append(dict(time=time,position=ref['position_enu'],velocity=ref['velocity_enu'],attitude=(0,0,0)))
        metrics = audit.fixed_metrics(CONFIG,states,phases,event)
        self.assertEqual(metrics['point']['ticks'],4001); self.assertEqual(metrics['circle']['ticks'],12001)
        self.assertEqual(metrics['disturbance']['ticks'],11001)
        states[66500]['velocity']=(.301,0,0)
        with self.assertRaisesRegex(ValueError,'Fixed final recovery dwell'):
            audit.fixed_metrics(CONFIG,states,phases,event)

    def test_independent_equations_against_existing_controller(self):
        for stack in ('px4', 'arducopter'):
            loop = PIDLoop(CONFIG, stack, .5); loop.reset('test', 1.)
            integral = [0.]*3
            for i in range(1, 501):
                now = 1+i*.01
                state = PIDState((2+.1*math.sin(i), 3+.1*math.cos(i), 3.1), (.03,-.1,.2),
                                 tuple(audit.wire.q_from_euler(.08,-.12,.3)))
                ref = reference(CONFIG, 'circle' if i % 7 == 0 else 'point', i*.01)
                actual = loop.update(now, state, ref, active=True)
                expected, thrust = audit.recompute(CONFIG, asdict(state), asdict(ref), actual['dt_s'], integral, .5)
                self.assertTrue(all(audit.near(actual['output'][k], v) for k,v in expected.items() if k != 'controller'))
                self.assertTrue(audit.near(actual['normalized_collective'], thrust))
                integral = expected['integral']

    def test_analytic_hover_and_integral_reset(self):
        s = dict(position_enu=[2,3,3], velocity_enu=[0,0,0], attitude_flu_to_enu=[1,0,0,0])
        ref = audit.desired(CONFIG, 'point', 0)
        out, thrust = audit.recompute(CONFIG,s,ref,.02,[0,0,0],.5)
        self.assertEqual(out['force_enu_n'], [0,0,1.515*9.8]); self.assertEqual(thrust,.5)
        s['position_enu'][0] = 1.9
        ref['velocity_enu'] = [.1,0,0]
        out, _ = audit.recompute(CONFIG,s,ref,.02,[.5,.5,.5],.5)
        self.assertTrue(audit.near(out['integral'], [.002,0,0]))

    def test_bad_dt_and_quaternion(self):
        s = dict(position_enu=[2,3,3], velocity_enu=[0,0,0], attitude_flu_to_enu=[1,0,0,0])
        for dt in (0, -.01, .201, float('nan')):
            with self.assertRaises(ValueError): audit.recompute(CONFIG,s,audit.desired(CONFIG,'point',0),dt,[0]*3,.5)
        s['attitude_flu_to_enu'][0] = 2
        with self.assertRaises(ValueError): audit.recompute(CONFIG,s,audit.desired(CONFIG,'point',0),.02,[0]*3,.5)

    def test_exact_1000_ticks_and_retransmitted_packet(self):
        rows, packets, event, sha = physical_fixture()
        packets.insert(1, copy.deepcopy(packets[0]))
        _, _, result = audit.physics(rows, packets, event, sha, 'fixture', 'arducopter')
        self.assertEqual(result['applied_ticks'],1000)

    def test_physics_negative_mutations(self):
        base = physical_fixture()
        def mutations(rows, packets):
            return {
                'deleted_tick': lambda: rows.pop(100),
                'missing_terminal': lambda: rows.pop(),
                'wrong_run': lambda: rows[100].update(run_id='other'),
                'missing_input': lambda: rows[100].update(raw_actuator_packet=None),
                'false_disturbance': lambda: rows[2001].update(applied_input16=[.5]*4+[0.]*12),
                'one_tick_extra': lambda: rows[2000].update(disturbance_active=True),
                'changed_identity': lambda: rows[100].update(disturbance_event_sha256='0'*64),
                'changed_inactive_channel': lambda: rows[2001]['applied_input16'].__setitem__(15,.1),
                'duplicated_integrated_packet': lambda: rows[100].update(raw_actuator_packet=rows[99]['raw_actuator_packet']),
                'wrong_raw_bytes': lambda: packets[0].update(packet_hex='00'*40),
            }
        for name in mutations(*base[:2]):
            rows, packets, event, sha = copy.deepcopy(base)
            mutations(rows,packets)[name]()
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.physics(rows,packets,event,sha,'fixture','arducopter')

    def test_late_event(self):
        rows, packets, event, sha = physical_fixture()
        for row in rows[1:1502]: row['disturbance_event_sha256'] = None
        with self.assertRaisesRegex(ValueError,'Late event'): audit.physics(rows,packets,event,sha,'fixture','arducopter')

    def test_event_wrong_identity_and_budget(self):
        event, raw, _ = event_fixture()
        with self.assertRaises(ValueError): audit.event_check(event,raw,'other')
        event['multiplier'] = .98
        with self.assertRaises(ValueError): audit.event_check(event,raw,'fixture')

    def test_trace_public_state_reset_and_equations(self):
        rows, phases, result, data = trace_fixture()
        matched, counts = audit.trace_audit(CONFIG,rows,phases,result,.5,data)
        self.assertEqual(len(matched),3); self.assertEqual(sum(counts.values()),3)

    def test_trace_ros_float32_envelope_uses_wire_tolerance(self):
        rows, phases, result, data = trace_fixture()
        for row in rows:
            att = row['public_envelope']['command']['att_ref']
            row['public_envelope']['command']['att_ref'] = list(struct.unpack('<4f', struct.pack('<4f', *att)))
        audit.trace_audit(CONFIG, rows, phases, result, .5, data)
        rows[0]['public_envelope']['command']['att_ref'][3] += 2e-6
        with self.assertRaisesRegex(ValueError, 'envelope differs'):
            audit.trace_audit(CONFIG, rows, phases, result, .5, data)

    def test_trace_negative_mutations(self):
        mutations = {
            'false_pid': lambda r,p,d: r[0]['output']['force_enu_n'].__setitem__(0, 1),
            'bad_dt': lambda r,p,d: r[0].update(dt_s=.01),
            'wrong_epoch': lambda r,p,d: r[0].update(control_epoch='other'),
            'wrong_hover': lambda r,p,d: r[0].update(calibration=.531),
            'label_only_position': lambda r,p,d: d['/uav1/prometheus/v2/command'][0][1]['command'].update(move_mode=0),
            'missing_state': lambda r,p,d: d['/uav1/prometheus/v2/state'].clear(),
            'wrong_command_ack': lambda r,p,d: d['/uav1/prometheus/text_info'].clear(),
            'wrong_reference_clock': lambda r,p,d: r[0].update(reference_origin_physical_s=9),
            'missing_stage': lambda r,p,d: r.pop(),
            'wrong_integral_reset': lambda r,p,d: r[1]['output']['integral'].__setitem__(0,.5),
        }
        for name, mutate in mutations.items():
            rows, phases, result, data = trace_fixture(); mutate(rows,phases,data)
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.trace_audit(CONFIG,rows,phases,result,.5,data)

    def test_single_tick_physical_failure_despite_online_ok(self):
        states = [dict(time=i/1000, position=(2,3,3), velocity=(0,0,0), attitude=(0,0,0)) for i in range(1,11001)]
        phases = {'pid_point_begin': dict(physical_start=1.,settle_s=6., measured_external_pid=True),
                  'pid_point_end': dict(physical_cursor=dict(final_time=11.), measured_external_pid=True,
                                        metric=dict(online_ok=True))}
        states[7000]['position'] = (2.301,3,3)
        with self.assertRaisesRegex(ValueError,'point position budget at 7.001'):
            audit.fixed_metrics(CONFIG,states,phases,{})

    def test_observed_result_alone_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'result.json').write_text(json.dumps(dict(status='observed',run_id='fake',stack='px4',online_ok=True)))
            result = audit.audit(root)
            self.assertEqual(result['status'],'rejected'); self.assertIn('failure',result)


if __name__ == '__main__': unittest.main()
