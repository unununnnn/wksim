"""WSL host namespace: pathname datagrams -> one latest response per stdin byte.

Run through wsl.exe pipes. No IP listener, DDS participant, or control channel.
"""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import stat
import sys
import time

from Simulator.wksim_core.state_stream import LatestState, MAX_PACKET


def private_path(path):
    path = Path(path)
    parent = path.parent
    if (not path.is_absolute() or parent.parent != Path("/tmp") or
            parent.is_symlink() or parent.resolve() != parent or len(str(path).encode()) > 107):
        raise ValueError("Socket must be directly inside a private directory under Linux /tmp")
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Socket directory must be owned by relay user with mode 0700")
    if path.exists() or path.is_symlink():
        raise ValueError("Socket path already exists; refusing to replace it")
    return path


def relay(path, run_id, vehicle_id=1, instance_id=None):
    packet_limit=MAX_PACKET
    if instance_id is None:
        latest=LatestState(run_id,vehicle_id)
    else:
        from Simulator.wksim_core.joint_state_stream import LatestJointState,MAX_PACKET as JOINT_LIMIT
        latest=LatestJointState(run_id,instance_id)
        packet_limit=JOINT_LIMIT
    path = private_path(path)
    # Never unlink another relay's socket. The owner removes only its own inode.
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as source:
        source.bind(str(path))
        inode = path.stat().st_ino
        os.chmod(path, 0o600)
        source.setblocking(False)
        try:
            while True:
                ready, _, _ = select.select([source, sys.stdin.fileno()], [], [])
                # Bounded drain. If the queue remains saturated, answer null;
                # never label an intermediate backlog sample as the current one.
                drained = False
                for _ in range(256):
                    try:
                        raw = source.recv(packet_limit + 1)
                    except BlockingIOError:
                        drained = True
                        break
                    latest.accept(raw)
                if sys.stdin.fileno() in ready:
                    request = os.read(sys.stdin.fileno(), 1)
                    if not request:
                        return
                    if request != b"?":
                        raise ValueError("Expected latest-state pull")
                    # A boot-time /tmp clear or external unlink leaves a bound
                    # datagram FD alive but unreachable. Report lost ownership
                    # instead of returning null forever or replacing a new owner.
                    if not path.exists() or path.stat().st_ino != inode:
                        raise ConnectionError("Owned state socket path was removed or replaced")
                    packet = latest.current() if drained else None
                    sys.stdout.write(json.dumps(dict(packet=packet, relay_wall_time_s=time.time()),
                                                separators=(",", ":"), allow_nan=False) + "\n")
                    sys.stdout.flush()
        finally:
            if path.exists() and path.stat().st_ino == inode:
                path.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-socket", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--vehicle-id", type=int, default=1)
    parser.add_argument("--instance-id", help="Select v3 joint manager identity instead of the v2 single stream")
    args = parser.parse_args()
    relay(args.state_socket, args.run_id, args.vehicle_id, args.instance_id)
