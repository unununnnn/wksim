"""One-way native MAVLink observation, never a GCS command/control connection.

The input is private SITL loopback UDP. The output is an unbound, nonblocking
Unix datagram socket: there is deliberately no receive or return path to the FC.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import select
import signal
import socket
import stat
import time

from .config import load_config
from .isolation import check_isolation
from .telemetry_dialect import load_dialect

MAX_DATAGRAM = 8192
MAX_DRAIN = 64


def checked_destination(path):
    """An absent receiver is allowed; never create, replace or remove its files."""
    path = Path(path)
    parent = path.parent
    info = parent.lstat()
    if (parent.resolve() != parent or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('Telemetry directory must be a non-symlink owned 0700 directory')
    try:
        info = path.lstat()
    except FileNotFoundError:
        return str(path)
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise ValueError('Telemetry receiver must be a non-symlink owned 0600 Unix socket')
    return str(path)


def decode_datagram(packet, system_id):
    """CRC/length and FC identity checks; return original messages, no re-encoding.

    A fresh parser per datagram prevents trailing partial packets or invalid CRCs
    from contaminating the next datagram. This is not MAVLink authentication.
    """
    dialect, _ = load_dialect('px4' if system_id == 22 else 'arducopter')
    if not packet or len(packet) > MAX_DATAGRAM:
        raise ValueError('Empty or oversized MAVLink datagram')
    parser = dialect.MAVLink(None)
    try:
        messages = parser.parse_buffer(packet)
    except Exception as error:
        raise ValueError('Invalid MAVLink datagram') from error
    if (not messages or b''.join(bytes(m.get_msgbuf()) for m in messages) != packet
            or any(m.get_type() == 'BAD_DATA' or m.get_type().startswith('UNKNOWN') or m.get_srcSystem() != system_id
                   or m.get_srcComponent() != 1 for m in messages)):
        raise ValueError('Incomplete MAVLink datagram or wrong FC identity')
    return messages


class Observer:
    def __init__(self, config):
        # Configuration and namespace admission are enforced by the runtime/CLI;
        # this class is also the bounded protocol/socket test seam.
        self.config = config
        self.destination = checked_destination(config['telemetry_socket'])
        self.system_id = 241 if config['stack'] == 'arducopter' else 22
        self.port = 14660 if config['stack'] == 'arducopter' else 14661
        self.peer = None
        self.sequence = 0
        self.counters = dict(received=0, sent=0, invalid=0, non_mavlink=0, wrong_peer=0, dropped=0)
        # Fail before binding if the existing decoder dependency is unavailable.
        _, self.decoder = load_dialect(config['stack'])
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.output = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.udp.bind(('127.0.0.1', self.port))
            self.udp.setblocking(False)
            self.output.setblocking(False)
        except BaseException:
            self.close()
            raise

    def forward(self, packet, peer):
        self.counters['received'] += 1
        if (peer[0] != '127.0.0.1'
                or (self.config['stack'] == 'px4' and peer[1] != 18591)
                or (self.peer is not None and peer != self.peer)):
            self.counters['wrong_peer'] += 1
            return None
        if packet and packet[0] not in (0xfe, 0xfd):
            # AP serial0 emits boot-console text on the same simulated port.
            # Reject it without treating text as a corrupted MAVLink frame.
            self.counters['non_mavlink'] += 1
            return None
        try:
            messages = decode_datagram(packet, self.system_id)
        except ValueError:
            self.counters['invalid'] += 1
            return None
        # AP's udpclient has an ephemeral source port; pin it only after decoding
        # a valid native heartbeat. Neither arbitrary bytes nor a foreign sysid
        # can set or replace that peer. The private namespace supplies isolation.
        if self.peer is None:
            autopilot = 3 if self.config['stack'] == 'arducopter' else 12
            if not any(m.get_type() == 'HEARTBEAT' and m.autopilot == autopilot for m in messages):
                self.counters['dropped'] += 1
                return None
            self.peer = peer
        self.sequence += 1
        record = dict(schema_version=1, kind='native_mavlink_observation',
                      run_id=self.config['run_id'], vehicle_id=self.config['vehicle_id'],
                      stack=self.config['stack'], system_id=self.system_id, component_id=1,
                      sequence=self.sequence, observed_monotonic_s=time.monotonic(),
                      observed_unix_s=time.time(), source=list(peer),
                      message_ids=[m.get_msgId() for m in messages],
                      packet_base64=base64.b64encode(packet).decode('ascii'))
        try:
            self.output.sendto(json.dumps(record, separators=(',', ':'), allow_nan=False).encode(), self.destination)
            self.counters['sent'] += 1
        except OSError:
            # No queue, retries, replay or wait for a consumer. No FC writes.
            self.counters['dropped'] += 1
        return record

    def poll(self, timeout=0.1):
        if not select.select([self.udp], [], [], timeout)[0]:
            return
        for _ in range(MAX_DRAIN):
            try:
                packet, peer = self.udp.recvfrom(MAX_DATAGRAM + 1)
            except BlockingIOError:
                break
            self.forward(packet, peer)

    def close(self):
        self.output.close()
        self.udp.close()

    def report(self):
        return dict(policy='observe_only_v1', control_path=False,
                    counters=dict(self.counters), peer=self.peer,
                    decoder=self.decoder,
                    freshness='application dequeue wall time, not kernel timestamp or simulation state validity')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    if 'telemetry_socket' not in config:
        parser.error('telemetry_socket must be explicitly configured')
    check_isolation()
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    observer = Observer(config)
    print(json.dumps(dict(ready=True, policy='observe_only_v1', port=observer.port)), flush=True)
    try:
        while not stopping:
            observer.poll()
    finally:
        observer.close()
        print(json.dumps(observer.report()), flush=True)


if __name__ == '__main__':
    main()
