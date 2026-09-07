"""Trace the real generated-message adapter without changing its decisions."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from rclpy.serialization import serialize_message, deserialize_message
from px4_msgs.msg import EstimatorStatusFlags
from prometheus_msgs.msg import UAVState
from rosidl_runtime_py.convert import message_to_ordereddict
from validation import test_prometheus_native as native_cases
from tools.debug_px4_native_state import install


class NativeTraceTests(unittest.TestCase):
    def scenario(self):
        fixture = native_cases.NativeTests()
        fixture.setUp()
        link = fixture.px
        output = [serialize_message(link.state(2))]
        fixture.now = 12.001
        for key in ('status', 'position', 'attitude', 'gps'):
            message = deepcopy(link.latest[key])
            if hasattr(message, 'timestamp_sample'):
                message.timestamp_sample = (message.timestamp_sample or message.timestamp)+1_000_000
            message.timestamp += 1_000_000
            link.receive(key, message)
        output.append(serialize_message(link.state(2)))
        estimator = deepcopy(link.latest['estimator'])
        estimator.timestamp += 1_000_000
        link.receive('estimator', estimator)
        output.append(serialize_message(link.state(2)))
        link.receive('estimator', deepcopy(estimator))
        output.append(serialize_message(link.state(2)))
        self.assertTrue(all(not pub.messages for pub in link.publishers.values()))
        return output

    def test_same_state_fields_and_exact_stale_source(self):
        baseline = self.scenario()
        def fields(values):
            # CDR alignment bytes are unspecified; compare every actual field,
            # retaining invalid NaN values rather than introducing a tolerance.
            return [json.dumps(message_to_ordereddict(deserialize_message(raw,UAVState)),
                               sort_keys=True,allow_nan=True) for raw in values]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'trace.jsonl'
            close = install(path)
            try:
                self.assertEqual(fields(self.scenario()), fields(baseline))
            finally:
                close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            states = [row for row in rows if row['kind']=='state_transition']
            self.assertEqual([row['odom_valid'] for row in states], [True, False, True])
            invalid = states[1]
            self.assertTrue(invalid['connected'])
            check = next(row for row in invalid['checks'] if 'estimator' in row['keys'])
            self.assertFalse(check['result'])
            self.assertAlmostEqual(check['ages_s']['estimator'], 2.001)
            self.assertEqual(check['stale_seconds'], 2.0)
            ages = {key:age for evaluated in invalid['checks'] for key,age in evaluated['ages_s'].items()}
            for key in ('status','position','attitude','gps'):
                self.assertEqual(ages[key], 0)
            estimator = deserialize_message(bytes.fromhex(invalid['sources']['estimator']['cdr_hex']), EstimatorStatusFlags)
            self.assertTrue(estimator.cs_tilt_align and estimator.cs_yaw_align)
            rejected = [row for row in rows if row['kind']=='native_callback' and not row['accepted']]
            self.assertEqual(rejected[0]['latest_rejection']['reason'], 'duplicate_source')

    @unittest.skipUnless(os.environ.get('WK_TRACE_ROS')=='1', 'explicit isolated ROS check')
    def test_real_callback_records_native_publisher_identity(self):
        import rclpy
        from prometheus_control.native_px4 import PX4Link
        from prometheus_control.frames import topic
        rclpy.init(args=[])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'trace.jsonl'
            close = install(path)
            node = rclpy.create_node('wksim_native_trace_test')
            try:
                link = PX4Link(node, '/trace', 22, clock=lambda:10.)
                publisher = node.create_publisher(EstimatorStatusFlags,
                    topic('/trace', 'out', 'estimator_status_flags', EstimatorStatusFlags), 1)
                deadline = time.monotonic()+5
                while publisher.get_subscription_count()!=1:
                    if time.monotonic()>=deadline:
                        self.fail('Real native trace subscription not discovered')
                    rclpy.spin_once(node, timeout_sec=.02)
                publisher.publish(EstimatorStatusFlags(timestamp=1_000_000, cs_tilt_align=True, cs_yaw_align=True))
                while 'estimator' not in link.latest:
                    if time.monotonic()>=deadline:
                        self.fail('Real callback did not receive the estimator message')
                    rclpy.spin_once(node, timeout_sec=.02)
            finally:
                node.destroy_node()
                close()
                rclpy.shutdown()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows = [row for row in rows if row['kind']=='native_callback']
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]['accepted'])
            self.assertEqual(rows[0]['accepted_received_monotonic_s'], 10.)
            writers = rows[0]['publishers_discovered_after_callback']
            self.assertEqual(len(writers), 1)
            self.assertEqual(len(writers[0]['gid']), 48)
            self.assertNotEqual(int(writers[0]['gid'],16), 0)
            if 'publisher_gid' not in rows[0]['receipt']['available_message_info_keys']:
                self.assertIsNone(rows[0]['receipt']['publisher_gid'])


if __name__=='__main__':
    unittest.main()
