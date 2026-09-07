"""Actual late/reopened consumer sockets through the private /tmp mount; no FC."""
import os
from pathlib import Path
import socket
import unittest
import uuid

from Simulator.wksim_runtime.isolation import isolate_temporary_files


@unittest.skipUnless(os.environ.get('WK_PRIVATE_TMP_TESTS')=='1','explicit private mount environment required')
class ConsumerDirectoryTests(unittest.TestCase):
    def test_late_and_reopened_receivers_share_only_admitted_directories(self):
        name='wksim-view-check-'+uuid.uuid4().hex[:12]
        local=Path('/tmp')/name;host=Path('/proc/1/root/tmp')/name
        info=isolate_temporary_files([local/'state.sock',local/'telemetry.sock'])
        self.assertEqual(len(info['consumer_directories']),1)
        self.assertEqual(local.stat().st_ino,host.stat().st_ino)
        self.assertEqual(local.stat().st_dev,host.stat().st_dev)
        self.assertNotEqual(Path('/tmp').stat().st_dev,Path('/proc/1/root/tmp').stat().st_dev)
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sender:
                # Both kinds of consumer bind after isolation; a display may
                # disappear and reopen without reconnecting the physics sender.
                for filename in ('state.sock','telemetry.sock','state.sock'):
                    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as receiver:
                        receiver.bind(str(host/filename));receiver.settimeout(.5)
                        sender.sendto(b'owned-observation',str(local/filename))
                        self.assertEqual(receiver.recv(100),b'owned-observation')
                    (host/filename).unlink()
            self.assertEqual(isolate_temporary_files([local/'state.sock']),info)
        finally:
            host.rmdir()


if __name__=='__main__':unittest.main()
