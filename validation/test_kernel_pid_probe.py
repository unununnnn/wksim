"""Offline lifecycle and fail-closed tests for the kernel PID probe wrapper."""
from __future__ import annotations

import errno
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import kernel_pid_probe as probe


CREATOR = {"pid": 10, "start_ticks": 20, "pgid": 10, "argv": ["creator"]}
NAMESPACE = {"path": "/proc/self/ns/pid", "dev": 8, "ino": 4026531836}
MAP_INFO = {"map_id": 1, "map_type": 1, "key_size": 4, "value_size": 40,
            "max_entries": 4096}
PROG_TAG = "eb0b3e23cc966c51"


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class FakeLibrary:
    def __init__(self):
        self.wk_pid_probe_open = FakeFunction(self.open)
        self.wk_pid_probe_lookup = FakeFunction(self.lookup)
        self.wk_pid_probe_info = FakeFunction(self.info)
        self.opened = None

    def open(self, dev, ino, max_entries, fds, verifier, verifier_len):
        self.opened = (dev, ino, max_entries, verifier_len)
        fds[0], fds[1], fds[2] = 40, 41, 42
        verifier.value = b"namespace-limited sched_switch probe"
        return 0

    def info(self, map_fd, values):
        self.assert_fd(map_fd)
        for index, field in enumerate(probe.MAP_INFO_FIELDS):
            values[index] = MAP_INFO[field]
        return 0

    def lookup(self, map_fd, tid, record):
        self.assert_fd(map_fd)
        if tid not in (0, 77):
            return -errno.ENOENT
        record = record._obj
        record.kernel_ids = 3 if tid == 0 else 1836
        record.local_tid = tid
        record.local_tgid = 77
        record.observed_boot_ns = 123456789
        record.comm = b"wk-probe"
        return 0

    @staticmethod
    def assert_fd(map_fd):
        if map_fd != 40:
            raise AssertionError(map_fd)


def _fdinfo_for(fd):
    if fd == 40:
        return dict(MAP_INFO)
    if fd == 41:
        return {"prog_id": 39, "prog_tag": PROG_TAG}
    if fd == 42:
        return {"link_type": "raw_tracepoint", "link_id": 1,
                "prog_id": 39, "prog_tag": PROG_TAG, "tp_name": "sched_switch"}
    raise AssertionError(fd)


def _manifest(source, library):
    return {
        "schema": probe.MANIFEST_SCHEMA,
        "run_id": "run-1",
        "boot_id": "boot-1",
        "creator": CREATOR,
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "library_path": str(library),
        "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "compiler": "/usr/bin/gcc",
        "compiler_argv": ["gcc", "-shared", "-fPIC"],
        "verifier": "namespace-limited sched_switch probe",
        "namespace": NAMESPACE,
        "map_info": MAP_INFO,
        "prog_id": 39,
        "prog_tag": PROG_TAG,
        "link_type": "raw_tracepoint",
        "link_tp_name": "sched_switch",
    }


class KernelPidProbeTests(unittest.TestCase):
    def test_create_compiles_explicit_flags_and_retains_three_fds(self):
        library = FakeLibrary()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "kernel_pid_probe_native.c"
            source.write_text("source")
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe.shutil, "which", return_value="/usr/bin/gcc"), \
                    patch.object(probe, "sys_platform_linux", return_value=True), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE), \
                    patch.object(probe, "json_identity", return_value=CREATOR), \
                    patch.object(probe.subprocess, "run") as compile_run, \
                    patch.object(probe, "_load_library", return_value=library), \
                    patch.object(probe, "_require_fdinfo",
                                 side_effect=lambda fd, *args: _fdinfo_for(fd)), \
                    patch.object(probe, "_read_fdinfo_text",
                                 return_value={"link_type": "raw_tracepoint",
                                               "tp_name": "sched_switch"}), \
                    patch.object(probe.os, "close") as close:
                def compile_side_effect(command, **kwargs):
                    Path(command[command.index("-o") + 1]).write_bytes(b"library")
                compile_run.side_effect = compile_side_effect
                handle = probe.create_probe(root / "fresh", "run-1", "boot-1")
                self.assertEqual(handle.inherited_fds(), (40, 42))
                self.assertEqual(handle.map_info, MAP_INFO)
                self.assertEqual(handle.manifest["prog_id"], 39)
                self.assertEqual(handle.manifest["link_tp_name"], "sched_switch")
                argv = compile_run.call_args.args[0]
                self.assertEqual(argv[1:8], ["-shared", "-fPIC", "-std=c11", "-O2",
                                             "-Wall", "-Wextra", "-Werror"])
                self.assertEqual(library.opened[:3], (8, 4026531836, probe.DEFAULT_MAX_ENTRIES))
                handle.release_parent_after_spawn()
                self.assertEqual(close.call_args_list, [unittest.mock.call(42),
                                                         unittest.mock.call(40),
                                                         unittest.mock.call(41)])
                self.assertTrue(handle.sampling_detached)
                handle.close()

    def test_adopt_lookup_drop_counter_and_link_lifecycle(self):
        library = FakeLibrary()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "kernel_pid_probe_native.c"
            library_path = root / "libkernel_pid_probe.so"
            source.write_text("source")
            library_path.write_bytes(b"library")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest(source, library_path)))
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe, "host_boot_id", return_value="boot-1"), \
                    patch.object(probe.os, "getppid", return_value=CREATOR["pid"]), \
                    patch.object(probe, "json_identity", return_value=CREATOR), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE), \
                    patch.object(probe, "_load_library", return_value=library), \
                    patch.object(probe, "_map_info", return_value=MAP_INFO), \
                    patch.object(probe, "_require_fdinfo",
                                 side_effect=lambda fd, *args: _fdinfo_for(fd)), \
                    patch.object(probe, "_read_fdinfo_text",
                                 return_value={"link_type": "raw_tracepoint",
                                               "tp_name": "sched_switch"}), \
                    patch.object(probe.os, "close") as close:
                handle = probe.adopt_probe(manifest_path, 40, 42, "run-1", "boot-1")
                self.assertEqual(handle.lookup(77)["kernel_ids"], 1836)
                self.assertEqual(handle.dropped_updates, 3)
                self.assertIsNone(handle.lookup(999))
                handle.stop_sampling()
                self.assertTrue(handle.sampling_detached)
                self.assertIsNone(handle.link_fd)
                self.assertEqual(handle.map_fd, 40)
                self.assertEqual(close.call_args_list, [unittest.mock.call(42)])
                handle.close()
                self.assertEqual(close.call_args_list,
                                 [unittest.mock.call(42), unittest.mock.call(40)])
                handle.close()
                self.assertEqual(close.call_count, 2)

    def test_duplicate_manifest_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            path.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaisesRegex(probe.KernelPidProbeError, "duplicate"):
                probe._strict_json(path)

    def test_missing_link_fields_fail_closed(self):
        library = FakeLibrary()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "kernel_pid_probe_native.c"
            library_path = root / "libkernel_pid_probe.so"
            source.write_text("source")
            library_path.write_bytes(b"library")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest(source, library_path)))
            def missing_link(fd, fields, label):
                if fd == 42:
                    return {"prog_id": 39, "prog_tag": PROG_TAG}
                return _fdinfo_for(fd)
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe, "host_boot_id", return_value="boot-1"), \
                    patch.object(probe.os, "getppid", return_value=CREATOR["pid"]), \
                    patch.object(probe, "json_identity", return_value=CREATOR), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE), \
                    patch.object(probe, "_load_library", return_value=library), \
                    patch.object(probe, "_map_info", return_value=MAP_INFO), \
                    patch.object(probe, "_require_fdinfo", side_effect=missing_link), \
                    patch.object(probe, "_read_fdinfo_text",
                                 side_effect=probe.KernelPidProbeError("link fdinfo missing: tp_name")):
                with self.assertRaisesRegex(probe.KernelPidProbeError, "link"):
                    probe.adopt_probe(manifest_path, 40, 42, "run-1", "boot-1")

    def test_hash_and_namespace_mismatches_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "kernel_pid_probe_native.c"
            library = root / "libkernel_pid_probe.so"
            source.write_text("source")
            library.write_bytes(b"library")
            manifest = _manifest(source, library)
            manifest["source_sha256"] = "0" * 64
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe, "host_boot_id", return_value="boot-1"), \
                    patch.object(probe.os, "getppid", return_value=CREATOR["pid"]), \
                    patch.object(probe, "json_identity", return_value=CREATOR), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE):
                with self.assertRaisesRegex(probe.KernelPidProbeError, "source hash"):
                    probe.adopt_probe(path, 40, 42, "run-1", "boot-1")

            manifest["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            manifest["namespace"] = dict(NAMESPACE, ino=NAMESPACE["ino"] + 1)
            path.write_text(json.dumps(manifest))
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe, "host_boot_id", return_value="boot-1"), \
                    patch.object(probe.os, "getppid", return_value=CREATOR["pid"]), \
                    patch.object(probe, "json_identity", return_value=CREATOR), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE):
                with self.assertRaisesRegex(probe.KernelPidProbeError, "namespace"):
                    probe.adopt_probe(path, 40, 42, "run-1", "boot-1")

    def test_parent_pid_reuse_and_boot_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "kernel_pid_probe_native.c"
            library = root / "libkernel_pid_probe.so"
            source.write_text("source")
            library.write_bytes(b"library")
            path = root / "manifest.json"
            path.write_text(json.dumps(_manifest(source, library)))
            reused_parent = dict(CREATOR, start_ticks=CREATOR["start_ticks"] + 1)
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE), \
                    patch.object(probe, "host_boot_id", return_value="boot-1"), \
                    patch.object(probe.os, "getppid", return_value=CREATOR["pid"]), \
                    patch.object(probe, "json_identity", return_value=reused_parent):
                with self.assertRaisesRegex(probe.KernelPidProbeError, "parent identity"):
                    probe.adopt_probe(path, 40, 42, "run-1", "boot-1")
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE), \
                    patch.object(probe, "host_boot_id", return_value="boot-2"), \
                    patch.object(probe, "_load_library"):
                with self.assertRaisesRegex(probe.KernelPidProbeError, "boot identity"):
                    probe.adopt_probe(path, 40, 42, "run-1", "boot-1")

    def test_unrelated_source_path_is_rejected_before_library_load(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "kernel_pid_probe_native.c"
            unrelated = root / "unrelated.c"
            library = root / "libkernel_pid_probe.so"
            source.write_text("source")
            unrelated.write_text("different source")
            library.write_bytes(b"library")
            manifest = _manifest(source, library)
            manifest["source_path"] = str(unrelated)
            manifest["source_sha256"] = hashlib.sha256(unrelated.read_bytes()).hexdigest()
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            with patch.object(probe, "SOURCE", source), \
                    patch.object(probe, "_namespace_proof", return_value=NAMESPACE), \
                    patch.object(probe, "host_boot_id", return_value="boot-1"), \
                    patch.object(probe.os, "getppid", return_value=CREATOR["pid"]), \
                    patch.object(probe, "json_identity", return_value=CREATOR), \
                    patch.object(probe, "_load_library") as load_library:
                with self.assertRaisesRegex(probe.KernelPidProbeError, "source path"):
                    probe.adopt_probe(path, 40, 42, "run-1", "boot-1")
                load_library.assert_not_called()

    def test_non_hash_map_type_is_rejected_before_library_load(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "kernel_pid_probe_native.c"
            library = root / "libkernel_pid_probe.so"
            source.write_text("source")
            library.write_bytes(b"library")
            manifest = _manifest(source, library)
            manifest["map_info"] = dict(MAP_INFO, map_type=2)
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            with patch.object(probe, "_namespace_proof", return_value=NAMESPACE), \
                    patch.object(probe, "_load_library") as load_library:
                with self.assertRaisesRegex(probe.KernelPidProbeError, "map_info ABI"):
                    probe.adopt_probe(path, 40, 42, "run-1", "boot-1")
                load_library.assert_not_called()


if __name__ == "__main__":
    unittest.main()
