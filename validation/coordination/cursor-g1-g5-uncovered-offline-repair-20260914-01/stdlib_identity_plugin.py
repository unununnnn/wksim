"""Order-independent stdlib identity probe for the G1/G5 offline repair.

Load with ``-p stdlib_identity_plugin`` and PYTHONPATH pointing at this
directory so capture happens before collection, regardless of pytest
argument order. Compares ``socket.socket``, ``subprocess.run``,
``ctypes.CDLL``, ``os.system`` identities and ``sys.dont_write_bytecode``
at ``pytest_collection_finish`` and ``pytest_sessionfinish``.

Does not open a socket or launch a process. This is not a capability
sandbox and does not claim native, real-socket, or product-process
coverage.
"""
from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys

PLUGIN_REGISTERED = False

CAPTURED = {
    "socket.socket": socket.socket,
    "subprocess.run": subprocess.run,
    "ctypes.CDLL": ctypes.CDLL,
    "os.system": os.system,
    "sys.dont_write_bytecode": sys.dont_write_bytecode,
}

HOOK_RESULTS = {
    "plugin_loaded": True,
    "collection_finish": None,
    "session_finish": None,
}


def assert_stdlib_clean(when):
    found = []
    if socket.socket is not CAPTURED["socket.socket"]:
        found.append("socket.socket")
    if subprocess.run is not CAPTURED["subprocess.run"]:
        found.append("subprocess.run")
    if ctypes.CDLL is not CAPTURED["ctypes.CDLL"]:
        found.append("ctypes.CDLL")
    if os.system is not CAPTURED["os.system"]:
        found.append("os.system")
    if sys.dont_write_bytecode != CAPTURED["sys.dont_write_bytecode"]:
        found.append("sys.dont_write_bytecode=%r" % (sys.dont_write_bytecode,))
    if found:
        raise AssertionError(
            "stdlib leak after %s (compared to pre-collection capture): %s"
            % (when, found)
        )
    return {
        "when": when,
        "socket.socket_is": True,
        "subprocess.run_is": True,
        "ctypes.CDLL_is": True,
        "os.system_is": True,
        "sys.dont_write_bytecode": sys.dont_write_bytecode,
        "sys.dont_write_bytecode_eq": True,
    }


def pytest_configure(config):
    global PLUGIN_REGISTERED
    PLUGIN_REGISTERED = True


def pytest_report_header(config):
    return [
        "stdlib_identity_plugin: pre-collection capture of socket.socket, "
        "subprocess.run, ctypes.CDLL, os.system identities; "
        "sys.dont_write_bytecode=%r" % (CAPTURED["sys.dont_write_bytecode"],)
    ]


def pytest_collection_finish(session):
    HOOK_RESULTS["collection_finish"] = assert_stdlib_clean("pytest_collection_finish")


def pytest_sessionfinish(session, exitstatus):
    HOOK_RESULTS["session_finish"] = assert_stdlib_clean("pytest_sessionfinish")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    collection = HOOK_RESULTS["collection_finish"]
    session = HOOK_RESULTS["session_finish"]
    terminalreporter.write_sep(
        "-",
        "stdlib identities match pre-collection capture after collection and session "
        "(socket.socket, subprocess.run, ctypes.CDLL, os.system, sys.dont_write_bytecode=%r)"
        % (CAPTURED["sys.dont_write_bytecode"],),
    )
    if collection is None or session is None:
        raise AssertionError(
            "stdlib_identity_plugin hooks did not both run: collection=%r session=%r"
            % (collection, session)
        )
