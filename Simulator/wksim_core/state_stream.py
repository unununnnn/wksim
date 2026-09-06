"""View-only product state. A failed renderer must never wait the physics loop."""
import json
import math
import re
import socket
import time

MAX_PACKET = 4096
MAX_AGE = 0.75
METADATA = dict(position_frame="NED", position_unit="m", quaternion_order="WXYZ",
                body_frame="FRD", rotor_unit="rpm", rotor_order=["FR", "RL", "FL", "RR"],
                configuration="quad-X")


def identity(run_id, vehicle_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        raise ValueError("run_id must be 1..64 ASCII letters/digits/underscore/hyphen, starting with a letter or digit")
    if type(vehicle_id) is not int or vehicle_id != 1:
        raise ValueError("This product stream supports vehicle_id 1 only")


def validate(packet, run_id, vehicle_id=1, now=None):
    identity(run_id, vehicle_id)
    if not isinstance(packet, dict):
        raise ValueError("Expected state object")
    if (type(packet.get("version")) is not int or packet["version"] != 2 or
            packet.get("run_id") != run_id or type(packet.get("vehicle_id")) is not int or
            packet["vehicle_id"] != vehicle_id or any(packet.get(k) != v for k, v in METADATA.items())):
        raise ValueError("Wrong identity or state convention")
    seq = packet.get("sequence")
    if type(seq) is not int or not 0 <= seq <= 2**53-1:
        raise ValueError("Invalid sequence")
    for key, length in (("position_ned_m", 3), ("quaternion_wxyz", 4), ("rotor_rpm", 4)):
        values = packet.get(key)
        if not isinstance(values, list) or len(values) != length or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("Invalid " + key)
    for key in ("sim_time_s", "source_wall_time_s"):
        value = packet.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid source time")
    age = (time.time() if now is None else now) - packet["source_wall_time_s"]
    if not -0.25 <= age <= MAX_AGE:
        raise ValueError("Expired or future state")
    if (max(map(abs, packet["position_ned_m"])) > 1e6 or
            abs(sum(v*v for v in packet["quaternion_wxyz"]) - 1) > 1e-5 or
            any(not 0 <= v <= 100000 for v in packet["rotor_rpm"])):
        raise ValueError("Invalid physical state")
    return packet


class LatestState:
    """One accepted state, never a playback queue. Rejected input cannot reset it."""
    def __init__(self, run_id, vehicle_id=1):
        identity(run_id, vehicle_id)
        self.run_id, self.vehicle_id = run_id, vehicle_id
        self.packet = None
        self.rejected = 0

    def accept(self, raw, now=None):
        try:
            if len(raw) > MAX_PACKET:
                raise ValueError("Oversize state")
            packet = validate(json.loads(raw), self.run_id, self.vehicle_id, now)
            if self.packet and (packet["sequence"] <= self.packet["sequence"] or
                                packet["sim_time_s"] <= self.packet["sim_time_s"]):
                raise ValueError("Old state")
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            self.rejected += 1
            return False
        self.packet = packet
        return True

    def current(self):
        if self.packet:
            try:
                return validate(self.packet, self.run_id, self.vehicle_id)
            except ValueError:
                pass
        return None


class StateWriter:
    def __init__(self, path=None, run_id=None, vehicle_id=1):
        self.socket = None
        self.sequence = 0
        self.dropped = 0
        if path is not None:
            identity(run_id, vehicle_id)
            self.path, self.run_id, self.vehicle_id = str(path), run_id, vehicle_id
            if not self.path.startswith("/") or len(self.path.encode()) > 107:
                raise ValueError("state_socket requires an absolute Linux pathname <=107 bytes")
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.socket.setblocking(False)

    def emit(self, state):
        if self.socket is None:
            return False
        self.sequence += 1
        packet = dict(METADATA, version=2, run_id=self.run_id, vehicle_id=self.vehicle_id,
                      sequence=self.sequence, sim_time_s=state[2], source_wall_time_s=time.time(),
                      position_ned_m=state[6:9], quaternion_wxyz=state[12:16], rotor_rpm=state[16:20])
        try:
            validate(packet, self.run_id, self.vehicle_id)
            raw = json.dumps(packet, separators=(",", ":"), allow_nan=False).encode()
            if len(raw) > MAX_PACKET:
                raise ValueError("Oversize state")
            self.socket.sendto(raw, self.path)
            return True
        except (OSError, ValueError, TypeError, OverflowError):
            self.dropped += 1
            return False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.socket:
            self.socket.close()


def add_arguments(parser):
    parser.add_argument("--state-socket", help="Optional view-only Linux pathname datagram endpoint")
    parser.add_argument("--run-id", help="Required with --state-socket; same identity as runtime config")
    parser.add_argument("--vehicle-id", type=int, default=1)
