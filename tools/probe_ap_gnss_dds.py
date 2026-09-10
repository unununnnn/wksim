"""Read-only DDS observation during the scheduled native ground GNSS probe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from probe_ap_gnss_schedule import run


class Observer:
    def __init__(self,out):
        import rclpy
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from ardupilot_msgs.msg import WksimState,Status
        from prometheus_control.rc_transport import RCTake
        from rosidl_runtime_py.convert import message_to_ordereddict
        if os.environ.get('ROS_DOMAIN_ID')!='77' or os.environ.get('ROS_LOCALHOST_ONLY')!='1':
            raise ValueError('Ground DDS requires private domain77/localhost')
        self.agent=self.node=self.raw=self.log=None;self.ros=rclpy
        self.convert=message_to_ordereddict;self.take=RCTake()
        binary='/root/wksim-dds-VxM6Ni/ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent'
        self.identity=dict(agent_binary=binary,agent_sha256=hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
                           topics=['/ap/status','/ap/wksim/local_state_v1'],observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        try:
            self.log=(out/'agent.log').open('x')
            self.agent=subprocess.Popen([binary,'udp4','-p','12019','-v','4'],stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
            self.identity['pid']=self.agent.pid
            rclpy.init();self.node=rclpy.create_node('wksim_gnss_ground_observer')
            self.raw=(out/'dds.jsonl').open('x',buffering=1)
            qos=QoSProfile(depth=1000,reliability=ReliabilityPolicy.BEST_EFFORT)
            self.subs=[self.node.create_subscription(cls,topic,lambda _:None,qos)
                for cls,topic in ((Status,'/ap/status'),(WksimState,'/ap/wksim/local_state_v1'))]
        except Exception:
            self.close();raise

    def poll(self):
        if self.agent.poll() is not None:raise RuntimeError('DDS Agent exited during ground observation')
        for sub in self.subs:
            for _ in range(100):
                value=self.take.take(sub)
                if value is None:break
                message,info=value
                self.raw.write(json.dumps(dict(topic=sub.topic_name,monotonic_ns=time.monotonic_ns(),
                    cdr_hex=info.cdr_hex,publisher_gid=info.publisher_gid.hex(),
                    source_timestamp=info.source_timestamp,received_timestamp=info.received_timestamp,
                    message=self.convert(message)))+'\n')
            else:raise RuntimeError('Ground DDS recorder did not drain')

    def close(self):
        if self.raw is not None and not self.raw.closed:self.raw.close()
        if self.node is not None:self.node.destroy_node();self.node=None
        if self.ros.ok():self.ros.shutdown()
        if self.agent is not None:
            if self.agent.poll() is None:self.agent.terminate()
            try:self.agent.wait(timeout=5)
            except subprocess.TimeoutExpired:self.agent.kill();self.agent.wait(timeout=5)
            self.identity['returncode']=self.agent.returncode
        if self.log is not None:self.log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('build',type=Path);parser.add_argument('out',type=Path)
    args=parser.parse_args();run(args.build.resolve(),args.out.resolve(),observer_factory=Observer)
