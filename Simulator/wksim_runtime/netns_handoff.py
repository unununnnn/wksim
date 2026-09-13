"""One-use Linux network-namespace handoff across WSL distributions.

Only network membership is transferred. Filesystem, IPC, ROS configuration,
scene authority and process supervision remain the caller's responsibility.
The exporter must already be in an owned private network namespace.
"""
import argparse
import array
import ctypes
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct

CLONE_NEWNET = 0x40000000
NS_GET_NSTYPE = 0xB703  # linux/nsfs.h: _IO(0xb7, 0x3)
LIMIT = 4096


def directory_path(value):
    directory = Path(value)
    if (directory.parent != Path("/mnt/wsl") or not directory.name.startswith("wksim-netns-")
            or directory.is_symlink() or directory.resolve(strict=True) != directory):
        raise ValueError("requires a real /mnt/wsl/wksim-netns-* directory")
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("handoff directory must be owned by caller and mode 0700")
    return directory


def namespace_identity(fd):
    import fcntl
    if fcntl.ioctl(fd, NS_GET_NSTYPE) != CLONE_NEWNET:
        raise ValueError("descriptor is not a network namespace")
    info = os.fstat(fd)
    return dict(device=info.st_dev, inode=info.st_ino)


def valid_namespace_identity(value):
    return (type(value) is dict and set(value) == {"device", "inode"}
            and all(type(value[key]) is int and 0 <= value[key] < 2**64
                    for key in ("device", "inode")) and value["inode"] > 0)


def peer_is_owner(sock):
    _, uid, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != os.geteuid():
        raise PermissionError("handoff peer has a different uid")


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode("ascii")


def unlink_owned(path, identity):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (info.st_dev, info.st_ino) != identity:
        raise RuntimeError("handoff path was replaced: " + str(path))
    path.unlink()


def export_namespace(directory, run_id, timeout=30.0):
    """Send one descriptor to one authenticated peer, then remove owned endpoints."""
    directory = directory_path(directory)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id or "") is None:
        raise ValueError("invalid run_id")
    if not 0 < timeout <= 300:
        raise ValueError("invalid handoff timeout")
    if os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net"):
        raise ValueError("refusing to export the distribution's default network")
    fd = os.open("/proc/self/ns/net", os.O_RDONLY | os.O_CLOEXEC)
    owned = []
    try:
        identity = namespace_identity(fd)
        grant = dict(version=1, run_id=run_id, token=secrets.token_hex(32), netns=identity)
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as listener:
            path = directory / "namespace.sock"
            listener.bind(str(path))
            info = path.lstat(); owned.append((path, (info.st_dev, info.st_ino)))
            listener.settimeout(timeout)
            listener.listen(1)
            pending = directory / ".grant-pending"
            grant_fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
            info = os.fstat(grant_fd); grant_identity = (info.st_dev, info.st_ino)
            owned.append((pending, grant_identity))
            with os.fdopen(grant_fd, "wb") as output:
                output.write(encode(grant))
            # Publish complete bytes atomically, without replacing an existing grant.
            path = directory / "grant.json"
            os.link(pending, path)
            owned.append((path, grant_identity))
            unlink_owned(pending, grant_identity)
            with listener.accept()[0] as peer:
                peer.settimeout(timeout)
                peer_is_owner(peer)
                message, _, flags, _ = peer.recvmsg(LIMIT)
                if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
                    raise ValueError("truncated handoff request")
                request = json.loads(message)
                if (type(request) is not dict or set(request) != {"version", "run_id", "token"}
                        or type(request["version"]) is not int or request["version"] != 1
                        or request["run_id"] != run_id
                        or not isinstance(request["token"], str)
                        or not secrets.compare_digest(request["token"], grant["token"])):
                    raise PermissionError("invalid namespace grant")
                reply = dict(version=1, run_id=run_id, netns=identity)
                body = encode(reply)
                sent = peer.sendmsg([body], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
                if sent != len(body):
                    raise RuntimeError("incomplete descriptor handoff")
                if peer.recv(32) != b"received":
                    raise RuntimeError("descriptor receipt was not acknowledged")
        return dict(run_id=run_id, netns=identity, descriptor_transferred=True)
    finally:
        os.close(fd)
        failures = []
        for path, identity in reversed(owned):
            try:
                unlink_owned(path, identity)
            except OSError as error:
                failures.append(str(error))
            except RuntimeError as error:
                failures.append(str(error))
        if failures:
            raise RuntimeError("handoff cleanup failed: " + "; ".join(failures))


def enter_namespace(directory, run_id, timeout=30.0):
    """Join the granted network in a single-threaded process; preserve mounts/IPC."""
    directory = directory_path(directory)
    if not 0 < timeout <= 300:
        raise ValueError("invalid handoff timeout")
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise RuntimeError("namespace entry requires a single-threaded process")
    grant_fd = os.open(directory / "grant.json", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(grant_fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= LIMIT):
            raise ValueError("invalid grant file ownership or mode")
        grant = json.loads(source.read(LIMIT + 1))
    if (type(grant) is not dict or set(grant) != {"version", "run_id", "token", "netns"}
            or type(grant["version"]) is not int or grant["version"] != 1
            or grant["run_id"] != run_id
            or not valid_namespace_identity(grant["netns"])
            or not isinstance(grant.get("token"), str)
            or re.fullmatch(r"[0-9a-f]{64}", grant.get("token", "")) is None):
        raise ValueError("namespace grant differs from the requested run")
    before = {name: os.readlink("/proc/self/ns/" + name) for name in ("net", "mnt", "ipc")}
    received = []
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as peer:
            peer.settimeout(timeout)
            peer.connect(str(directory / "namespace.sock"))
            peer_is_owner(peer)
            peer.sendall(encode({k: grant[k] for k in ("version", "run_id", "token")}))
            message, ancillary, flags, _ = peer.recvmsg(
                LIMIT, socket.CMSG_SPACE(16 * array.array("i").itemsize), socket.MSG_CMSG_CLOEXEC)
            unexpected = False
            for level, kind, data in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    descriptors = array.array("i")
                    descriptors.frombytes(data[:len(data) - len(data) % descriptors.itemsize])
                    received.extend(descriptors)
                else:
                    unexpected = True
            if unexpected or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or len(received) != 1:
                raise ValueError("expected exactly one complete namespace descriptor")
            reply = json.loads(message)
            if (type(reply) is not dict or type(reply.get("version")) is not int
                    or not valid_namespace_identity(reply.get("netns"))
                    or reply != dict(version=1, run_id=run_id, netns=grant["netns"])):
                raise ValueError("namespace response identity mismatch")
            if namespace_identity(received[0]) != grant["netns"]:
                raise ValueError("received namespace differs from the grant")
            libc = ctypes.CDLL(None, use_errno=True)
            libc.setns.argtypes = (ctypes.c_int, ctypes.c_int)
            libc.setns.restype = ctypes.c_int
            if libc.setns(received[0], CLONE_NEWNET) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            after = {name: os.readlink("/proc/self/ns/" + name) for name in before}
            if after["net"] != "net:[" + str(grant["netns"]["inode"]) + "]" or any(
                    before[name] != after[name] for name in ("mnt", "ipc")):
                raise RuntimeError("namespace entry changed an unexpected namespace")
            peer.sendall(b"received")
            return dict(run_id=run_id, before=before, after=after)
    finally:
        for fd in received:
            os.close(fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "enter"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "export":
        print(json.dumps(export_namespace(args.directory, args.run_id)))
    else:
        result = enter_namespace(args.directory, args.run_id)
        if args.command:
            command = args.command[1:] if args.command[0] == "--" else args.command
            if not command:
                raise ValueError("missing command")
            os.execvp(command[0], command)
        print(json.dumps(result))
