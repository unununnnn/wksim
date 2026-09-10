"""#99 RC_POS_CONTROL scenario task; session_v1 protocol only.

The task node owns the software-RC publisher, so the publisher GID and the
control epoch are bound in-process. Frames are strict `wksim.rc-input`
envelopes and every published frame is logged raw. The neutral stream is
kept alive through arming, native takeoff and activation so the candidate
never expires mid-setup. Scenarios:
movement / recenter / yaw / stream-stall / mode-out / new-takeover.
"""
import json
import math
import time

from std_msgs.msg import String

from .task import Task, grounded

NEUTRAL = [1500, 1500, 1500, 1500, 1000, 1500, 1000, 1000]
VERSION = 1
SOURCE = "wksim.rc-input"


def physical(row):
    v = row["vehicle"]
    return dict(time=row["time"], position=(v[3], v[4], -v[5]))


class RCTask(Task):
    def __init__(self, directory, health, phase, flight_stack, *, scenario, boot_id, stream_id,
                 truth_path, **kwargs):
        if kwargs.get("protocol") != "session_v1":
            raise ValueError("RCTask requires session_v1")
        super().__init__(directory, health, phase, flight_stack, **kwargs)
        if scenario not in ("movement", "recenter", "yaw", "stream-stall", "mode-out", "new-takeover"):
            raise ValueError("unknown RC scenario")
        self.scenario = scenario
        self.boot_id = boot_id
        self.stream_id = stream_id
        self.truth_path = truth_path
        self.rc_pub = self.node.create_publisher(String, self.topic_root + "v2/rc_input", 1)
        self.rc_sequence = 0
        self.rc_frames = []
        self.phase('rc_scenario', scenario=scenario, stream_id=stream_id)

    def publish_rc(self, channels):
        if self.epoch is None:
            raise RuntimeError("No current control epoch observed")
        self.rc_sequence += 1
        payload = {"version": VERSION, "source": SOURCE, "run_id": self.run_id,
                   "control_epoch": self.epoch, "uav_id": 1, "boot_id": self.boot_id,
                   "stream_id": self.stream_id, "sequence": self.rc_sequence,
                   "produced_monotonic_ns": time.monotonic_ns(), "channels_us": list(channels)}
        self.rc_pub.publish(String(data=json.dumps(payload)))
        self.rc_frames.append(payload)
        self.log.write(json.dumps(dict(wall=time.monotonic() - self.started,
                                       published="rc_frame", message=payload)) + "\n")
        self.log.flush()
        return payload

    def pump_rc(self, channels, seconds):
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            self.publish_rc(channels)
            self.pump()
            time.sleep(0.02)

    def wait_event(self, label, predicate, timeout=20):
        start = len(self.events)
        self.wait(label, lambda: any(predicate(e) for e in self.events[start:]), timeout)

    def send_with_rc(self, msg, label, timeout=45):
        """Setup envelope whose ack wait keeps the neutral RC stream fresh."""
        start = len(self.events)
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        self.sent.append(self.convert(msg))
        self.request_id += 1
        outgoing = self.SetupRequest(version=1, run_id=self.run_id, control_epoch=self.epoch,
                                     request_id=self.request_id, setup=msg)
        self.envelopes.append(self.convert(outgoing))
        self.log.write(json.dumps(dict(wall=time.monotonic() - self.started,
                                       published='SetupRequest', message=self.envelopes[-1],
                                       request_envelope=True)) + '\n')
        self.log.flush()
        expected = self.request_id
        self.setup_pub.publish(outgoing)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(e.get('event') == 'setup_completed' and e.get('request_id') == expected
                   for e in self.events[start:]):
                return
            self.publish_rc(NEUTRAL)
            self.pump()
            time.sleep(0.02)
        raise RuntimeError(label + ' timeout')

    def truth_rows(self, after=0.0):
        rows = []
        with open(self.truth_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["time"] >= after:
                    rows.append(physical(row))
        return rows

    def rc_setup(self):
        self.pump_rc(NEUTRAL, 1.5)
        self.wait_event("rc_candidate", lambda e: e.get("event") == "rc_frame"
                        and e.get("state") == "CANDIDATE" and e.get("accepted"))
        self.send_with_rc(self.Setup(cmd=self.Setup.ARMING, arming=True), "arming_completed")
        self.send_with_rc(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state="RC_POS_CONTROL"),
                          "rc_setup_completed")

    def land_and_disarm(self):
        try:
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LAND'),
                      'land_mode_completed', 15)
        except RuntimeError:
            pass  # Landing already underway or state changed; ground wait decides.
        self.wait('grounded', lambda: grounded(self.state), 60)
        self.send(self.Setup(cmd=self.Setup.ARMING, arming=False), 'disarm_completed')

    def execute(self):
        self.wait("session_ready", lambda: self.epoch is not None, 30)
        self.rc_setup()
        anchor = self.truth_rows()[-1]
        getattr(self, "scenario_" + self.scenario.replace("-", "_"))(anchor)
        self.phase("rc_scenario_complete", scenario=self.scenario)
        self.land_and_disarm()

    def scenario_movement(self, anchor):
        stick = [1500, 1650, 1500, 1500, 1000, 1500, 1000, 1000]
        self.pump_rc(stick, 4.0)
        rows = self.truth_rows(anchor["time"])
        moved = rows[-1]["position"][0] - anchor["position"][0]
        if not moved > 0.5:
            raise RuntimeError("RC movement produced no physical +x displacement: %r" % moved)
        self.phase("rc_movement_observed", moved_x_m=moved)

    def scenario_recenter(self, anchor):
        stick = [1500, 1650, 1500, 1500, 1000, 1500, 1000, 1000]
        self.pump_rc(stick, 3.0)
        moved_anchor = self.truth_rows()[-1]
        self.pump_rc(NEUTRAL, 4.0)
        rows = self.truth_rows(moved_anchor["time"])
        drift = math.dist(rows[-1]["position"], moved_anchor["position"])
        if not drift < 2.0:
            raise RuntimeError("Recenter drifted beyond transition budget: %r" % drift)
        self.phase("rc_recenter_observed", drift_m=drift)

    def scenario_yaw(self, anchor):
        stick = [1500, 1500, 1500, 1650, 1000, 1500, 1000, 1000]
        self.pump_rc(stick, 3.0)
        self.pump_rc(NEUTRAL, 1.0)
        self.phase("rc_yaw_segment_done")

    def _stream_stall_once(self):
        stick = [1500, 1650, 1500, 1500, 1000, 1500, 1000, 1000]
        self.pump_rc(stick, 2.0)
        self.phase("stall_begin")
        self.wait_event("rc_revoked", lambda e: e.get("event") == "control_revoked"
                        and "rc_input_revoked" in str(e.get("reason")), 20)
        self.pump_rc(NEUTRAL, 2.0)
        self.phase("rc_stall_revoke_observed")

    def scenario_stream_stall(self, anchor):
        self._stream_stall_once()

    def scenario_mode_out(self, anchor):
        stick = [1500, 1650, 1500, 1500, 1000, 1500, 1000, 1000]
        self.pump_rc(stick, 2.0)
        mode = "POSCTL" if self.flight_stack == "px4" else "AUTO.LOITER"
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode=mode), "mode_out_completed")
        self.wait_event("mode_out_revoked", lambda e: e.get("event") == "control_revoked"
                        and "external_mode_left" in str(e.get("reason")), 10)
        self.phase("rc_mode_out_observed", mode=mode)

    def scenario_new_takeover(self, anchor):
        self._stream_stall_once()
        self.stream_id = "%032x" % (int(self.stream_id, 16) + 1)
        self.rc_sequence = 0
        self.rc_setup()
        stick = [1500, 1650, 1500, 1500, 1000, 1500, 1000, 1000]
        self.pump_rc(stick, 2.0)
        rows = self.truth_rows(anchor["time"])
        moved = rows[-1]["position"][0] - anchor["position"][0]
        if not moved > 0.3:
            raise RuntimeError("New takeover produced no physical movement: %r" % moved)
        self.phase("rc_new_takeover_observed", moved_x_m=moved)
