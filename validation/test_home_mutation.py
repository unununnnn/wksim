"""Packet tests for the single, explicitly authorized simulation home actor."""
import unittest
from unittest.mock import Mock

from pymavlink.dialects.v20 import common as mavlink
from Simulator.wksim_runtime.home_mutation import HomeMutation


class HomeMutationTests(unittest.TestCase):
    def test_int_packet_preserves_coordinates_and_has_only_one_request(self):
        actor = HomeMutation.__new__(HomeMutation)
        actor.peer, actor.request, actor.system_id = ('127.0.0.1', 14550), None, 22
        actor.poll = Mock()
        packets = []
        actor.write = lambda raw: packets.append(bytes(raw))
        actor.protocol = mavlink.MAVLink(actor, srcSystem=246, srcComponent=190)
        home = dict(latitude_deg=40.1540302, longitude_deg=116.2593683, alt_amsl_m=50.)
        request = actor.change(home)
        packet = mavlink.MAVLink(None).parse_buffer(packets[0])[0]
        self.assertEqual(packet.get_type(), 'COMMAND_INT')
        self.assertEqual((packet.command, packet.frame, packet.param1), (179, mavlink.MAV_FRAME_GLOBAL, 0.))
        self.assertEqual((packet.x, packet.y), (401540302, 1162593683))
        self.assertEqual((packet.get_srcSystem(), packet.get_srcComponent()), (246, 190))
        self.assertAlmostEqual(packet.z, 50.1, places=5)
        with self.assertRaisesRegex(ValueError, 'Only one'): actor.change(home)
        self.assertEqual(len(packets), 1)

    def test_no_unobserved_peer_or_unfrozen_delta(self):
        actor = HomeMutation.__new__(HomeMutation)
        actor.peer, actor.request = None, None
        home = dict(latitude_deg=40., longitude_deg=116., alt_amsl_m=50.)
        with self.assertRaisesRegex(ValueError, 'heartbeat'): actor.change(home)
        actor.peer = ('127.0.0.1', 14550)
        with self.assertRaisesRegex(ValueError, 'Frozen home'): actor.change(home, altitude_delta_m=10.)


if __name__ == '__main__': unittest.main()
