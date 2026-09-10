"""Real DDS observer wiring, no FC or flight commands."""
import os
from pathlib import Path
import tempfile
import time
import unittest


@unittest.skipUnless(os.environ.get('WKSIM_GNSS_ROS_TESTS')=='1','isolated ROS test environment required')
class ObserverTests(unittest.TestCase):
    def test_px4_gps_uses_actual_native_vehicle_gps_position_topic(self):
        import rclpy
        from px4_msgs.msg import SensorGps
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from prometheus_control.frames import topic
        from Simulator.wksim_runtime.gnss_task import GNSSTask
        rclpy.init();task=writer=None
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'truth.jsonl').write_text('')
                task=GNSSTask(root,lambda:None,lambda _:None,'px4',scene_epoch='b'*32,
                              run_id='a'*32,protocol='session_v1')
                writer=rclpy.create_node('gnss_observer_fixture')
                pub=writer.create_publisher(SensorGps,topic('/wksim_px4_21','out','vehicle_gps_position',SensorGps),
                                           QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT))
                deadline=time.monotonic()+5;stamp=1000000
                while 'gps' not in task.native_rows and time.monotonic()<deadline:
                    pub.publish(SensorGps(timestamp=stamp,fix_type=3,satellites_used=10));stamp+=100000
                    task.pump()
                self.assertIn('gps',task.native_rows)
                self.assertTrue(task.native_fresh('gps'))
                task.close();task=None
        finally:
            if task is not None:task.close()
            if writer is not None:writer.destroy_node()
            if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':unittest.main()
