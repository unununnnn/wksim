"""Actual installed Node/TCP/helper integration with synthetic ROS inputs; no FC."""
import json
import hashlib
import shutil
import importlib.util
import os
from pathlib import Path
import sys
import time

import rclpy
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock
from wksim_msgs.msg import SessionState, SetupRequest, CommandRequest
from prometheus_msgs.msg import TextInfo, UAVControlState

# Keep the sealed Simulator package first. Only the experiment helper lives in tools.
repo = Path(__file__).resolve().parents[1]
sys.path.append(str(repo))
from tools.planner_release_handoff import handoff_and_release, prepare_planner
import Simulator.wksim_runtime.planner_command_egress as egress


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(exist_ok=False, parents=True)
    prefix = Path(sys.argv[2]).resolve()
    if not Path(egress.__file__).resolve().is_relative_to(prefix):
        raise RuntimeError('Fixture did not import sealed Simulator')
    sources = [repo/'tools/planner_release_handoff.py', Path(__file__).resolve(),
               Path(importlib.util.find_spec('Simulator.wksim_runtime.planner_transport_node').origin),
               Path(egress.__file__)]
    hashes = {}
    for index, source in enumerate(sources):
        data=source.read_bytes()
        hashes[str(source)]=hashlib.sha256(data).hexdigest()
        snapshot=output/'sources'/str(index)/source.name
        snapshot.parent.mkdir(parents=True,exist_ok=True)
        snapshot.write_bytes(data)
    rclpy.init(args=[])
    report = dict(scope='synthetic ROS input, actual installed Node and TCP helper only',
                  physical_acceptance=False, native_ack_is_synthetic=True,
                  fixture_module_path=egress.__file__, source_sha256=hashes,
                  namespaces={name:os.readlink('/proc/self/ns/'+name) for name in ('net','ipc','mnt')})
    driver = None
    try:
        driver = Driver(output)
        if len(sys.argv)>3 and sys.argv[3]=='prewarm':
            driver.freeze_clock=True
            driver._prepared_planner_handoff=prepare_planner(driver,output=output/'handoff',
                environment=dict(os.environ),mode='BRAKE',expected_native_mode='BRAKE')
            prepared=driver._prepared_planner_handoff
            assert driver.task_time()==0
            assert prepared.record['timestamps']['warm_ready_ros_ns']==0
            assert 'wksim_planner_transport' not in driver.node.get_node_names()
            report['prewarm_at_clock_zero']=True
            report['node_absent_before_activation']=True
            driver.freeze_clock=False
        deadline = time.monotonic()+8
        while driver.task_time()==0:
            if time.monotonic()>deadline: raise TimeoutError('ROS fixture clock not initialized')
            driver.pump()
        report['handoff'] = handoff_and_release(driver, output=output/'handoff',
              environment=dict(os.environ), mode='BRAKE', expected_native_mode='BRAKE')
        if driver.requests != [30] or driver.commands:
            raise AssertionError(('unexpected public output',driver.requests,driver.commands))
        if driver.request_id != 30 or driver.command_id != 17:
            raise AssertionError('Fixture counters changed unexpectedly')
        report.update(status='pass',setup_request_ids=driver.requests,command_outputs=len(driver.commands))
    except BaseException as exc:
        report.update(status='failed',error=repr(exc))
        raise
    finally:
        if driver is not None:
            prepared=getattr(driver,'_prepared_planner_handoff',None)
            if prepared is not None:prepared.close_prepared()
            driver.node.destroy_node()
        rclpy.shutdown()
        report['source_unchanged'] = all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha for name,sha in hashes.items())
        if not report['source_unchanged']:report['status']='failed'
        (output/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


class Driver:
    protocol='session_v1'
    active=True
    pending_request_id=None
    use_sim_time=True
    uav_id=1
    run_id='handoff-installed-fixture'
    epoch='b'*32
    topic_root='/uav1/prometheus/'
    command_id=17
    request_id=29

    def __init__(self, output):
        self.directory=output
        self.started=time.monotonic()
        self.sequence=0
        self.freeze_clock=False
        self.requests=[]
        self.commands=[]
        self.node=rclpy.create_node('release_helper_fixture', parameter_overrides=[Parameter('use_sim_time',value=True)])
        self.clock=self.node.create_publisher(Clock,'/clock',10)
        self.state_pub=self.node.create_publisher(SessionState,self.topic_root+'v2/state',10)
        self.events=self.node.create_publisher(TextInfo,self.topic_root+'text_info',10)
        self.subscriptions=[self.node.create_subscription(SetupRequest,self.topic_root+'v2/setup',self.setup,10),
                            self.node.create_subscription(CommandRequest,self.topic_root+'v2/command',self.commands.append,10)]

    def setup(self,message):
        if (message.run_id,message.control_epoch,message.request_id,message.setup.px4_mode)!=(self.run_id,self.epoch,30,'BRAKE'):
            raise AssertionError('Unexpected actual SetupRequest identity or mode')
        self.requests.append(message.request_id)
        self.request_id=message.request_id
        for kind,fields in [('native_ack',dict(accepted=True,stage='simple')),
                            ('setup_completed',dict(action='mode',value='BRAKE',native_mode='BRAKE'))]:
            self.events.publish(TextInfo(message_type=TextInfo.INFO,message=json.dumps(dict(
                version=1,run_id=self.run_id,control_epoch=self.epoch,request_id=message.request_id,event=kind,**fields))))

    def task_time(self):
        return self.node.get_clock().now().nanoseconds/1e9

    def fresh(self):
        return True  # Explicit synthetic fixture state, never a flight admission.

    def pump(self):
        now=time.monotonic()
        if now-self.started>25: raise TimeoutError('Fixture wall watchdog')
        ns=0 if self.freeze_clock else (1000+int((now-self.started)*1000))*1000000
        clock=Clock()
        clock.clock.sec,clock.clock.nanosec=divmod(ns,1000000000)
        self.clock.publish(clock)
        self.sequence+=1
        state=SessionState(version=1,run_id=self.run_id,control_epoch=self.epoch,sequence=self.sequence,
                           last_request_id=self.request_id,command_high_water=self.command_id,
                           source_received_valid=True,source_received_monotonic_s=now,published_monotonic_s=now)
        state.state.uav_id=state.control.uav_id=1
        state.state.connected=state.state.odom_valid=True
        state.state.header.frame_id='map'
        state.state.header.stamp.sec,state.state.header.stamp.nanosec=divmod(ns,1000000000)
        state.control.control_state=UAVControlState.COMMAND_CONTROL
        self.state_pub.publish(state)
        rclpy.spin_once(self.node,timeout_sec=.01)


if __name__=='__main__':main()
