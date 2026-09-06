# Copyright 2022 AMOVLAB; wksim migration changes 2026.
# SPDX-License-Identifier: Apache-2.0
"""Bounded Prometheus ENU/body position mission, with observed cancellation.

Ports the dispatch/feedback/abort flow of the pinned tutorial_demo basic
enu_xyz_pos_control, body_xyz_pos_control and waypoint_pos_control examples.
The ROS1 examples remain intact. No native control publisher is added here.
"""
import json
import math
import os
import time
import uuid
from copy import deepcopy

from .task import Task, grounded, state_time
from .mission_plan import validate_mission, resolve_waypoint
from .mission_cancel import CancelMailbox
from .mission_actions import ActionMailbox


class MissionCancelled(Exception):
    """Stop dispatching waypoints; not a statement about vehicle motion."""


class MissionPaused(RuntimeError):
    """Healthy operator release, distinct from stale state or a native fault."""

    def __init__(self, reason, request=None):
        super().__init__('Mission lost task control: ' + reason + '; no automatic reacquisition')
        self.reason, self.request = reason, request


class MissionTask(Task):
    def __init__(self, directory, *args, mission, truth_cursor, **kwargs):
        self.plan = validate_mission(mission)
        if kwargs.get('protocol') != 'session_v1' or kwargs.get('restart_control') is not None:
            raise ValueError('Mission requires session_v1 without a planned control restart')
        super().__init__(directory, *args, **kwargs)
        self.directory, self.truth_cursor = directory, truth_cursor
        self.mission_id = uuid.uuid4().hex
        self.mailbox = CancelMailbox(directory, self.run_id, self.mission_id)
        self.actions = ActionMailbox(directory, self.run_id, self.mission_id)
        self.action_token = uuid.uuid4().hex
        self.release_event = None
        self.control_generation = None
        self.pauses = []
        self._operator_wait_total, self._operator_wait_started = 0.0, None
        self.mission_state, self.progress_records, self.waypoints = 'accepted', [], []
        self.cancel_request = None
        self.interruptible = self.control_required = self.control_taken = False
        self.command_id = 0
        self.mission_log = (directory / 'mission.jsonl').open('x', encoding='utf-8', buffering=1)
        self.progress('accepted', event='mission_accepted', scope='validated task plan; not flight-controller acceptance')

    def progress(self, state=None, **fields):
        if state is not None:
            if state != self.mission_state:
                self.action_token = uuid.uuid4().hex
            self.mission_state = state
        record = dict(version=1, run_id=self.run_id, mission_id=self.mission_id,
                      control_epoch=self.epoch, state=self.mission_state,
                      native_generation=self.native_generation, action_token=self.action_token,
                      allowed_actions=self.allowed_actions(),
                      update_sequence=len(self.progress_records)+1,
                      received_monotonic_s=time.monotonic(),
                      public_boot_time_s=state_time(self.state) if self.state is not None else None,
                      command_id=self.command_id, request_id=self.request_id, **fields)
        text = json.dumps(record, allow_nan=False) + '\n'
        self.progress_records.append(json.loads(text))  # Immutable evidence snapshots, not live waypoint aliases.
        self.mission_log.write(text)
        temporary = self.directory / ('.mission-status-' + self.mission_id + '.tmp')
        with temporary.open('w', encoding='utf-8') as output:
            output.write(text)
        os.replace(temporary, self.directory / 'mission-status.json')
        self.phase(record.get('event', state))

    def poll_cancel(self):
        request = self.mailbox.poll()
        if request is not None and self.cancel_request is None:
            self.cancel_request = request
            self.progress(event='cancel_received', cancel_request=request,
                          disposition='future waypoints suppressed; in-flight request may still complete')

    def check_cancel(self):
        self.poll_cancel()
        if self.cancel_request is not None:
            raise MissionCancelled()

    def owns_control(self):
        control = self.latest.get('control_state')
        return bool(self.fresh() and self.state.armed and control is not None
                    and control.control_state == control.COMMAND_CONTROL and not control.failsafe
                    and self.state.mode == ('OFFBOARD' if self.flight_stack == 'px4' else 'GUIDED'))

    @property
    def operator_wait_seconds(self):
        current = 0.0 if self._operator_wait_started is None else time.monotonic()-self._operator_wait_started
        return self._operator_wait_total + current

    def allowed_actions(self):
        if self.control_generation is None or self.native_generation != self.control_generation or not self.fresh():
            return []
        if self.mission_state == 'paused' and self.state.armed:
            return ['resume']
        if self.mission_state in ('running', 'takeover') and self.control_required and self.owns_control():
            return ['pause']
        return []

    def on_control_revoked(self, event):
        if (self.control_taken and event.get('reason') == 'external_mode_left_no_automatic_reacquisition'):
            self.release_event = event
        else:
            super().on_control_revoked(event)

    def check_generation(self):
        if self.control_generation is not None and self.native_generation != self.control_generation:
            raise RuntimeError('Native generation changed; recorded mission targets cannot be resumed')

    def pump(self):
        super().pump()
        self.check_generation()
        # Even an externally requested public mode change can remove ownership
        # without a control_revoked text event. Never rely on text alone.
        if self.control_required and not self.owns_control():
            control = self.latest.get('control_state')
            external = self.state.mode != ('OFFBOARD' if self.flight_stack == 'px4' else 'GUIDED')
            if (control is not None and (external or control.control_state == 0)
                    and (not control.failsafe or self.release_event is not None)):
                raise MissionPaused('external operator mode/control release')
            raise RuntimeError('Mission lost task control: external mode/control change; no automatic reacquisition')
        self.poll_cancel()
        if self.interruptible and self.cancel_request is not None:
            raise MissionCancelled()
        if self.interruptible and 'pause' in self.allowed_actions():
            request = self.actions.poll(self.action_token, self.epoch, self.native_generation, ['pause'])
            if request is not None:
                raise MissionPaused('explicit pause request', request)

    def pause_and_resume(self, pause):
        """Release once, then observe without output until a fresh explicit offer.

        An external mode release never causes another mode command here. A cancel
        while another owner is airborne stays pending: explicit resume authorizes
        a new takeover and landing, or that owner can land without our commands.
        Native faults, clock resets and stale state are still fatal, not recovery.
        """
        self.interruptible = self.control_required = False
        self.progress('pausing', event='mission_pausing', reason=pause.reason, action_request=pause.request)
        if pause.request is not None:
            Task.pump(self)
            self.check_generation()
            if not self.owns_control():
                raise RuntimeError('Pause release requires current task ownership')
            mode = 'AUTO.LOITER' if self.flight_stack == 'px4' else 'BRAKE'
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode=mode), 'pause_hold_acknowledged')
            self.wait('pause_release_observed', lambda: self.state.mode == mode
                      and self.latest['control_state'].control_state == 0, 10)
        else:
            # Public setup clears COMMAND_CONTROL before the FC's mode ACK.
            # Observe that transition without stealing it with another request.
            external_mode = 'OFFBOARD' if self.flight_stack == 'px4' else 'GUIDED'
            self.wait('external_release_observed', lambda: self.state.mode != external_mode
                      and self.latest['control_state'].control_state == 0, 10)
        entry = dict(reason=pause.reason, pause_request=pause.request, control_epoch=self.epoch,
                     native_generation=self.native_generation, start_boot_s=state_time(self.state),
                     start_monotonic_s=time.monotonic(), start_truth=self.truth_cursor(),
                     publications_before=len(self.envelopes))
        self.pauses.append(entry)
        self._operator_wait_started = time.monotonic()
        self.progress('paused', event='mission_paused', pause=deepcopy(entry),
                      disposition='physics and FC continue; no task output; explicit new resume required')
        request = None
        try:
            while request is None:
                Task.pump(self)  # Still checks child liveness, public freshness and fatal events.
                self.check_generation()
                self.poll_cancel()
                if self.cancel_request is not None and grounded(self.state, self.uav_id):
                    raise MissionCancelled()
                request = self.actions.poll(self.action_token, self.epoch, self.native_generation,
                                            self.allowed_actions())
        finally:
            elapsed = time.monotonic()-self._operator_wait_started
            self._operator_wait_total += elapsed
            self._operator_wait_started = None
            entry.update(wait_wall_s=elapsed, end_boot_s=state_time(self.state),
                         end_monotonic_s=time.monotonic(),
                         end_truth=self.truth_cursor(), publications_after=len(self.envelopes),
                         resume_request=request)
        self.progress('resuming', event='mission_resume_received', action_request=request,
                      disposition='new COMMAND_CONTROL request holds current pose; not replay of prior input')
        self.release_event = None
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'resume_control_acknowledged', 40)
        self.wait('resume_ownership_observed', self.owns_control, 10)
        entry['resume_setup_request_id'] = self.envelopes[-1]['request_id']
        self.control_required = self.interruptible = True
        self.progress('running', event='mission_resumed', pause=deepcopy(entry),
                      disposition='new command required; interrupted waypoint dwell restarts in full')
        self.check_cancel()  # A pending cancel lands only after the explicit new takeover.

    def send(self, msg, label, timeout=10):
        if self.interruptible:
            self.pump()  # Poll immediately before dispatching the next command.
        previous = self.interruptible
        self.interruptible = False
        try:
            # Drain this accepted operation to its actual acknowledgement. A
            # queued cancel is latched, never mistaken for instantaneous recall.
            return super().send(msg, label, timeout)
        finally:
            self.interruptible = previous

    def command(self, **fields):
        # A public operator may have used larger MOVE IDs while owning control.
        observed = [e['command_id'] for e in self.events if e.get('event') == 'command_accepted'
                    and type(e.get('command_id')) is int]
        self.command_id = max([self.command_id, *observed])
        self.command_id += 1
        return self.Cmd(command_id=self.command_id, **fields)

    def land(self):
        self.interruptible = False
        self.pump()
        if not self.owns_control():
            raise RuntimeError('Cannot request mission landing without current task ownership')
        self.control_required = False
        self.progress('landing', event='landing_requested', disposition='LAND request; not a landed acknowledgement')
        self.send(self.command(agent_cmd=self.Cmd.LAND), 'land_accepted')
        self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id), 30)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
        completed_at = time.monotonic()
        self.wait('normal_stop_ready', lambda: self.fresh() and grounded(self.state, self.uav_id)
                  and self.received.get('state', 0) > completed_at)

    def cancel(self):
        self.interruptible = False
        self.progress('cancelling', event='mission_cancelling')
        if not self.fresh():
            raise RuntimeError('Cancellation cannot resolve motion from stale state')
        if grounded(self.state, self.uav_id):
            disposition = 'already_disarmed_on_ground'
        elif self.control_taken:
            self.land()
            disposition = 'landed_and_disarmed_public; physics corroboration pending'
        elif self.state.armed and abs(self.state.position[2]) < 0.3:
            # The adapter also requires its actual native landed bit. Rejection
            # is a failure, not a reason to force disarm or manufacture takeoff.
            self.send(self.Setup(cmd=self.Setup.ARMING, arming=False), 'cancel_ground_disarm_completed')
            self.wait('cancel_disarmed_ground', lambda: grounded(self.state, self.uav_id), 10)
            disposition = 'ordinary_ground_disarm_observed'
        else:
            raise RuntimeError('Cancel has no safe authorized disposition for the observed state')
        self.progress('cancelled', event='mission_cancelled', disposition=disposition,
                      completed_waypoints=sum(w['status'] == 'completed' for w in self.waypoints))

    def execute(self):
        try:
            self.wait('public_control_ready', lambda: self.fresh() and
                      self.setup_pub.get_subscription_count() == 1 and
                      self.command_pub.get_subscription_count() == 1, 55)
            if not grounded(self.state, self.uav_id):
                raise RuntimeError('Mission requires initial disarmed ground state')
            self.active = True
            self.check_cancel()
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
            if self.flight_stack == 'px4':
                mode_completed_at = time.monotonic()
                self.wait('native_prearm_health_ready', lambda: self.arm_ready(mode_completed_at), 55)
            self.check_cancel()
            self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
            self.wait('armed', lambda: self.state.armed)
            self.check_cancel()
            self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                      'task_control_ready', 40)
            self.wait('task_ownership_observed', self.owns_control, 10)
            self.control_taken = self.control_required = True
            self.control_generation = self.native_generation
            self.progress('takeover', event='mission_takeover')
            self.interruptible = True
            # Preserve the accepted takeoff reference if this phase is interrupted.
            reference = next((e for e in reversed(self.events) if e.get('event') == 'takeover_reference'), None)
            resume_takeoff = False
            while True:
                try:
                    if resume_takeoff:
                        self.send(self.command(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS,
                                  position_ref=reference['position_enu_m'], yaw_ref=reference['yaw_enu_rad']),
                                  'takeoff_resume_target_accepted')
                    self.wait('takeoff_reached', lambda: self.state.position[2] >= 2.5, 25)
                    self.dwell('hold_completed', lambda: abs(self.state.position[2] - 3) <= 0.6
                               and max(abs(x) for x in self.state.attitude[:2]) <= 0.35, 5)
                    break
                except MissionPaused as pause:
                    self.pause_and_resume(pause)
                    if reference is None:
                        raise RuntimeError('Missing recorded takeoff reference; refusing to invent a resume target')
                    resume_takeoff = True
            for index, waypoint in enumerate(self.plan['waypoints'], 1):
                self.visit(index, waypoint)
            self.check_cancel()
            while True:
                try:
                    self.land()
                    break
                except MissionPaused as pause:
                    self.pause_and_resume(pause)
            if self.cancel_request is not None:
                self.progress('cancelled', event='mission_cancelled', disposition='landing already in progress; observed ground')
            else:
                self.progress('completed', event='mission_completed', disposition='all waypoints dwelled; public ground; physics corroboration pending')
        except MissionCancelled:
            try:
                while True:
                    try:
                        self.cancel()
                        break
                    except MissionPaused as pause:
                        try:
                            self.pause_and_resume(pause)
                        except MissionCancelled:
                            pass  # Ground arrival or explicit resume; reevaluate safe cancellation.
            except Exception as error:
                self.fail(str(error))
                raise
        except Exception as error:
            self.fail(str(error))
            raise

    def visit(self, index, waypoint):
        while True:
            try:
                self.pump()
                break
            except MissionPaused as pause:
                self.pause_and_resume(pause)
        anchor = dict(position=[float(x) for x in self.state.position], yaw=float(self.state.attitude[2]),
                      source_boot_time_s=state_time(self.state), received_monotonic_s=self.received['state'])
        target = resolve_waypoint(waypoint, anchor['position'], anchor['yaw'])
        record = dict(index=index, status='running', input=waypoint, anchor=anchor,
                      target_enu_m=target['position_enu_m'], yaw_enu_rad=target['yaw_enu_rad'],
                      dwell_s=waypoint['dwell_s'], attempts=[])
        self.waypoints.append(record)
        def at_waypoint():
            yaw_error = math.remainder(float(self.state.attitude[2])-record['yaw_enu_rad'], 2*math.pi)
            return (math.dist(self.state.position, record['target_enu_m']) <= 0.5
                    and math.hypot(*self.state.velocity) <= 0.5 and abs(yaw_error) <= 0.15)
        while True:
            resumed = bool(record['attempts'])
            command = self.command(agent_cmd=self.Cmd.MOVE,
                move_mode=self.Cmd.XYZ_POS if resumed or waypoint['frame'] == 'enu' else self.Cmd.XYZ_POS_BODY,
                position_ref=record['target_enu_m'] if resumed else waypoint['position_m'],
                yaw_ref=record['yaw_enu_rad'] if resumed else waypoint['yaw_rad'])
            attempt = dict(command_id=self.command_id, resumed=resumed, status='dispatch_pending')
            record['attempts'].append(attempt)
            before = len(self.envelopes)
            try:
                self.send(command, f'waypoint_{index}_accepted')
                attempt.update(status='accepted', request_id=self.envelopes[-1]['request_id'])
                record.update(command_id=self.command_id, request_id=attempt['request_id'])
                self.progress('running', event='waypoint_running', waypoint=deepcopy(record))
                self.wait(f'waypoint_{index}_reached', at_waypoint, 30)
                self.dwell_waypoint(record, at_waypoint)
                attempt['status'] = 'completed'
                break
            except MissionPaused as pause:
                attempt.update(status='interrupted', reason=pause.reason)
                if len(self.envelopes) > before:
                    attempt['request_id'] = self.envelopes[before]['request_id']
                self.progress(event='waypoint_interrupted', waypoint=deepcopy(record))
                for key in ('dwell_start_boot_s', 'dwell_end_boot_s', 'dwell_start_truth', 'dwell_end_truth'):
                    record.pop(key, None)
                self.pause_and_resume(pause)
        record['status'] = 'completed'
        self.progress(event='waypoint_completed', waypoint=deepcopy(record))

    def dwell_waypoint(self, record, predicate):
        """A passage through tolerance is not a dwell. Restart the entire window
        on an excursion, keeping a bounded settling deadline and every failure.
        Freshness/ownership errors from pump remain fatal and are never retried.
        """
        deadline, start = time.monotonic()+15, None
        while True:
            self.pump()
            if not predicate():
                if start is not None:
                    self.progress(event='waypoint_dwell_reset', index=record['index'],
                                  invalidated_start_boot_s=start, reason='outside unchanged integration tolerance')
                    record.pop('dwell_start_boot_s', None)
                    record.pop('dwell_start_truth', None)
                    start = None
            elif start is None:
                start = state_time(self.state)
                record['dwell_start_boot_s'], record['dwell_start_truth'] = start, self.truth_cursor()
                self.progress(event='waypoint_dwell_started', waypoint=record.copy())
            elif state_time(self.state)-start >= record['dwell_s']:
                record['dwell_end_boot_s'], record['dwell_end_truth'] = state_time(self.state), self.truth_cursor()
                self.phase(f"waypoint_{record['index']}_dwelled")
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(f"waypoint_{record['index']}: continuous boot-clock dwell timeout")

    def fail(self, reason):
        self.interruptible = self.control_required = False
        self.progress('failed', event='mission_failed', reason=reason,
                      disposition='no further mission commands; actual motion unresolved until runtime teardown')

    def report(self):
        result = super().report()
        result['mission'] = dict(version=1, mission_id=self.mission_id, state=self.mission_state,
            plan=self.plan, waypoints=self.waypoints, progress=self.progress_records,
            cancel_request=self.cancel_request, cancel_rejections=self.mailbox.rejections,
            pauses=self.pauses, action_rejections=self.actions.rejections,
            operator_wait_seconds=self.operator_wait_seconds,
            thresholds=dict(position_m=0.5, speed_m_s=0.5, yaw_rad=0.15),
            clocks='FC boot dwell and independent physics record cursors; not equated')
        return result

    def close(self):
        self.mission_log.close()
        super().close()
