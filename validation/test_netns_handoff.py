"""Reject malformed grants/capsules without joining or leaking received FDs."""
import array
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime import netns_handoff as handoff


@unittest.skipUnless(sys.platform == "linux", "Linux namespace descriptors")
class HandoffRejectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wksim-netns-", dir="/mnt/wsl")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.grant = dict(version=1, run_id="test", token="a" * 64,
                          netns=dict(device=4, inode=12345))
        self.write_grant()

    def write_grant(self):
        path = self.directory / "grant.json"
        path.write_text(json.dumps(self.grant))
        path.chmod(0o600)

    def test_float_and_bool_namespace_identity_rejected_before_socket(self):
        for value in (True, 4.0, -1, 2**64, "4"):
            self.grant["netns"]["device"] = value
            self.write_grant()
            with self.subTest(value=value), patch.object(handoff.socket, "socket") as constructor:
                with self.assertRaises(ValueError):
                    handoff.enter_namespace(self.directory, "test")
                constructor.assert_not_called()

    def test_symlinked_grant_rejected(self):
        path = self.directory / "grant.json"
        target = self.directory / "other.json"
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaises(OSError):
            handoff.enter_namespace(self.directory, "test")

    def test_rejected_capsules_close_every_received_fd(self):
        for count, flags, reply in (
                (2, 0, dict(version=1, run_id="test", netns=self.grant["netns"])),
                (1, socket.MSG_CTRUNC, {}),
                (1, socket.MSG_TRUNC, {}),
                (1, 0, dict(version=True, run_id="test", netns=self.grant["netns"])),
                (1, 0, dict(version=1, run_id="wrong", netns=self.grant["netns"]))):
            descriptors = [os.open("/proc/self/ns/net", os.O_RDONLY) for _ in range(count)]
            class Peer:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def settimeout(self, value): pass
                def connect(self, path): pass
                def sendall(self, value): pass
                def getsockopt(self, *args): return struct.pack("3i", os.getpid(), os.geteuid(), os.getegid())
                def recvmsg(self, *args):
                    return (json.dumps(reply).encode(),
                            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", descriptors).tobytes())],
                            flags, None)
            with self.subTest(count=count, flags=flags, reply=reply), \
                    patch.object(handoff.socket, "socket", return_value=Peer()), \
                    patch.object(handoff.ctypes, "CDLL") as libc:
                try:
                    with self.assertRaises(ValueError):
                        handoff.enter_namespace(self.directory, "test")
                    libc.assert_not_called()
                    for fd in descriptors:
                        with self.assertRaises(OSError): os.fstat(fd)
                finally:
                    for fd in descriptors:
                        try: os.close(fd)
                        except OSError: pass


if __name__ == "__main__":
    unittest.main()
