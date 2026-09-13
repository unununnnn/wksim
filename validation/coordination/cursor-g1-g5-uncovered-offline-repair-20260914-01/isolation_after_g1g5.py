"""Isolation after collecting/running the G1/G5 offline drift suite.

Compares live stdlib objects to identities captured by
``stdlib_identity_plugin`` before collection. Fails closed if that plugin
was not registered via ``-p`` before collection, so argument order cannot
bypass the check.

Does not open a socket or launch a process. Does not claim native,
real-socket, or product-process coverage.
"""
from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys
import unittest

try:
    import stdlib_identity_plugin as _probe
except ImportError:
    _probe = None


class IsolationAfterG1G5Tests(unittest.TestCase):
    def test_plugin_captured_identities_are_unpatched(self):
        if _probe is None:
            self.fail(
                "stdlib_identity_plugin must be importable from PYTHONPATH "
                "and loaded via -p before collection"
            )
        if not getattr(_probe, "PLUGIN_REGISTERED", False):
            self.fail(
                "stdlib_identity_plugin was imported as a plain module; "
                "load it with -p before collection so capture is order-independent"
            )
        self.assertIsNotNone(_probe.HOOK_RESULTS["collection_finish"])
        _probe.assert_stdlib_clean("isolation-test")
        self.assertIs(socket.socket, _probe.CAPTURED["socket.socket"])
        self.assertIs(subprocess.run, _probe.CAPTURED["subprocess.run"])
        self.assertIs(ctypes.CDLL, _probe.CAPTURED["ctypes.CDLL"])
        self.assertIs(os.system, _probe.CAPTURED["os.system"])
        self.assertEqual(
            sys.dont_write_bytecode, _probe.CAPTURED["sys.dont_write_bytecode"]
        )
        self.assertFalse(hasattr(socket.socket, "assert_not_called"))
        self.assertFalse(hasattr(subprocess.run, "assert_not_called"))
        self.assertFalse(hasattr(ctypes.CDLL, "assert_not_called"))
        self.assertFalse(hasattr(os.system, "assert_not_called"))


if __name__ == "__main__":
    unittest.main()
