"""Identity, clock and actual nonblocking datagram tests; not flight evidence."""
import copy
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from Simulator.wksim_core.state_stream import METADATA
from Simulator.wksim_core.joint_state_stream import LatestJointState,JointStateWriter,validate
from Simulator.ue55.product_bridge import display_packet


def packet():
    return dict(METADATA,version=3,kind='joint_state',run_id='joint-test',instance_id='a'*32,epoch='b'*32,
        generation=1,sequence=1,step=4,sim_time_ns=4_000_000,phase='running',source_wall_time_s=100,
        vehicles=[dict(vehicle_id=uid,stack=stack,position_ned_m=[0,0,-3],quaternion_wxyz=[1,0,0,0],
                       rotor_rpm=[100,200,300,400],model_time_s=.004)
                  for uid,stack in ((1,'arducopter'),(2,'px4'))])


class JointStateTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','Linux publisher setup path')
    def test_optional_socket_setup_failure_is_observable_and_nonfatal(self):
        with patch('Simulator.wksim_core.joint_state_stream.socket.socket',side_effect=OSError('descriptor exhausted')):
            writer=JointStateWriter('/tmp/joint-test/state.sock','joint-test','a'*32,'b'*32,1)
        self.assertIsNone(writer.socket)
        self.assertIn('descriptor exhausted',writer.setup_error)
        self.assertFalse(writer.emit({},0,'faulted',force=True))
        writer.close()

    def test_retired_generations_and_pause_have_separate_guards(self):
        latest=LatestJointState('joint-test','a'*32);first=packet()
        self.assertTrue(latest.accept(json.dumps(first),now=100))
        paused=dict(first,sequence=2,phase='paused')
        self.assertTrue(latest.accept(json.dumps(paused),now=100))
        self.assertFalse(latest.accept(json.dumps(first),now=100))
        reset=copy.deepcopy(first);reset.update(epoch='c'*32,generation=2,sequence=0,step=0,sim_time_ns=0)
        for item in reset['vehicles']:item['model_time_s']=0
        partial=dict(reset,vehicles=reset['vehicles'][:1])
        self.assertFalse(latest.accept(json.dumps(partial),now=100))
        self.assertTrue(latest.accept(json.dumps(reset),now=100))
        self.assertFalse(latest.accept(json.dumps(paused),now=100))
        self.assertEqual(latest.packet['epoch'],'c'*32)

    def test_rejection_does_not_mutate_current_scene(self):
        latest=LatestJointState('joint-test','a'*32);first=packet()
        self.assertTrue(latest.accept(json.dumps(first),now=100))
        changes=[dict(instance_id='c'*32),dict(run_id='foreign'),dict(epoch='d'*32),dict(sequence=True),
                 dict(sim_time_ns=4000001),dict(position_frame='ENU'),dict(source_wall_time_s=98),dict(extra=1)]
        for fields in changes:
            with self.subTest(fields=fields):
                value=dict(first,sequence=2);value.update(fields)
                self.assertFalse(latest.accept(json.dumps(value),now=100))
                self.assertEqual(latest.packet,first)
        for field,value in (('vehicle_id',2),('model_time_s',.005),('quaternion_wxyz',[0,0,0,0]),
                            ('rotor_rpm',[0,float('nan'),0,0]),('position_ned_m',[0,0,'3'])):
            changed=copy.deepcopy(first);changed['sequence']=2;changed['vehicles'][0][field]=value
            self.assertFalse(latest.accept(json.dumps(changed),now=100))
        raw=json.dumps(first).replace('"sequence": 1','"sequence": 2,"sequence": 3')
        self.assertFalse(latest.accept(raw,now=100))
        self.assertEqual(latest.packet,first)

    def test_display_clock_mapping_keeps_original_authoritative_clocks(self):
        original=packet()
        mapped=display_packet(dict(packet=original,relay_wall_time_s=100.1),'joint-test','a'*32,
                              .05,1000000,validator=validate)
        self.assertEqual({k:v for k,v in mapped.items() if k in original},original)
        self.assertAlmostEqual(mapped['transport_age_bound_s'],.15)
        self.assertAlmostEqual(mapped['display_wall_time_s'],999999.85)
        self.assertEqual(len(mapped),22)
        with self.assertRaises(ValueError):
            display_packet(dict(packet=original,relay_wall_time_s=100.7),'joint-test','a'*32,.1,1000000,validator=validate)

    @unittest.skipUnless(sys.platform=='linux','Real Linux Unix datagram backpressure')
    def test_missing_and_full_receiver_do_not_queue_or_wait(self):
        with tempfile.TemporaryDirectory(prefix='joint-view-') as name:
            path=str(Path(name)/'state.sock')
            state=[0.0]*120;state[2]=.004;state[12]=1;state[16:20]=[100,200,300,400]
            states={'arducopter':state,'px4':state}
            writer=JointStateWriter(path,'joint-test','a'*32,'b'*32,1)
            writer.socket.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4096)
            try:
                self.assertFalse(writer.emit(states,4,'running',force=True))
                with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as receiver:
                    receiver.bind(path);receiver.settimeout(1)
                    for _ in range(64):writer.emit(states,4,'paused',force=True)
                    self.assertGreater(writer.sent,0);self.assertGreater(writer.dropped,1)
                    raw=receiver.recv(8192);received=json.loads(raw)
                    validate(received,'joint-test','a'*32)
                    self.assertEqual(received['step'],4)
                    self.assertEqual(received['vehicles'][1]['rotor_rpm'],[100,200,300,400])
            finally:writer.close()


if __name__=='__main__':unittest.main()
