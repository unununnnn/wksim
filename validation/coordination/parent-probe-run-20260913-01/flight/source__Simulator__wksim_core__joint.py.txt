"""One two-FC input timeline; the caller owns processes, policy and publication.

Extracts the proven model/JSON/HIL handshakes from the ground probe for real
flight. It never sends task, arming or mode commands. Inputs are held between
their native updates; AP next-frame is not a control-calculation-complete ACK.
"""
import json
import math
import os
import gc
import select
import socket
import time

from .ap_json import decode_servos, sensor_fields, sensor_message
from .px4_mavlink import Sender, actuator_commands, gps_arguments
from .worker import receive_workers


class InputTimeout(TimeoutError):
    def __init__(self, stack, deadline):
        super().__init__(stack+' input wall deadline exceeded')
        self.stack,self.deadline=stack,deadline


def before_deadline(deadline,stack=None):
    if time.monotonic()>=deadline:
        if stack is not None: raise InputTimeout(stack,deadline)
        raise TimeoutError('Joint FC input wall deadline exceeded')


class JointPhysics:
    def __init__(self, stack, clock, workers, health, record, *, terrain_feedback=None):
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
        self.inflight = None
        self.terrain_feedback = terrain_feedback
        # Opt-in diagnostic sampling; disabled in normal product execution.
        self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'
        if self.cpu_timing:
            collection_start = [None]
            def gc_timing(phase, info):
                if phase == 'start':
                    collection_start[0] = (time.monotonic_ns(), time.thread_time_ns())
                elif collection_start[0] is not None:
                    began, cpu = collection_start[0]
                    collection_start[0] = None
                    self.record('diagnostic_gc_timing', generation=info['generation'],
                        collected=info['collected'], wall_start_ns=began, wall_end_ns=time.monotonic_ns(),
                        thread_cpu_ns=time.thread_time_ns()-cpu)
            gc.callbacks.append(gc_timing)
            stack.callback(gc.callbacks.remove, gc_timing)

    def initialize_states(self, initial_states):
        """Copy exact one-shot worker responses before the first model step."""
        if self.clock.tick != 0:
            raise ValueError('Initial states may only be recorded at tick zero')
        if self.states:
            raise ValueError('Initial states were already recorded')
        if not isinstance(initial_states, dict) or set(initial_states) != set(self.workers):
            raise ValueError('Initial states must exactly match the worker set')
        copied = {}
        response_fields = {'version', 'epoch', 'tick', 'state', 'initial'}
        for name in self.workers:
            response = initial_states[name]
            if (not isinstance(response, dict) or set(response) != response_fields
                    or type(response.get('version')) is not int or response['version'] != 1
                    or response.get('epoch') != self.clock.epoch
                    or type(response.get('tick')) is not int or response['tick'] != 0
                    or response.get('initial') is not True):
                raise ValueError(f'Invalid initial-state response for {name}')
            state = response['state']
            if (not isinstance(state, list) or len(state) != 120
                    or any(isinstance(value, bool) or not isinstance(value, (int, float))
                           or not math.isfinite(value) for value in state)):
                raise ValueError(f'Invalid 120-value initial state for {name}')
            copied[name] = list(state)
        self.states = copied

    def wait_readable(self, sock, deadline, stack=None):
        self.health()
        before_deadline(deadline,stack)
        ready=bool(select.select([sock], [], [], .002)[0])
        before_deadline(deadline,stack)
        return ready

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

    def wait_ap(self, previous, deadline=None):
        deadline = time.monotonic()+5 if deadline is None else deadline
        while True:
            if not self.wait_readable(self.ap, deadline,'arducopter'):
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
                candidate=dict(frame=frame,commands=commands)
                try: before_deadline(deadline,'arducopter')
                except InputTimeout:
                    # Received evidence is retained, but cannot release a model
                    # step until an explicit input repair accepts this same ACK.
                    self.pending_ap=candidate
                    raise
                return candidate
            if frame != previous:
                raise ValueError('AP actuator frame discontinuity')
            # Duplicate requests are retained but never issue another model tick.

    def wait_px4(self, deadline=None):
        startup = self.px_time is None
        deadline = time.monotonic() + (.004 if startup else 5) if deadline is None else deadline
        while time.monotonic() < deadline:
            try: readable=self.wait_readable(self.connection,deadline,'px4')
            except InputTimeout:
                if startup: return False  # Initial 4ms polling window, before synchronization.
                raise
            if not readable:
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
                if not startup: before_deadline(deadline,'px4')
                return True
        if not startup:
            raise InputTimeout('px4',deadline)
        return False

    def advance(self):
        marks = [(time.monotonic_ns(), time.thread_time_ns())] if self.cpu_timing else None
        self.health()
        tick = self.clock.begin_step()
        ap_frame, px_time = self.pending_ap['frame'], self.px_time
        inputs = dict(arducopter=self.pending_ap['commands'], px4=self.px_commands)
        self.inflight=dict(tick=tick,ap_source_frame=ap_frame,px4_source_time_us=px_time,stage='model')
        requests = {}
        for name, commands in inputs.items():
            req = dict(version=1, epoch=self.clock.epoch, tick=tick, commands=commands)
            if self.terrain_feedback is not None:
                if name not in self.states:
                    raise RuntimeError(f'Missing prior state for {name} at tick {tick}')
                req['terrain'] = self.terrain_feedback.query_terrain(name, tick, self.states[name])
            requests[name] = (self.workers[name], req)
        responses = receive_workers(requests, self.clock.epoch, health=self.health)
        self.clock.commit(responses)
        self.inflight['model_ticks']={name:response['tick'] for name,response in responses.items()}
        self.states = {name: list(response['state']) for name, response in responses.items()}
        if marks is not None: marks.append((time.monotonic_ns(), time.thread_time_ns()))
        # Single serialization pass; byte-identical to building sensor_message
        # then parsing/updating/re-encoding (same field order and options).
        value = sensor_fields(self.states['arducopter'])
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
        if marks is not None: marks.append((time.monotonic_ns(), time.thread_time_ns()))
        self.finish_inputs()
        if marks is not None:
            marks.append((time.monotonic_ns(), time.thread_time_ns()))
            if marks[-1][0]-marks[0][0] > 2_000_000 or tick % 250 == 0:
                self.record('diagnostic_step_cpu_timing', wall_start_ns=marks[0][0], wall_end_ns=marks[-1][0],
                    stages={name:dict(wall_ns=b[0]-a[0],thread_cpu_ns=b[1]-a[1])
                            for name,a,b in zip(('health_and_models','encode_send','native_inputs'),marks,marks[1:])},
                    limitation='Thread CPU separates execution from off-CPU time; off-CPU includes I/O wait and descheduling')
        if tick > 4000 and self.px_time is None:
            raise TimeoutError('PX4 actuator startup exceeded four simulation seconds')
        return self.states

    def _native_wait(self, stack, wait, *args):
        """Run one native FC input wait, bracketing it only when diagnostics are on.

        Returns (result, segment). segment is None and no clock is read when the
        WKSIM_JOINT_CPU_TIMING diagnostic is off, so default execution is unchanged.
        A raised input timeout propagates without producing a segment or record, so
        the fail-closed path is preserved. The bracket covers only the wait_ap /
        wait_px4 call itself, never the ack/barrier or record overhead around it.
        """
        if not getattr(self, 'cpu_timing', False):
            return wait(*args), None
        wall_start, cpu_start = time.monotonic_ns(), time.thread_time_ns()
        result = wait(*args)
        wall_end, cpu_end = time.monotonic_ns(), time.thread_time_ns()
        return result, dict(stack=stack, wall_start_ns=wall_start, wall_end_ns=wall_end,
                            wall_ns=wall_end-wall_start, thread_cpu_ns=cpu_end-cpu_start)

    def finish_inputs(self, *, recovering=False, deadline=None):
        """Complete the already-produced sensor step; never issue a model RPC."""
        if self.inflight is None or self.clock.pending is not None or self.inflight['tick']!=self.clock.tick:
            raise ValueError('No complete model state has an outstanding native input')
        if recovering and (not self.clock.input_pending or self.clock.phase!='faulted'):
            raise ValueError('Input repair requires an explicitly selected latched fault')
        tick=self.clock.tick
        input_waits=[]
        self.inflight['stage']='ap_input'
        if self.pending_ap['frame']!=tick:
            self.pending_ap, seg = self._native_wait('arducopter', self.wait_ap,
                                                     self.inflight['ap_source_frame'], deadline)
            if seg is not None:
                seg['ap_frame']=self.pending_ap['frame']; input_waits.append(seg)
        if not recovering: self.clock.acknowledge_ap(self.pending_ap['frame'])
        if tick % 4 == 0:
            self.inflight['stage']='px4_input'
            if recovering and self.px_time==tick*1000:
                synchronized = True
            else:
                synchronized, seg = self._native_wait('px4', self.wait_px4, deadline)
                if seg is not None:
                    seg['px4_time_us']=self.px_time; input_waits.append(seg)
            if recovering: self.clock.repair_input(self.pending_ap['frame'],self.px_time)
            else: self.clock.barrier(self.pending_ap['frame'], self.px_time, synchronized)
            self.record('barrier', ap_next_frame=self.pending_ap['frame'], px4_time_us=self.px_time,
                        synchronized=synchronized)
        elif recovering: self.clock.repair_input(self.pending_ap['frame'],self.px_time)
        self.record('step', ap_source_frame=self.inflight['ap_source_frame'],
                    px4_source_time_us=self.inflight['px4_source_time_us'],
                    model_ticks=self.inflight['model_ticks'])
        if input_waits:
            native_wall_ns=sum(seg['wall_ns'] for seg in input_waits)
            if native_wall_ns > 2_000_000 or tick % 250 == 0:
                self.record('diagnostic_native_input_timing',
                    ap_source_frame=self.inflight['ap_source_frame'],
                    px4_source_time_us=self.inflight['px4_source_time_us'],
                    native_wait_wall_ns=native_wall_ns, waits=input_waits,
                    limitation='Retained slow(>2ms native wait)/periodic(tick%250) samples, not a full census. '
                        'Each wait brackets only the supervisor wait_ap/wait_px4 call; acknowledge_ap, '
                        'barrier/repair_input and all record writes are excluded and stay in the combined '
                        'native_inputs stage. Supervisor off-CPU during a wait includes I/O wait and '
                        'descheduling; it does not identify the native FC, host or Windows cause.')
        self.inflight=None
