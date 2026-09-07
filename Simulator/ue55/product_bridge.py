"""Windows product view: pull current WSL state, validate, forward to UE loopback.

One outstanding pipe request bounds transport buffering. UE ACKs never reach
physics. Restart this bridge to reconnect; the source uses unconnected sendto.
"""
import argparse
from contextlib import nullcontext
import json
import math
from pathlib import Path
import socket
import subprocess
import time

from Simulator.wksim_core.state_stream import LatestState, MAX_PACKET, MAX_AGE, validate
from Simulator.ue55.bridge import actor_errors


def display_packet(envelope, run_id, vehicle_id, roundtrip_s, windows_wall, *, validator=validate):
    """Bound age using same-WSL clock plus full monotonic roundtrip, not UTC offset.

    Original source clocks remain intact. display_wall_time_s is a conservative
    Windows-only freshness bound, NOT a new authoritative simulation timestamp.
    """
    if not isinstance(envelope, dict):
        raise ValueError('Invalid relay envelope')
    relay_wall = envelope.get('relay_wall_time_s')
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in (relay_wall, roundtrip_s, windows_wall)):
        raise ValueError('Invalid relay timing')
    if roundtrip_s < 0 or roundtrip_s > MAX_AGE:
        raise ValueError('Expired pipe roundtrip')
    packet = envelope.get('packet')
    if packet is None:
        return None
    validator(packet, run_id, vehicle_id, now=relay_wall)
    age_bound = max(0, relay_wall-packet['source_wall_time_s']) + roundtrip_s
    if age_bound > MAX_AGE:
        raise ValueError('Expired source plus pipe delay')
    return dict(packet, display_wall_time_s=windows_wall-age_bound,
                display_clock='windows_utc_bound', transport_age_bound_s=age_bound)


def bridge(repo, path, run_id, vehicle_id=1, port=19060, readback=None, *, instance_id=None):
    packet_limit=MAX_PACKET
    validator=validate
    compare=actor_errors
    state_id=vehicle_id
    if instance_id is None:
        latest=LatestState(run_id,vehicle_id)
    else:
        from Simulator.wksim_core.joint_state_stream import LatestJointState,MAX_PACKET as JOINT_LIMIT,validate as validate_joint
        from .joint_bridge import joint_actor_errors
        latest=LatestJointState(run_id,instance_id)
        packet_limit=JOINT_LIMIT;validator=validate_joint;compare=joint_actor_errors;state_id=instance_id
    def frame_key(value):
        return ((value.get('generation'),value.get('epoch'),value.get('sequence'))
                if instance_id is not None else value.get('sequence'))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid UE port")
    argv = ["wsl.exe", "-d", "Ubuntu-22.04", "--cd", repo, "--exec", "python3", "-m",
            "Simulator.ue55.state_relay", "--state-socket", path, "--run-id", run_id,
            "--vehicle-id", str(vehicle_id)]
    if instance_id is not None:argv+=['--instance-id',instance_id]
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW) as child, \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp, \
            (Path(readback).open("x", encoding="utf-8", buffering=1) if readback else nullcontext()) as evidence:
        # Windows recvfrom requires a bound socket even before the first state.
        udp.bind(("127.0.0.1", 0))
        udp.setblocking(False)
        pending = {};last_ack=None
        try:
            while True:
                requested_at = time.monotonic()
                child.stdin.write(b"?")
                child.stdin.flush()
                raw = child.stdout.readline(packet_limit + 2)
                if not raw:
                    raise ConnectionError("WSL state relay exited")
                if not raw.endswith(b"\n") or len(raw) > packet_limit + 1:
                    raise ValueError("Oversize relay response")
                mapped = None
                try:
                    envelope = json.loads(raw)
                    mapped = display_packet(envelope, run_id, state_id,
                                            time.monotonic()-requested_at, time.time(),validator=validator)
                except (ValueError, TypeError, OverflowError, RecursionError):
                    pass
                if mapped and latest.accept(json.dumps(envelope['packet']), now=envelope['relay_wall_time_s']):
                    if instance_id is not None:
                        pending={key:value for key,value in pending.items()
                                 if key[:2]==(mapped['generation'],mapped['epoch'])}
                    try:
                        udp.sendto(json.dumps(mapped, separators=(",", ":")).encode(), ("127.0.0.1", port))
                        if evidence:
                            pending[frame_key(mapped)] = mapped
                            if len(pending) > 64:
                                del pending[next(iter(pending))]
                    except OSError:
                        pass
                for _ in range(64):
                    try:
                        ack_raw, sender = udp.recvfrom(packet_limit + 1)
                    except (BlockingIOError, ConnectionResetError):
                        break
                    if not evidence or sender != ("127.0.0.1", port) or len(ack_raw) > packet_limit:
                        continue
                    try:
                        ack = json.loads(ack_raw)
                        packet = pending.get(frame_key(ack))
                        if packet is None:
                            continue
                        errors = compare(packet, ack)
                        key=frame_key(ack)
                        if instance_id is not None:
                            if key[:2]!=(latest.packet['generation'],latest.packet['epoch']):continue
                            if last_ack is not None and (key[0]<last_ack[0] or key[:2]==last_ack[:2] and key[2]<=last_ack[2]):continue
                        elif last_ack is not None and key<=last_ack:continue
                    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
                        continue
                    del pending[frame_key(ack)]
                    last_ack=frame_key(ack)
                    evidence.write(json.dumps(dict(packet=packet, ack=ack, errors=errors), allow_nan=False) + "\n")
                time.sleep(0.02)
        finally:
            child.stdin.close()  # EOF asks this relay to unlink its own socket.
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.terminate()  # Only the bridge-owned launcher, never a global process kill.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wsl-repo", required=True, help="Linux path to this wksim checkout")
    parser.add_argument("--state-socket", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--vehicle-id", type=int, default=1)
    parser.add_argument("--port", type=int, default=19060)
    parser.add_argument("--readback", help="Optional new diagnostic JSONL of correlated actual UE Actor ACKs")
    parser.add_argument("--instance-id", help="Select the v3 joint manager instead of the v2 single stream")
    args = parser.parse_args()
    bridge(args.wsl_repo, args.state_socket, args.run_id, args.vehicle_id, args.port, args.readback,instance_id=args.instance_id)
