"""Pure extraction/clock boundary checks; live DDS evidence is tested separately."""
from pathlib import Path
import sys
from types import SimpleNamespace as Value
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from joint_clock_observer import ap_counter_recurrence, check_sample, extract


class ObserverBoundaryTests(unittest.TestCase):
    def test_source_fingerprint_is_not_for_duplicates_or_time_reversal(self):
        self.assertEqual(ap_counter_recurrence([.001, .002, .003]), [1000, 2000, 3000])
        for samples in ([0.0], [.001, .001], [.002, .001], [.001, float('nan')], [1.0]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                ap_counter_recurrence(samples)

    def test_ap_boot_header_must_agree_exactly(self):
        message = Value(time_boot_us=1234567, header=Value(stamp=Value(sec=1, nanosec=234567000)))
        self.assertEqual(extract('ap_clock', message), dict(stamp_us=1234567, header_ns=1234567000))
        message.header.stamp.nanosec += 1
        with self.assertRaisesRegex(ValueError, 'disagree'):
            extract('ap_clock', message)

    def test_future_and_regressed_clocks_are_not_receipt_lag(self):
        self.assertEqual(check_sample(dict(stamp_us=7988999), 8000, 7980000), 7988999)
        with self.assertRaisesRegex(ValueError, 'outside'):
            check_sample(dict(stamp_us=8000001), 8000)
        with self.assertRaisesRegex(ValueError, 'regressed'):
            check_sample(dict(stamp_us=7980000), 8000, 7988999)
        with self.assertRaises(ValueError):
            check_sample(dict(stamp_us=True), 1)

    def test_native_identity_and_armed_checks(self):
        for armed in (False, True):
            message = Value(system_id=22, arming_state=2 if armed else 1, ARMING_STATE_ARMED=2, timestamp=1000)
            value = extract('px4_status', message)
            if armed:
                with self.assertRaisesRegex(ValueError, 'armed'):
                    check_sample(value, 1)
            else:
                self.assertEqual(check_sample(value, 1), 1000)
        message.system_id = 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            extract('px4_status', message)


if __name__ == '__main__':
    unittest.main()
