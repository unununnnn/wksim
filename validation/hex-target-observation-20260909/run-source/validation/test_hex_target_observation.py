"""Offline AP observation transport and source-representation regressions."""
import copy
import struct
import time
import json
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace as N

from pymavlink.dialects.v20 import common as mavlink
from Simulator.wksim_runtime.hex_task import HexTask
from tools import audit_hex_flight as audit


class ObservationTests(unittest.TestCase):
    def task(self, result=0, foreign=False, respond=True):
        task = object.__new__(HexTask)
        task.flight_stack, task.epoch, task.native_generation = 'arducopter', 'epoch', 7
        task.target_system, task.peer = 241, ('127.0.0.1', 17000)
        task.dialect, task.encoder = mavlink, mavlink.MAVLink(None, srcSystem=245, srcComponent=190)
        task.budget = {'parameter_read_timeout_s': .02}
        task.hex_result, task.mav_messages = {}, []
        task.ground_current = lambda: True
        task.cursor = lambda: {'final_time': 1.}
        task.task_time, task.pump = time.monotonic, lambda: None
        task.phase = lambda label: None
        events, sent = [], []
        task.record = lambda kind, **fields: events.append(dict(kind=kind, **fields))
        encoder = mavlink.MAVLink(None, srcSystem=241, srcComponent=1)
        def send(raw, peer):
            sent.append(mavlink.MAVLink(None).parse_buffer(raw)[0])
            if respond:
                msg = mavlink.MAVLink_command_ack_message(511, result, 0, 0, 245, 190)
                packet = msg.pack(encoder)
                task.mav_messages.append(dict(message=msg.to_dict(), packet_hex=packet.hex(),
                    source_system=242 if foreign else 241, source_component=1, peer=peer))
            return len(raw)
        task.channel = N(sendto=send)
        return task, sent, events

    def test_three_explicit_observation_requests_and_acks(self):
        task, sent, events = self.task()
        task.configure_target_observation()
        self.assertEqual([m.param1 for m in sent], [87, 85, 245])
        self.assertTrue(all(m.command == 511 and m.param2 == 100000 and
            (m.target_system,m.target_component)==(241,1) and m.confirmation==0 and
            [m.param3,m.param4,m.param5,m.param6,m.param7]==[0]*5 for m in sent))
        self.assertEqual(sum(r['kind']=='observation_interval_ack' for r in events),3)
        self.assertEqual(sum(r['kind']=='observation_interval_tx' for r in events),3)

    def test_allowlist_rejects_motion_and_unknown_message_ids(self):
        for message_id in (True, 0, 76, 84, 86, 400, 511):
            task,sent,_=self.task()
            with self.subTest(message_id=message_id), self.assertRaises(ValueError):
                task.request_observation_interval(message_id)
            self.assertEqual(sent,[])

    def test_denied_unsupported_foreign_and_missing_ack_fail(self):
        for result in (1,2,3,4):
            task,_,_=self.task(result=result)
            with self.subTest(result=result),self.assertRaises(RuntimeError):
                task.request_observation_interval(87)
        for options in ({'foreign':True},{'respond':False}):
            task,_,_=self.task(**options)
            with self.subTest(options=options),self.assertRaises(TimeoutError):
                task.request_observation_interval(87)
        task,_,_=self.task(result=5)
        with self.assertRaises(TimeoutError): task.request_observation_interval(87)

    def test_ground_identity_short_send_and_hard_deadline(self):
        task,sent,_=self.task()
        task.ground_current=lambda:False
        with self.assertRaises(RuntimeError): task.request_observation_interval(87)
        self.assertEqual(sent,[])
        task,_,events=self.task()
        task.channel.sendto=lambda *args:0
        with self.assertRaisesRegex(RuntimeError,'Incomplete'): task.request_observation_interval(87)
        self.assertEqual(events[0]['kind'],'observation_interval_tx')
        task,_,_=self.task()
        task.pump=lambda:time.sleep(.025)
        with self.assertRaises(TimeoutError): task.request_observation_interval(87)
        task,_,_=self.task()
        task.pump=lambda:setattr(task,'native_generation',8)
        with self.assertRaisesRegex(RuntimeError,'identity'): task.request_observation_interval(87)

    def test_new_landed_observation_required_and_px4_unchanged(self):
        task,sent,_=self.task()
        task.mav_messages=[dict(message=dict(mavpackettype='EXTENDED_SYS_STATE',landed_state=1),
            source_system=241,source_component=1,peer=task.peer)]
        with self.assertRaises(TimeoutError): task.wait_native_landed()
        task.pump=lambda:task.mav_messages.append(copy.deepcopy(task.mav_messages[0]))
        task.wait_native_landed()
        task.flight_stack='px4'
        task.configure_target_observation(); task.wait_native_landed()
        self.assertEqual(sent,[])

    def test_observation_audit_binds_encoded_requests_and_raw_ack(self):
        task,_,events=self.task()
        task.configure_target_observation()
        records=[]; messages=[]
        for i in range(3):
            tx=next(e for e in events if e['kind']=='observation_interval_tx' and e['message_id']==(87,85,245)[i])
            ack=next(e for e in events if e['kind']=='observation_interval_ack' and e['message_id']==(87,85,245)[i])
            records.extend([dict(tx,monotonic=1+i),dict(ack,monotonic=1.02+i)])
            messages.append(dict(task.mav_messages[i],monotonic=1.01+i))
        messages=json.loads(json.dumps(messages))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'hex-native.jsonl'
            path.write_text(''.join(json.dumps(r)+'\n' for r in records))
            result={'stack':'arducopter','protocol':{'parameter_read_timeout_s':10}}
            phases={'arming_completed':{'observed_monotonic_s':5},'public_control_ready':{'observed_monotonic_s':4}}
            self.assertEqual(audit.ap_observation_requests(Path(directory),result,messages,phases)['message_ids'],[87,85,245])
            messages[1]['message']['target_component']=191
            with self.assertRaises(ValueError): audit.ap_observation_requests(Path(directory),result,messages,phases)


def receipts_fixture():
    home=dict(time_boot_us=52280000,home_latitude_e7=401540302,
              home_longitude_e7=1162593683,home_altitude_cm=4997)
    def target(stamp,lat,lon):
        return dict(header=dict(frame_id='map',stamp=dict(sec=int(stamp),nanosec=round(stamp%1*1e9))),
            latitude=lat,longitude=lon,altitude=3.,yaw=0.,coordinate_frame=6,type_mask=0x9f8)
    data={'/ap/cmd_gps_pose':[(dict(monotonic=573.9),target(52.280,40.1540302,116.2593683)),
                            (dict(monotonic=574.154),target(52.316,40.1540571,116.2593918))],
          '/ap/wksim/local_state_v1':[({},home),({},dict(home,time_boot_us=52316000))]}
    phases={'waypoint_accepted':dict(observed_monotonic_s=574.128,native_boot_s=52.294),
            'land_accepted':dict(observed_monotonic_s=578.668,native_boot_s=56.831)}
    messages=[dict(monotonic=550.,message=dict(mavpackettype='GPS_GLOBAL_ORIGIN',
        latitude=401540302,longitude=1162593683,altitude=50000))]
    messages += [dict(monotonic=574.2,message=dict(mavpackettype='POSITION_TARGET_GLOBAL_INT',
        time_boot_ms=52350,coordinate_frame=0,type_mask=0xfff8,lat_int=401540570,lon_int=1162593917,
        alt=52.96999740600586)),dict(monotonic=574.21,message=dict(mavpackettype='POSITION_TARGET_LOCAL_NED',
        time_boot_ms=52360,coordinate_frame=1,type_mask=0xff8,x=2.9944770336151123,
        y=1.9994386434555054,z=-2.9700000286102295))]
    def guip(t,x,y):
        return dict(TimeUS=t,Type=2,pX=x,pY=y,pZ=300.,Terrain=0,
            vX=0.,vY=0.,vZ=0.,aX=0.,aY=0.,aZ=0.)
    guided=[guip(52304000,401540288.,1162593664.),guip(52331000,401540576.,1162593920.)]
    return data,messages,phases,guided


class TargetReceiptsTests(unittest.TestCase):
    def test_global_log_representation_roundtrip_and_legitimate_prior_target(self):
        value=audit.ap_target_receipts(*receipts_fixture())
        self.assertEqual(value['preceding_guip_targets'],1)
        self.assertEqual(value['new_goal_guip_targets'],1)
        self.assertEqual(value['global_receipts'],1)
        self.assertEqual(value['local_receipts'],1)

    def test_missing_unknown_old_after_new_and_wrong_numeric_representation_fail(self):
        for mutation in ('missing_global','missing_local','unknown','metres','old_after_new','wrong_alt','echo_e7'):
            data,messages,phases,guided=receipts_fixture()
            if mutation=='missing_global': messages.pop(1)
            elif mutation=='missing_local': messages.pop(2)
            elif mutation=='unknown': guided[1]['pX']+=1024
            elif mutation=='metres': guided[1].update(pX=3.,pY=2.,pZ=-3.)
            elif mutation=='old_after_new': guided.append(dict(guided[0],TimeUS=52400000))
            elif mutation=='wrong_alt': messages[1]['message']['alt']=52.97
            elif mutation=='echo_e7': messages[1]['message'].update(lat_int=401540571,lon_int=1162593918)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                audit.ap_target_receipts(data,messages,phases,guided)

    def test_old_global_after_new_guip_cannot_be_explained_by_old_dds(self):
        data,messages,phases,guided=receipts_fixture()
        stale=dict(messages[1],message=dict(messages[1]['message'],time_boot_ms=52340,
            lat_int=401540302,lon_int=1162593683))
        messages.insert(1,stale)
        with self.assertRaises(ValueError): audit.ap_target_receipts(data,messages,phases,guided)


if __name__=='__main__': unittest.main()
