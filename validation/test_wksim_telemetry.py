"""Linux socket contract tests; run only inside a fresh `unshare --net` namespace.

No flight controllers, UE, QGC, hardware, or runtime launchers are involved.
"""
import base64
from contextlib import contextmanager
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
from pymavlink.dialects.v20 import ardupilotmega as mav
from Simulator.wksim_runtime.telemetry import (
    MAX_DATAGRAM, MAX_DRAIN, Observer, checked_destination, decode_datagram,
)
from Simulator.wksim_runtime.telemetry_dialect import load_dialect


def packet(system=22, component=1, version=2, heartbeat=True, autopilot=12):
    encoder = mav.MAVLink(None, srcSystem=system, srcComponent=component)
    message = (mav.MAVLink_heartbeat_message(2, autopilot, 0, 0, 3, 3)
               if heartbeat else mav.MAVLink_attitude_message(123, 1, 2, 3, 4, 5, 6))
    return bytes(message.pack(encoder, force_mavlink1=version == 1))


@contextmanager
def bounded():
    def expired(*_):
        raise AssertionError('Telemetry operation blocked for more than two seconds')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 2)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class DecoderTests(unittest.TestCase):
    def test_real_pinned_px4_esc_info_packet_is_not_unknown(self):
        # Original private SITL datagram from sitl-telemetry-j5nt3lem, not an
        # encoder-produced approximation. PyPI's ArduPilot fork lacks ID290.
        wire = base64.b64decode('/S4AADkWASIBAECtEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADQB9AH0AfQBwAEAA8eWw==')
        message, = decode_datagram(wire, 22)
        self.assertEqual(message.get_type(), 'ESC_INFO')
        self.assertEqual(message.get_msgId(), 290)
        self.assertEqual(bytes(message.get_msgbuf()), wire)

    def test_v1_v2_and_concatenation_preserve_wire_bytes(self):
        for system in (22, 241):
            for version in (1, 2):
                wire = packet(system, version=version)
                self.assertEqual(wire[0], 0xfe if version == 1 else 0xfd)
                for data in (wire, wire + packet(system, heartbeat=False)):
                    with self.subTest(system=system, version=version, length=len(data)):
                        messages = decode_datagram(data, system)
                        self.assertEqual(b''.join(bytes(m.get_msgbuf()) for m in messages), data)

    def test_crc_truncation_junk_size_and_mixed_identity_rejected(self):
        for version in (1, 2):
            good = packet(version=version)
            corrupt = good[:-1] + bytes([good[-1] ^ 0x80])
            cases = [b'', b'x' * (MAX_DATAGRAM + 1), corrupt, b'junk' + good,
                     good + b'junk', packet(23), packet(component=2),
                     good + packet(23), good + packet(component=2), good + corrupt]
            cases.extend(good[:n] for n in range(1, len(good)))
            cases.extend(good + good[:n] for n in range(1, len(good)))
            for index, data in enumerate(cases):
                with self.subTest(version=version, case=index):
                    with self.assertRaises(ValueError):
                        decode_datagram(data, 22)
                    self.assertEqual(len(decode_datagram(good, 22)), 1)


class SocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not sys.platform.startswith('linux'):
            raise unittest.SkipTest('Linux Unix datagram tests require unshare --net')
        if os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
            raise RuntimeError('Refusing real sockets in the host network namespace')
        if {name for _, name in socket.if_nameindex()} != {'lo'}:
            raise RuntimeError('Expected a fresh namespace containing only loopback')

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='wksim-telemetry-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.directory.chmod(0o700)
        self.path = self.directory / 'receiver.sock'

    def receiver(self, path=None):
        path = path or self.path
        result = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(result.close)
        result.bind(str(path))
        path.chmod(0o600)
        result.settimeout(0.2)
        return result

    def observer(self, stack='px4'):
        result = Observer(dict(stack=stack, telemetry_socket=str(self.path),
                               run_id='telemetry-unit', vehicle_id=1))
        self.addCleanup(result.close)
        return result

    def sender(self, port=18591, address='127.0.0.1'):
        result = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(result.close)
        result.bind((address, port))
        result.setblocking(False)
        return result

    def deliver(self, observer, sender, wire):
        sender.sendto(wire, ('127.0.0.1', observer.port))
        with bounded():
            observer.poll(0.1)
        with self.assertRaises(BlockingIOError):
            sender.recvfrom(65535)

    def test_output_original_bytes_metadata_unbound_and_no_udp_reply(self):
        receiver = self.receiver()
        observer = self.observer()
        sender = self.sender()
        for sequence, version in enumerate((1, 2), 1):
            wire = packet(version=version) + packet(heartbeat=False, version=version)
            monotonic_before, unix_before = time.monotonic(), time.time()
            self.deliver(observer, sender, wire)
            data, address = receiver.recvfrom(65535)
            record = json.loads(data)
            self.assertFalse(address)
            self.assertEqual(base64.b64decode(record['packet_base64'], validate=True), wire)
            self.assertEqual(record['message_ids'], [0, 30])
            self.assertEqual(record['sequence'], sequence)
            self.assertEqual(record['source'], ['127.0.0.1', 18591])
            self.assertEqual(record['system_id'], 22)
            self.assertEqual(record['component_id'], 1)
            self.assertEqual(record['run_id'], 'telemetry-unit')
            self.assertLessEqual(monotonic_before, record['observed_monotonic_s'])
            self.assertLessEqual(record['observed_monotonic_s'], time.monotonic())
            self.assertLessEqual(unix_before, record['observed_unix_s'])
            self.assertLessEqual(record['observed_unix_s'], time.time())
            self.assertNotIn('received_monotonic_s', record)
            self.assertNotIn('received_unix_s', record)
        self.assertFalse(observer.output.getsockname())
        self.assertFalse(observer.output.getblocking())
        self.assertFalse(observer.udp.getblocking())
        report = observer.report()
        self.assertFalse(report['control_path'])
        _, expected_decoder = load_dialect('px4')
        self.assertEqual(report['decoder']['source'], expected_decoder['source'])
        self.assertEqual(report['decoder']['version'], expected_decoder['version'])
        self.assertEqual(report['decoder']['sha256'], hashlib.sha256(Path(expected_decoder['source']).read_bytes()).hexdigest())
        self.assertEqual(report['counters'], dict(received=2, sent=2, invalid=0, non_mavlink=0, wrong_peer=0, dropped=0))
        report['counters']['sent'] = 999
        self.assertEqual(observer.report()['counters']['sent'], 2)

    def test_wrong_address_port_and_invalid_identity_cannot_pin(self):
        observer = self.observer()
        for sender in (self.sender(18591, '127.0.0.2'), self.sender(0)):
            self.deliver(observer, sender, packet())
            self.assertIsNone(observer.peer)
        sender = self.sender()
        for wire in (packet(23), packet(component=2), packet()[:-1], packet() + packet(23)):
            self.deliver(observer, sender, wire)
            self.assertIsNone(observer.peer)
        self.assertEqual(observer.counters['wrong_peer'], 2)
        self.assertEqual(observer.counters['invalid'], 4)
        self.assertEqual(observer.counters['sent'], 0)

    def test_ap_pins_ephemeral_port_only_after_fc_heartbeat(self):
        receiver = self.receiver()
        observer = self.observer('arducopter')
        first, second = self.sender(0), self.sender(0)
        for wire in (b'bad', packet(22), packet(241, heartbeat=False),
                     packet(241, autopilot=8), packet(241, autopilot=12)):
            self.deliver(observer, first, wire)
            self.assertIsNone(observer.peer)
        self.deliver(observer, second, packet(241, autopilot=3))
        receiver.recv(65535)
        self.assertEqual(observer.peer, second.getsockname())
        self.deliver(observer, first, packet(241, autopilot=3))
        self.assertEqual(observer.peer, second.getsockname())
        self.assertEqual(observer.counters['wrong_peer'], 1)
        self.deliver(observer, second, packet(241, heartbeat=False))
        self.assertEqual(json.loads(receiver.recv(65535))['message_ids'], [30])
        with self.assertRaises(socket.timeout):
            receiver.recv(65535)

    def test_px4_rejects_ap_heartbeat_before_pinning(self):
        receiver = self.receiver()
        observer, sender = self.observer(), self.sender()
        self.deliver(observer, sender, packet(autopilot=3))
        self.assertIsNone(observer.peer)
        self.assertEqual(observer.counters['dropped'], 1)
        self.deliver(observer, sender, packet(autopilot=12))
        self.assertEqual(observer.peer, sender.getsockname())
        self.assertEqual(json.loads(receiver.recv(65535))['sequence'], 1)

    def test_ap_boot_console_is_rejected_separately_from_invalid_frames(self):
        observer, sender = self.observer('arducopter'), self.sender(0)
        # Actual AP startup text captured in sitl-telemetry-j5nt3lem.
        wire = base64.b64decode('CgpJbml0IEFyZHVDb3B0ZXIgVjQuNy4wICgxNTExZjI3MSkKCkZyZWUgUkFNOiA1MjQyODgKQm9vdGluZyAwLzAKRmlybXdhcmUgY2hhbmdlOiBlcmFzaW5nIEVFUFJPTS4uLgpkb25lLgo=')
        self.deliver(observer, sender, wire)
        self.assertEqual(observer.counters['non_mavlink'], 1)
        self.assertEqual(observer.counters['invalid'], 0)
        self.assertIsNone(observer.peer)

    def test_oversized_udp_datagram_is_rejected_and_next_packet_recovers(self):
        receiver = self.receiver()
        observer, sender = self.observer(), self.sender()
        self.deliver(observer, sender, packet() + b'\0' * MAX_DATAGRAM)
        self.assertIsNone(observer.peer)
        self.assertEqual(observer.counters['invalid'], 1)
        self.deliver(observer, sender, packet())
        self.assertEqual(json.loads(receiver.recv(65535))['sequence'], 1)

    def test_absent_receiver_drops_without_replay_or_return_command(self):
        observer, sender = self.observer(), self.sender()
        self.deliver(observer, sender, packet())
        self.assertFalse(self.path.exists())
        self.assertEqual(observer.counters['dropped'], 1)
        receiver = self.receiver()
        self.deliver(observer, sender, packet(heartbeat=False))
        self.assertEqual(json.loads(receiver.recv(65535))['sequence'], 2)
        with self.assertRaises(socket.timeout):
            receiver.recv(65535)

    def test_full_queue_and_disconnected_receiver_drop_without_blocking(self):
        receiver = self.receiver()
        observer, sender = self.observer(), self.sender()
        queue_limit = int(Path('/proc/sys/net/unix/max_dgram_qlen').read_text())
        self.assertLess(queue_limit, 10000, 'Unexpected namespace queue limit')
        for _ in range(queue_limit + 3):
            self.deliver(observer, sender, packet())
        self.assertGreater(observer.counters['sent'], 0)
        self.assertGreater(observer.counters['dropped'], 0)
        sent = observer.counters['sent']
        receiver.close()
        dropped = observer.counters['dropped']
        self.deliver(observer, sender, packet())
        self.assertEqual(observer.counters['dropped'], dropped + 1)
        self.assertEqual(observer.counters['sent'], sent)
        self.assertTrue(self.path.exists())
        self.path.unlink()
        replacement = self.receiver()
        with self.assertRaises(socket.timeout):
            replacement.recv(65535)
        self.deliver(observer, sender, packet())
        self.assertEqual(json.loads(replacement.recv(65535))['sequence'], queue_limit + 5)

    def test_poll_drains_at_most_64_datagrams(self):
        observer, sender = self.observer(), self.sender()
        observer.udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        for _ in range(MAX_DRAIN + 5):
            sender.sendto(packet(), ('127.0.0.1', observer.port))
        with bounded():
            observer.poll(0)
        self.assertEqual(observer.counters['received'], 64)
        observer.poll(0)
        self.assertEqual(observer.counters['received'], 69)
        with self.assertRaises(BlockingIOError):
            sender.recv(65535)

    def test_socket_lifecycle_private_binding_exclusivity_and_failed_init_cleanup(self):
        receiver = self.receiver()
        observer = self.observer()
        self.assertEqual(observer.udp.getsockname(), ('127.0.0.1', 14661))
        before = len(os.listdir('/proc/self/fd'))
        with self.assertRaises(OSError) as failure:
            self.observer()
        self.assertEqual(failure.exception.errno, errno.EADDRINUSE)
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        other = self.observer('arducopter')
        self.assertEqual(other.udp.getsockname(), ('127.0.0.1', 14660))
        observer.close()
        observer.close()
        self.assertEqual(observer.udp.fileno(), -1)
        self.assertEqual(observer.output.fileno(), -1)
        self.assertGreaterEqual(receiver.fileno(), 0)
        self.assertTrue(self.path.is_socket())
        replacement = self.observer()
        self.assertEqual(replacement.udp.getsockname()[1], 14661)

    def test_destination_path_permissions_symlinks_and_ownership(self):
        self.assertEqual(checked_destination(self.path), str(self.path))
        for mode in (0o755, 0o777, 0o750):
            self.directory.chmod(mode)
            with self.assertRaises(ValueError):
                checked_destination(self.path)
        self.directory.chmod(0o700)
        self.path.touch(mode=0o600)
        with self.assertRaises(ValueError):
            checked_destination(self.path)
        self.path.unlink()
        receiver = self.receiver()
        for mode in (0o666, 0o660, 0o400):
            self.path.chmod(mode)
            with self.assertRaises(ValueError):
                checked_destination(self.path)
        self.path.chmod(0o600)
        alias = self.directory / 'alias.sock'
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            checked_destination(alias)
        directory_alias = self.directory / 'alias-dir'
        directory_alias.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(ValueError):
            checked_destination(directory_alias / 'receiver.sock')
        with self.assertRaises((ValueError, FileNotFoundError)):
            checked_destination(self.directory / 'missing' / 'receiver.sock')
        with self.assertRaises(ValueError):
            checked_destination(Path('relative.sock'))
        if os.geteuid() == 0:
            for target in (self.path, self.directory):
                os.chown(target, 65534, -1)
                try:
                    with self.assertRaises(ValueError):
                        checked_destination(self.path)
                finally:
                    os.chown(target, 0, -1)
        self.assertGreaterEqual(receiver.fileno(), 0)


if __name__ == '__main__':
    unittest.main()
