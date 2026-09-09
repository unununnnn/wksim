"""Joint quad-X authority: integer physics time, never a rendering/wall clock.

The supervisor owns workers, FC handshakes and cold restart. This object never
steps a model itself. A partial/failed worker step faults the scene; it cannot
be resumed as though the two model processes had rolled back.
"""
import math
import re
import socket


class SceneClock:
    VEHICLES = frozenset(('arducopter', 'px4'))
    STEP_NS, MACRO_TICKS = 1_000_000, 4

    def __init__(self, epoch):
        if not isinstance(epoch, str) or not re.fullmatch('[0-9a-f]{32}', epoch):
            raise ValueError('Scene epoch must be 32 lowercase hexadecimal characters')
        self.epoch = epoch
        self.tick = self.last_barrier = self.last_request = 0
        self.pending = None
        self.phase, self.reason = 'running', None
        self.single_remaining = 0
        self.synchronized = False
        self.last_input_tick, self.recoverable = 0, False
        self.input_pending = False

    def begin_step(self):
        if self.phase not in ('running', 'stepping') or self.pending is not None:
            raise ValueError('Scene does not permit another physics step')
        if self.tick % self.MACRO_TICKS == 0 and self.last_barrier != self.tick:
            raise ValueError('Previous input barrier is still incomplete')
        if self.phase == 'stepping' and self.single_remaining == 0:
            raise ValueError('Single-step budget exhausted; input barrier still required')
        self.pending = self.tick + 1
        return self.pending

    def commit(self, responses):
        try:
            if (self.pending is None or self.phase not in ('running', 'stepping')
                    or not isinstance(responses, dict) or set(responses) != self.VEHICLES):
                raise ValueError('A joint tick requires both model responses')
            for response in responses.values():
                if (not isinstance(response, dict) or set(response) != {'version', 'epoch', 'tick', 'state'}
                        or type(response['version']) is not int or response['version'] != 1
                        or response['epoch'] != self.epoch or type(response['tick']) is not int
                        or response['tick'] != self.pending):
                    raise ValueError('Model acknowledgement has wrong version, epoch or tick')
                state = response['state']
                if (not isinstance(state, list) or len(state) != 120
                        or any(type(x) not in (int, float) or not math.isfinite(x) for x in state)
                        or abs(state[2] - self.pending / 1000) > 1e-8
                        or round(state[60]) != self.pending * 1000):
                    raise ValueError('Model state does not prove this authoritative tick')
        except (ValueError, TypeError, OverflowError) as error:
            self.fault(str(error))
            raise
        self.tick, self.pending = self.pending, None
        if self.phase == 'stepping':
            self.single_remaining -= 1
        return self.tick * self.STEP_NS

    def barrier(self, ap_next_frame, px4_time_us, synchronized):
        if (self.phase not in ('running', 'stepping') or self.tick <= self.last_barrier
                or self.pending is not None or self.tick % self.MACRO_TICKS
                or type(ap_next_frame) is not int or ap_next_frame != self.tick
                or type(synchronized) is not bool
                or (synchronized and (type(px4_time_us) is not int or px4_time_us != self.tick * 1000))
                or (self.synchronized and not synchronized)):
            self.fault('Invalid joint input barrier')
            raise ValueError(self.reason)
        self.synchronized |= synchronized
        self.last_barrier = self.tick
        self.last_input_tick = self.tick
        if self.phase == 'stepping' and self.single_remaining == 0:
            self.phase = 'paused'

    def acknowledge_ap(self, frame):
        if (self.pending is not None or self.phase not in ('running', 'stepping')
                or type(frame) is not int or frame != self.tick or self.tick <= self.last_input_tick):
            self.fault('Invalid per-tick AP input acknowledgement')
            raise ValueError(self.reason)
        self.last_input_tick = self.tick

    def suspend(self, reason):
        """Recoverable communication failure at a completed real microstep.

        Never rolls back a model or hides an incomplete model/input response.
        At a non-macro tick, the last PX4 barrier remains the preceding 4ms
        boundary and its real actuator output is still the held input.
        """
        if (self.phase not in ('running', 'paused') or self.pending is not None
                or not self.synchronized or self.last_input_tick != self.tick
                or self.last_barrier != self.tick-self.tick % self.MACRO_TICKS
                or not isinstance(reason, str) or not reason):
            raise ValueError('Communication suspension needs a completed authoritative input step')
        self.phase, self.reason, self.recoverable = 'faulted', reason, True
        return self.snapshot()

    def request(self, request):
        if (not isinstance(request, dict) or set(request) != {'version', 'epoch', 'request_id', 'action'}
                or type(request['version']) is not int or request['version'] != 1
                or request['epoch'] != self.epoch or type(request['request_id']) is not int
                or not self.last_request < request['request_id'] < 2**64):
            raise ValueError('Invalid, replayed or retired scene request')
        # Consume a current envelope even if its action is rejected in this phase.
        self.last_request = request['request_id']
        action = request['action']
        if action == 'stop':
            self.phase = 'stopped'
            self.recoverable = False
        elif action == 'recover':
            if (self.phase != 'faulted' or not self.recoverable or self.pending is not None
                    or self.input_pending
                    or self.last_input_tick != self.tick
                    or self.last_barrier != self.tick-self.tick % self.MACRO_TICKS):
                raise ValueError('Only explicit recovery of a completed communication-fault boundary is allowed')
            self.phase, self.reason, self.recoverable = 'running', None, False
        elif (self.pending is not None or self.last_barrier != self.tick
              or not self.synchronized or self.phase not in ('running', 'paused')):
            raise ValueError('Scene action requires a synchronized, non-faulted input boundary')
        elif action == 'pause' and self.phase == 'running':
            self.phase = 'paused'
        elif action == 'step' and self.phase == 'paused':
            self.phase, self.single_remaining = 'stepping', self.MACRO_TICKS
        elif action == 'resume' and self.phase == 'paused':
            self.phase = 'running'
        else:
            raise ValueError('Unsupported scene action or transition')
        return self.snapshot()

    def suspend_input(self, reason):
        """Latch an input timeout after both models committed, without rollback."""
        if (self.phase not in ('running','stepping') or self.pending is not None
                or not self.synchronized or self.tick<=self.last_barrier
                or self.last_input_tick not in (self.tick,self.tick-1)
                or not isinstance(reason,str) or not reason):
            raise ValueError('Input suspension requires a known committed model step')
        self.phase,self.reason,self.recoverable,self.input_pending='faulted',reason,True,True
        self.single_remaining=0
        return self.snapshot()

    def repair_input(self, ap_frame, px4_time_us):
        """Accept only this frozen step's real acknowledgements; remain faulted."""
        expected_px=(self.tick-self.tick%4)*1000
        if (self.phase!='faulted' or not self.recoverable or not self.input_pending
                or self.pending is not None or type(ap_frame) is not int or ap_frame!=self.tick
                or type(px4_time_us) is not int or px4_time_us!=expected_px):
            raise ValueError('Input recovery did not prove the exact frozen boundary')
        self.last_input_tick=self.tick
        if self.tick%4==0: self.last_barrier=self.tick
        self.input_pending=False
        return self.snapshot()

    def fault(self, reason):
        self.phase, self.reason = 'faulted', str(reason)
        self.recoverable = False
        self.input_pending = False

    def snapshot(self):
        return dict(version=1, epoch=self.epoch, tick=self.tick, time_ns=self.tick*self.STEP_NS,
                    phase=self.phase, last_barrier_tick=self.last_barrier,
                    synchronized=self.synchronized, pending_tick=self.pending,
                    single_remaining=self.single_remaining, last_request_id=self.last_request,
                    fault=self.reason, last_input_tick=self.last_input_tick, recoverable=self.recoverable,
                    input_pending=self.input_pending)


class ClockPublisher:
    """One cooperative /clock owner per private Linux network namespace/domain.

    Linux abstract sockets give atomic ownership and crash cleanup without lock
    files. A foreign DDS /clock publisher is also rejected when discovered.
    The supplied ROS node/context remains the supervisor's responsibility.
    """
    def __init__(self, node):
        from rosgraph_msgs.msg import Clock
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from .isolation import check_isolation
        check_isolation()
        domain_id = node.context.get_domain_id()
        if type(domain_id) is not int or not 0 <= domain_id <= 232:
            raise ValueError('Invalid ROS domain for scene clock')
        self.node, self.message_type, self.publications = node, Clock, 0
        self.paused_republications = 0
        self.faulted_republications = 0
        self.epoch, self.last_tick = None, None
        self.owner = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.publisher = None
        try:
            self.owner.bind('\0wksim-scene-clock-v1-' + str(domain_id))
            if node.count_publishers('/clock'):
                raise RuntimeError('Another /clock publisher already exists')
            self.publisher = node.create_publisher(Clock, '/clock', QoSProfile(
                depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE))
        except BaseException:
            self.close()
            raise

    def publish(self, clock):
        if self.publisher is None or self.node.count_publishers('/clock') > 1:
            raise RuntimeError('Scene lost unique /clock publisher ownership')
        fault_boundary = (isinstance(clock, SceneClock) and clock.phase == 'faulted' and clock.recoverable
                          and (clock.input_pending or clock.last_input_tick == clock.tick
                               and clock.last_barrier == clock.tick-clock.tick%4))
        if (not isinstance(clock, SceneClock) or clock.pending is not None
                or clock.phase not in ('running', 'stepping', 'paused') and not fault_boundary):
            raise ValueError('Only committed, non-faulted scene time may be published')
        repeated = self.last_tick is not None and clock.tick == self.last_tick
        if (self.epoch is not None and clock.epoch != self.epoch
                or repeated and not fault_boundary and (clock.phase != 'paused' or not clock.synchronized
                                                        or clock.last_barrier != clock.tick)
                or fault_boundary and not repeated
                or not repeated and clock.tick != (0 if self.last_tick is None else self.last_tick+1)):
            raise ValueError('Clock publication skipped a tick or crossed an unretired epoch')
        message = self.message_type()
        message.clock.sec, message.clock.nanosec = divmod(clock.tick * clock.STEP_NS, 1_000_000_000)
        self.publisher.publish(message)
        self.epoch, self.last_tick = clock.epoch, clock.tick
        self.publications += 1
        # Volatile/best-effort consumers can miss the last tick or join while
        # paused. Retransmit only this committed synchronized boundary; never
        # manufacture another step or treat retransmission as model progress.
        self.paused_republications += int(repeated and clock.phase == 'paused')
        self.faulted_republications += int(repeated and fault_boundary)

    def close(self):
        if self.publisher is not None:
            self.node.destroy_publisher(self.publisher)
            self.publisher = None
        self.owner.close()
