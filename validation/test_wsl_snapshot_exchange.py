"""Unit tests for the pure data contract and atomic create-only exchange.

Verifies schema validation, cryptographic challenge-response binding,
rejection of duplicate keys, nonfinite numbers, bool-as-int masquerading,
tampering, replay, create-only non-overwrite semantics, symlink rejection,
and caller-side monotonic timeout evaluation.
"""

from __future__ import annotations

import hashlib
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import time
import unittest
import uuid

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.wsl_snapshot_exchange import (
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    decode_json_strict,
    encode_json_strict,
    is_strict_int,
    is_strict_pos_int,
    make_snapshot_request,
    make_snapshot_response,
    publish_create_only,
    validate_32_hex,
    validate_identity_record,
    validate_owners_dict,
    validate_snapshot_request,
    validate_snapshot_response,
    verify_elapsed_monotonic,
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


def _sample_request_kwargs() -> dict[str, any]:
    return {
        "run_id": "scheduler-test-12345",
        "epoch": "0123456789abcdef0123456789abcdef",
        "boot_id": "boot-uuid-0001",
        "target_pid_ns": 4026532245,
        "collector": {"pid": 601, "start_ticks": 1205},
        "owners": _sample_owners(),
        "phase": "pre_bootstrap_leaders",
        "request_id": "abcdef0123456789abcdef0123456789",
    }


def _sample_snapshot_payload() -> dict[str, any]:
    return {
        "root_pid_ns": 4026532233,
        "target_pid_ns": 4026532245,
        "leaders": {
            "supervisor": {"local_pid": 605, "global_tid": 1015, "start_ticks": 1210},
            "ap_worker": {"local_pid": 701, "global_tid": 1120, "start_ticks": 1250},
            "px4_worker": {"local_pid": 702, "global_tid": 1125, "start_ticks": 1252},
            "ap_fc": {"local_pid": 736, "global_tid": 4449, "start_ticks": 1300},
            "px4_fc": {"local_pid": 740, "global_tid": 4550, "start_ticks": 1305},
        },
    }


class TestStrictJsonEncodingAndDecoding(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows publication boundary')
    def test_unc_publication_is_rejected_before_creating_files(self):
        with self.assertRaisesRegex(ValueError, 'UNC publication is unsupported'):
            publish_create_only(r'\\wsl.localhost\Ubuntu-22.04\tmp\never-created.json', {'test': True})

    def test_actual_snapshot_pid_maps_roundtrip_without_key_collisions(self):
        req = make_snapshot_request(**_sample_request_kwargs())
        raw = encode_json_strict(req)
        payload = {"leaders": {605: {"local_tid": 605}},
                   "tasks_by_local_tid": {605: {"local_tid": 605}}}
        resp = make_snapshot_response(request=req, request_bytes=raw,
                                      boot_id=req["boot_id"], snapshot=payload)
        self.assertEqual(decode_json_strict(encode_json_strict(resp))["snapshot"]["leaders"]["605"],
                         {"local_tid": 605})
        self.assertIn(605, payload["leaders"])
        with self.assertRaisesRegex(ValueError, "collide"):
            make_snapshot_response(request=req, request_bytes=raw, boot_id=req["boot_id"],
                                   snapshot={"leaders": {605: {}, "605": {}}})

    def test_boot_binding_is_required_without_optional_expected_boot(self):
        req = make_snapshot_request(**_sample_request_kwargs())
        raw = encode_json_strict(req)
        resp = make_snapshot_response(request=req, request_bytes=raw,
                                      boot_id="wrong-boot", snapshot={"tasks": []})
        with self.assertRaisesRegex(ValueError, "boot_id mismatch"):
            verify_snapshot_response_binding(resp, expected_request=req, expected_request_bytes=raw)

    def test_request_object_must_match_hashed_bytes_in_both_directions(self):
        req = make_snapshot_request(**_sample_request_kwargs())
        raw = encode_json_strict(req)
        changed = copy.deepcopy(req)
        changed["owners"]["ap_fc"]["start_ticks"] += 1
        with self.assertRaisesRegex(ValueError, "request object differs"):
            make_snapshot_response(request=changed, request_bytes=raw,
                                   boot_id=req["boot_id"], snapshot={"tasks": []})
        resp = make_snapshot_response(request=req, request_bytes=raw,
                                      boot_id=req["boot_id"], snapshot={"tasks": []})
        with self.assertRaisesRegex(ValueError, "request object differs"):
            verify_snapshot_response_binding(resp, expected_request=changed, expected_request_bytes=raw)

    def test_encode_decode_roundtrip(self):
        val = {"key": "val", "num": 42, "nested": {"list": [1, 2, 3]}}
        raw = encode_json_strict(val)
        self.assertIsInstance(raw, bytes)
        decoded = decode_json_strict(raw)
        self.assertEqual(val, decoded)

    def test_reject_duplicate_keys(self):
        duplicate_json = '{"a": 1, "b": 2, "a": 3}'
        with self.assertRaises(ValueError) as cm:
            decode_json_strict(duplicate_json)
        self.assertIn("Duplicate JSON key rejected", str(cm.exception))

    def test_reject_nonfinite_in_decode(self):
        for raw in ('{"val": NaN}', '{"val": Infinity}', '{"val": -Infinity}'):
            with self.assertRaises(ValueError) as cm:
                decode_json_strict(raw)
            self.assertTrue("Nonfinite" in str(cm.exception) or "rejected" in str(cm.exception))

    def test_reject_nonfinite_in_encode(self):
        for num in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError) as cm:
                encode_json_strict({"bad": num})
            self.assertIn("Nonfinite float rejected", str(cm.exception))

    def test_reject_non_dict_top_level(self):
        with self.assertRaises(ValueError) as cm:
            decode_json_strict("[1, 2, 3]")
        self.assertIn("must be an object", str(cm.exception))


class TestTypeAndIdentityValidators(unittest.TestCase):
    def test_is_strict_int_and_pos_int(self):
        self.assertTrue(is_strict_int(0))
        self.assertTrue(is_strict_int(42))
        self.assertTrue(is_strict_int(-10))
        self.assertFalse(is_strict_int(True))
        self.assertFalse(is_strict_int(False))
        self.assertFalse(is_strict_int(1.5))
        self.assertFalse(is_strict_int("42"))

        self.assertTrue(is_strict_pos_int(1))
        self.assertTrue(is_strict_pos_int(999999))
        self.assertFalse(is_strict_pos_int(0))
        self.assertFalse(is_strict_pos_int(-5))
        self.assertFalse(is_strict_pos_int(True))
        self.assertFalse(is_strict_pos_int(False))

    def test_validate_32_hex(self):
        valid = "0123456789abcdef0123456789abcdef"
        self.assertEqual(validate_32_hex(valid, "test"), valid)
        for invalid in (
            "0123456789ABCDEF0123456789ABCDEF",  # uppercase
            "0123456789abcdef",                    # 16 chars
            valid + "a",                           # 33 chars
            "0123456789abcdef0123456789abcdeg",  # non-hex 'g'
            12345,
            None,
        ):
            with self.assertRaises(ValueError):
                validate_32_hex(invalid, "test")

    def test_validate_identity_record(self):
        valid = {"pid": 100, "start_ticks": 200, "pgid": 100, "argv": ["python3", "app.py"]}
        res = validate_identity_record(valid, "proc")
        self.assertEqual(res["pid"], 100)

        # bool as int
        with self.assertRaises(ValueError):
            validate_identity_record({"pid": True, "start_ticks": 200}, "proc")
        with self.assertRaises(ValueError):
            validate_identity_record({"pid": 100, "start_ticks": False}, "proc")
        with self.assertRaises(ValueError):
            validate_identity_record({"pid": 100, "start_ticks": 200, "pgid": True}, "proc")

        # non-positive int
        with self.assertRaises(ValueError):
            validate_identity_record({"pid": 0, "start_ticks": 200}, "proc")
        with self.assertRaises(ValueError):
            validate_identity_record({"pid": 100, "start_ticks": -1}, "proc")

        # invalid argv
        with self.assertRaises(ValueError):
            validate_identity_record({"pid": 100, "start_ticks": 200, "argv": ["ok", 123]}, "proc")

    def test_validate_owners_dict(self):
        owners = _sample_owners()
        validated = validate_owners_dict(owners)
        self.assertEqual(len(validated), 5)

        # missing role
        incomplete = dict(owners)
        incomplete.pop("px4_fc")
        with self.assertRaises(ValueError) as cm:
            validate_owners_dict(incomplete)
        self.assertIn("Missing: ['px4_fc']", str(cm.exception))

        # extra role
        extra = dict(owners)
        extra["rogue_role"] = {"pid": 999, "start_ticks": 100}
        with self.assertRaises(ValueError) as cm:
            validate_owners_dict(extra)
        self.assertIn("Extra: ['rogue_role']", str(cm.exception))


class TestSnapshotRequestAndResponseContract(unittest.TestCase):
    def test_request_construction_and_validation(self):
        kwargs = _sample_request_kwargs()
        req = make_snapshot_request(**kwargs)
        self.assertEqual(req["schema"], REQUEST_SCHEMA)
        self.assertEqual(req["phase"], "pre_bootstrap_leaders")
        validated = validate_snapshot_request(req)
        self.assertEqual(validated, req)

    def test_request_phase_validation(self):
        kwargs = _sample_request_kwargs()
        kwargs["phase"] = "post_capture_tasks"
        req = make_snapshot_request(**kwargs)
        self.assertEqual(req["phase"], "post_capture_tasks")

        kwargs["phase"] = "unsupported_phase"
        with self.assertRaises(ValueError) as cm:
            make_snapshot_request(**kwargs)
        self.assertIn("phase must be one of", str(cm.exception))

    def test_request_bool_target_pid_ns(self):
        kwargs = _sample_request_kwargs()
        kwargs["target_pid_ns"] = True
        with self.assertRaises(ValueError) as cm:
            make_snapshot_request(**kwargs)
        self.assertIn("target_pid_ns must be a positive int", str(cm.exception))

    def test_response_construction_and_verification(self):
        req = make_snapshot_request(**_sample_request_kwargs())
        req_bytes = encode_json_strict(req)

        resp = make_snapshot_response(
            request=req,
            request_bytes=req_bytes,
            boot_id="boot-uuid-0001",
            snapshot=_sample_snapshot_payload(),
            issued_monotonic_ns=123456789,
        )
        self.assertEqual(resp["schema"], RESPONSE_SCHEMA)
        self.assertEqual(resp["request_sha256"], hashlib.sha256(req_bytes).hexdigest())

        # verify response passes strict binding check
        verify_snapshot_response_binding(
            resp,
            expected_request=req,
            expected_request_bytes=req_bytes,
            expected_boot_id="boot-uuid-0001",
        )

    def test_response_tampering_and_replay_detection(self):
        req = make_snapshot_request(**_sample_request_kwargs())
        req_bytes = encode_json_strict(req)
        resp = make_snapshot_response(
            request=req,
            request_bytes=req_bytes,
            boot_id="boot-uuid-0001",
            snapshot=_sample_snapshot_payload(),
            issued_monotonic_ns=123456789,
        )

        # 1. request_sha256 tampered
        tampered = dict(resp, request_sha256="0" * 64)
        with self.assertRaises(ValueError) as cm:
            verify_snapshot_response_binding(tampered, expected_request=req, expected_request_bytes=req_bytes)
        self.assertIn("request_sha256 mismatch", str(cm.exception))

        # 2. request_id tampered (cross-request replay)
        tampered = dict(resp, request_id="f" * 32)
        with self.assertRaises(ValueError) as cm:
            verify_snapshot_response_binding(tampered, expected_request=req, expected_request_bytes=req_bytes)
        self.assertIn("request_id mismatch", str(cm.exception))

        # 3. epoch tampered
        tampered = dict(resp, epoch="e" * 32)
        with self.assertRaises(ValueError) as cm:
            verify_snapshot_response_binding(tampered, expected_request=req, expected_request_bytes=req_bytes)
        self.assertIn("epoch mismatch", str(cm.exception))

        # 4. phase tampered
        tampered = dict(resp, phase="post_capture_tasks")
        with self.assertRaises(ValueError) as cm:
            verify_snapshot_response_binding(tampered, expected_request=req, expected_request_bytes=req_bytes)
        self.assertIn("phase mismatch", str(cm.exception))

        # 5. target_pid_ns tampered
        tampered = dict(resp, target_pid_ns=99999999)
        with self.assertRaises(ValueError) as cm:
            verify_snapshot_response_binding(tampered, expected_request=req, expected_request_bytes=req_bytes)
        self.assertIn("target_pid_ns mismatch", str(cm.exception))

        # 6. boot_id mismatch
        with self.assertRaises(ValueError) as cm:
            verify_snapshot_response_binding(
                resp, expected_request=req, expected_request_bytes=req_bytes, expected_boot_id="different-boot"
            )
        self.assertIn("boot_id mismatch", str(cm.exception))

        # 7. collector identity tampered
        tampered = dict(resp, collector={"pid": 9999, "start_ticks": 100})
        with self.assertRaises(ValueError) as cm:
            verify_snapshot_response_binding(tampered, expected_request=req, expected_request_bytes=req_bytes)
        self.assertIn("collector identity mismatch", str(cm.exception))


class TestAtomicCreateOnlyPublication(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_publish_create_only_success_and_readback(self):
        target = self.root / "sub" / "request.json"
        target.parent.mkdir(parents=True, exist_ok=True)

        req = make_snapshot_request(**_sample_request_kwargs())
        written_bytes = publish_create_only(target, req)

        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), written_bytes)

        # decode from published file
        decoded = decode_json_strict(written_bytes)
        self.assertEqual(decoded["schema"], REQUEST_SCHEMA)

    def test_publish_create_only_refuses_overwrite(self):
        target = self.root / "file.json"
        req1 = make_snapshot_request(**_sample_request_kwargs())
        publish_create_only(target, req1)
        self.assertTrue(target.exists())

        # Second publication must raise FileExistsError and preserve original content
        req2 = dict(req1, run_id="altered_run_id")
        with self.assertRaises(FileExistsError):
            publish_create_only(target, req2)

        # Verify original was NOT overwritten
        decoded = decode_json_strict(target.read_bytes())
        self.assertEqual(decoded["run_id"], req1["run_id"])

    def test_publish_refuses_symlink(self):
        target = self.root / "sym_target.json"
        real_file = self.root / "real_file.json"
        real_file.write_text("existing")

        try:
            os.symlink(real_file, target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported in this test environment")

        req = make_snapshot_request(**_sample_request_kwargs())
        with self.assertRaises(ValueError) as cm:
            publish_create_only(target, req)
        self.assertIn("Symlink", str(cm.exception))


class TestCallerMonotonicTimeout(unittest.TestCase):
    def test_verify_elapsed_monotonic_success(self):
        start = time.monotonic_ns()
        time.sleep(0.005)
        elapsed = verify_elapsed_monotonic(start, timeout_s=1.0)
        self.assertGreater(elapsed, 0)

    def test_verify_elapsed_monotonic_timeout(self):
        start = time.monotonic_ns() - 2_000_000_000  # 2s in the past
        with self.assertRaises(TimeoutError) as cm:
            verify_elapsed_monotonic(start, timeout_s=0.5)
        self.assertIn("Snapshot exchange timed out", str(cm.exception))

    def test_verify_elapsed_monotonic_rejects_bool_or_invalid(self):
        with self.assertRaises(ValueError):
            verify_elapsed_monotonic(True, 1.0)
        with self.assertRaises(ValueError):
            verify_elapsed_monotonic(time.monotonic_ns(), True)
        with self.assertRaises(ValueError):
            verify_elapsed_monotonic(time.monotonic_ns(), -1.0)
        with self.assertRaises(ValueError):
            verify_elapsed_monotonic(time.monotonic_ns(), float("nan"))


if __name__ == "__main__":
    unittest.main()
