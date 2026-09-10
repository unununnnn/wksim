"""Adapter from bound ArUco seam records to real public UAVCommand sends.

The adapter owns no ROS resources: it borrows the host task's ``send`` (which
keeps the session_v1 request numbering, control_epoch envelope, ACK waiting
and raw logging in ``Task.send``, ``task.py:320``) and the task's ``Cmd``
message class. Only two public commands are ever built:

- ``MOVE``/``XYZ_VEL_BODY`` with the seam's bounded body velocity
  (``UAVCommand.msg:12,29``: MOVE=4, XYZ_VEL_BODY=4);
- ``CURRENT_POS_HOVER`` (agent_cmd=2) whenever the current authority step shows
  no fresh MOVE. The control processor re-resolves the last accepted MOVE
  every cycle, so HOLD actively replaces the persisted velocity setpoint —
  including the first HOLD, because the host task may have published a MOVE
  before this adapter existed. Only after this adapter itself has confirmed a
  hover send, and no new command intervened, is a repeated HOLD suppressed.

Freshness and idempotency: ``process`` requires the caller's current authority
step (no guessing, no regression). A MOVE whose intent validity ended before
the current step is never published; it degrades to the hover path. HOLD
records are judged on their own record step and never inherit an old MOVE's
validity. Re-processing the exact same record step is an idempotent no-send
(``duplicate_record``); an older record step is a replay and raises.

``command_id`` starts from the caller-supplied host high-water mark
(``last_command_id``) and increases strictly and only when a command is
actually sent (``accept`` rejects non-increasing body command ids). If
``Task.send`` published but its ACK wait raised, the correlation record keeps
the consumed command_id with ``send_failed``/``ack_unconfirmed`` and the
exception propagates; the id is never reused. Foreign or illegal records are
rejected before any message is built or id consumed. The seam record's epoch
is the joint scene epoch; it is never used as control_epoch. All flight
parameters come from the caller; this module supplies no defaults and no
takeoff/landing, runner, or transport bridge logic.
"""
import copy
import math

from Simulator.wksim_runtime.aruco_tracking_input import (
    ArucoTrackingSeam, SEAM_SCHEMA, HOLD_PUBLIC_COMMAND, MAX_STEP)


ACTION_SCHEMA = "wksim.aruco-public-command.v1"
MOVE_FIELDS = ("agent_cmd", "move_mode", "velocity_ref", "yaw_rate_mode", "yaw_rate_ref")


def _now_step(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_STEP:
        raise ValueError(f"current authority step must be within 0..{MAX_STEP}")
    return value


class ArucoCommandAdapter:
    """Send public velocity/hover commands for one bound ArucoTrackingSeam."""

    def __init__(self, task, seam, *, scene_epoch, last_command_id):
        if not isinstance(seam, ArucoTrackingSeam):
            raise TypeError("A bound ArucoTrackingSeam is required")
        if not isinstance(scene_epoch, str) or len(scene_epoch) != 32:
            raise ValueError("scene_epoch must be the 32-digit joint scene epoch")
        if type(last_command_id) is not int or not 0 <= last_command_id <= 2**32-1:
            raise ValueError("last_command_id must be the host's used command_id high-water mark")
        for attribute in ("run_id", "uav_id", "Cmd", "send"):
            if not hasattr(task, attribute):
                raise TypeError(f"task must expose {attribute}; this adapter never creates its own channel")
        authority = seam.authority
        if authority["run_id"] != task.run_id:
            raise ValueError("seam run differs from the task run")
        if authority["epoch"] != scene_epoch:
            raise ValueError("seam epoch differs from the joint scene epoch")
        if authority["camera"]["vehicle_id"] != task.uav_id:
            raise ValueError("the bound camera belongs to a different control vehicle")
        self.task, self.seam, self.scene_epoch = task, seam, scene_epoch
        self._command_id = last_command_id
        self._last_sent = None  # None | "move" | "hover" (this adapter's own sends)
        self._last_record_step = None
        self._last_now_step = None
        self.actions = []

    def _validate_record(self, record):
        """All rejection happens here, before any message build or id spend."""
        if not isinstance(record, dict) or record.get("schema") != SEAM_SCHEMA:
            raise ValueError("record is not a bound seam record")
        authority = self.seam.authority
        if any(record.get(key) != authority[key] for key in
               ("run_id", "epoch", "stream_id", "instance_id", "generation")):
            raise ValueError("record does not come from the current seam binding")
        if record["run_id"] != self.task.run_id or record["epoch"] != self.scene_epoch:
            raise ValueError("record run/scene_epoch differs from this task")
        step = record.get("authority_step")
        if not isinstance(step, int) or isinstance(step, bool) or step < 0:
            raise ValueError("record authority_step is invalid")
        if self._last_record_step is not None and step < self._last_record_step:
            raise ValueError("record is older than the last processed one; replay is rejected")
        command = record.get("command")
        hold = record.get("hold_action")
        if command is not None and (not isinstance(command, dict) or command.get("agent_cmd") != "MOVE"):
            raise ValueError("seam command is not the public MOVE mapping")
        if command is not None:
            intent=record.get('intent')
            velocity=command.get('velocity_ref')
            if (set(command)!=set(MOVE_FIELDS) or command.get('move_mode')!='XYZ_VEL_BODY'
                    or command.get('yaw_rate_mode') is not True or command.get('yaw_rate_ref')!=0
                    or not isinstance(velocity,list) or len(velocity)!=3
                    or any(type(v) not in (int,float) or not math.isfinite(v) for v in velocity)
                    or not isinstance(intent,dict) or intent.get('move_mode')!='XYZ_VEL_BODY'
                    or intent.get('velocity_ref')!=velocity
                    or any(intent.get(key)!=record[key] for key in ('run_id','epoch','stream_id'))):
                raise ValueError('Invalid or inconsistent bounded MOVE fields')
        if command is None and not (isinstance(hold, dict) and hold.get("required")
                                    and hold.get("public_command") == HOLD_PUBLIC_COMMAND):
            raise ValueError("seam record carries neither a command nor the required hold_action")
        return step

    def _build(self, fields, command_id):
        cmd = self.task.Cmd()
        if fields["agent_cmd"] == "MOVE":
            cmd.agent_cmd = self.task.Cmd.MOVE
            cmd.move_mode = self.task.Cmd.XYZ_VEL_BODY
            cmd.velocity_ref = [float(value) for value in fields["velocity_ref"]]
            cmd.yaw_rate_mode = True
            cmd.yaw_rate_ref = 0.0
        elif fields["agent_cmd"] == HOLD_PUBLIC_COMMAND:
            cmd.agent_cmd = self.task.Cmd.CURRENT_POS_HOVER
        else:
            raise ValueError("seam produced an unsupported public command")
        cmd.control_level = self.task.Cmd.DEFAULT_CONTROL
        cmd.command_id = command_id
        return cmd

    def _send(self, fields, label, record, step, now_step, action):
        """Consume one id and send; a raised ACK wait still records the spend."""
        command_id = self._command_id+1
        if command_id > 2**32-1:
            raise ValueError('Public uint32 command_id exhausted; new control epoch required')
        message = self._build(fields, command_id)
        self._command_id = command_id
        correlation = {
            "schema": ACTION_SCHEMA,
            "run_id": record["run_id"],
            "scene_epoch": record["epoch"],
            "stream_id": record["stream_id"],
            "authority_step": step,
            "authority_now_step": now_step,
            "seam_reason": record.get("reason"),
            "action": action,
            "command_id": command_id,
            "ack_scope": "public_command_accepted; not native FC ACK or action completion",
            "public_fields": ({key: fields[key] for key in MOVE_FIELDS} if action == "move"
                              else {"agent_cmd": HOLD_PUBLIC_COMMAND}),
        }
        try:
            self.task.send(message, label)
        except BaseException as error:
            correlation.update(send_failed=True, ack_unconfirmed=True, error=repr(error))
            self.actions.append(copy.deepcopy(correlation))
            self._last_record_step = step
            self._last_now_step = now_step
            self._last_sent = None  # The request may have reached control before the ACK failed.
            raise
        correlation.update(send_failed=False, ack_unconfirmed=False)
        self.actions.append(copy.deepcopy(correlation))
        return correlation

    def _correlate(self, record, step, now_step, action):
        self._last_now_step = now_step
        correlation = {
            "schema": ACTION_SCHEMA,
            "run_id": record["run_id"],
            "scene_epoch": record["epoch"],
            "stream_id": record["stream_id"],
            "authority_step": step,
            "authority_now_step": now_step,
            "seam_reason": record.get("reason"),
            "action": action,
            "command_id": None,
            "public_fields": None,
        }
        self.actions.append(copy.deepcopy(correlation))
        return correlation

    def process(self, record, *, authority_step):
        """Validate one seam record at the caller's current authority step.

        Sends the required public command, if any, and returns the correlation
        record. Suppression semantics: ``duplicate_record`` = the same still-fresh
        MOVE record re-processed; expiry is checked first and still requires hover.
        ``suppressed_hold`` = a repeated HOLD after this adapter's own
        confirmed hover with no intervening command; ``expired_move`` = a MOVE
        whose intent validity ended before the current step, degraded to the
        hover path instead of being published.
        """
        now_step = _now_step(authority_step)
        if self._last_now_step is not None and now_step < self._last_now_step:
            raise ValueError("current authority step regressed")
        step = self._validate_record(record)
        if step > now_step:
            raise ValueError('Record authority step is in the future')
        command = record["command"]
        if command is not None:
            intent = record.get("intent") or {}
            capture = intent.get("step")
            valid_until = intent.get("valid_until_step")
            if type(capture) is not int or type(valid_until) is not int or not 0 <= capture <= step <= valid_until:
                raise ValueError("accepted intent lacks capture/validity steps")
            if capture > now_step:
                raise ValueError("intent capture step is in the future")
            if now_step <= valid_until:
                if step == self._last_record_step:
                    return self._correlate(record, step, now_step, "duplicate_record")
                correlation = self._send(command, "aruco-tracking-move", record, step, now_step, "move")
                self._last_sent = "move"
            else:
                command = None  # Expired MOVE: never publish; degrade to hover.
                record = dict(record, reason="expired_move:" + str(record.get("reason")))
        if command is None:
            if self._last_sent != "hover":
                # First hover included: the host may have published a MOVE
                # before this adapter existed, and that setpoint persists.
                correlation = self._send({"agent_cmd": HOLD_PUBLIC_COMMAND},
                                         "aruco-tracking-hover", record, step, now_step, "hover")
                self._last_sent = "hover"
            else:
                correlation = self._correlate(record, step, now_step, "suppressed_hold")
        self._last_record_step = step
        self._last_now_step = now_step
        return correlation
