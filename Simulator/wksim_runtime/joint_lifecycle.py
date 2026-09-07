"""Explicit approved pause/step/resume candidate around the real joint core.

Owns only scene permissions. High-level/native flight requests remain in the
unchanged public Task -> installed Control path. The surrounding runner owns
and supervises every process and socket in its private Linux namespaces.
"""
import json
import math
import time

from Simulator.wksim_core.worker import receive_worker
from prometheus_control.scene import TOPIC, PERIOD_SECONDS, LEASE_SECONDS


class JointLifecycle:
    def __init__(self, node, clock, publisher, directory, run_id, started, observer):
        import rclpy
        from std_msgs.msg import String
        from rclpy.serialization import serialize_message
        self.ros, self.Message, self.serialize = rclpy, String, serialize_message
        self.node, self.clock, self.clock_publisher = node, clock, publisher
        self.observer, self.run_id, self.started = observer, run_id, started
        self.phase, self.sequence, self.next_publish = 'running', 0, 0.
        self.next_spin = 0.
        self.faulted_uav_ids = []
        self.acks, self.events, self.completed = {}, [], False
        self.log = (directory/'scene-lifecycle.jsonl').open('x', buffering=1)
        self.publisher = node.create_publisher(String, TOPIC, 1)
        self.subscriptions = [node.create_subscription(String, TOPIC+f'/control/uav{uid}',
            lambda message, uid=uid: self.receive(uid, message), 1) for uid in (1, 2)]
        self.periodic(force=True)

    def record(self, kind, **fields):
        self.log.write(json.dumps(dict(kind=kind, wall=time.monotonic()-self.started,
            epoch=self.clock.epoch, tick=self.clock.tick, phase=self.phase, **fields),
            allow_nan=False, separators=(',', ':'))+'\n')

    def receive(self, uid, message):
        self.record('ack_raw', uav_id=uid, cdr_hex=self.serialize(message).hex())
        try:
            if len(message.data.encode()) > 4096:
                raise ValueError('oversized_ack')
            value = json.loads(message.data)
            if not isinstance(value, dict):
                raise ValueError('non_object_ack')
        except (ValueError, TypeError) as error:
            self.record('ack_rejected', uav_id=uid, reason=str(error))
            return
        session = self.observer.sessions.get(uid)
        now = time.monotonic()
        if (session is None or type(value.get('version')) is not int or value['version'] != 1
                or value.get('run_id') != self.run_id or value.get('scene_epoch') != self.clock.epoch
                or type(value.get('uav_id')) is not int or value['uav_id'] != uid
                or value.get('control_epoch') != session.control_epoch
                or type(value.get('ready')) is not bool
                or type(value.get('issued_monotonic_s')) not in (int, float)
                or not now-LEASE_SECONDS <= value['issued_monotonic_s'] <= now
                or type(value.get('request_id')) is not int or value['request_id'] != self.clock.last_request
                or value.get('phase') != self.phase or type(value.get('sequence')) is not int
                or not 0 < value['sequence'] <= self.sequence
                or type(value.get('source_boot_ns')) is not int or value['source_boot_ns'] < 0):
            self.record('ack_rejected', uav_id=uid, reason='foreign_stale_or_invalid_ack')
            return
        previous = self.acks.get(uid)
        if previous and value['issued_monotonic_s'] <= previous['issued_monotonic_s']:
            return
        self.acks[uid] = value

    def periodic(self, force=False):
        now = time.monotonic()
        if force or now >= self.next_publish:
            self.sequence += 1
            value = dict(version=2, run_id=self.run_id, scene_epoch=self.clock.epoch,
                sequence=self.sequence, request_id=self.clock.last_request, phase=self.phase,
                tick=self.clock.tick, time_ns=self.clock.tick*1000000,
                issued_monotonic_s=now, lease_seconds=LEASE_SECONDS,faulted_uav_ids=list(self.faulted_uav_ids))
            message = self.Message(data=json.dumps(value, allow_nan=False, separators=(',', ':')))
            self.publisher.publish(message)
            self.record('permission', message=value, cdr_hex=self.serialize(message).hex())
            if self.phase == 'paused':
                self.clock_publisher.publish(self.clock)
                self.record('paused_clock', publication=self.clock_publisher.publications,
                            time_ns=self.clock.tick*1000000)
            elif self.phase == 'faulted' and self.clock.recoverable:
                self.clock_publisher.publish(self.clock)
                self.record('faulted_clock', publication=self.clock_publisher.publications,
                            time_ns=self.clock.tick*1000000)
            self.next_publish = now+PERIOD_SECONDS
        # Several model/socket checks call periodic within the same substep.
        # Keep permission/deadline/process checks at every original call, but
        # bound redundant executor dispatch to 500Hz for this two-vehicle node,
        # matching the existing 2ms wait polling bound. State is 100Hz per
        # participant; ACKs can also reach 100Hz during pause/recovery.
        # Explicit phase changes still dispatch immediately; no wait is added.
        if force or now >= self.next_spin:
            self.ros.spin_once(self.node, timeout_sec=0)
            self.next_spin = now+.002

    def acknowledged(self):
        now = time.monotonic()
        return all(uid in self.acks and self.acks[uid]['request_id'] == self.clock.last_request
            and self.acks[uid]['phase'] == self.phase and self.acks[uid]['ready']
            and 0 <= now-self.acks[uid]['issued_monotonic_s'] <= LEASE_SECONDS for uid in (1, 2))

    def set_phase(self, phase):
        self.phase = self.observer.phase = phase
        self.acks.clear()
        self.periodic(force=True)

    def snapshot(self, physics):
        return dict(authority=self.clock.snapshot(), publications=self.clock_publisher.publications,
            republications=self.clock_publisher.paused_republications,
            faulted_republications=self.clock_publisher.faulted_republications,
            models={name:receive_worker(worker, dict(version=1, epoch=self.clock.epoch, snapshot=True),
                       self.clock.epoch) for name, worker in physics.workers.items()})

    def communication_fault(self, reason, affected_uav_ids=None):
        self.clock.suspend(reason)
        if affected_uav_ids is not None:
            self.faulted_uav_ids=list(affected_uav_ids)
        self.set_phase('faulted')
        self.record('communication_fault', reason=reason, authority=self.clock.snapshot())

    def begin_recovery(self):
        frozen = self.clock.snapshot()
        self.clock.request(dict(version=1, epoch=self.clock.epoch,
            request_id=self.clock.last_request+1, action='recover'))
        self.set_phase('recovering')
        self.recovery_started = time.monotonic()
        return frozen

    def recover_physics(self, advance, frozen=None):
        if frozen is None:
            frozen = self.begin_recovery()
        if self.phase != 'recovering' or self.clock.phase != 'running':
            raise ValueError('Physical recovery requires an explicit current recovery request')
        started = self.recovery_started
        while True:
            ready = self.acknowledged() and self.clock.tick % 4 == 0
            if time.monotonic()-started >= 5:
                self.communication_fault('native_recovery_readiness_timeout')
                raise TimeoutError('Explicit communication recovery did not regain fresh native state in 5s')
            if ready:
                break
            advance()
        if any(value['source_boot_ns'] <= frozen['time_ns'] or not value.get('task_control_released')
               for value in self.acks.values()):
            raise RuntimeError('Communication recovery requires new native state and withdrawn task control')
        result = dict(frozen=frozen, recovered=self.clock.snapshot(), wall_seconds=time.monotonic()-started,
                      control_ack=dict(self.acks), task_control_released=True)
        self.record('physics_recovery_verified', observation=result)
        self.set_phase('running')
        return result

    def pause_window(self, physics, health, label):
        before = self.snapshot(physics)
        started = time.monotonic()
        while time.monotonic()-started < 4.0:
            health()
            time.sleep(.002)
        after = self.snapshot(physics)
        if not self.acknowledged() or before['models'] != after['models'] or before['authority'] != after['authority']:
            raise RuntimeError('Joint pause state or live dual control acknowledgement failed')
        value = dict(action=label, before=before, after=after, wall_seconds=time.monotonic()-started,
                     control_ack=dict(self.acks))
        self.events.append(value)
        self.record('verified_pause', observation=value)

    def permission_loss(self, physics, children):
        """Withhold only our permission; all actual FC/DDS processes stay live."""
        before = self.snapshot(physics)
        started = time.monotonic()
        self.record('permission_withheld')
        def observe(seconds, publish):
            deadline = time.monotonic()+seconds
            while time.monotonic() < deadline:
                if publish:
                    self.periodic()
                self.observer.pump()
                for name, child, _ in children:
                    if not name.endswith('-task') and child.poll() is not None:
                        raise RuntimeError(f'{name} unexpectedly exited in permission-loss observation')
                time.sleep(.002)
        observe(1.2, False)
        failed = {name:child.poll() for name, child, _ in children if name.endswith('-task')}
        if len(failed) != 2 or any(code != 1 for code in failed.values()):
            raise RuntimeError('Missing natural task failure after permission expiry')
        if any(uid not in self.observer.sessions or not self.observer.sessions[uid].control.failsafe for uid in (1, 2)):
            raise RuntimeError('Controls were not revoked after permission expiry')
        self.record('fresh_permission_after_expiry')
        observe(.7, True)
        after = self.snapshot(physics)
        if before['models'] != after['models'] or before['authority'] != after['authority']:
            raise RuntimeError('Expired permission or reconnection advanced frozen physics')
        if any(not self.observer.sessions[uid].control.failsafe for uid in (1, 2)):
            raise RuntimeError('Fresh heartbeat automatically reacquired control after expiry')
        value = dict(status='observed_fault', before=before, after=after,
            withheld_window_s=1.2, renewed_observation_s=.7, started_wall=started-self.started,
            ended_wall=time.monotonic()-self.started, task_exit_codes=failed,
            original_pause=self.events[0])
        self.record('verified_permission_loss', observation=value)
        return value

    def exercise(self, physics, health, advance, fault_children=None):
        self.clock.request(dict(version=1, epoch=self.clock.epoch,
                           request_id=self.clock.last_request+1, action='pause'))
        self.set_phase('paused')
        self.pause_window(physics, health, 'first_pause')
        if fault_children is not None:
            return self.permission_loss(physics, fault_children)
        before = self.snapshot(physics)
        self.clock.request(dict(version=1, epoch=self.clock.epoch,
                           request_id=self.clock.last_request+1, action='step'))
        self.set_phase('stepping')
        for _ in range(4):
            advance()
        if self.clock.tick != before['authority']['tick']+4 or self.clock.phase != 'paused':
            raise RuntimeError('Single-step was not exactly four authoritative ticks')
        self.set_phase('paused')
        self.events.append(dict(action='single_step', before=before, after=self.snapshot(physics)))
        self.pause_window(physics, health, 'second_pause')
        resumed_at = self.clock.tick
        self.clock.request(dict(version=1, epoch=self.clock.epoch,
                           request_id=self.clock.last_request+1, action='resume'))
        self.set_phase('resuming')
        deadline = time.monotonic()+5
        while True:
            ready = self.acknowledged() and self.clock.tick % 4 == 0
            if time.monotonic() >= deadline:
                raise TimeoutError('Explicit scene resume did not obtain fresh dual native state in 5s')
            if ready:
                break
            advance()
        if any(value['source_boot_ns'] <= resumed_at*1000000 for value in self.acks.values()):
            raise RuntimeError('Resume acknowledged an old native source sample')
        self.events.append(dict(action='resume', frozen_tick=resumed_at,
                               resume_tick=self.clock.tick, control_ack=dict(self.acks)))
        self.set_phase('running')
        self.completed = True
        return dict(status='pass', approved_lease_period_s=PERIOD_SECONDS, approved_lease_s=LEASE_SECONDS,
                    resume_wait_s=5, events=self.events)

    def close(self):
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)
        self.node.destroy_publisher(self.publisher)
        self.log.close()
