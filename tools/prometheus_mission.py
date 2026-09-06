"""Bounded SITL test client: ONLY Prometheus public setup/command topics.

Uses the diagnostic observer's existing ROS executor; never sends native FC
commands. Installed control node is a separate process, owned by the runner.
"""
import hashlib
import json
from pathlib import Path
import time

from prometheus_msgs.msg import UAVCommand as Cmd, UAVSetup, UAVState, UAVControlState, TextInfo
from rosidl_runtime_py.convert import message_to_ordereddict
import prometheus_control


class PrometheusMission:
    def __init__(self, node, result_dir, workspace, protocol='legacy_v1'):
        self.node = node
        self.protocol, self.run_id, self.epoch = protocol, result_dir.name, None
        self.request_id, self.session_sequence = 0, 0
        self.envelopes = []
        package = Path(prometheus_control.__file__).resolve().parent
        if not package.is_relative_to(workspace.resolve() / 'install'):
            raise RuntimeError(f'Expected installed control package under {workspace}, got {package}')
        self.implementation = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in package.glob('*.py')}
        self.started = time.monotonic()
        self.log = (result_dir/'prometheus.jsonl').open('x', encoding='utf-8', buffering=1)
        self.latest, self.events, self.sent = {}, [], []
        self.subscriptions = [node.create_subscription(cls, '/uav1/prometheus/'+key,
            lambda msg, key=key: self.receive(key, msg), 10) for key, cls in (
                ('state', UAVState), ('control_state', UAVControlState), ('text_info', TextInfo))]
        if protocol == 'session_v1':
            from wksim_msgs.msg import SetupRequest, CommandRequest, SessionState
            self.SetupRequest, self.CommandRequest = SetupRequest, CommandRequest
            self.subscriptions.append(node.create_subscription(SessionState, '/uav1/prometheus/v2/state', self.receive_session, 10))
            self.setup_pub = node.create_publisher(SetupRequest, '/uav1/prometheus/v2/setup', 1)
            self.command_pub = node.create_publisher(CommandRequest, '/uav1/prometheus/v2/command', 1)
        else:
            self.setup_pub = node.create_publisher(UAVSetup, '/uav1/prometheus/setup', 1)
            self.command_pub = node.create_publisher(Cmd, '/uav1/prometheus/command', 1)
        self.pending = None
        self.next_id = 1
        self.event_cursor = 0

    def record(self, **fields):
        self.log.write(json.dumps(dict(wall=time.monotonic()-self.started, **fields))+'\n')

    def receive(self, key, msg):
        self.latest[key] = msg
        self.record(topic='/uav1/prometheus/'+key, message=message_to_ordereddict(msg))
        if key == 'text_info':
            event = json.loads(msg.message)
            if self.protocol == 'legacy_v1' or (event.get('run_id') == self.run_id and event.get('control_epoch') == self.epoch):
                self.events.append(event)

    def receive_session(self, msg):
        self.record(topic='/uav1/prometheus/v2/state', message=message_to_ordereddict(msg))
        if msg.version != 1 or msg.run_id != self.run_id or len(msg.control_epoch) != 32:
            return
        if self.epoch is not None and self.epoch != msg.control_epoch:
            raise RuntimeError('Control epoch changed; explicitly start a new request scope')
        if msg.sequence <= self.session_sequence:
            return
        self.epoch, self.session_sequence = msg.control_epoch, msg.sequence
        self.latest['session_state'] = msg

    def ready(self):
        state = self.latest.get('state')
        return (state is not None and state.connected and state.odom_valid and
                self.setup_pub.get_subscription_count() and self.command_pub.get_subscription_count()
                and (self.protocol == 'legacy_v1' or self.epoch is not None))

    def send(self, msg):
        if self.pending is not None:
            raise RuntimeError('Mission test already awaits a Prometheus response')
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        self.pending = (len(self.events), msg)
        self.sent.append(message_to_ordereddict(msg))
        self.record(**{('published' if self.protocol == 'legacy_v1' else 'public_payload'): type(msg).__name__}, message=self.sent[-1])
        outgoing = msg
        if self.protocol == 'session_v1':
            if self.epoch is None:
                raise RuntimeError('Current control epoch is unknown')
            self.request_id += 1
            cls = self.SetupRequest if isinstance(msg, UAVSetup) else self.CommandRequest
            outgoing = cls(version=1, run_id=self.run_id, control_epoch=self.epoch, request_id=self.request_id,
                           **{('setup' if isinstance(msg, UAVSetup) else 'command'): msg})
            self.envelopes.append(message_to_ordereddict(outgoing))
            self.record(published=cls.__name__, message=self.envelopes[-1], request_envelope=True)
        (self.setup_pub if isinstance(msg, UAVSetup) else self.command_pub).publish(outgoing)

    def setup(self, **fields):
        self.send(UAVSetup(**fields))

    def move(self, *, yaw=0.0):
        self.send(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_POS, command_id=self.next_id,
                      position_ref=[2.0, 3.0, 3.0], yaw_ref=float(yaw)))
        self.next_id += 1

    def land(self):
        self.send(Cmd(agent_cmd=Cmd.LAND, command_id=self.next_id))
        self.next_id += 1

    def check_failure(self):
        for event in self.events[self.event_cursor:]:
            if event['event'] in ('setup_rejected', 'command_rejected', 'control_revoked'):
                raise RuntimeError(f'Prometheus node rejected/released control: {event}')
        self.event_cursor = len(self.events)

    def done(self):
        if self.pending is None:
            return True
        start, msg = self.pending
        for event in self.events[start:]:
            expected = 'setup_completed' if isinstance(msg, UAVSetup) else 'command_accepted'
            if (event['event'] == expected and (isinstance(msg, UAVSetup) or event['command_id'] == msg.command_id)
                    and (self.protocol == 'legacy_v1' or event.get('request_id') == self.request_id)):
                self.pending = None
                return True
        return False

    def report(self):
        return dict(scope='Public Prometheus setup/command input; installed native node; native DDS and MAVLink are independent state observers',
                    implementation_sha256=self.implementation, sent=self.sent, events=self.events,
                    protocol=self.protocol, run_id=self.run_id, control_epoch=self.epoch, request_envelopes=self.envelopes,
                    final={key: message_to_ordereddict(value) for key, value in self.latest.items() if key != 'text_info'})
