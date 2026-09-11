"""Independent BODY-velocity MOVE → native setpoint audit for ArUco tracking runs.

Scope (deliberately narrow): whether each accepted public MOVE/XYZ_VEL_BODY
command became the expected native setpoint, with real IEEE quantization and
raw-CDR provenance. No HOLD verdicts, no flight-completion claims, and no
change to any run's existing verdict (tracking-08 stays failed on rate).

Timing derivation, verified against the installed sources:
- ``command.py:87-96``: yaw comes from the normalized ``state.attitude_q``.
- ``command.py`` ``step``: the first resolve_move result for a BODY command is
  cached (``body_reference``); ``resolve_move`` rotates XY by that yaw and
  leaves Z unrotated; shaping (``shaping.py:87-91``) with yaw_rate_mode returns
  the velocity and a float32 yaw rate directly, without deadband.
- ``node.py``: ``on_command`` only accepts; ``tick`` reads native state, then
  drives (publishing native setpoints), then publishes SessionState. So the
  native samples a command produces are published in the SAME tick, BEFORE the
  SessionState that first carries its request id. Every native sample is
  therefore mapped to the immediately following SessionState (strict
  source_timestamp bounds, adjacent sequence, same epoch) and attributed to
  that state's ``last_request_id``. The reference state for the cached BODY yaw
  remains the first SessionState carrying the request.
- Requests without such a state (rejected pre-acceptance, merged, unexecuted)
  are never treated as accepted; they are listed unresolved, not matched.

Only the frozen scenario is accepted: agent_cmd MOVE(4), move_mode
XYZ_VEL_BODY(4), yaw_rate_mode True, yaw_rate_ref 0. PX4 raw
TrajectorySetpoint carries NED float32 velocities with position/acceleration/
jerk/yaw NaN and yawspeed=-rate; AP cmd_vel TwistStamped/map carries the ENU
double velocity unswapped (native_arducopter.py writes target.velocity
directly) plus the yaw rate. Every declared MOVE needs at least one native
sample, and all corresponding samples must match bit-exactly (float32 for
PX4, double for AP). A unique observed publisher GID is required for
consistency but does NOT prove graph-wide publisher exclusivity.

Evidence envelope (aruco_raw_capture): exactly one start record at row 0 and
one end record at the last row; start carries the capture node identity,
run/epoch/uav; end carries status complete, per-topic sample counts and the
final chain hash — all verified against the actual rows, not just the chain.

Runs only where the ROS message overlays are importable (WSL); no nodes are
created. Usage:
  python3 -B tools/audit_aruco_native_moves.py <epoch_dir> --output <new.json>
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ZERO_HASH = "0" * 64
COMMAND_TOPIC_SUFFIX = "/prometheus/v2/command"
STATE_TOPIC_SUFFIX = "/prometheus/v2/state"
PX4_SETPOINT_SUFFIX = "/fmu/in/trajectory_setpoint"
AP_VELOCITY_TOPIC = "/ap/cmd_vel"
MOVE, XYZ_VEL_BODY = 4, 4
STACK_UAV = {"arducopter": "1", "px4": "2"}


def fail(failures, code, **detail):
    failures.append(dict(code=code, **detail))


def verify_chain(rows, failures, name):
    previous = ZERO_HASH
    for index, row in enumerate(rows):
        recorded = row.get("record_sha256")
        if row.get("prev_record_sha256") != previous:
            fail(failures, "hash_chain_broken", file=name, row=index)
        content = {k: v for k, v in row.items() if k != "record_sha256"}
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != recorded:
            fail(failures, "record_hash_mismatch", file=name, row=index)
        previous = recorded


def verify_envelope(rows, data, stack, failures, unresolved):
    """Start/end/count/identity of the raw capture, beyond the hash chain."""
    name = Path  # placeholder-free local reference
    if not rows or rows[0].get("kind") != "aruco_raw_capture_start":
        fail(failures, "capture_start_missing", stack=stack)
        return
    if rows[-1].get("kind") != "aruco_raw_capture_end":
        fail(failures, "capture_end_missing", stack=stack)
        return
    if any(r.get("kind") in ("aruco_raw_capture_start", "aruco_raw_capture_end")
           for r in rows[1:-1]):
        fail(failures, "capture_marker_in_stream", stack=stack)
    start, end = rows[0], rows[-1]
    if (start.get("node_name") != f"wksim_aruco_raw_{stack}"
            or str(start.get("uav_id")) != STACK_UAV[stack]):
        fail(failures, "capture_identity_differs", stack=stack)
    run_id, epoch = start.get("run_id"), start.get("epoch")
    if not run_id or not isinstance(epoch, str) or len(epoch) != 32:
        fail(failures, "capture_run_epoch_invalid", stack=stack)
    if end.get("status") != "complete":
        fail(failures, "capture_incomplete", stack=stack,
             status=end.get("status"))
    counts = {}
    for row in data:
        counts[row["topic"]] = counts.get(row["topic"], 0) + 1
    declared = end.get("samples_per_topic", {})
    if end.get("total_samples") != len(data) or declared != counts:
        fail(failures, "capture_sample_count_differs", stack=stack,
             actual_total=len(data), declared_total=end.get("total_samples"))
    if data and (end.get("final_hash_chain") != data[-1].get("record_sha256")
                 or end.get("prev_record_sha256") != data[-1].get("record_sha256")):
        fail(failures, "capture_final_hash_differs", stack=stack)
    if end.get("write_failure_reports"):
        fail(failures, "capture_write_failures", stack=stack)
    return run_id, epoch


def decode(rows, types_module):
    from rclpy.serialization import deserialize_message
    for row in rows:
        cls = getattr(types_module, row["type"].split("/")[-1])
        yield row, deserialize_message(bytes.fromhex(row["cdr_hex"]), cls)


def quaternion_yaw(w, x, y, z):
    """Independent but numerically identical to command.py update_state:
    math.hypot normalization (NOT sqrt of summed squares) then atan2."""
    norm = math.hypot(w, x, y, z)
    if not math.isfinite(norm) or norm < 1e-9:
        raise ValueError("zero quaternion in reference state")
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def px4_expected(velocity_body, yaw, np):
    """rotate_xy into the world frame, then ENU->NED with float32 on the wire."""
    vx, vy, vz = (float(v) for v in velocity_body)
    east = vx * math.cos(yaw) - vy * math.sin(yaw)    # world ENU x
    north = vx * math.sin(yaw) + vy * math.cos(yaw)   # world ENU y
    f32 = np.float32
    return {"velocity": [f32(north), f32(east), f32(-vz)],  # NED = [y, x, -z]
            "yawspeed": f32(-0.0)}


def ap_expected(velocity_body, yaw):
    """native_arducopter writes target.velocity unswapped into Twist.linear:
    linear.x = world ENU x (east), linear.y = world ENU y (north)."""
    vx, vy, vz = (float(v) for v in velocity_body)
    east = vx * math.cos(yaw) - vy * math.sin(yaw)
    north = vx * math.sin(yaw) + vy * math.cos(yaw)
    return {"linear": (east, north, vz), "angular_z": 0.0}


def audit_stack(path, stack, failures, unresolved):
    import numpy as np
    from importlib import import_module
    with open(path, encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    verify_chain(rows, failures, Path(path).name)
    data = [r for r in rows if r.get("kind") == "raw_cdr_sample"]
    envelope = verify_envelope(rows, data, stack, failures, unresolved)
    if not data:
        unresolved.append(dict(stack=stack, reason="no raw samples"))
        return {"stack": stack, "moves": []}
    run_id, epoch = envelope if envelope else (None, None)
    wksim_msgs = import_module("wksim_msgs.msg")
    commands = [(r, m) for r, m in decode(
        [r for r in data if r["topic"].endswith(COMMAND_TOPIC_SUFFIX)], wksim_msgs)]
    states = [(r, m) for r, m in decode(
        [r for r in data if r["topic"].endswith(STATE_TOPIC_SUFFIX)], wksim_msgs)]
    if stack == "px4":
        px4_msgs = import_module("px4_msgs.msg")
        native = [(r, m) for r, m in decode(
            [r for r in data if r["topic"].endswith(PX4_SETPOINT_SUFFIX)], px4_msgs)]
    else:
        geometry = import_module("geometry_msgs.msg")
        native = [(r, m) for r, m in decode(
            [r for r in data if r["topic"] == AP_VELOCITY_TOPIC], geometry)]
    gids = {r["publisher_gid"] for r, _ in native}
    if len(gids) > 1:
        fail(failures, "native_publisher_gid_not_unique", stack=stack, gids=sorted(gids))
    for i in range(1, len(states)):
        previous, current = states[i - 1], states[i]
        if current[1].sequence != previous[1].sequence + 1:
            fail(failures, "session_state_sequence_gap", stack=stack,
                 at_sequence=int(current[1].sequence))
        if current[1].control_epoch != previous[1].control_epoch:
            fail(failures, "session_state_epoch_changed", stack=stack)
        if current[0]["source_timestamp"] <= previous[0]["source_timestamp"]:
            fail(failures, "session_state_time_regressed", stack=stack)
    # control_epoch is the control-session epoch, deliberately NOT the scene
    # epoch: run identity is run_id; control_epoch must be consistent within
    # this stack's commands and states.
    # A coordination stack can publish SessionState without receiving any
    # public command (for example, the non-tracking vehicle in an ArUco run).
    # Anchor that stack to its observed state epoch instead of comparing every
    # state against None.  When commands exist they remain authoritative, so a
    # command/state epoch mismatch is still rejected below.
    control_epoch = (commands[0][1].control_epoch if commands else
                     states[0][1].control_epoch if states else None)
    for row, message in commands:
        if message.run_id != run_id or message.control_epoch != control_epoch:
            fail(failures, "command_identity_differs", stack=stack,
                 request_id=message.request_id)
    for _, state in states:
        if state.run_id != run_id or state.control_epoch != control_epoch:
            fail(failures, "state_identity_differs", stack=stack,
                 sequence=int(state.sequence))
    # Reference state: the first SessionState carrying each request, strictly
    # after the command left the task. Only requests with one are executed.
    references = {}
    for row, message in commands:
        for position, (state_row, state) in enumerate(states):
            if (state.last_request_id == message.request_id
                    and state.control_epoch == message.control_epoch
                    and state_row["source_timestamp"] > row["source_timestamp"]):
                references[message.request_id] = (position, state_row, state)
                break
    # Every native sample maps to the SessionState published in its own tick:
    # strict bounds previous_state.source < sample.source < following_state.source.
    # Equality on either bound is ambiguous and the sample is never attributed.
    import bisect
    state_timestamps = [row["source_timestamp"] for row, _ in states]
    attributed = {}
    unattributed = 0
    ambiguous = 0
    for row, message in native:
        stamp = row["source_timestamp"]
        position = bisect.bisect_right(state_timestamps, stamp)
        if position >= len(states):
            unattributed += 1
            continue
        if position > 0 and stamp <= state_timestamps[position - 1]:
            ambiguous += 1  # Equal to the previous state's stamp: ambiguous.
            continue
        state = states[position][1]
        attributed.setdefault(state.last_request_id, []).append((row, message))
    if unattributed:
        unresolved.append(dict(stack=stack, reason="native samples after the last SessionState",
                               samples=unattributed))
    if ambiguous:
        unresolved.append(dict(stack=stack,
                               reason="native samples exactly on a SessionState timestamp bound",
                               samples=ambiguous))
    moves = []
    last_command_id = 0
    for row, message in commands:
        command = message.command
        if (command.agent_cmd != MOVE or command.move_mode != XYZ_VEL_BODY
                or command.yaw_rate_mode is not True or command.yaw_rate_ref != 0):
            continue  # Outside the frozen scenario: excluded, not judged.
        rid = message.request_id
        entry = {"request_id": rid, "command_id": command.command_id,
                 "source_timestamp": row["source_timestamp"]}
        moves.append(entry)
        if command.command_id <= last_command_id:
            fail(failures, "command_id_not_increasing", stack=stack, request_id=rid)
        last_command_id = command.command_id
        reference = references.get(rid)
        if reference is None:
            # Rejected pre-acceptance, merged, or unexecuted: never accepted.
            unresolved.append(dict(stack=stack, request_id=rid,
                                   reason="no SessionState carried this request; rejected/merged/unexecuted"))
            entry["status"] = "unresolved"
            continue
        position, state_row, state = reference
        if position == 0 or states[position - 1][1].sequence != state.sequence - 1:
            fail(failures, "reference_state_sequence_not_adjacent", stack=stack, request_id=rid)
        q = state.state.attitude_q
        yaw = quaternion_yaw(q.w, q.x, q.y, q.z)
        velocity = [float(v) for v in command.velocity_ref]  # wire float32 values
        window = [m for _, m in attributed.get(rid, [])]
        if not window:
            unresolved.append(dict(stack=stack, request_id=rid,
                                   reason="no native setpoint sample attributed to this request"))
            entry["status"] = "unresolved"
            continue
        if stack == "px4":
            expected = px4_expected(velocity, yaw, np)
            consistent = all(
                all(math.isnan(v) for v in (*m.position, *m.acceleration, *m.jerk))
                and math.isnan(m.yaw)
                and all(np.float32(a) == np.float32(b) for a, b in
                        zip(m.velocity, expected["velocity"]))
                and np.float32(m.yawspeed) == expected["yawspeed"]
                for m in window)
        else:
            expected = ap_expected(velocity, yaw)
            consistent = all(
                m.header.frame_id == "map"
                and (float(m.twist.linear.x), float(m.twist.linear.y),
                     float(m.twist.linear.z)) == expected["linear"]
                and float(m.twist.angular.z) == expected["angular_z"]
                for m in window)
        if not consistent:
            fail(failures, "native_setpoint_differs", stack=stack, request_id=rid,
                 samples=len(window))
            entry["status"] = "failed"
            continue
        entry.update(status="proven", samples=len(window), yaw_rad=yaw,
                     reference_state_sequence=int(state.sequence),
                     native_gids=len(gids))
    return {"stack": stack, "run_id": run_id, "epoch": epoch,
            "native_samples": len(native), "native_publisher_gids": sorted(gids),
            "moves": moves}


def audit_epoch(epoch_dir):
    epoch_dir = Path(epoch_dir)
    failures, unresolved = [], []
    stacks = {}
    for path in sorted(epoch_dir.glob("tasks/*/*/aruco-raw-dds.jsonl")):
        stacks[path.parent.name] = audit_stack(path, path.parent.name,
                                               failures, unresolved)
    if set(stacks) != {"arducopter", "px4"}:
        unresolved.append(dict(reason="incomplete dual-stack raw capture",
                               present=sorted(stacks)))
    proven = [m for side in stacks.values() for m in side["moves"] if m.get("status") == "proven"]
    status = ("failed" if failures else
              "pass" if proven and not unresolved else
              "unresolved")
    return {"schema": "wksim.aruco-native-moves.v2", "status": status,
            "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "raw_sha256": {str(p.relative_to(epoch_dir)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(epoch_dir.glob('tasks/*/*/aruco-raw-dds.jsonl'))},
            "scope": "BODY velocity MOVE to native setpoint only; no HOLD/flight/rate verdict",
            "stacks": stacks, "failures": failures, "unresolved": unresolved,
            "proven_moves": len(proven),
            "uncovered": ["unique observed publisher GID is not graph-wide publisher exclusivity",
                          "record_sha256 recomputation uses the capture module's canonical-JSON rule",
                          "HOLD/hover replacement and full flight acceptance are out of scope"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epoch_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_epoch(args.epoch_dir)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "proven_moves")}))
    print(f"failures={len(result['failures'])} unresolved={len(result['unresolved'])}")
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
