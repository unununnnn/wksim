"""Opt-in real ROS graph check in an isolated DDS domain; no SITL or messages sent."""
import os
import time
import unittest


@unittest.skipUnless(os.getenv('WKSIM_RUN_ROS_DISCOVERY_TEST')=='1','Explicit isolated DDS test only')
class ActualPublisherDiscovery(unittest.TestCase):
    def test_real_writer_gid_and_silent_second_publisher(self):
        import rclpy
        from std_msgs.msg import String
        from Simulator.wksim_runtime.aruco_publisher_guard import ArucoPublisherGuard
        self.assertEqual(os.environ.get('ROS_DOMAIN_ID'),'213')
        rclpy.init()
        nodes=[]
        try:
            owner=rclpy.create_node('wksim_joint_px4_control');nodes.append(owner)
            observer=rclpy.create_node('wksim_guard_discovery_test');nodes.append(observer)
            topic='/wksim_guard_test/native_target'
            owner.create_publisher(String,topic,10)
            def wait_count(count):
                deadline=time.monotonic()+5
                while len(observer.get_publishers_info_by_topic(topic)) != count:
                    if time.monotonic()>deadline: self.fail('DDS discovery timeout')
                    rclpy.spin_once(observer,timeout_sec=.02)
            wait_count(1)
            guard=ArucoPublisherGuard(observer,'px4',{topic:'std_msgs/msg/String'})
            first=guard.snapshot()
            self.assertEqual(first['topics'][topic]['publisher_count'],1)
            gid=observer.get_publishers_info_by_topic(topic)[0].endpoint_gid
            self.assertTrue(guard.validate_sample(topic,bytes(gid)))
            self.assertEqual(first['topics'],guard.snapshot()['topics'])
            silent=rclpy.create_node('wksim_guard_silent_writer');nodes.append(silent)
            silent.create_publisher(String,topic,10)  # Deliberately never publish.
            wait_count(2)
            with self.assertRaisesRegex(ValueError,'multiple publishers'):guard.snapshot()
        finally:
            for node in reversed(nodes):node.destroy_node()
            rclpy.shutdown()


if __name__=='__main__':unittest.main()
