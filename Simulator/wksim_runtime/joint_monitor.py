"""Read-only public state and raw DDS evidence for the formal joint supervisor."""
import json
import re
import time

from .task import valid_state


class JointMonitor:
    def __init__(self,node,directory,clock,*,write_probe=None):
        import rclpy
        from rclpy.serialization import serialize_message
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from wksim_msgs.msg import SessionState
        from prometheus_msgs.msg import TextInfo
        self.node,self.clock,self.ros,self.serialize=node,clock,rclpy,serialize_message
        self.sessions,self.received,self.subscriptions={},{},[]
        self.phase='starting'
        self.write_probe=write_probe
        self.log=(directory/'public-dds.jsonl').open('x',buffering=65536)
        for uid in (1,2):
            for suffix,cls in (('v2/state',SessionState),('text_info',TextInfo)):
                name=f'/uav{uid}/prometheus/{suffix}'
                self.subscriptions.append(node.create_subscription(cls,name,
                    lambda message,uid=uid,name=name:self.receive(uid,name,message),
                    QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT)))

    def receive(self,uid,name,message):
        now=time.monotonic()
        text=json.dumps(dict(topic=name,epoch=self.clock.epoch,tick=self.clock.tick,
            received_monotonic_s=now,cdr_hex=self.serialize(message).hex()),separators=(',',':'))+'\n'
        if self.write_probe: self.write_probe.write(self.log,'public-dds',text)
        else: self.log.write(text)
        if name.endswith('/v2/state'):
            old=self.sessions.get(uid)
            if (message.version!=1 or not re.fullmatch('[0-9a-f]{32}',message.control_epoch)
                    or message.state.uav_id!=uid or message.control.uav_id!=uid
                    or message.sequence<=0 or old is not None
                    and (old.control_epoch!=message.control_epoch or message.sequence<=old.sequence)):
                return
            self.sessions[uid],self.received[uid]=message,now

    def ready(self,run_id):
        now=time.monotonic()
        return all(uid in self.sessions and self.sessions[uid].run_id==run_id
            and self.sessions[uid].state.uav_id==uid and self.sessions[uid].control.uav_id==uid
            and valid_state(self.sessions[uid].state,uid)
            and 0<=now-self.sessions[uid].published_monotonic_s<=2
            and self.sessions[uid].source_received_valid
            and 0<=now-self.sessions[uid].source_received_monotonic_s<=2
            and 0<=now-self.received[uid]<=2 for uid in (1,2))

    def pump(self):
        self.ros.spin_once(self.node,timeout_sec=0)

    def can_pause(self,run_id):
        return self.ready(run_id) and all(self.sessions[uid].state.armed
            and self.sessions[uid].state.mode==mode
            and self.sessions[uid].control.control_state==self.sessions[uid].control.COMMAND_CONTROL
            and not self.sessions[uid].control.failsafe
            for uid,mode in ((1,'GUIDED'),(2,'OFFBOARD')))

    def close(self):
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)
        self.log.close()
