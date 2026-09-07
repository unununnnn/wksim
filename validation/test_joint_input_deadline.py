"""Deadline/queued-packet unit checks using real socket bytes, not flight proof."""
import socket
import unittest
from unittest.mock import patch

from Simulator.wksim_core.ap_json import SERVO_PACKET
from Simulator.wksim_core.joint import JointPhysics,InputTimeout
from Simulator.wksim_runtime.scene_clock import SceneClock


class InputDeadlineTests(unittest.TestCase):
    def physics(self):
        value=object.__new__(JointPhysics)
        value.health=lambda:None
        value.record=lambda *args,**kwargs:None
        value.peer=None;value.px_time=4000;value.px_commands=[0.]*16
        value.pending_ap=dict(frame=4,commands=[0.]*16)
        return value

    def clock(self,total):
        clock=SceneClock('a'*32)
        for tick in range(1,total+1):
            clock.begin_step()
            state=[0.]*120;state[2]=tick/1000;state[60]=tick*1000
            clock.commit({name:dict(version=1,epoch=clock.epoch,tick=tick,state=state) for name in clock.VEHICLES})
            if tick<total or total%4==0:clock.acknowledge_ap(tick)
            if tick%4==0 and tick<total:clock.barrier(tick,tick*1000,True)
        clock.suspend_input('test input deadline')
        return clock

    def test_select_ready_after_deadline_does_not_consume_packet(self):
        p=self.physics()
        reader,writer=socket.socketpair()
        with reader,writer:
            writer.sendall(b'x')
            with patch('Simulator.wksim_core.joint.time.monotonic',side_effect=[0.,5.]):
                with self.assertRaises(InputTimeout):p.wait_readable(reader,5.,'px4')
            self.assertEqual(reader.recv(1),b'x')

    def test_ap_packet_parsed_after_deadline_is_held_for_explicit_repair(self):
        p=self.physics();now=[0.]
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver,\
             socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
            receiver.bind(('127.0.0.1',0));sender.sendto(SERVO_PACKET.pack(18458,1000,5,*([1500]*16)),receiver.getsockname())
            p.ap=receiver;p.record=lambda *args,**kwargs:now.__setitem__(0,5.)
            with patch('Simulator.wksim_core.joint.time.monotonic',side_effect=lambda:now[0]):
                with self.assertRaises(InputTimeout):p.wait_ap(4,deadline=5.)
            self.assertEqual(p.pending_ap['frame'],5)
            p.clock=self.clock(5)
            p.inflight=dict(tick=5,ap_source_frame=4,px4_source_time_us=4000,model_ticks={name:5 for name in p.clock.VEHICLES})
            p.wait_ap=lambda *args: self.fail('Must use the held actual ACK')
            p.finish_inputs(recovering=True)
            self.assertEqual((p.clock.tick,p.clock.phase,p.clock.input_pending),(5,'faulted',False))

    def test_px4_packet_parsed_after_deadline_is_held_for_explicit_repair(self):
        from pymavlink.dialects.v20 import common
        p=self.physics();now=[0.];p.clock=self.clock(8)
        p.pending_ap=dict(frame=8,commands=[0.]*16)
        p.inflight=dict(tick=8,ap_source_frame=7,px4_source_time_us=4000,model_ticks={name:8 for name in p.clock.VEHICLES})
        encoder=common.MAVLink(None)
        packet=encoder.hil_actuator_controls_encode(8000,[.5]*16,0,flags=1).pack(encoder)
        reader,writer=socket.socketpair()
        with reader,writer:
            writer.sendall(packet);p.connection=reader;p.protocol=common.MAVLink(None)
            p.record=lambda *args,**kwargs:now.__setitem__(0,5.)
            with patch('Simulator.wksim_core.joint.time.monotonic',side_effect=lambda:now[0]):
                with self.assertRaises(InputTimeout):p.wait_px4(deadline=5.)
            self.assertEqual(p.px_time,8000)
            p.wait_px4=lambda *args: self.fail('Must use the held actual ACK')
            p.finish_inputs(recovering=True)
            self.assertEqual((p.clock.tick,p.clock.phase,p.clock.input_pending),(8,'faulted',False))


if __name__=='__main__':unittest.main()
