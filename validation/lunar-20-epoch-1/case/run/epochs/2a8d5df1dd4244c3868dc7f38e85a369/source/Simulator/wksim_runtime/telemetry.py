"""Native MAVLink observation with an explicit optional contained GCS byte bridge.

The diagnostic destination remains one-way. The opt-in GCS path relays actual
GCS bytes and never constructs native commands or drives the public task.
"""
import argparse
import base64
from contextlib import ExitStack
import hashlib
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
    def __init__(self, config, *, gcs_hash_log=None):
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
        self.gcs_target = None
        self.gcs_forward_path = None
        self.gcs_reverse = None
        self.gcs_reverse_path = None
        self.gcs_reverse_inode = None
        self.qgc_pinned = False
        self.qgc_identity = None
        self.reverse_digest = hashlib.sha256()
        self.gcs_packet_hashes = set()
        self.gcs_hashes_truncated = False
        self.gcs_hash_log = gcs_hash_log
        self.gcs_hash_log_records = 0
        self.gcs_hash_log_digest = hashlib.sha256()
        if config.get('gcs_udp_forward'):
            # The declared QGC loopback endpoint belongs to the Windows bridge.
            # The experiment side exchanges byte-identical raw MAVLink over
            # owned UNIX datagram sockets in the telemetry directory.
            host, port = config['gcs_udp_forward'].rsplit(':', 1)
            self.gcs_target = (host, int(port))
            self.counters.update(gcs_forwarded=0, gcs_failed=0, reverse_received=0, reverse_forwarded=0,
                                 reverse_dropped=0, reverse_wrong_peer=0, reverse_invalid=0, reverse_non_mavlink=0)
            directory = Path(config['telemetry_socket']).parent
            self.gcs_forward_path = directory/'gcs-forward.sock'
            self.gcs_reverse_path = directory/'gcs-reverse.sock'
            self.gcs_reverse = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.output = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.udp.bind(('127.0.0.1', self.port))
            self.udp.setblocking(False)
            self.output.setblocking(False)
            if self.gcs_reverse is not None:
                self.gcs_reverse.bind(str(self.gcs_reverse_path))
                self.gcs_reverse_inode = self.gcs_reverse_path.stat().st_ino
                os.chmod(self.gcs_reverse_path, 0o600)
                self.gcs_reverse.setblocking(False)
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
        if self.gcs_forward_path is not None:
            # Byte-identical raw MAVLink to the owned forward socket for the
            # GCS relay, only with a pinned native peer. No queue/retry/replay.
            try:
                self.output.sendto(packet, str(self.gcs_forward_path))
                self.counters['gcs_forwarded'] += 1
            except OSError:
                self.counters['gcs_failed'] += 1
            else:
                packet_hash = hashlib.sha256(packet).hexdigest()
                if len(self.gcs_packet_hashes) < 8192:
                    self.gcs_packet_hashes.add(packet_hash)
                else:
                    self.gcs_hashes_truncated = True
                if self.gcs_hash_log is not None:
                    line = json.dumps(dict(sequence=self.counters['gcs_forwarded'], size=len(packet),
                                           sha256=packet_hash), separators=(',', ':'))+'\n'
                    if self.gcs_hash_log.write(line) != len(line):
                        raise OSError('Incomplete GCS source hash log write')
                    self.gcs_hash_log_digest.update(line.encode('ascii'))
                    self.gcs_hash_log_records += 1
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

    def reverse_forward(self, packet):
        self.counters['reverse_received'] += 1
        if packet and packet[0] not in (0xfe, 0xfd):
            self.counters['reverse_non_mavlink'] += 1
            return
        dialect, _ = load_dialect(self.config['stack'])
        try:
            messages = dialect.MAVLink(None).parse_buffer(packet)
        except Exception:
            self.counters['reverse_invalid'] += 1
            return
        if (not messages or not packet or len(packet) > MAX_DATAGRAM or
                b''.join(bytes(m.get_msgbuf()) for m in messages) != packet or
                any(m.get_type() == 'BAD_DATA' for m in messages)):
            self.counters['reverse_invalid'] += 1
            return
        # The reverse socket accepts only same-uid writers inside the owned
        # directory; a valid GCS heartbeat must still precede any forwarding.
        candidate_identity = self.qgc_identity
        if not self.qgc_pinned:
            heartbeats = [m for m in messages if m.get_type() == 'HEARTBEAT' and getattr(m, 'type', None) == 6 and getattr(m, 'autopilot', None) == 8]
            if not heartbeats:
                self.counters['reverse_dropped'] += 1
                return
            heartbeat = heartbeats[0]
            candidate_identity = (heartbeat.get_srcSystem(), heartbeat.get_srcComponent())
        if any((m.get_srcSystem(), m.get_srcComponent()) != candidate_identity for m in messages):
            self.counters['reverse_wrong_peer'] += 1
            return
        self.qgc_identity = candidate_identity
        self.qgc_pinned = True
        if self.peer is None:
            self.counters['reverse_dropped'] += 1
            return
        try:
            self.udp.sendto(packet, self.peer)
            self.counters['reverse_forwarded'] += 1
            self.reverse_digest.update(len(packet).to_bytes(4, 'big') + packet)
        except OSError:
            self.counters['reverse_dropped'] += 1

    def poll(self, timeout=0.1):
        sources = [self.udp] + ([self.gcs_reverse] if self.gcs_reverse is not None else [])
        ready = select.select(sources, [], [], timeout)[0]
        if self.udp in ready:
            for _ in range(MAX_DRAIN):
                try:
                    packet, peer = self.udp.recvfrom(MAX_DATAGRAM + 1)
                except BlockingIOError:
                    break
                self.forward(packet, peer)
        if self.gcs_reverse is not None and self.gcs_reverse in ready:
            for _ in range(MAX_DRAIN):
                try:
                    packet = self.gcs_reverse.recv(MAX_DATAGRAM + 1)
                except BlockingIOError:
                    break
                self.reverse_forward(packet)

    def close(self):
        self.output.close()
        self.udp.close()
        if self.gcs_reverse is not None:
            self.gcs_reverse.close()
            try:
                if self.gcs_reverse_inode is not None and self.gcs_reverse_path.exists() and self.gcs_reverse_path.lstat().st_ino == self.gcs_reverse_inode:
                    self.gcs_reverse_path.unlink()
            except OSError:
                pass

    def report(self):
        result = dict(policy='explicit_gcs_bridge_v1' if self.gcs_target else 'observe_only_v1', control_path=bool(self.gcs_target),
                    counters=dict(self.counters), peer=self.peer,
                    decoder=self.decoder,
                    reverse_forwarded_sha256=self.reverse_digest.hexdigest() if self.gcs_target else None,
                    gcs_forwarded_packet_sha256=sorted(self.gcs_packet_hashes),
                    gcs_hashes_truncated=self.gcs_hashes_truncated,
                    freshness='application dequeue wall time, not kernel timestamp or simulation state validity')
        if self.gcs_hash_log is not None:
            result['gcs_forward_hash_log'] = dict(path=str(self.gcs_hash_log.name), records=self.gcs_hash_log_records,
                                                 sha256=self.gcs_hash_log_digest.hexdigest())
        return result


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
    with ExitStack() as files:
        hash_log = (files.enter_context(args.config.with_name('gcs-forward-hashes.jsonl').open('x',encoding='ascii',buffering=1))
                    if config.get('gcs_udp_forward') else None)
        observer = Observer(config, gcs_hash_log=hash_log)
        print(json.dumps(dict(ready=True, policy=observer.report()['policy'], port=observer.port)), flush=True)
        try:
            while not stopping:
                observer.poll()
        finally:
            observer.close()
            print(json.dumps(observer.report()), flush=True)


if __name__ == '__main__':
    main()
