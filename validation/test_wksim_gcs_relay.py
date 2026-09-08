"""Real pipe/UNIX-socket transport checks; no FC or QGC is emulated as acceptance."""
import base64
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from Simulator.wksim_runtime.gcs_relay import private_path


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux UNIX socket transport')
class RelayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='wksim-gcs-test-', dir='/tmp')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.reverse = self.root / 'reverse.sock'
        self.forward = self.root / 'forward.sock'
        self.sink = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(self.sink.close)
        self.sink.bind(str(self.reverse)); self.reverse.chmod(0o600)
        self.sink.settimeout(.15)
        self.source = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(self.source.close)
        self.child = subprocess.Popen([sys.executable, '-B', '-m', 'Simulator.wksim_runtime.gcs_relay',
            '--forward-socket', str(self.forward), '--reverse-socket', str(self.reverse)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup_child)
        self.sequence = 0
        self.assertTrue(self.read()['ready'])

    def cleanup_child(self):
        if self.child.poll() is None:
            self.child.stdin.close()
            self.child.wait(timeout=3)
        self.child.stdout.close(); self.child.stderr.close()
        if not self.child.stdin.closed: self.child.stdin.close()

    def read(self):
        self.assertTrue(select.select([self.child.stdout], [], [], 3)[0], 'Relay blocked')
        return json.loads(self.child.stdout.readline())

    def request(self, reverse=None, age=0):
        self.sequence += 1
        row = dict(sequence=self.sequence, created_unix_s=time.time() - age,
                   reverse=base64.b64encode(reverse).decode() if reverse is not None else None)
        self.child.stdin.write(json.dumps(row).encode() + b'\n'); self.child.stdin.flush()
        return self.read()

    def test_batch_preserves_distinct_datagrams_and_never_repeats(self):
        packets = [b'\xfdheartbeat', b'\xfeattitude', b'\xfdparameter']
        for packet in packets: self.source.sendto(packet, str(self.forward))
        self.assertEqual([base64.b64decode(v) for v in self.request()['frames']], packets)
        self.assertEqual(self.request()['frames'], [])

    def test_reverse_exact_bytes_expired_drop_and_eof_cleanup(self):
        raw = b'\xfdwire-byte-transport-only'
        self.assertEqual(self.request(raw)['counters']['reverse_forwarded'], 1)
        self.assertEqual(self.sink.recv(8192), raw)
        time.sleep(.55)  # Let the WSL-local response lease expire; UTC is not shared authority.
        self.assertEqual(self.request(raw)['counters']['reverse_expired'], 1)
        with self.assertRaises(socket.timeout): self.sink.recv(8192)
        self.child.stdin.close(); self.child.wait(timeout=3)
        self.assertEqual(self.child.returncode, 0)
        self.assertFalse(self.forward.exists()); self.assertTrue(self.reverse.is_socket())

    def test_replaced_observer_cannot_receive_old_bridge_data(self):
        self.reverse.unlink()
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(replacement.close)
        replacement.bind(str(self.reverse)); self.reverse.chmod(0o600); replacement.settimeout(.15)
        self.child.wait(timeout=3)
        self.assertNotEqual(self.child.returncode, 0)
        self.assertFalse(self.forward.exists())
        with self.assertRaises(socket.timeout): replacement.recv(8192)

    def test_socket_symlink_and_permissions_rejected(self):
        alias = self.root / 'alias.sock'; alias.symlink_to(self.reverse)
        with self.assertRaises(ValueError): private_path(alias, must_exist=True)
        self.reverse.chmod(0o666)
        with self.assertRaises(ValueError): private_path(self.reverse, must_exist=True)


if __name__ == '__main__':
    unittest.main()
