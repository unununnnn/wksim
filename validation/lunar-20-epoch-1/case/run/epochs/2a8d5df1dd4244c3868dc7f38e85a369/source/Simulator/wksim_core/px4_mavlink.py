"""PX4 simulator_mavlink TCP physics backend; same independent quad-X model.

4 model substeps per IMU frame (250 Hz); simulation time is authoritative.
After startup, each actuator frame unlocks the next sensor frame.
"""
import argparse
import json
import math
from pathlib import Path
import socket
import time

from pymavlink.dialects.v20 import common as mavlink
from .model import Model
from .state_stream import StateWriter, add_arguments


def actuator_commands(message):
    if not message.mode & mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
        return [0.0] * 16
    motors = list(message.controls[:4])
    if len(motors) != 4 or any(not math.isfinite(x) or not 0 <= x <= 1 for x in motors):
        raise ValueError("PX4 quad-X motor outputs must be finite normalized [0,1]")
    return motors + [0.0] * 12


def gps_arguments(state):
    gps = state[90:120]
    # Source template uses atan2(north,east) for COG. The MAVLink contract is
    # clockwise from north: derive COG from the already-scaled NED velocity.
    cog = round(math.degrees(math.atan2(gps[8], gps[7])) % 360 * 100) % 36000
    if math.hypot(gps[7], gps[8]) < 1:
        cog = 0
    return (round(gps[0]), round(gps[11]), round(gps[1]), round(gps[2]), round(gps[3]),
            round(gps[4]), round(gps[5]), round(gps[6]), round(gps[7]), round(gps[8]),
            round(gps[9]), cog, round(gps[12]))


class Sender:
    def __init__(self, connection):
        self.connection = connection

    def write(self, packet):
        self.connection.sendall(packet)


def serve(library, port, trace_path, duration=180, speedup=3, *, state_socket=None, run_id=None, vehicle_id=1):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
        listener.settimeout(30)
        print(json.dumps({"ready": True, "port": port, "library": str(library)}), flush=True)
        connection, _ = listener.accept()
    with connection, StateWriter(state_socket, run_id, vehicle_id) as state_writer, \
            Model(library) as model, Path(trace_path).open("x", encoding="utf-8", buffering=1) as trace:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        protocol = mavlink.MAVLink(Sender(connection), srcSystem=254, srcComponent=51)
        commands = [0.0] * 16
        actuator_time = None
        frames = 0
        duplicates = 0
        started = time.monotonic()

        def send_sensors(state):
            sensor = state[60:90]
            protocol.hil_sensor_send(round(sensor[0]), *sensor[1:14], round(sensor[14]))
            if model.ticks % 100 == 0:
                protocol.hil_gps_send(*gps_arguments(state))

        while duration is None or model.ticks * 0.001 < duration:
            delay = model.ticks * 0.001 / speedup - (time.monotonic() - started)
            if delay > 0:
                time.sleep(delay)
            state = model.step(commands, 4)
            state_writer.emit(state)
            send_sensors(state)
            frames += 1
            if frames == 1 or frames % 5 == 0:
                trace.write(json.dumps({"time": state[2], "actuator_time_usec": actuator_time,
                                        "controls": commands, "vehicle": state[:60],
                                        "sensor": state[60:90]}, allow_nan=False) + "\n")
            # PX4 needs initial IMU frames before it can publish actuators. Once
            # actuators arrive we require lockstep and never free-run on a timeout.
            end = time.monotonic() + (5 if actuator_time is not None else 0.004)
            next_control = False
            while not next_control:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    if actuator_time is not None:
                        raise TimeoutError("PX4 actuator timeout; physics stopped")
                    break
                connection.settimeout(remaining)
                try:
                    packet = connection.recv(8192)
                except socket.timeout:
                    continue
                if not packet:
                    raise ConnectionError("PX4 simulator connection closed")
                for message in protocol.parse_buffer(packet) or []:
                    if message.get_type() != "HIL_ACTUATOR_CONTROLS":
                        continue
                    if not message.flags & 1:
                        raise RuntimeError("This profile requires PX4 lockstep support")
                    if message.time_usec == actuator_time:
                        duplicates += 1
                        send_sensors(state)
                        continue
                    if actuator_time is not None and message.time_usec < actuator_time:
                        raise RuntimeError("PX4 actuator clock moved backwards")
                    commands = actuator_commands(message)
                    actuator_time = message.time_usec
                    next_control = True
        summary = {"frames": frames, "simulation_seconds": model.ticks * 0.001,
                   "wall_seconds": time.monotonic() - started, "duplicates": duplicates}
        print(json.dumps(summary), flush=True)
        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--port", type=int, default=4581)
    parser.add_argument("--trace", required=True, type=Path)
    lifetime = parser.add_mutually_exclusive_group()
    lifetime.add_argument("--duration", type=float, default=180)
    lifetime.add_argument("--run-until-stopped", action="store_true",
                          help="no simulated-duration limit; supervisor owns lifetime; actuator timeout remains active")
    parser.add_argument("--speedup", type=float, default=3)
    add_arguments(parser)
    args = parser.parse_args()
    if not 0 < args.duration <= 3600:
        parser.error("duration must be in (0,3600] simulated seconds")
    if not 0 < args.speedup <= 10:
        parser.error("speedup must be in (0,10]")
    serve(args.library, args.port, args.trace, None if args.run_until_stopped else args.duration, args.speedup,
          state_socket=args.state_socket, run_id=args.run_id, vehicle_id=args.vehicle_id)
