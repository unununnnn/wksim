"""Unit checks for the bounded probe, not a substitute for real flight evidence."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_joint_clock import encoded, json_identity, step_request
from audit_joint_clock_probe import check_px_clock


class ProbeContractTests(unittest.TestCase):
    def test_only_next_integer_tick_is_admitted(self):
        commands = [0.0] * 16
        self.assertIs(step_request(dict(tick=1, commands=commands), 0), commands)
        for request in (None, {}, dict(tick=True, commands=commands), dict(tick=1.0, commands=commands),
                        dict(tick=0, commands=commands), dict(tick=2, commands=commands),
                        dict(tick=1, commands=commands, reset=True)):
            with self.subTest(request=request), self.assertRaises(ValueError):
                step_request(request, 0)
        with self.assertRaises(ValueError):
            step_request(dict(tick=1, commands=commands), 1)

    def test_nonfinite_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            encoded(dict(time=float('nan')))

    def test_raw_px_clock_regression_between_good_barriers_is_rejected(self):
        previous = check_px_clock(8000, 8000000, 7996000, False)
        with self.assertRaisesRegex(ValueError, 'regressed'):
            check_px_clock(8004, 7999000, previous, False)
        with self.assertRaisesRegex(ValueError, 'ahead'):
            check_px_clock(8004, 8005000, previous, False)
        self.assertEqual(check_px_clock(8004, 8004000, previous, False), 8004000)

    def test_each_paused_px_packet_must_match_the_pause_barrier(self):
        # Before/after snapshots alone would miss this stale middle packet.
        with self.assertRaisesRegex(ValueError, 'inside pause'):
            check_px_clock(8000, 7999000, None, True)
        self.assertEqual(check_px_clock(8000, 8000000, 8000000, True), 8000000)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux /proc identity')
    def test_identity_is_stable_and_uses_kernel_start_ticks(self):
        identity = json_identity(os.getpid())
        self.assertEqual(identity, json_identity(os.getpid()))
        self.assertGreater(identity['start_ticks'], 0)
        self.assertEqual(identity['pgid'], os.getpgid(0))
        self.assertNotIn('state', identity)
        self.assertIsNone(json_identity(2**30))


if __name__ == '__main__':
    unittest.main()
