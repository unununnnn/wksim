"""Read-only live truth -> UE loopback bridge for the local boundary diagnostic.

The shared trace file crosses the private WSL network namespace without exposing
DDS or modifying firewall rules. This diagnostic transport is NOT the final ROS2
scene/state distribution module. UE acknowledgements never gate physics/control.
"""
import json
import math


class LatestTruth:
    """Tail complete JSONL records; coalesce backlog, retain an incomplete line."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.pending = b""
        self.records = 0

    def poll(self):
        if not self.path.is_file():
            return None
        with self.path.open("rb") as source:
            source.seek(self.offset)
            chunk = source.read()
            self.offset = source.tell()
        lines = (self.pending + chunk).split(b"\n")
        self.pending = lines.pop()
        if not lines:
            return None
        self.records += len(lines)
        record = json.loads(lines[-1])
        # AP records include their servo frame. PX4 records have no frame field:
        # use this trace's complete-record ordinal, not an invented FC counter.
        record.setdefault("frame", self.records)
        return record


def packet_from_truth(record, run_id, vehicle_id):
    if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
        raise ValueError("Expected lowercase UUID hex run identity")
    if vehicle_id not in ("px4", "arducopter"):
        raise ValueError("Unknown flight stack")
    vehicle = record["vehicle"]
    sequence, stamp = record["frame"], record["time"]
    if type(sequence) is not int or not 0 <= sequence <= 2**53 - 1:
        raise ValueError("Invalid sequence")
    fields = vehicle[6:9] + vehicle[12:16] + vehicle[16:20]
    if len(fields) != 11 or any(type(v) not in (int, float) or not math.isfinite(v) for v in fields + [stamp]):
        raise ValueError("Invalid physical state")
    if stamp < 0 or max(map(abs, vehicle[6:9])) > 1e6:
        raise ValueError("Invalid time or position")
    if abs(sum(v*v for v in vehicle[12:16]) - 1) > 1e-5:
        raise ValueError("Invalid quaternion norm")
    if any(not 0 <= v <= 100000 for v in vehicle[16:20]):
        raise ValueError("Invalid rotor speed")
    return dict(version=1, run_id=run_id, vehicle_id=vehicle_id, sequence=sequence,
                sim_time_s=stamp, position_ned_m=vehicle[6:9],
                quaternion_wxyz=vehicle[12:16], rotor_rpm=vehicle[16:20])


def actor_errors(packet, ack):
    """Actor readback, not proof that a frame was rendered. Quat sign invariant."""
    if ack["run_id"] != packet["run_id"] or ack["sequence"] != packet["sequence"]:
        raise ValueError("Uncorrelated UE acknowledgement")
    p, q = packet["position_ned_m"], packet["quaternion_wxyz"]
    expected_p = [p[0]*100, p[1]*100, -p[2]*100]
    expected_q = [-q[1], -q[2], q[3], q[0]]
    actual_p, actual_q = ack["ue_position_cm"], ack["ue_quaternion_xyzw"]
    if len(actual_p) != 3 or len(actual_q) != 4 or not all(
            type(v) in (int, float) and math.isfinite(v) for v in actual_p + actual_q + [ack["sim_time_s"]]):
        raise ValueError("Invalid UE readback")
    # UE normalizes actor rotations. Compare normalized source, not raw drift.
    norm = math.sqrt(sum(v*v for v in expected_q))
    expected_q = [v/norm for v in expected_q]
    return dict(position_cm=math.dist(expected_p, actual_p),
                quaternion_l2=min(math.dist(expected_q, actual_q), math.dist(expected_q, [-v for v in actual_q])),
                sim_time_s=abs(packet["sim_time_s"] - ack["sim_time_s"]))
