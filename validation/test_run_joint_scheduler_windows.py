"""Unit tests for Windows host launcher for WSL joint scheduler profiling.

Verifies process orchestration, stdin EOF signaling, bounded grace period waiting,
refusal to kill wsl.exe or user processes, recording of need_cleanup and process identity,
verification of report.json evidence fields, Windows/WSL path conversion,
rejection of non-fresh directories and UNC paths, file redirection of stdout/stderr,
and handling of server spawn failures and KeyboardInterrupt.
"""
from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.run_joint_scheduler_windows import (
    DEFAULT_DISTRO,
    DEFAULT_GRACE_PERIOD_S,
    check_wsl_directory_status,
    is_strict_zero_int,
    main,
    product_result_clean,
    read_linux_report,
    run_joint_scheduler_windows,
    validate_fresh_windows_dir,
    validate_fresh_wsl_dir,
    verify_cleanup_evidence,
    verify_report_evidence,
    windows_path_to_wsl_mnt,
)


class MockProcess:
    def __init__(
        self,
        cmd: list[str],
        pid: int = 12345,
        returncode: int = 0,
        delay_exit: bool = False,
        exit_on_stdin_close: bool = True,
        hang: bool = False,
        stdout_bytes: bytes = b"mock stdout\n",
        stderr_bytes: bytes = b"",
    ):
        self.cmd = cmd
        self.pid = pid
        self._returncode = returncode
        self.delay_exit = delay_exit
        self.exit_on_stdin_close = exit_on_stdin_close
        self.hang = hang
        self.stdout_bytes = stdout_bytes
        self.stderr_bytes = stderr_bytes
        self._terminated = False
        self.killed = False

        class MockStdin:
            def __init__(self, outer):
                self.outer = outer
                self.closed = False

            def close(self):
                self.closed = True
                if self.outer.exit_on_stdin_close and not self.outer.hang:
                    self.outer.delay_exit = False

        self.stdin = MockStdin(self)

    def poll(self) -> int | None:
        if self.hang:
            return None
        if self.delay_exit:
            return None
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.hang:
            raise subprocess.TimeoutExpired(self.cmd, timeout or 0)
        return self._returncode

    def terminate(self) -> None:
        self._terminated = True
        self.delay_exit = False

    def kill(self) -> None:
        self.killed = True
        self.delay_exit = False


def _valid_product_result() -> dict[str, any]:
    return {
        "status": "pass",
        "epochs": [
            {
                "epoch": "00000000000000000000000000000001",
                "remaining_group_members": [],
                "result": {"status": "pass"},
            }
        ],
    }


def _valid_report() -> dict[str, any]:
    return {
        "status": "diagnostic_captured_and_retired",
        "components_started": {"preflight": True, "manager": True, "collector": True},
        "preflight_identity": {"pid": 10, "start_ticks": 100, "pgid": 10},
        "preflight_returncode": 0,
        "preflight_group_snapshot": [{"pid": 10, "start_ticks": 100}],
        "remaining_preflight_group": [],
        "manager": {"pid": 12, "start_ticks": 102, "pgid": 12},
        "manager_returncode": 0,
        "manager_group_snapshot": [{"pid": 12, "start_ticks": 102}],
        "collector_returncode": 0,
        "collector": {"pid": 13, "start_ticks": 103, "pgid": 13},
        "epoch_groups_retired": True,
        "sources_unchanged": True,
        "remaining_manager_group": [],
        "capture": {
            "complete": True,
            "instance_removed": True,
        },
        "product_result": _valid_product_result(),
    }


def _cleanup_clean_partial_report() -> dict[str, any]:
    """A cancelled (partial diagnostic) report whose cleanup is fully proven.

    Uses only fields the real profile_joint_scheduler schema writes: an
    interrupted run carries a top-level 'error' and may lack full diagnostic
    evidence, yet every created component is provably retired.
    """
    return {
        "error": "HostCancelled: host stdin closed",
        "components_started": {"preflight": True, "manager": True, "collector": True},
        "preflight_identity": {"pid": 11, "start_ticks": 101, "pgid": 11},
        "preflight_returncode": 0,
        "preflight_group_snapshot": [{"pid": 11, "start_ticks": 101}],
        "remaining_preflight_group": [],
        "manager": {"pid": 12, "start_ticks": 102, "pgid": 12},
        "manager_returncode": 0,
        "manager_group_snapshot": [{"pid": 12, "start_ticks": 102}],
        "remaining_manager_group": [],
        "collector": {"pid": 13, "start_ticks": 103, "pgid": 13},
        "collector_returncode": 0,
        "epoch_groups_retired": True,
        "capture": {
            "complete": False,
            "instance_removed": True,
        },
    }


class TestRunJointSchedulerWindows(unittest.TestCase):
    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.test_root = Path(self.tmpdir_obj.name)
        self.exchange_dir = self.test_root / "exchange"
        self.output_wsl = "/root/wksim-scheduler-probe-20260913-test"

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def test_windows_path_to_wsl_mnt(self):
        c_path = Path("C:/data/exchange")
        self.assertEqual(windows_path_to_wsl_mnt(c_path), "/mnt/c/data/exchange")

        d_path = Path("D:\\nested\\folder")
        self.assertEqual(windows_path_to_wsl_mnt(d_path), "/mnt/d/nested/folder")

        # UNC path rejected
        with self.assertRaisesRegex(ValueError, "UNC paths cannot be converted"):
            windows_path_to_wsl_mnt(r"\\wsl.localhost\Ubuntu\tmp")
        with self.assertRaisesRegex(ValueError, "UNC paths cannot be converted"):
            windows_path_to_wsl_mnt("//server/share/path")

    def test_validate_fresh_windows_dir(self):
        fresh_dir = self.test_root / "fresh_exchange"
        # Does not exist -> created
        validated = validate_fresh_windows_dir(fresh_dir)
        self.assertTrue(validated.is_dir())

        # Exists and empty -> accepted
        self.assertEqual(validate_fresh_windows_dir(fresh_dir), validated)

        # Exists and NOT empty -> rejected
        (fresh_dir / "existing.tmp").write_text("busy")
        with self.assertRaisesRegex(ValueError, "must be fresh and empty, but contains files"):
            validate_fresh_windows_dir(fresh_dir)

        # File instead of directory -> rejected
        dummy_file = self.test_root / "file.txt"
        dummy_file.write_text("hello")
        with self.assertRaises(NotADirectoryError):
            validate_fresh_windows_dir(dummy_file)

        # UNC rejected
        with self.assertRaisesRegex(ValueError, "UNC exchange directory rejected"):
            validate_fresh_windows_dir(r"\\wsl.localhost\tmp")

        # Linux private root rejected
        with self.assertRaisesRegex(ValueError, "Linux private root exchange directory rejected"):
            validate_fresh_windows_dir("/root/forbidden")

    def test_validate_fresh_wsl_dir(self):
        # Aligns with profile pattern /root/wksim-scheduler-probe-*
        self.assertEqual(
            validate_fresh_wsl_dir(self.output_wsl, check_fn=lambda path, d, w: False),
            self.output_wsl,
        )

        # Mismatch pattern rejected
        with self.assertRaisesRegex(ValueError, "must match profile pattern"):
            validate_fresh_wsl_dir("/tmp/new_dir", check_fn=lambda p, d, w: False)

        with self.assertRaisesRegex(ValueError, "must match profile pattern"):
            validate_fresh_wsl_dir("relative/path", check_fn=lambda p, d, w: False)

        # Path traversal .. rejected
        with self.assertRaisesRegex(ValueError, "must not contain '..'"):
            validate_fresh_wsl_dir("/root/wksim-scheduler-probe-test/../evil", check_fn=lambda p, d, w: False)

        # Already exists rejected
        with self.assertRaisesRegex(ValueError, "directory already exists in WSL"):
            validate_fresh_wsl_dir(self.output_wsl, check_fn=lambda p, d, w: True)

        with self.assertRaisesRegex(ValueError, "with /root as its parent"):
            validate_fresh_wsl_dir(
                "/root/wksim-scheduler-probe-test/nested",
                check_fn=lambda p, d, w: False,
            )

    def test_check_wsl_directory_status(self):
        injected = "/root/wksim-scheduler-probe-$(echo injected); echo hacked"
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"")) as run:
            self.assertFalse(check_wsl_directory_status(injected))
            command = run.call_args.args[0]
            self.assertIn('"$1"', command[8])
            self.assertEqual(command[9], "wksim-output-check")
            self.assertEqual(command[10], injected)

        # rc 0 -> True
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")):
            self.assertTrue(check_wsl_directory_status(self.output_wsl))

        # rc 1 -> False
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"")):
            self.assertFalse(check_wsl_directory_status(self.output_wsl))

        # rc 2 / symlink -> ValueError
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 2, stdout=b"SYMLINK", stderr=b"")):
            with self.assertRaisesRegex(ValueError, "is a symlink"):
                check_wsl_directory_status(self.output_wsl)

        # other rc -> RuntimeError
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 127, stdout=b"", stderr=b"sh: not found")):
            with self.assertRaisesRegex(RuntimeError, "unexpected code 127"):
                check_wsl_directory_status(self.output_wsl)

    def test_happy_path_success(self):
        linux_proc = MockProcess(cmd=["wsl"], pid=101, returncode=0, delay_exit=False)
        server_proc = MockProcess(cmd=["python"], pid=102, returncode=0, delay_exit=False)

        captured_cmds = []

        def mock_popen(cmd, **kwargs):
            captured_cmds.append(cmd)
            # Simulate writing output to log files
            if "stdout" in kwargs and hasattr(kwargs["stdout"], "write"):
                kwargs["stdout"].write(b"process output line\n")
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        result = run_joint_scheduler_windows(
            output_wsl=self.output_wsl,
            exchange_dir=self.exchange_dir,
            timeout_s=10.0,
            popen_fn=mock_popen,
            read_report_fn=lambda out, d, w: _valid_report(),
            check_wsl_dir_fn=lambda p, d, w: False,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["report_status"], "diagnostic_captured_and_retired")
        self.assertTrue(linux_proc.stdin.closed)
        self.assertFalse(linux_proc.killed)

        # Check command construction: -u root and --cd
        linux_cmd = captured_cmds[0]
        self.assertIn("-u", linux_cmd)
        self.assertIn("root", linux_cmd)
        self.assertIn("--cd", linux_cmd)
        self.assertIn(DEFAULT_DISTRO, linux_cmd)

        # Log files created in exchange dir
        self.assertTrue((self.exchange_dir / "wsl_runner.stdout.log").exists())
        self.assertTrue((self.exchange_dir / "snapshot_server.stdout.log").exists())

        # run_log.json was written create-only
        log_file = self.exchange_dir / "run_log.json"
        self.assertTrue(log_file.exists())
        log_data = json.loads(log_file.read_text())
        self.assertEqual(log_data["status"], "success")
        self.assertFalse(log_data["need_cleanup"])
        self.assertTrue(log_data["cleanup_verified"])

    def test_server_failure_closes_stdin_and_waits(self):
        linux_proc = MockProcess(cmd=["wsl"], pid=201, returncode=0, delay_exit=True, exit_on_stdin_close=True)
        server_proc = MockProcess(cmd=["python"], pid=202, returncode=1)

        def mock_popen(cmd, **kwargs):
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        with self.assertRaisesRegex(RuntimeError, "Snapshot server failed with exit code 1"):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=5.0,
                grace_period_s=0.1,
                popen_fn=mock_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                read_raw_report_fn=lambda out, d, w: _cleanup_clean_partial_report(),
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        self.assertTrue(linux_proc.stdin.closed)
        self.assertFalse(linux_proc.killed)

        log_data = json.loads((self.exchange_dir / "run_log.json").read_text())
        self.assertEqual(log_data["status"], "failed")
        self.assertFalse(log_data["need_cleanup"])
        # wrapper exited AND the raw report proved full cleanup
        self.assertTrue(log_data["cleanup_verified"])

    def test_server_spawn_failure_cleans_up_running_linux(self):
        linux_proc = MockProcess(cmd=["wsl"], pid=205, returncode=0, delay_exit=True, exit_on_stdin_close=True)

        call_count = 0

        def failing_server_popen(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return linux_proc
            raise OSError("Simulated server spawn failure")

        with self.assertRaisesRegex(OSError, "Simulated server spawn failure"):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=5.0,
                grace_period_s=0.1,
                popen_fn=failing_server_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                read_raw_report_fn=lambda out, d, w: _cleanup_clean_partial_report(),
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        # Linux proc was started, so its stdin must have been closed to trigger self-exit
        self.assertTrue(linux_proc.stdin.closed)
        self.assertFalse(linux_proc.killed)

        log_data = json.loads((self.exchange_dir / "run_log.json").read_text())
        self.assertEqual(log_data["status"], "failed")
        self.assertIn("Simulated server spawn failure", log_data["failure_reason"])
        self.assertTrue(log_data["cleanup_verified"])
        self.assertFalse(log_data["need_cleanup"])

    def test_keyboard_interrupt_cleans_up_running_linux(self):
        linux_proc = MockProcess(cmd=["wsl"], pid=206, returncode=0, delay_exit=True, exit_on_stdin_close=True)

        call_count = 0

        def interrupting_popen(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return linux_proc
            raise KeyboardInterrupt("Simulated Ctrl+C")

        with self.assertRaises(KeyboardInterrupt):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=5.0,
                grace_period_s=0.1,
                popen_fn=interrupting_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                read_raw_report_fn=lambda out, d, w: _cleanup_clean_partial_report(),
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        self.assertTrue(linux_proc.stdin.closed)
        self.assertFalse(linux_proc.killed)

        log_data = json.loads((self.exchange_dir / "run_log.json").read_text())
        self.assertEqual(log_data["status"], "failed")
        self.assertIn("KeyboardInterrupt", log_data["failure_reason"])
        self.assertTrue(log_data["cleanup_verified"])
        self.assertFalse(log_data["need_cleanup"])

    def test_deadline_timeout_signals_linux_stdin(self):
        linux_proc = MockProcess(cmd=["wsl"], pid=301, returncode=0, delay_exit=True, exit_on_stdin_close=True)
        server_proc = MockProcess(cmd=["python"], pid=302, returncode=0, delay_exit=True)

        def mock_popen(cmd, **kwargs):
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        with self.assertRaisesRegex(RuntimeError, "Execution timed out"):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=0.05,
                poll_interval_s=0.01,
                grace_period_s=0.1,
                popen_fn=mock_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                read_raw_report_fn=lambda out, d, w: _cleanup_clean_partial_report(),
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        self.assertTrue(linux_proc.stdin.closed)
        self.assertFalse(linux_proc.killed)

    def test_linux_hang_saves_need_cleanup_and_identity_without_killing(self):
        # Linux process ignores stdin close and hangs
        linux_proc = MockProcess(cmd=["wsl"], pid=401, returncode=0, delay_exit=True, hang=True)
        server_proc = MockProcess(cmd=["python"], pid=402, returncode=1)

        def mock_popen(cmd, **kwargs):
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        with self.assertRaisesRegex(RuntimeError, "need_cleanup=True"):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=2.0,
                grace_period_s=0.05,
                popen_fn=mock_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        self.assertTrue(linux_proc.stdin.closed)
        # CRITICAL: Launcher must NEVER kill wsl.exe
        self.assertFalse(linux_proc.killed)

        log_data = json.loads((self.exchange_dir / "run_log.json").read_text())
        self.assertEqual(log_data["status"], "failed")
        self.assertTrue(log_data["need_cleanup"])
        # still live: cleanup was NOT verified and the reason is recorded
        self.assertFalse(log_data["cleanup_verified"])
        self.assertIn("still live", log_data["cleanup_reason"])
        self.assertIsNotNone(log_data["identity"])
        self.assertEqual(log_data["identity"]["pid"], 401)
        self.assertEqual(log_data["identity"]["output_wsl"], self.output_wsl)

    def test_linux_rc1_with_residue_marks_need_cleanup(self):
        # Linux wrapper exited rc=1, but its report shows a residual manager group:
        # wrapper exit alone must NOT be recorded as cleanup done.
        linux_proc = MockProcess(cmd=["wsl"], pid=601, returncode=1)
        server_proc = MockProcess(cmd=["python"], pid=602, returncode=0, delay_exit=True)

        def mock_popen(cmd, **kwargs):
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        dirty_report = _cleanup_clean_partial_report()
        dirty_report["remaining_manager_group"] = [{"pid": 999}]

        with self.assertRaisesRegex(RuntimeError, "Linux runner failed with exit code 1"):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=5.0,
                grace_period_s=0.1,
                popen_fn=mock_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                read_raw_report_fn=lambda out, d, w: dirty_report,
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        self.assertTrue(linux_proc.stdin.closed)
        self.assertFalse(linux_proc.killed)

        log_data = json.loads((self.exchange_dir / "run_log.json").read_text())
        self.assertEqual(log_data["status"], "failed")
        self.assertTrue(log_data["need_cleanup"])
        self.assertFalse(log_data["cleanup_verified"])
        self.assertIn("remaining_manager_group", log_data["cleanup_reason"])
        self.assertEqual(log_data["identity"]["pid"], 601)

    def test_linux_rc1_without_report_marks_need_cleanup(self):
        # Linux wrapper exited rc=1 but the raw report cannot be read at all:
        # cleanup evidence is missing, so cleanup is unverified.
        linux_proc = MockProcess(cmd=["wsl"], pid=603, returncode=1)
        server_proc = MockProcess(cmd=["python"], pid=604, returncode=0, delay_exit=True)

        def mock_popen(cmd, **kwargs):
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        def missing_report(out, d, w):
            raise RuntimeError("Failed to read report.json from WSL (rc=1): No such file or directory")

        with self.assertRaisesRegex(RuntimeError, "Linux runner failed with exit code 1"):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=5.0,
                grace_period_s=0.1,
                popen_fn=mock_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                read_raw_report_fn=missing_report,
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        self.assertFalse(linux_proc.killed)

        log_data = json.loads((self.exchange_dir / "run_log.json").read_text())
        self.assertEqual(log_data["status"], "failed")
        self.assertTrue(log_data["need_cleanup"])
        self.assertFalse(log_data["cleanup_verified"])
        self.assertIn("unreadable", log_data["cleanup_reason"])

    def test_cancelled_partial_but_fully_cleaned_verifies_cleanup(self):
        # Host cancel: wrapper exits rc=1 with a partial diagnostic, but the raw
        # report proves every created component retired.  cleanup_verified=True
        # while the failure status is preserved.
        linux_proc = MockProcess(cmd=["wsl"], pid=611, returncode=1)
        server_proc = MockProcess(cmd=["python"], pid=612, returncode=0, delay_exit=True)

        def mock_popen(cmd, **kwargs):
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        with self.assertRaisesRegex(RuntimeError, "Linux runner failed with exit code 1"):
            run_joint_scheduler_windows(
                output_wsl=self.output_wsl,
                exchange_dir=self.exchange_dir,
                timeout_s=5.0,
                grace_period_s=0.1,
                popen_fn=mock_popen,
                read_report_fn=lambda out, d, w: _valid_report(),
                read_raw_report_fn=lambda out, d, w: _cleanup_clean_partial_report(),
                check_wsl_dir_fn=lambda p, d, w: False,
            )

        self.assertFalse(linux_proc.killed)

        log_data = json.loads((self.exchange_dir / "run_log.json").read_text())
        # failure status is preserved; cleanup verdict is recorded separately
        self.assertEqual(log_data["status"], "failed")
        self.assertIn("Linux runner failed", log_data["failure_reason"])
        self.assertTrue(log_data["cleanup_verified"])
        self.assertFalse(log_data["need_cleanup"])
        self.assertIsNone(log_data["identity"])

    def test_strict_report_evidence_validation(self):
        nested = _valid_report()
        nested['product_result']['epochs'][0]['result']['detail'] = {'error': 'unretired child'}
        with self.assertRaisesRegex(RuntimeError, 'nested failure evidence'):
            verify_report_evidence(nested)
        capture_error = _valid_report()
        capture_error['capture']['errors'] = ['lost trace records']
        with self.assertRaisesRegex(RuntimeError, 'nested failure evidence'):
            verify_report_evidence(capture_error)

        # 1. False treated as 0 must be REJECTED
        bad_rc = _valid_report()
        bad_rc["manager_returncode"] = False
        with self.assertRaisesRegex(RuntimeError, "manager_returncode must be exact int 0"):
            verify_report_evidence(bad_rc)

        bad_col_rc = _valid_report()
        bad_col_rc["collector_returncode"] = False
        with self.assertRaisesRegex(RuntimeError, "collector_returncode must be exact int 0"):
            verify_report_evidence(bad_col_rc)

        # 2. Truthy strings treated as True must be REJECTED
        bad_flag = _valid_report()
        bad_flag["epoch_groups_retired"] = "true"
        with self.assertRaisesRegex(RuntimeError, "epoch_groups_retired must be True"):
            verify_report_evidence(bad_flag)

        bad_source = _valid_report()
        bad_source["sources_unchanged"] = 1
        with self.assertRaisesRegex(RuntimeError, "sources_unchanged must be True"):
            verify_report_evidence(bad_source)

        # 3. remaining_manager_group not []
        bad_group = _valid_report()
        bad_group["remaining_manager_group"] = [{"pid": 999}]
        with self.assertRaisesRegex(RuntimeError, "remaining_manager_group must be \\[\\]"):
            verify_report_evidence(bad_group)

        # 4. capture complete not True
        bad_cap1 = _valid_report()
        bad_cap1["capture"]["complete"] = "true"
        with self.assertRaisesRegex(RuntimeError, "capture.complete must be True"):
            verify_report_evidence(bad_cap1)

        # 5. capture instance_removed not True
        bad_cap2 = _valid_report()
        bad_cap2["capture"]["instance_removed"] = False
        with self.assertRaisesRegex(RuntimeError, "capture.instance_removed must be True"):
            verify_report_evidence(bad_cap2)

        # 6. product_result not clean
        bad_prod = _valid_report()
        bad_prod["product_result"]["status"] = "failed"
        with self.assertRaisesRegex(RuntimeError, "product_result is not clean"):
            verify_report_evidence(bad_prod)

        # 7. cleanup error keys
        bad_cleanup = _valid_report()
        bad_cleanup["collector_cleanup_error"] = "Tracefs busy"
        with self.assertRaisesRegex(RuntimeError, "nested failure evidence"):
            verify_report_evidence(bad_cleanup)

    def test_invalid_parameters_types(self):
        for bad_val in (-1.0, 0.0, float("nan"), float("inf"), True, False, "60"):
            with self.subTest(timeout_s=bad_val):
                with self.assertRaises(ValueError):
                    run_joint_scheduler_windows(self.output_wsl, self.exchange_dir, timeout_s=bad_val)
            with self.subTest(grace_period_s=bad_val):
                with self.assertRaises(ValueError):
                    run_joint_scheduler_windows(self.output_wsl, self.exchange_dir, grace_period_s=bad_val)
            with self.subTest(poll_interval_s=bad_val):
                with self.assertRaises(ValueError):
                    run_joint_scheduler_windows(self.output_wsl, self.exchange_dir, poll_interval_s=bad_val)

    def test_cli_main_success_and_failure(self):
        linux_proc = MockProcess(cmd=["wsl"], pid=501, returncode=0)
        server_proc = MockProcess(cmd=["python"], pid=502, returncode=0)

        def mock_popen(cmd, **kwargs):
            if "profile_joint_scheduler.py" in " ".join(cmd):
                return linux_proc
            return server_proc

        with patch("tools.run_joint_scheduler_windows.subprocess.Popen", side_effect=mock_popen), \
             patch("tools.run_joint_scheduler_windows.check_wsl_directory_status", return_value=False), \
             patch("tools.run_joint_scheduler_windows.read_linux_report_file", return_value=json.dumps(_valid_report())):
            rc = main([
                "--output-wsl", self.output_wsl,
                "--exchange-dir", str(self.exchange_dir),
                "--distro", DEFAULT_DISTRO,
                "--timeout", "10.0",
                "--grace-period", "1.0",
            ])
            self.assertEqual(rc, 0)

        # CLI failure with nonexistent / invalid arguments
        rc_err = main([
            "--output-wsl", self.output_wsl,
            "--exchange-dir", r"\\wsl.localhost\invalid",
            "--timeout", "1.0",
        ])
        self.assertEqual(rc_err, 1)


class TestVerifyCleanupEvidence(unittest.TestCase):
    """Direct checks of the cleanup-only verifier against the real report schema."""

    def test_partial_but_fully_retired_report_verifies(self):
        ok, reason = verify_cleanup_evidence(_cleanup_clean_partial_report())
        self.assertTrue(ok, reason)

    def test_full_success_report_also_verifies(self):
        ok, reason = verify_cleanup_evidence(_valid_report())
        self.assertTrue(ok, reason)

    def test_non_dict_report_rejected(self):
        ok, reason = verify_cleanup_evidence("not a dict")
        self.assertFalse(ok)
        self.assertIn("not a dict", reason)

    def test_missing_residue_evidence_is_unknown_not_clean(self):
        report = _cleanup_clean_partial_report()
        del report["remaining_preflight_group"]
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("remaining_preflight_group", reason)

    def test_missing_group_snapshot_is_unknown_not_clean(self):
        report = _cleanup_clean_partial_report()
        del report["manager_group_snapshot"]
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("manager_group_snapshot", reason)

    def test_residue_rejects(self):
        report = _cleanup_clean_partial_report()
        report["remaining_manager_group"] = [{"pid": 999}]
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("remaining_manager_group", reason)

    def test_live_collector_returncode_none_rejects(self):
        report = _cleanup_clean_partial_report()
        report["collector_returncode"] = None
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("collector_returncode", reason)

    def test_cleanup_error_rejects(self):
        report = _cleanup_clean_partial_report()
        report["manager_cleanup_error"] = "force kill failed"
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("manager_cleanup_error", reason)

    def test_trace_instance_not_removed_rejects(self):
        report = _cleanup_clean_partial_report()
        report["capture"]["instance_removed"] = False
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("instance_removed", reason)

    def test_epoch_groups_not_retired_rejects(self):
        report = _cleanup_clean_partial_report()
        report["epoch_groups_retired"] = False
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("epoch_groups_retired", reason)

    def test_missing_components_started_is_unknown(self):
        report = _cleanup_clean_partial_report()
        del report["components_started"]
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("components_started", reason)

    def test_three_components_explicitly_not_started_can_be_clean(self):
        report = {"components_started": {role: False for role in ("preflight", "manager", "collector")}}
        ok, reason = verify_cleanup_evidence(report)
        self.assertTrue(ok, reason)

    def test_started_component_missing_returncode_is_unknown(self):
        report = _cleanup_clean_partial_report()
        report["collector_returncode"] = None
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("collector_returncode", reason)

    def test_trace_loss_with_resources_clean_is_still_cleanup_clean(self):
        report = _cleanup_clean_partial_report()
        report["status"] = "failed"
        report["capture"]["errors"] = ["trace loss"]
        ok, reason = verify_cleanup_evidence(report)
        self.assertTrue(ok, reason)

    def test_nested_cleanup_error_rejects_even_when_resources_look_clean(self):
        report = _cleanup_clean_partial_report()
        report["capture"]["cleanup_error"] = "tracefs instance removal failed"
        ok, reason = verify_cleanup_evidence(report)
        self.assertFalse(ok)
        self.assertIn("nested cleanup failure", reason)


if __name__ == "__main__":
    unittest.main()
