"""Owned WSL UNIX datagrams to the bounded Windows GCS stdio transport."""
import argparse
import base64
from collections import deque
import json
import math
import os
from pathlib import Path
import select
import socket
import stat
import sys
import time

MAX_FRAME = 8192
MAX_BATCH = 64
MAX_AGE = 0.5
MAX_LINE = 12000


def private_path(path, *, must_exist):
    path = Path(path)
    parent = path.parent
    if (not path.is_absolute() or parent.parent != Path('/tmp') or
            parent.is_symlink() or parent.resolve() != parent or len(str(path).encode()) > 107):
        raise ValueError('Socket must be directly inside a private directory under Linux /tmp')
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('Socket directory must be owned by relay user with mode 0700')
    if must_exist:
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('Reverse socket must be an owned non-symlink 0600 socket')
    elif path.exists() or path.is_symlink():
        raise ValueError('Socket path already exists; refusing to replace it')
    return path


def frame_bytes(value):
    raw = base64.b64decode(value, validate=True)
    if not raw or len(raw) > MAX_FRAME or raw[0] not in (0xfe, 0xfd):
        raise ValueError('Empty, oversized or non-MAVLink frame')
    return raw


def relay(forward_socket, reverse_socket):
    forward_socket = private_path(forward_socket, must_exist=False)
    reverse_socket = private_path(reverse_socket, must_exist=True)
    if forward_socket.parent != reverse_socket.parent or forward_socket == reverse_socket:
        raise ValueError('Separate sockets must share one private experiment directory')
    reverse_inode = reverse_socket.stat().st_ino
    counters = dict(forward_dropped=0, reverse_forwarded=0, reverse_expired=0)
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as source, socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sink:
        sink.connect(str(reverse_socket))  # Pins this observer; never reconnect into a new run.
        source.bind(str(forward_socket))
        inode = forward_socket.stat().st_ino
        os.chmod(forward_socket, 0o600)
        source.setblocking(False)
        sink.setblocking(False)
        stdin_fd = sys.stdin.fileno()
        pending, sequence = b'', 0
        frames = deque(maxlen=MAX_BATCH)
        def emit(value):
            sys.stdout.write(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')
            sys.stdout.flush()
        try:
            emit(dict(ready=True, pid=os.getpid(), start_ticks=Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]))
            issued_at = time.monotonic()
            while True:
                ready, _, _ = select.select([source, stdin_fd], [], [], .2)
                if (not reverse_socket.exists() or reverse_socket.stat().st_ino != reverse_inode or
                        not forward_socket.exists() or forward_socket.stat().st_ino != inode):
                    raise ConnectionError('Experiment socket removed or replaced; bridge must stop')
                now = time.monotonic()
                for _ in range(MAX_BATCH):
                    try:
                        raw = source.recv(MAX_FRAME + 1)
                    except BlockingIOError:
                        break
                    if not raw or len(raw) > MAX_FRAME or raw[0] not in (0xfe, 0xfd):
                        counters['forward_dropped'] += 1
                        continue
                    if len(frames) == MAX_BATCH:
                        counters['forward_dropped'] += 1
                    frames.append((now, raw))
                if stdin_fd not in ready:
                    continue
                chunk = os.read(stdin_fd, MAX_LINE + 1)
                if not chunk:
                    return
                pending += chunk
                if len(pending) > MAX_LINE:
                    raise ValueError('Oversized bridge request')
                while b'\n' in pending:
                    line, _, pending = pending.partition(b'\n')
                    request = json.loads(line)
                    if request == {'stop': True}:
                        emit(dict(stopped=True, counters=counters))
                        return
                    seq = request.get('sequence')
                    if type(seq) is not int or seq != sequence + 1:
                        raise ValueError('Out-of-order bridge request')
                    sequence = seq
                    stamp = request.get('created_unix_s')
                    if type(stamp) not in (int, float) or not math.isfinite(stamp):
                        raise ValueError('Invalid transport timestamp')
                    if request.get('reverse') is not None:
                        raw = frame_bytes(request['reverse'])
                        # One outstanding request: the previous response is a local
                        # monotonic lease. Windows/WSL UTC offsets are not authority.
                        if time.monotonic() - issued_at > MAX_AGE:
                            counters['reverse_expired'] += 1
                        else:
                            try:
                                sink.send(raw)
                                counters['reverse_forwarded'] += 1
                            except BlockingIOError:
                                counters['reverse_expired'] += 1
                    now = time.monotonic()
                    batch = []
                    while frames:
                        stamp, raw = frames.popleft()
                        if now - stamp <= MAX_AGE:
                            batch.append(base64.b64encode(raw).decode('ascii'))
                        else:
                            counters['forward_dropped'] += 1
                    emit(dict(sequence=sequence, frames=batch, counters=counters))
                    issued_at = time.monotonic()
        finally:
            if forward_socket.exists() and forward_socket.lstat().st_ino == inode:
                forward_socket.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forward-socket', required=True)
    parser.add_argument('--reverse-socket', required=True)
    args = parser.parse_args()
    relay(args.forward_socket, args.reverse_socket)

