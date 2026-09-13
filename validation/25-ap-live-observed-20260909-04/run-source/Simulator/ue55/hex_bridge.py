"""Experimental Hex live raw tail -> bounded WSL pull -> Windows UE loopback.

No native library is loaded. No state is replayed or sent into physics/control.
Run with -m Simulator.ue55.hex_bridge; --relay is the owned Linux child mode.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from Simulator.ue55.bridge import actor_errors

MAX_AGE = .75
MAX_PACKET = 8192
MAX_RAW = 65536
ANGLES = (90, 270, 330, 150, 30, 210)
SPINS = (1, -1, 1, -1, -1, 1)
ORDER = [f"M{i}" for i in range(1, 7)]
METADATA = dict(position_frame="NED", position_unit="m", quaternion_order="WXYZ",
                body_frame="FRD", rotor_unit="rpm", configuration="hex-X")
SOURCE_KEYS = {"version", "kind", "run_id", "instance_id", "model_identity", "vehicle_id",
               "sequence", "step", "sim_time_ns", "sim_time_s", "source_monotonic_s",
               "source_age_s", "rotor_order", "position_ned_m", "quaternion_wxyz", "rotor_rpm", *METADATA}
DISPLAY_KEYS = {"display_clock", "display_wall_time_s", "transport_age_bound_s"}


def binding(run_id, instance_id, model_identity):
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        raise ValueError("Invalid run identity")
    if not isinstance(instance_id, str) or not re.fullmatch(r"[0-9a-f]{32}", instance_id):
        raise ValueError("Invalid view instance")
    if not isinstance(model_identity, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", model_identity):
        raise ValueError("Invalid model identity")
    return dict(run_id=run_id, instance_id=instance_id, model_identity=model_identity)


def number(value, minimum=-math.inf, maximum=math.inf):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def integer(value, maximum=2**53-1):
    return type(value) is int and 0 <= value <= maximum


def vector(value, count, minimum=-math.inf, maximum=math.inf):
    return type(value) is list and len(value) == count and all(number(x, minimum, maximum) for x in value)


def validate(packet, expected, *, now=None, source=False):
    keys = SOURCE_KEYS if source else SOURCE_KEYS | DISPLAY_KEYS
    if type(packet) is not dict or set(packet) != keys:
        raise ValueError("Unexpected Hex state fields")
    if any(packet[k] != value for k, value in expected.items()) or any(packet[k] != v for k, v in METADATA.items()):
        raise ValueError("Foreign binding or coordinate metadata")
    if (type(packet["version"]) is not int or packet["version"] != 4 or packet["kind"] != "hex_state" or
            type(packet["vehicle_id"]) is not int or packet["vehicle_id"] != 1 or packet["rotor_order"] != ORDER):
        raise ValueError("Wrong version/vehicle/motor layout")
    if (not integer(packet["sequence"]) or not integer(packet["step"], 9007199254) or
            not integer(packet["sim_time_ns"]) or packet["sim_time_ns"] != packet["step"] * 1000000 or
            not number(packet["sim_time_s"], 0) or abs(packet["sim_time_s"] - packet["step"] / 1000) > 1e-8 or
            not number(packet["source_monotonic_s"], 0) or not number(packet["source_age_s"], 0, MAX_AGE)):
        raise ValueError("Invalid source clock")
    if (not vector(packet["position_ned_m"], 3, -1e6, 1e6) or
            not vector(packet["quaternion_wxyz"], 4) or
            abs(sum(x*x for x in packet["quaternion_wxyz"]) - 1) > 1e-5 or
            not vector(packet["rotor_rpm"], 6, 0, 100000)):
        raise ValueError("Invalid six-motor physical state")
    if not source:
        now = time.time() if now is None else now
        if (packet["display_clock"] != "windows_utc_bound" or
                not number(packet["transport_age_bound_s"], packet["source_age_s"], MAX_AGE) or
                not number(packet["display_wall_time_s"]) or not number(now) or
                not -.25 <= now - packet["display_wall_time_s"] <= MAX_AGE):
            raise ValueError("Stale/future Windows display bound")
    return packet


def packet_from_record(record, expected, now_ns):
    output = record.get("output120")
    tick, observed = record.get("tick"), record.get("observed_monotonic_ns")
    if (record.get("kind") != "step" or not vector(output, 120) or not integer(tick, 9007199254) or
            type(observed) is not int or observed < 0 or type(now_ns) is not int or now_ns < observed):
        raise ValueError("Invalid native raw step")
    packet = dict(version=4, kind="hex_state", **expected, vehicle_id=1, sequence=tick, step=tick,
                  sim_time_ns=tick * 1000000, sim_time_s=output[2], source_monotonic_s=observed / 1e9,
                  source_age_s=(now_ns-observed)/1e9, **METADATA, rotor_order=ORDER.copy(),
                  position_ned_m=output[6:9], quaternion_wxyz=output[12:16], rotor_rpm=output[16:22])
    return validate(packet, expected, source=True)


class LiveRawTail:
    """Read appended complete raw records once, with immutable start binding."""
    def __init__(self, path, expected):
        self.path, self.expected = Path(path), expected
        self.identity = None
        self.offset = 0
        self.pending = b""
        self.started = False
        self.ended = False
        self.last_tick = -1
        self.last_monotonic = -1
        # Existing records are never candidate state, even if their clock is recent.
        if self.path.exists():
            self._open(existing=True)

    def _start(self, record):
        if (record.get("kind") != "start" or record.get("schema") != "wksim.hex.physics.v1" or
                record.get("run_id") != self.expected["run_id"] or
                record.get("model_identity") != self.expected["model_identity"]):
            raise ValueError("Raw start does not match launcher-verified run/model")
        self.started = True

    def _open(self, existing=False):
        with self.path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            self.identity = (info.st_dev, info.st_ino)
            if existing and info.st_size:
                self._start(json.loads(stream.readline(MAX_RAW + 1)))
                # Retire existing completed traces without consuming recorded state.
                stream.seek(max(0, info.st_size-MAX_RAW))
                tail = stream.read().split(b"\n")
                if len(tail) > 1 and tail[-2]:
                    last = json.loads(tail[-2])
                    if last.get("kind") == "end":
                        self.ended = True
                stream.seek(-1, 2)
                if stream.read(1) != b"\n":
                    raise ValueError("Existing raw trace ends in an incomplete record")
                self.offset = info.st_size

    def poll(self, now_ns=None):
        if self.ended:
            return None
        if self.identity is None:
            if not self.path.exists():
                return None
            self._open()
        info = self.path.stat()
        if (info.st_dev, info.st_ino) != self.identity or info.st_size < self.offset:
            raise ConnectionError("Owned live raw file was replaced or truncated")
        with self.path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != self.identity or opened.st_size < self.offset:
                raise ConnectionError("Owned live raw file changed before read")
            stream.seek(self.offset)
            chunk = stream.read(8 * 1024 * 1024)
            self.offset = stream.tell()
        lines = (self.pending + chunk).split(b"\n")
        self.pending = lines.pop()
        if len(self.pending) > MAX_RAW or any(len(line) > MAX_RAW for line in lines):
            raise ValueError("Oversize native raw record")
        latest = None
        for line in lines:
            record = json.loads(line)
            if type(record) is not dict:
                raise ValueError("Raw record must be an object")
            kind = record.get("kind")
            if kind == "start":
                if self.started:
                    raise ValueError("Unexpected repeated physical lifetime")
                self._start(record)
            elif not self.started:
                raise ValueError("Raw step arrived before bound start")
            elif kind == "end":
                self.ended = True
                latest = None
                break
            elif kind == "step":
                tick, mono = record.get("tick"), record.get("observed_monotonic_ns")
                if not integer(tick, 9007199254) or type(mono) is not int or tick <= self.last_tick or mono <= self.last_monotonic:
                    raise ValueError("Replayed or regressed raw step")
                self.last_tick, self.last_monotonic = tick, mono
                latest = record
            elif kind not in ("initialized", "actuator"):
                raise ValueError("Unknown raw record")
        if latest is None or self.offset < info.st_size:
            return None
        try:
            return packet_from_record(latest, self.expected, time.monotonic_ns() if now_ns is None else now_ns)
        except ValueError:
            return None  # Consume expired/invalid samples once; never retimestamp.


def display_packet(envelope, expected, roundtrip_s, windows_wall):
    if type(envelope) is not dict or set(envelope) != {"packet", "relay_monotonic_s", "ended"} or type(envelope["ended"]) is not bool:
        raise ValueError("Invalid Hex relay envelope")
    if not number(roundtrip_s, 0, MAX_AGE) or not number(windows_wall) or not number(envelope["relay_monotonic_s"], 0):
        raise ValueError("Invalid or expired pipe timing")
    if envelope["ended"] or envelope["packet"] is None:
        return None
    packet = validate(envelope["packet"], expected, source=True)
    source_age = envelope["relay_monotonic_s"] - packet["source_monotonic_s"]
    if source_age < 0 or source_age + 1e-6 < packet["source_age_s"]:
        raise ValueError("Invalid Linux monotonic bound")
    bound = source_age + roundtrip_s
    mapped = dict(packet, display_clock="windows_utc_bound", display_wall_time_s=windows_wall-bound,
                  transport_age_bound_s=bound)
    return validate(mapped, expected, now=windows_wall)


class LatestHex:
    def __init__(self, expected):
        self.expected, self.packet = expected, None

    def accept(self, packet, now=None):
        validate(packet, self.expected, now=now)
        if self.packet is not None and any(packet[key] <= self.packet[key] for key in ("sequence", "step", "source_monotonic_s")):
            raise ValueError("Replayed/stale Hex packet")
        self.packet = packet
        return packet


def actor_readback_errors(packet, ack, previous=None):
    """Independent pose/geometry/RPM/yaw and accepted-step phase observations."""
    if (type(ack) is not dict or ack.get("kind") != "hex_actor" or ack.get("version") != 4 or
            any(ack.get(k) != packet[k] for k in ("run_id", "instance_id", "model_identity", "vehicle_id", "sequence", "step", "sim_time_ns"))):
        raise ValueError("Uncorrelated Hex Actor ACK")
    errors = actor_errors(packet, ack)
    rotors = ack.get("rotors")
    if type(rotors) is not list or len(rotors) != 6 or ack.get("geometry_offset_cm") != [0, 0, 10]:
        raise ValueError("Missing six actual rotor components")
    errors.update(origin_local_cm=0., origin_world_cm=0., rpm=0., yaw_deg=0., diameter_cm=0., phase_deg=None)
    phases = []
    for i, rotor in enumerate(rotors):
        if (rotor.get("motor") != ORDER[i] or type(rotor.get("spin")) is not int or rotor["spin"] != SPINS[i] or
                not all(vector(rotor.get(k), 3) for k in ("origin_local_cm", "origin_world_cm", "mesh_extent_cm", "scale")) or
                not all(number(rotor.get(k)) for k in ("rpm", "yaw_deg", "phase_deg"))):
            raise ValueError("Invalid actual rotor readback")
        expected_mesh = "/Game/Wksim/P450/SM_p450_cw.SM_p450_cw" if SPINS[i] > 0 else "/Game/Wksim/P450/SM_p450_ccw.SM_p450_ccw"
        if rotor.get("mesh") != expected_mesh or not rotor["scale"][0] > 0 or max(rotor["scale"]) != min(rotor["scale"]):
            raise ValueError("Wrong spin mesh or nonuniform scale")
        a = math.radians(ANGLES[i])
        local = [22.5 * math.cos(a), 22.5 * math.sin(a), 10.]
        # Rotate using independently converted source quaternion, not ACK orientation.
        w, x, y, z = packet["quaternion_wxyz"]
        x, y = -x, -y
        norm = math.sqrt(w*w+x*x+y*y+z*z)
        w, x, y, z = (v/norm for v in (w, x, y, z))
        vx, vy, vz = local
        world = [(1-2*y*y-2*z*z)*vx + (2*x*y-2*z*w)*vy + (2*x*z+2*y*w)*vz,
                 (2*x*y+2*z*w)*vx + (1-2*x*x-2*z*z)*vy + (2*y*z-2*x*w)*vz,
                 (2*x*z-2*y*w)*vx + (2*y*z+2*x*w)*vy + (1-2*x*x-2*y*y)*vz]
        p = packet["position_ned_m"]
        world = [world[0]+100*p[0], world[1]+100*p[1], world[2]-100*p[2]]
        errors["origin_local_cm"] = max(errors["origin_local_cm"], math.dist(local, rotor["origin_local_cm"]))
        errors["origin_world_cm"] = max(errors["origin_world_cm"], math.dist(world, rotor["origin_world_cm"]))
        errors["rpm"] = max(errors["rpm"], abs(packet["rotor_rpm"][i]-rotor["rpm"]))
        errors["yaw_deg"] = max(errors["yaw_deg"], abs((rotor["yaw_deg"]-rotor["phase_deg"]+180) % 360-180))
        errors["diameter_cm"] = max(errors["diameter_cm"], abs(2*max(rotor["mesh_extent_cm"][:2])*rotor["scale"][0]-18))
        phases.append(rotor["phase_deg"])
    prior_step = ack.get("previous_step")
    if prior_step == -1:
        errors["phase_deg"] = max(map(abs, phases))
    elif previous is not None and previous.get("step") == prior_step and all(previous.get(k) == ack[k] for k in ("run_id", "instance_id", "model_identity")):
        delta = (packet["step"]-prior_step)/1000
        errors["phase_deg"] = max(abs(phases[i] - previous["rotors"][i]["phase_deg"] - packet["rotor_rpm"][i]*6*delta*SPINS[i]) for i in range(6))
    return errors


def relay(path, expected):
    tail = LiveRawTail(path, expected)
    while True:
        request = sys.stdin.buffer.read(1)
        if not request:
            return
        if request != b"?":
            raise ValueError("Expected bounded state pull")
        packet = tail.poll()
        response = dict(packet=packet, relay_monotonic_s=time.monotonic(), ended=tail.ended)
        print(json.dumps(response, allow_nan=False, separators=(",", ":")), flush=True)


def bridge(repo, path, expected, port, readback, duration=None):
    if not 1024 <= port <= 65535 or (duration is not None and not number(duration, .001, 3600)):
        raise ValueError("Invalid port/duration")
    argv = ["wsl.exe", "-d", "Ubuntu-22.04", "--cd", repo, "--exec", "python3", "-m",
            "Simulator.ue55.hex_bridge", "--relay", "--raw", path]
    for key, value in expected.items():
        argv += ["--"+key.replace("_", "-"), value]
    latest, pending, previous = LatestHex(expected), {}, None
    started = time.monotonic()
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW) as child, \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp, \
            Path(readback).open("x", encoding="utf-8", buffering=1) as evidence:
        udp.bind(("127.0.0.1", 0))
        udp.setblocking(False)
        try:
            while duration is None or time.monotonic()-started < duration:
                requested_at = time.monotonic()
                child.stdin.write(b"?")
                child.stdin.flush()
                raw = child.stdout.readline(MAX_PACKET + 2)
                if not raw or not raw.endswith(b"\n") or len(raw) > MAX_PACKET+1:
                    raise ConnectionError("Hex relay exited or returned oversized response")
                envelope = json.loads(raw)
                try:
                    mapped = display_packet(envelope, expected, time.monotonic()-requested_at, time.time())
                    if mapped:
                        latest.accept(mapped)
                        udp.sendto(json.dumps(mapped, allow_nan=False, separators=(",", ":")).encode(), ("127.0.0.1", port))
                        pending[mapped["sequence"]] = mapped
                        if len(pending) > 128:
                            del pending[next(iter(pending))]
                except (ValueError, OSError):
                    pass
                for _ in range(64):
                    try:
                        ack_raw, sender = udp.recvfrom(MAX_PACKET+1)
                    except (BlockingIOError, ConnectionResetError):
                        break
                    if sender != ("127.0.0.1", port) or len(ack_raw) > MAX_PACKET:
                        continue
                    try:
                        ack = json.loads(ack_raw)
                        packet = pending.get(ack.get("sequence"))
                        if packet is None or previous is not None and ack["sequence"] <= previous["sequence"]:
                            continue
                        errors = actor_readback_errors(packet, ack, previous)
                    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                        continue
                    del pending[ack["sequence"]]
                    previous = ack
                    evidence.write(json.dumps(dict(packet=packet, ack=ack, errors=errors), allow_nan=False)+"\n")
                if envelope.get("ended"):
                    return
                time.sleep(.02)
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.terminate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relay", action="store_true")
    parser.add_argument("--raw", required=True, help="Absolute WSL path to this run's native raw JSONL")
    for name in ("run-id", "instance-id", "model-identity"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--wsl-repo")
    parser.add_argument("--port", type=int, default=19060)
    parser.add_argument("--readback")
    parser.add_argument("--duration", type=float)
    args = parser.parse_args()
    expected = binding(args.run_id, args.instance_id, args.model_identity)
    if args.relay:
        if not Path(args.raw).is_absolute():
            parser.error("raw must be an absolute Linux path")
        relay(args.raw, expected)
    else:
        if not args.wsl_repo or not args.readback:
            parser.error("Windows bridge requires --wsl-repo and --readback")
        bridge(args.wsl_repo, args.raw, expected, args.port, args.readback, args.duration)


if __name__ == "__main__":
    main()
