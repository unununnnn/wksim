"""ArduCopter JSON physics backend for the reviewed quad-X model; loopback SITL only.

Protocol: ArduPilot libraries/SITL/SIM_JSON.{h,cpp}, commit 1511f271.
MAVLink/DDS commands are separate from this actuator/sensor physics loop.
"""
import argparse
import json
from pathlib import Path
import socket
import struct
import time

from .model import Model
from .state_stream import StateWriter, add_arguments

SERVO_PACKET = struct.Struct("<HHI16H")


def decode_servos(packet):
    if len(packet) != SERVO_PACKET.size:
        raise ValueError("This quad-X profile requires the 16-channel JSON packet")
    magic, rate, frame, *pwm = SERVO_PACKET.unpack(packet)
    if magic != 18458:
        raise ValueError("Invalid JSON backend magic")
    if rate == 0:
        raise ValueError("Invalid zero frame-rate hint")
    # SIM_JSON permits a fixed physics step independent of the rate hint. At
    # startup ArduCopter advertises its default rate before adapting to timestamps.
    # Quad X motor order matches the generated source: FR, RL, FL, RR.
    # Zero is an inactive output; never interpret it as a negative actuator value.
    if any(value != 0 and not 1000 <= value <= 2000 for value in pwm[:4]):
        raise ValueError("Motor PWM outside the configured 1000..2000 range")
    normalized = [max(0, value - 1000) / 1000 for value in pwm[:4]] + [0.0] * 12
    return frame, rate, pwm, normalized


def sensor_fields(state):
    # Use the model's sensor output, NOT Vehicle[24:27] (body velocity derivative).
    return {"timestamp": state[2],
            "imu": {"gyro": state[64:67], "accel_body": state[61:64]},
            "position": state[6:9], "quaternion": state[12:16], "velocity": state[3:6]}


def sensor_message(state):
    data = sensor_fields(state)
    return ("\n" + json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


class Lockstep:
    def __init__(self, model):
        self.model = model
        self.frame = None
        self.reply = None
        self.state = None
        self.pwm = None
        self.duplicates = 0
        self.rate_hint = None

    def update(self, packet):
        frame, rate, pwm, normalized = decode_servos(packet)
        if frame == self.frame:
            self.duplicates += 1
            return self.reply, False
        if self.frame is not None and frame != (self.frame + 1) % (2 ** 32):
            raise RuntimeError("Actuator frame discontinuity; restart this isolated run")
        self.state = self.model.step(normalized)
        self.reply = sensor_message(self.state)
        self.frame, self.pwm = frame, pwm
        self.rate_hint = rate
        return self.reply, True


def serve(library, port, trace_path, duration=120, idle_timeout=5, *, state_socket=None, run_id=None, vehicle_id=1):
    started = time.monotonic()
    peer = None
    frames = 0
    with StateWriter(state_socket, run_id, vehicle_id) as state_writer, \
            Model(library) as model, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, \
            Path(trace_path).open("x", encoding="utf-8", buffering=1) as trace:
        sock.bind(("127.0.0.1", port))
        sock.settimeout(30)  # First connection may wait for the flight-controller process.
        loop = Lockstep(model)
        print(json.dumps({"ready": True, "port": port, "library": str(library)}), flush=True)
        while duration is None or model.ticks * 0.001 < duration:
            packet, address = sock.recvfrom(4096)
            if peer is not None and address != peer:
                continue
            reply, advanced = loop.update(packet)
            if peer is None:
                peer = address
                sock.settimeout(idle_timeout)
            sock.sendto(reply, address)
            if advanced:
                state_writer.emit(loop.state)
                frames += 1
                if frames == 1 or frames % 20 == 0:
                    trace.write(json.dumps({"frame": loop.frame, "rate_hint": loop.rate_hint, "time": loop.state[2],
                                            "pwm": loop.pwm, "vehicle": loop.state[:60],
                                            "sensor": loop.state[60:90]}, allow_nan=False) + "\n")
        summary = {"frames": frames, "simulation_seconds": model.ticks * 0.001,
                   "wall_seconds": time.monotonic() - started, "duplicates": loop.duplicates}
        print(json.dumps(summary), flush=True)
        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--port", type=int, default=19002)
    parser.add_argument("--trace", required=True, type=Path)
    lifetime = parser.add_mutually_exclusive_group()
    lifetime.add_argument("--duration", type=float, default=120)
    lifetime.add_argument("--run-until-stopped", action="store_true",
                          help="no simulated-duration limit; supervisor owns lifetime; idle timeout remains active")
    add_arguments(parser)
    args = parser.parse_args()
    if not 0 < args.duration <= 3600:
        parser.error("duration must be in (0,3600] simulated seconds")
    serve(args.library, args.port, args.trace, None if args.run_until_stopped else args.duration,
          state_socket=args.state_socket, run_id=args.run_id, vehicle_id=args.vehicle_id)
