"""Unit tests for Windows host WSL snapshot request server.

Verifies serving pre_bootstrap_leaders and post_capture_tasks requests,
rejection of UNC paths and Linux root paths, deadline timeouts across all execution
points, request size bounds with read(max_request_bytes + 1), rejection of linked
requests, cross-phase invariants (run/epoch/boot/ns/collector/owners must match,
request_id must differ), strict typing of max_request_bytes and poll_interval,
system boot_id verification, collector + 5 owners validation with strict positive
integer start_ticks, and CLI execution.
"""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.serve_wsl_snapshot_requests import (
    MAX_REQUEST_BYTES,
    PHASES,
    main,
    serve_snapshot_requests,
    validate_exchange_dir,
)
from tools.wsl_snapshot_exchange import (
    decode_json_strict,
    encode_json_strict,
    make_snapshot_request,
    publish_create_only,
    verify_snapshot_response_binding,
)


def _sample_owners() -> dict[str, dict[str, any]]:
    return {
        "supervisor": {"pid": 605, "start_ticks": 1210},
        "ap_worker": {"pid": 701, "start_ticks": 1250},
        "px4_worker": {"pid": 702, "start_ticks": 1252},
        "ap_fc": {"pid": 736, "start_ticks": 1300},
        "px4_fc": {"pid": 740, "start_ticks": 1305},
    }


def _sample_collector() -> dict[str, any]:
    return {"pid": 601, "start_ticks": 1205}


def _sample_snapshot(owners: dict[str, dict[str, any]], collector: dict[str, any]) -> dict[str, any]:
    targets = dict(owners)
    targets["collector"] = collector
    leaders = {}
    for role, meta in targets.items():
        leaders[meta["pid"]] = {
            "local_tgid": meta["pid"],
            "local_tid": meta["pid"],
            "global_tid": meta["pid"] + 1000,
            "start_ticks": meta["start_ticks"],
            "role": role,
            "comm": role[:15],
        }
    return {
        "root_pid_ns": 4026532233,
        "target_pid_ns": 4026532245,
        "lsns_evidence": {"root_ns": 4026532233, "target_ns": 4026532245},
        "leaders": leaders,
        "tasks": list(leaders.values()),
    }


class TestServeWslSnapshotRequests(unittest.TestCase):
    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.exchange_dir = Path(self.tmpdir_obj.name)
        self.boot_id = "boot-test-uuid-42"
        self.owners = _sample_owners()
        self.collector = _sample_collector()

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def _write_request(self, phase: str, boot_id: str | None = None, request_id: str | None = None, **kwargs) -> tuple[Path, dict, bytes]:
        kw = {
            "run_id": "test-run-1",
            "epoch": "0123456789abcdef0123456789abcdef",
            "boot_id": boot_id or self.boot_id,
            "target_pid_ns": 4026532245,
            "collector": self.collector,
            "owners": self.owners,
            "phase": phase,
            "request_id": request_id or ("11111111111111111111111111111111" if phase == "pre_bootstrap_leaders" else "22222222222222222222222222222222"),
        }
        kw.update(kwargs)
        req_dict = make_snapshot_request(**kw)
        req_bytes = encode_json_strict(req_dict)
        req_path = self.exchange_dir / f"{phase}.request.json"
        req_path.write_bytes(req_bytes)
        return req_path, req_dict, req_bytes

    def test_serve_two_phases_success(self):
        _, req1, bytes1 = self._write_request("pre_bootstrap_leaders")
        _, req2, bytes2 = self._write_request("post_capture_tasks")

        mock_snap = _sample_snapshot(self.owners, self.collector)

        result = serve_snapshot_requests(
            exchange_dir=self.exchange_dir,
            timeout_s=5.0,
            snapshot_fn=lambda **kw: mock_snap,
            boot_id_fn=lambda **kw: self.boot_id,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["phases_handled"], ["pre_bootstrap_leaders", "post_capture_tasks"])

        # Verify response 1
        resp1_path = self.exchange_dir / "pre_bootstrap_leaders.response.json"
        self.assertTrue(resp1_path.exists())
        resp1 = decode_json_strict(resp1_path.read_bytes())
        verify_snapshot_response_binding(resp1, expected_request=req1, expected_request_bytes=bytes1)

        # Verify response 2
        resp2_path = self.exchange_dir / "post_capture_tasks.response.json"
        self.assertTrue(resp2_path.exists())
        resp2 = decode_json_strict(resp2_path.read_bytes())
        verify_snapshot_response_binding(resp2, expected_request=req2, expected_request_bytes=bytes2)

    def test_reject_unc_path(self):
        with self.assertRaisesRegex(ValueError, "UNC exchange directory rejected"):
            validate_exchange_dir(r"\\wsl.localhost\Ubuntu-22.04\tmp")
        with self.assertRaisesRegex(ValueError, "UNC exchange directory rejected"):
            validate_exchange_dir(r"//wsl.localhost/Ubuntu-22.04/tmp")

    def test_reject_nonexistent_and_file_path(self):
        with self.assertRaises(FileNotFoundError):
            validate_exchange_dir(self.exchange_dir / "nonexistent_subfolder")

        test_file = self.exchange_dir / "dummy.txt"
        test_file.write_text("hello")
        with self.assertRaises(FileNotFoundError):
            validate_exchange_dir(test_file)

    def test_reject_linux_root_dir(self):
        with self.assertRaisesRegex(ValueError, "Linux private root exchange directory rejected"):
            validate_exchange_dir("/root/forbidden_exchange")

    def test_timeout_waiting_for_first_request(self):
        with self.assertRaises(TimeoutError):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=0.03,
                poll_interval_s=0.005,
                snapshot_fn=lambda **kw: {},
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_timeout_waiting_for_second_request(self):
        self._write_request("pre_bootstrap_leaders")
        mock_snap = _sample_snapshot(self.owners, self.collector)

        with self.assertRaises(TimeoutError):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=0.05,
                poll_interval_s=0.005,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_invalid_parameters_types(self):
        # timeout_s
        for invalid in (-1.0, 0.0, float("nan"), float("inf"), True, False, "5"):
            with self.subTest(timeout_s=invalid):
                with self.assertRaises(ValueError):
                    serve_snapshot_requests(self.exchange_dir, timeout_s=invalid)

        # max_request_bytes
        for invalid in (-1, 0, True, False, 1.5, "65536", None):
            with self.subTest(max_request_bytes=invalid):
                with self.assertRaises(ValueError):
                    serve_snapshot_requests(self.exchange_dir, timeout_s=1.0, max_request_bytes=invalid)

        # poll_interval_s
        for invalid in (-0.1, 0.0, float("nan"), float("inf"), True, False, "0.05", None):
            with self.subTest(poll_interval_s=invalid):
                with self.assertRaises(ValueError):
                    serve_snapshot_requests(self.exchange_dir, timeout_s=1.0, poll_interval_s=invalid)

    def test_request_exceeds_max_bytes_and_empty_request(self):
        self._write_request("pre_bootstrap_leaders")
        mock_snap = _sample_snapshot(self.owners, self.collector)

        with self.assertRaisesRegex(ValueError, "exceeds max size limit"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                max_request_bytes=50,  # lower than request JSON size
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

        # Empty request file
        empty_req = self.exchange_dir / "pre_bootstrap_leaders.request.json"
        empty_req.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "Empty request file"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_complete_request_is_readable_before_publisher_unlinks_temporary(self):
        self._write_request("pre_bootstrap_leaders")
        self._write_request("post_capture_tasks")
        req_path = self.exchange_dir / "pre_bootstrap_leaders.request.json"
        alias_path = self.exchange_dir / "alias.tmp"
        os.link(req_path, alias_path)

        mock_snap = _sample_snapshot(self.owners, self.collector)
        try:
            result = serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )
            self.assertEqual(result['status'], 'ok')
        finally:
            alias_path.unlink(missing_ok=True)

    def test_response_already_exists_fails_fast(self):
        # Pre-create response 1
        resp_file = self.exchange_dir / "pre_bootstrap_leaders.response.json"
        resp_file.write_text("{\"preexisting\": true}\n")

        with self.assertRaisesRegex(RuntimeError, "Response file already exists"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: {},
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_boot_id_mismatch_with_request(self):
        self._write_request("pre_bootstrap_leaders", boot_id="request-boot-id")
        mock_snap = _sample_snapshot(self.owners, self.collector)

        with self.assertRaisesRegex(RuntimeError, "System boot_id mismatch"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: "system-different-boot-id",
            )

    def test_boot_id_changed_during_snapshot(self):
        self._write_request("pre_bootstrap_leaders", boot_id="boot-before")
        mock_snap = _sample_snapshot(self.owners, self.collector)

        call_count = 0

        def shifting_boot_id(**kw):
            nonlocal call_count
            call_count += 1
            return "boot-before" if call_count == 1 else "boot-after-reboot"

        with self.assertRaisesRegex(RuntimeError, "System boot_id changed during snapshot"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=shifting_boot_id,
            )

    def test_snapshot_leader_not_dict(self):
        self._write_request("pre_bootstrap_leaders")
        targets = dict(self.owners)
        targets["collector"] = self.collector
        leaders = {m["pid"]: {"start_ticks": m["start_ticks"]} for m in targets.values()}
        leaders[605] = "not-a-dict-record"  # supervisor is a string instead of dict
        bad_snapshot = {"leaders": leaders}

        with self.assertRaisesRegex(ValueError, "leader record must be a dict"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: bad_snapshot,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_snapshot_missing_start_ticks(self):
        self._write_request("pre_bootstrap_leaders")
        targets = dict(self.owners)
        targets["collector"] = self.collector
        leaders = {m["pid"]: {"start_ticks": m["start_ticks"]} for m in targets.values()}
        leaders[605] = {"comm": "supervisor"}  # missing start_ticks entirely
        bad_snapshot = {"leaders": leaders}

        with self.assertRaisesRegex(ValueError, "start_ticks must be a positive int"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: bad_snapshot,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_snapshot_non_positive_or_bool_start_ticks(self):
        for bad_ticks in (True, False, 0, -10):
            with self.subTest(bad_ticks=bad_ticks):
                self._write_request("pre_bootstrap_leaders")
                targets = dict(self.owners)
                targets["collector"] = self.collector
                leaders = {m["pid"]: {"start_ticks": m["start_ticks"]} for m in targets.values()}
                leaders[605] = {"start_ticks": bad_ticks}
                bad_snapshot = {"leaders": leaders}

                with self.assertRaisesRegex(ValueError, "start_ticks must be a positive int"):
                    serve_snapshot_requests(
                        exchange_dir=self.exchange_dir,
                        timeout_s=1.0,
                        snapshot_fn=lambda **kw: bad_snapshot,
                        boot_id_fn=lambda **kw: self.boot_id,
                    )

    def test_snapshot_missing_collector(self):
        self._write_request("pre_bootstrap_leaders")
        targets = dict(self.owners)
        leaders = {m["pid"]: {"start_ticks": m["start_ticks"]} for m in targets.values()}
        bad_snapshot = {"leaders": leaders}

        with self.assertRaisesRegex(ValueError, "Target process collector .* missing"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: bad_snapshot,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_snapshot_missing_owner(self):
        self._write_request("pre_bootstrap_leaders")
        mock_snap = _sample_snapshot(self.owners, self.collector)
        del mock_snap["leaders"][740]  # delete px4_fc

        with self.assertRaisesRegex(ValueError, "Target process px4_fc .* missing"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_snapshot_ticks_mismatch(self):
        self._write_request("pre_bootstrap_leaders")
        mock_snap = _sample_snapshot(self.owners, self.collector)
        mock_snap["leaders"][736]["start_ticks"] += 999  # modify ap_fc start_ticks

        with self.assertRaisesRegex(ValueError, "start_ticks mismatch"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_collector_collides_with_owner_pid(self):
        colliding_collector = {"pid": 740, "start_ticks": 1205}
        req_dict = make_snapshot_request(
            run_id="test-run-1",
            epoch="0123456789abcdef0123456789abcdef",
            boot_id=self.boot_id,
            target_pid_ns=4026532245,
            collector=colliding_collector,
            owners=self.owners,
            phase="pre_bootstrap_leaders",
            request_id="abcdef0123456789abcdef0123456789",
        )
        req_path = self.exchange_dir / "pre_bootstrap_leaders.request.json"
        req_path.write_bytes(encode_json_strict(req_dict))

        with self.assertRaisesRegex(ValueError, "Collector pid 740 collides with an owner pid"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: {},
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_injected_function_error_propagates_without_swallowing(self):
        self._write_request("pre_bootstrap_leaders")

        def buggy_boot_id(**kw):
            raise TypeError("Real internal bug in boot_id function")

        with self.assertRaisesRegex(TypeError, "Real internal bug in boot_id function"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: {},
                boot_id_fn=buggy_boot_id,
            )

    def test_cross_phase_invariants_rejected(self):
        mock_snap = _sample_snapshot(self.owners, self.collector)

        def _cleanup():
            for p in self.exchange_dir.glob("*"):
                p.unlink(missing_ok=True)

        # 1. run_id mismatch
        _cleanup()
        self._write_request("pre_bootstrap_leaders", run_id="run-A")
        self._write_request("post_capture_tasks", run_id="run-B")
        with self.assertRaisesRegex(ValueError, "run_id mismatch"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

        # 2. epoch mismatch
        _cleanup()
        self._write_request("pre_bootstrap_leaders", epoch="00000000000000000000000000000001")
        self._write_request("post_capture_tasks", epoch="00000000000000000000000000000002")
        with self.assertRaisesRegex(ValueError, "epoch mismatch"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

        # 3. target_pid_ns mismatch
        _cleanup()
        self._write_request("pre_bootstrap_leaders", target_pid_ns=4026532245)
        self._write_request("post_capture_tasks", target_pid_ns=4026532299)
        with self.assertRaisesRegex(ValueError, "target_pid_ns mismatch"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

        # 4. collector mismatch
        _cleanup()
        self._write_request("pre_bootstrap_leaders", collector={"pid": 601, "start_ticks": 1205})
        self._write_request("post_capture_tasks", collector={"pid": 601, "start_ticks": 1206})
        with self.assertRaisesRegex(ValueError, "collector mismatch"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

        # 5. identical request_id (replay attack)
        _cleanup()
        self._write_request("pre_bootstrap_leaders", request_id="33333333333333333333333333333333")
        self._write_request("post_capture_tasks", request_id="33333333333333333333333333333333")
        with self.assertRaisesRegex(ValueError, "request_id must be distinct"):
            serve_snapshot_requests(
                exchange_dir=self.exchange_dir,
                timeout_s=1.0,
                snapshot_fn=lambda **kw: mock_snap,
                boot_id_fn=lambda **kw: self.boot_id,
            )

    def test_deadline_checks_at_all_stages(self):
        mock_snap = _sample_snapshot(self.owners, self.collector)

        # Deadline expires before pre-snapshot boot_id query
        self._write_request("pre_bootstrap_leaders")
        with patch("time.monotonic", side_effect=[100.0, 100.01, 105.0]):  # start, wait, before boot_before
            with self.assertRaisesRegex(TimeoutError, "Timed out before boot_id query"):
                serve_snapshot_requests(
                    exchange_dir=self.exchange_dir,
                    timeout_s=1.0,
                    snapshot_fn=lambda **kw: mock_snap,
                    boot_id_fn=lambda **kw: self.boot_id,
                )

    def test_cli_main_success_and_failure(self):
        self._write_request("pre_bootstrap_leaders")
        self._write_request("post_capture_tasks")
        mock_snap = _sample_snapshot(self.owners, self.collector)

        with patch("tools.serve_wsl_snapshot_requests.query_wsl_system_boot_id", return_value=self.boot_id), \
             patch("tools.serve_wsl_snapshot_requests.snapshot_wsl_root_tasks", return_value=mock_snap):
            rc = main(["--exchange-dir", str(self.exchange_dir), "--timeout", "5.0"])
            self.assertEqual(rc, 0)

        # CLI failure with nonexistent directory
        rc_err = main(["--exchange-dir", str(self.exchange_dir / "nonexistent_dir"), "--timeout", "1.0"])
        self.assertEqual(rc_err, 1)


if __name__ == "__main__":
    unittest.main()
