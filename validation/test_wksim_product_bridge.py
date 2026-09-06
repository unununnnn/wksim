"""Real loopback receive-before-first-state regression, including Windows Winsock."""
import io
import unittest
from unittest.mock import patch

from Simulator.ue55.product_bridge import bridge, display_packet
from Simulator.wksim_core.state_stream import METADATA


class EmptyRelay:
    def __init__(self):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(b'{"packet":null,"relay_wall_time_s":1000}\n')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stdin.close()
        self.stdout.close()

    def wait(self, timeout):
        return 0


class ProductBridgeTest(unittest.TestCase):
    def test_clock_offset_is_not_source_age_and_slow_transport_still_expires(self):
        packet = dict(METADATA, version=2, run_id='clock-test', vehicle_id=1, sequence=1,
                      source_wall_time_s=1000., sim_time_s=12., position_ned_m=[1, 2, -3],
                      quaternion_wxyz=[1, 0, 0, 0], rotor_rpm=[1, 2, 3, 4])
        envelope = dict(packet=packet, relay_wall_time_s=1000.1)
        for host_clock in (3., 10000., 1e9):
            output = display_packet(envelope, 'clock-test', 1, .05, host_clock)
            self.assertEqual(output['source_wall_time_s'], 1000.)
            self.assertEqual(output['sim_time_s'], 12.)
            self.assertAlmostEqual(output['display_wall_time_s'], host_clock-.15)
        with self.assertRaisesRegex(ValueError, 'Expired'):
            display_packet(envelope, 'clock-test', 1, .7, 10000.)
        with self.assertRaisesRegex(ValueError, 'Expired'):
            display_packet(envelope, 'clock-test', 1, 1, 10000.)

    def test_no_state_yet_does_not_recv_on_unbound_windows_socket(self):
        with patch('subprocess.CREATE_NO_WINDOW', 0, create=True), \
                patch('subprocess.Popen', return_value=EmptyRelay()):
            with self.assertRaisesRegex(ConnectionError, 'relay exited'):
                bridge('/unused', '/tmp/unused/state.sock', 'no-state-yet')


if __name__ == '__main__':
    unittest.main()
