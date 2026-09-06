"""One two-FC input timeline; the caller owns processes, policy and publication.

Extracts the proven model/JSON/HIL handshakes from the ground probe for real
flight. It never sends task, arming or mode commands. Inputs are held between
their native updates; AP next-frame is not a control-calculation-complete ACK.
"""
import json
import select
import socket
import time

from .ap_json import decode_servos, sensor_message
from .px4_mavlink import Sender, actuator_commands, gps_arguments
from .worker import receive_worker


class JointPhysics:
    def __init__(self, stack, clock, workers, health, record):
        from pymavlink.dialects.v20 import common
        self.clock, self.workers = clock, workers
        self.health, self.record = health, record
        self.protocol_type = common.MAVLink
        self.ap = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        self.ap.bind(('127.0.0.1', 19002))
        self.ap.setblocking(False)
        self.listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(('127.0.0.1', 4581))
        self.listener.listen(1)
        self.listener.setblocking(False)
        self.stack = stack
        self.connection = self.peer = self.pending_ap = None
        self.px_time = None
        self.px_commands = [0.0]*16
        self.states = {}

    def wait_readable(self, sock, deadline):
        self.health()
        if time.monotonic() >= deadline:
            raise TimeoutError('Joint FC input wall deadline exceeded')
        return bool(select.select([sock], [], [], .002)[0])

    def connect(self):
        deadline = time.monotonic()+25
        while not self.wait_readable(self.listener, deadline):
            pass
        self.connection, address = self.listener.accept()
        if address[0] != '127.0.0.1':
            self.connection.close()
            raise ValueError('Non-loopback PX4 simulator peer')
        self.stack.enter_context(self.connection)
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connection.settimeout(2)
        self.protocol = self.protocol_type(Sender(self.connection), srcSystem=254, srcComponent=51)
        self.pending_ap = self.wait_ap(None)
        self.record('connected', ap_peer=list(self.peer), px4_peer=list(address))

    def wait_ap(self, previous):
        deadline = time.monotonic()+5
        while True:
            if not self.wait_readable(self.ap, deadline):
                continue
            packet, address = self.ap.recvfrom(4096)
            if self.peer is None:
                self.peer = address
            if address != self.peer or address[0] != '127.0.0.1':
                raise ValueError('AP simulator peer changed')
            frame, rate, pwm, commands = decode_servos(packet)
            self.record('actuator', stack='arducopter', raw_hex=packet.hex(), frame=frame,
                        rate=rate, pwm=pwm, commands=commands)
            if previous is None or frame == (previous+1) % 2**32:
                return dict(frame=frame, commands=commands)
            if frame != previous:
                raise ValueError('AP actuator frame discontinuity')
            # Duplicate requests are retained but never issue another model tick.

    def wait_px4(self):
        startup = self.px_time is None
        deadline = time.monotonic() + (.004 if startup else 5)
        while time.monotonic() < deadline:
            if not self.wait_readable(self.connection, deadline):
                continue
            data = self.connection.recv(8192)
            if not data:
                raise ConnectionError('PX4 simulator TCP closed')
            acknowledged = False
            for message in self.protocol.parse_buffer(data) or []:
                if message.get_type() != 'HIL_ACTUATOR_CONTROLS':
                    continue
                self.record('actuator', stack='px4', raw_hex=bytes(message.get_msgbuf()).hex(),
                            message=message.to_dict())
                stamp = message.time_usec
                if (not message.flags & 1 or stamp > self.clock.tick*1000
                        or self.px_time is not None and stamp < self.px_time):
                    raise ValueError('PX4 lost lockstep, moved backwards or supplied future controls')
                self.px_time, self.px_commands = stamp, actuator_commands(message)
                acknowledged |= stamp == self.clock.tick*1000
            if acknowledged:
                return True
        if not startup:
            raise TimeoutError('PX4 did not acknowledge the exact input barrier')
        return False

    def advance(self):
        self.health()
        tick = self.clock.begin_step()
        ap_frame, px_time = self.pending_ap['frame'], self.px_time
        inputs = dict(arducopter=self.pending_ap['commands'], px4=self.px_commands)
        responses = {name: receive_worker(self.workers[name], dict(version=1, epoch=self.clock.epoch,
                     tick=tick, commands=commands), self.clock.epoch) for name, commands in inputs.items()}
        self.clock.commit(responses)
        self.states = {name: response['state'] for name, response in responses.items()}
        value = json.loads(sensor_message(self.states['arducopter']))
        value.update(no_lockstep=False, no_time_sync=False)
        packet = ('\n'+json.dumps(value, separators=(',', ':'), allow_nan=False)+'\n').encode('ascii')
        self.ap.sendto(packet, self.peer)
        self.record('sensor', stack='arducopter', packet_hex=packet.hex(), source_frame=ap_frame)
        if tick % 4 == 0:
            sensor = self.states['px4'][60:90]
            imu = self.protocol.hil_sensor_encode(round(sensor[0]), *sensor[1:14], round(sensor[14]))
            self.protocol.send(imu)
            self.record('sensor', stack='px4', raw_hex=bytes(imu.get_msgbuf()).hex(), timestamp_us=round(sensor[0]))
            if tick % 100 == 0:
                gps = self.protocol.hil_gps_encode(*gps_arguments(self.states['px4']))
                self.protocol.send(gps)
                self.record('gps', stack='px4', raw_hex=bytes(gps.get_msgbuf()).hex())
        self.pending_ap = self.wait_ap(ap_frame)
        if tick % 4 == 0:
            synchronized = self.wait_px4()
            self.clock.barrier(self.pending_ap['frame'], self.px_time, synchronized)
            self.record('barrier', ap_next_frame=self.pending_ap['frame'], px4_time_us=self.px_time,
                        synchronized=synchronized)
        self.record('step', ap_source_frame=ap_frame, px4_source_time_us=px_time,
                    model_ticks={name: response['tick'] for name, response in responses.items()})
        if tick > 4000 and self.px_time is None:
            raise TimeoutError('PX4 actuator startup exceeded four simulation seconds')
        return self.states
