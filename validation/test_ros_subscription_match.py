"""Opt-in real FastDDS matching, run only inside a private test namespace."""
import os
import unittest


@unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS') == '1',
                     'Requires explicitly isolated ROS test namespace')
class MatchingTests(unittest.TestCase):
    def test_actual_matching_differs_from_graph_and_requires_compatible_qos(self):
        import json
        import time
        import uuid
        import rclpy
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String
        from rclpy.serialization import serialize_message
        from tools.ros_subscription_match import MatchedPublishers
        self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
        rclpy.init()
        node = rclpy.create_node('wksim_match_test_' + uuid.uuid4().hex)
        received = []
        sub = node.create_subscription(String, '/wksim_match_test', received.append,
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE))
        counter = MatchedPublishers()
        evidence = dict(identity=counter.identity, observations=[])

        def wait(predicate):
            deadline = time.monotonic() + 5
            while not predicate():
                if time.monotonic() >= deadline:
                    self.fail('Actual ROS matching/receipt timed out')
                rclpy.spin_once(node, timeout_sec=0.01)

        def observe(stage):
            evidence['observations'].append(dict(stage=stage,
                graph=node.count_publishers(sub.topic_name), matched=counter.count(sub)))

        try:
            self.assertEqual(counter.count(sub), 0)
            observe('absent')
            bad = node.create_publisher(String, sub.topic_name,
                QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT))
            wait(lambda: node.count_publishers(sub.topic_name) == 1)
            end = time.monotonic() + 0.5
            while time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.01)
                self.assertEqual(counter.count(sub), 0)
            observe('incompatible_publisher_graph_only')
            node.destroy_publisher(bad)
            wait(lambda: node.count_publishers(sub.topic_name) == 0)
            good = node.create_publisher(String, sub.topic_name, 10)
            wait(lambda: counter.count(sub) == 1)
            observe('compatible_actual_match')
            good.publish(serialize_message(String(data='real native transport sample')))
            wait(lambda: len(received) == 1)
            self.assertEqual(received[0].data, 'real native transport sample')
            node.destroy_publisher(good)
            wait(lambda: counter.count(sub) == 0)
            observe('publisher_removed')
            print(json.dumps(evidence), flush=True)
        finally:
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
