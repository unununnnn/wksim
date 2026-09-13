"""Real Humble DDS metadata test, no flight controllers or native commands."""
import json
import time
import unittest
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from prometheus_control.rc_transport import RCTake

class RCTransportTests(unittest.TestCase):
    def test_two_real_writer_gids_and_exact_cdr(self):
        rclpy.init()
        reader = rclpy.create_node('rc_transport_reader')
        writer = rclpy.create_node('rc_transport_writer')
        try:
            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
            sub = reader.create_subscription(String, '/wksim/test_rc_gid', lambda _: None, qos)
            pubs = [writer.create_publisher(String, '/wksim/test_rc_gid', qos) for _ in range(2)]
            take = RCTake()
            deadline = time.monotonic()+5
            while any(pub.get_subscription_count() != 1 for pub in pubs):
                if time.monotonic() > deadline: self.fail('DDS discovery timeout')
                time.sleep(.02)
            seen = {}
            while len(seen) < 2 and time.monotonic() < deadline:
                for i, pub in enumerate(pubs): pub.publish(String(data=json.dumps({'writer': i})))
                time.sleep(.03)
                for _ in range(20):
                    sample = take.take(sub)
                    if sample is None: break
                    msg, info = sample
                    seen[json.loads(msg.data)['writer']] = info.publisher_gid
                    self.assertTrue(info.cdr_hex)
            self.assertEqual(len(seen), 2)
            self.assertNotEqual(seen[0], seen[1])
            discovery = {bytes(p.endpoint_gid) for p in reader.get_publishers_info_by_topic(sub.topic_name)}
            self.assertEqual(set(seen.values()), discovery)
        finally:
            writer.destroy_node(); reader.destroy_node(); rclpy.shutdown()

if __name__ == '__main__': unittest.main()
