"""Offline delivery-entry contract: real parser / admit / check calls.

This module covers MAIN CLI construction and early rejection, PV/MIXED
diagnostic gates, SHA256 + duplicate-key identity of the three frozen Linux
manifests, TEMP negatives for those checks, and a separately modelled
historical fe3 sibling.  It is pure Python: no ROS, DDS, MATLAB, native,
SITL, FC, UE, build, or flight process is started.

Not covered, and a green run here is not:
#84 / #33 / #26 acceptance, Full, G6, official MIXED/entry promotion,
auditor --output overwrite policy, or transferring a fe3 PASS onto MAIN.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

MAIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MAIN))
sys.path.insert(0, str(MAIN / "tools"))

import ap_mixed_candidate as mixed
import audit_26_closure_readiness as audit_26
import audit_pv_trajectory as audit_pv
import joint_control_candidate as control_candidate
import joint_message_candidate as message_candidate
from Simulator.wksim_core import joint as joint_mod
from Simulator.wksim_runtime.config import ConfigError
from Simulator.wksim_runtime.joint_rate_probe import (
    TIMING_PROBE_ENV,
    timing_probe_enabled,
    timing_probe_identity,
)
from tools import run_joint_flight as runner
from verify_ap_pv_candidate import checked_json

# Published freeze identities from docs/coordination/short-cycle-goal.md.
# Compared to file bytes, not to source FINAL_* assignments.
FROZEN_AP_SHA256 = "1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c"
FROZEN_CONTROL_SHA256 = "6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e"
FROZEN_MESSAGE_SHA256 = "29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219"
FROZEN_MANIFESTS = (
    ("/root/wksim-ap-mixed-fhuf05l9/mixed-build.json", FROZEN_AP_SHA256),
    ("/root/wksim-joint-control-c2IXOr/build.json", FROZEN_CONTROL_SHA256),
    ("/root/wksim-ros2-Rzj3Pf/message-build.json", FROZEN_MESSAGE_SHA256),
)
WSL_UNC_ROOT = Path(r"\\wsl$\Ubuntu-22.04")


def linux_file(posix_path):
    """Readable host path for a Linux /root file, or None if absent."""
    if os.name != "nt":
        direct = Path(posix_path)
        if direct.is_file():
            return direct
    unc = WSL_UNC_ROOT / posix_path.lstrip("/").replace("/", os.sep)
    if unc.is_file():
        return unc
    return None


def historical_fe3_root():
    """Historical fe3 comparison checkout, never treated as the MAIN entry."""
    runner_rel = Path("tools") / "run_joint_flight.py"
    if os.name != "nt":
        posix = Path("/root/wksim-release-acceptance-fe3")
        if (posix / runner_rel).is_file():
            return posix
    unc = WSL_UNC_ROOT / r"root\wksim-release-acceptance-fe3"
    if (unc / runner_rel).is_file():
        return unc
    return None


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_cli_parser(func):
    """Run the real main()'s argparse construction, stopping before parse_args."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    fn = tree.body[0]
    if not isinstance(fn, ast.FunctionDef):
        raise TypeError(func)
    namespace = dict(func.__globals__)
    for stmt in fn.body:
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "parse_args"
            for node in ast.walk(stmt)
        ):
            break
        exec(compile(ast.Module(body=[stmt], type_ignores=[]), func.__name__, "exec"), namespace)
    parsers = [value for value in namespace.values() if isinstance(value, argparse.ArgumentParser)]
    if len(parsers) != 1:
        raise AssertionError(
            f"{func.__qualname__} did not construct exactly one ArgumentParser"
        )
    return parsers[0]


def cpu_timing_enabled(environ):
    """Evaluate the real JointPhysics.__init__ assignment without constructing it."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(joint_mod.JointPhysics.__init__)))
    for stmt in ast.walk(tree):
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Attribute)
            and stmt.targets[0].attr == "cpu_timing"
        ):
            code = compile(ast.Expression(stmt.value), "cpu_timing", "eval")
            return eval(code, {"os": SimpleNamespace(environ=environ)})
    raise AssertionError("JointPhysics.__init__ has no cpu_timing assignment")


def position_argv():
    return [
        "run",
        "--control-manifest", "control.json",
        "--control-sha256", "c" * 64,
        "--ap-manifest", "ap.json",
        "--ap-sha256", "a" * 64,
        "--task-profile", "position",
    ]


def mixed_argv():
    return [
        "run",
        "--control-manifest", "control.json",
        "--control-sha256", "c" * 64,
        "--ap-mixed-manifest", "mixed.json",
        "--ap-mixed-sha256", "m" * 64,
        "--task-profile", runner.MIXED_PROFILE,
    ]


def pv_argv():
    return [
        "run",
        "--control-manifest", "control.json",
        "--control-sha256", "c" * 64,
        "--ap-mixed-manifest", "mixed.json",
        "--ap-mixed-sha256", "m" * 64,
        "--message-manifest", "message.json",
        "--message-sha256", "g" * 64,
        "--task-profile", runner.PV_PROFILE,
    ]


def parse_main(argv, *, run_return=0):
    with patch.object(runner, "run", return_value=run_return) as execute:
        code = runner.main(argv)
    return code, execute


def reject_main(argv):
    with patch.object(runner, "run") as execute, unittest.TestCase().assertRaises(SystemExit) as error:
        runner.main(argv)
    return error.exception.code, execute


class MainEntryParserTests(unittest.TestCase):
    """MAIN run_joint_flight parser: legal flags accepted, illegal rejected."""

    def test_main_parser_accepts_position_mixed_and_pv_and_rejects_unknown(self):
        for argv in (position_argv(), mixed_argv(), pv_argv()):
            with self.subTest(argv=argv):
                code, execute = parse_main(argv)
                self.assertEqual(code, 0)
                execute.assert_called_once()
        extra = position_argv() + ["--px4-manifest", "px4.json", "--px4-sha256", "p" * 64]
        code, execute = parse_main(extra)
        self.assertEqual(code, 0)
        self.assertEqual(execute.call_args.args[0].px4_manifest, "px4.json")
        code, execute = reject_main(position_argv() + ["--not-a-delivery-flag"])
        self.assertEqual(code, 2)
        execute.assert_not_called()

    def test_main_parser_rejects_incomplete_pairs_and_missing_required_control(self):
        code, execute = reject_main(["run", "--task-profile", "position"])
        self.assertEqual(code, 2)
        execute.assert_not_called()
        code, execute = reject_main(position_argv()[:-2] + ["--message-manifest", "m.json"])
        self.assertEqual(code, 2)
        execute.assert_not_called()
        code, execute = reject_main(mixed_argv() + ["--message-manifest", "m.json"])
        self.assertEqual(code, 2)
        execute.assert_not_called()

    def test_main_parser_rejects_historical_candidate_profile_literal(self):
        argv = [
            "run",
            "--control-manifest", "control.json",
            "--control-sha256", "c" * 64,
            "--ap-manifest", "ap.json",
            "--ap-sha256", "a" * 64,
            "--task-profile", "candidate",
        ]
        code, execute = reject_main(argv)
        self.assertEqual(code, 2)
        execute.assert_not_called()

    def test_main_entry_is_verified_even_if_sibling_lookup_returns_none(self):
        _ = historical_fe3_root()
        code, execute = parse_main(position_argv())
        self.assertEqual(code, 0)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[0].task_profile, "position")


class AuditCliParserTests(unittest.TestCase):
    """Auditor CLIs are taken from the real main() argparse construction."""

    def test_audit_pv_parser_accepts_directory_output_profile_and_rejects_unknown(self):
        parser = build_cli_parser(audit_pv.main)
        with tempfile.TemporaryDirectory(prefix="wksim-delivery-pv-", dir=tempfile.gettempdir()) as tmp:
            directory = Path(tmp) / "raw"
            output = Path(tmp) / "report.json"
            directory.mkdir()
            args = parser.parse_args(
                [str(directory), "--output", str(output), "--task-profile", runner.PV_PROFILE]
            )
        self.assertEqual(args.directory, directory)
        self.assertEqual(args.output, output)
        self.assertEqual(args.task_profile, runner.PV_PROFILE)
        with self.assertRaises(SystemExit) as error:
            parser.parse_args(["--not-an-audit-flag"])
        self.assertEqual(error.exception.code, 2)

    def test_audit_26_parser_defaults_to_repo_manifest_and_rejects_unknown(self):
        parser = build_cli_parser(audit_26.main)
        args = parser.parse_args([])
        self.assertEqual(args.manifest, audit_26.DEFAULT_MANIFEST)
        self.assertTrue(args.manifest.is_file())
        self.assertIsNone(args.output)
        with tempfile.TemporaryDirectory(prefix="wksim-delivery-26-", dir=tempfile.gettempdir()) as tmp:
            output = Path(tmp) / "out.json"
            chosen = Path(tmp) / "other.json"
            chosen.write_text("{}", encoding="utf-8")
            args = parser.parse_args(["--manifest", str(chosen), "--output", str(output)])
        self.assertEqual(args.manifest, chosen)
        self.assertEqual(args.output, output)
        with self.assertRaises(SystemExit) as error:
            parser.parse_args(["--root", str(MAIN)])
        self.assertEqual(error.exception.code, 2)


class AdmitAndCheckRejectionTests(unittest.TestCase):
    """admit()/check() reject illegal pairings before any verify walk."""

    def test_admit_rejects_incomplete_message_pair_before_verify(self):
        with patch.object(mixed, "verify", side_effect=AssertionError("verify started")):
            report = mixed.admit(
                "mixed.json", "a" * 64, "control.json", "b" * 64, "unit-run",
                message_manifest="message.json", message_checksum=None,
            )
        self.assertFalse(report["ok"])
        self.assertEqual(report["children_created"], 0)
        self.assertIn("incomplete", report["reasons"][0]["message"])

    def test_admit_rejects_inexact_final_manifests_before_verify(self):
        with patch.object(mixed, "verify", side_effect=AssertionError("verify started")):
            report = mixed.admit(
                "mixed.json", "0" * 64, "control.json", mixed.FINAL_CONTROL_SHA,
                "unit-run", task_profile=mixed.PV_PROFILE,
                message_manifest="message.json",
                message_checksum=mixed.FINAL_MESSAGE_SHA,
            )
        self.assertFalse(report["ok"])
        self.assertIn("exact final manifests", report["reasons"][0]["message"])

    def test_admit_rejects_unsupported_and_historical_task_profiles(self):
        with patch.object(mixed, "verify", side_effect=AssertionError("verify started")):
            for profile in ("position", "candidate", "PV", "MIXED"):
                with self.subTest(profile=profile):
                    report = mixed.admit(
                        "mixed.json", "a" * 64, "control.json", "b" * 64,
                        "unit-run", task_profile=profile,
                    )
                    self.assertFalse(report["ok"])
                    self.assertIn("Unsupported task", report["reasons"][0]["message"])

    def test_admit_rejects_pv_or_current_mixed_without_message_candidate(self):
        with patch.object(mixed, "verify", side_effect=AssertionError("verify started")):
            pv = mixed.admit(
                "mixed.json", mixed.FINAL_AP_SHA, "control.json",
                mixed.FINAL_CONTROL_SHA, "unit-run", task_profile=mixed.PV_PROFILE,
            )
            current = mixed.admit(
                "mixed.json", mixed.FINAL_AP_SHA, "control.json",
                mixed.FINAL_CONTROL_SHA, "unit-run", task_profile=mixed.PROFILE,
            )
        self.assertFalse(pv["ok"])
        self.assertIn("explicit final message candidate", pv["reasons"][0]["message"])
        self.assertFalse(current["ok"])
        self.assertIn("explicit final message candidate", current["reasons"][0]["message"])

    def test_control_and_message_check_reject_malformed_or_mismatched_sha256(self):
        with tempfile.TemporaryDirectory(prefix="wksim-delivery-check-", dir=tempfile.gettempdir()) as tmp:
            control_path = Path(tmp) / "build.json"
            message_path = Path(tmp) / "message-build.json"
            control_path.write_bytes(b'{"root": "/tmp/not-a-candidate"}\n')
            message_path.write_bytes(b'{"root": "/tmp/not-a-workspace"}\n')
            control_digest = sha256_file(control_path)
            message_digest = sha256_file(message_path)
            for checker, path, digest in (
                (control_candidate.check, control_path, control_digest),
                (message_candidate.check, message_path, message_digest),
            ):
                with self.subTest(checker=checker.__module__):
                    with self.assertRaisesRegex(ValueError, "SHA256 differs"):
                        checker(path, "0" * 64)
                    with self.assertRaisesRegex(ValueError, "SHA256 differs"):
                        checker(path, "NOT-A-SHA256")
                    with self.assertRaisesRegex(ValueError, "SHA256 differs"):
                        checker(path, digest.upper())
                    with self.assertRaises(ValueError) as error:
                        checker(path, digest)
                    self.assertNotIn("SHA256 differs", str(error.exception))


class RateAndModeGateTests(unittest.TestCase):
    """Diagnostic gates allow the current PV/MIXED set, not candidate/PV literals."""

    def test_timing_probe_env_is_three_state_and_classified_diagnostic_only(self):
        self.assertFalse(timing_probe_enabled({}))
        self.assertFalse(timing_probe_enabled({TIMING_PROBE_ENV: "0"}))
        self.assertTrue(timing_probe_enabled({TIMING_PROBE_ENV: "1"}))
        for value in ("", "2", "true", "candidate", "PV"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    timing_probe_enabled({TIMING_PROBE_ENV: value})
        identity = timing_probe_identity()
        self.assertEqual(identity["classification"], "diagnostic_only")
        self.assertFalse(identity["production_performance"])

    def test_timing_probe_run_gate_allows_pv_mixed_and_rejects_position_candidate(self):
        allowed = (runner.PV_PROFILE, runner.MIXED_PROFILE)
        self.assertNotIn("candidate", allowed)
        self.assertNotIn("PV", allowed)
        for profile in allowed:
            args = SimpleNamespace(task_profile=profile, async_model_evidence=False)
            with self.subTest(profile=profile), patch.dict(
                os.environ, {TIMING_PROBE_ENV: "1"}, clear=False,
            ), patch.object(runner, "check_isolation", side_effect=RuntimeError("after-gate")) as isolate:
                with self.assertRaisesRegex(RuntimeError, "after-gate"):
                    runner.run(args)
                isolate.assert_called_once()
        for profile in ("position", "candidate"):
            args = SimpleNamespace(task_profile=profile, async_model_evidence=False)
            with self.subTest(profile=profile), patch.dict(
                os.environ, {TIMING_PROBE_ENV: "1"}, clear=False,
            ), patch.object(runner, "check_isolation") as isolate:
                with self.assertRaises(ValueError):
                    runner.run(args)
                isolate.assert_not_called()

    def test_async_model_evidence_allows_only_pv_and_mixed(self):
        code, execute = parse_main(pv_argv() + ["--async-model-evidence"])
        self.assertEqual(code, 0)
        self.assertTrue(execute.call_args.args[0].async_model_evidence)
        code, execute = parse_main(mixed_argv() + ["--async-model-evidence"])
        self.assertEqual(code, 0)
        self.assertTrue(execute.call_args.args[0].async_model_evidence)
        code, execute = reject_main(position_argv() + ["--async-model-evidence"])
        self.assertEqual(code, 2)
        execute.assert_not_called()
        for profile in (runner.PV_PROFILE, runner.MIXED_PROFILE):
            args = SimpleNamespace(task_profile=profile, async_model_evidence=True)
            with self.subTest(allowed=profile), patch.dict(
                os.environ, {TIMING_PROBE_ENV: "0"}, clear=False,
            ), patch.object(runner, "check_isolation", side_effect=RuntimeError("after-gate")) as isolate:
                with self.assertRaisesRegex(RuntimeError, "after-gate"):
                    runner.run(args)
                isolate.assert_called_once()
        args = SimpleNamespace(task_profile="position", async_model_evidence=True)
        with patch.dict(os.environ, {TIMING_PROBE_ENV: "0"}, clear=False), patch.object(
            runner, "check_isolation",
        ) as isolate:
            with self.assertRaises(ValueError):
                runner.run(args)
            isolate.assert_not_called()

    def test_cpu_timing_predicate_is_true_only_for_literal_one(self):
        self.assertTrue(cpu_timing_enabled({"WKSIM_JOINT_CPU_TIMING": "1"}))
        for value in ("0", "true", "01", "", None):
            environ = {} if value is None else {"WKSIM_JOINT_CPU_TIMING": value}
            with self.subTest(value=value):
                self.assertFalse(cpu_timing_enabled(environ))


class FrozenManifestIdentityTests(unittest.TestCase):
    """Frozen manifests are identified by bytes + SHA256 + unique JSON keys."""

    def _resolve_frozen(self):
        """Resolve each frozen manifest independently; absent entries become per-item skips."""
        return [(posix, linux_file(posix), digest) for posix, digest in FROZEN_MANIFESTS]

    def test_frozen_external_manifests_read_bytes_match_sha256_and_unique_keys(self):
        for posix, path, digest in self._resolve_frozen():
            with self.subTest(posix=posix):
                if path is None:
                    self.skipTest("frozen Linux manifest not reachable")
                raw = path.read_bytes()
                self.assertGreater(len(raw), 0)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
                record = checked_json(path, digest)
                self.assertIsInstance(record, dict)

    def test_missing_first_manifest_does_not_block_later_reachable_verification(self):
        with tempfile.TemporaryDirectory(prefix="wksim-delivery-gap-", dir=tempfile.gettempdir()) as tmp:
            entries = []
            for index in range(3):
                path = Path(tmp) / f"build-{index}.json"
                path.write_bytes(b'{"probe": %d}\n' % index)
                entries.append((f"/root/gap-{index}/build.json", sha256_file(path), path))
            seen = []

            def gap_linux_file(posix):
                seen.append(posix)
                for candidate, _, path in entries:
                    if candidate == posix:
                        return None if candidate == entries[0][0] else path
                return None

            mocked = tuple((posix, digest) for posix, digest, _ in entries)
            with patch.object(sys.modules[__name__], "linux_file", gap_linux_file), patch.object(
                sys.modules[__name__], "FROZEN_MANIFESTS", mocked,
            ):
                case = FrozenManifestIdentityTests(
                    "test_frozen_external_manifests_read_bytes_match_sha256_and_unique_keys"
                )
                result = case.run(unittest.TestResult())
            self.assertEqual(seen, [posix for posix, _, _ in entries])
            skipped = [subtest.params["posix"] for subtest, _ in result.skipped]
            self.assertEqual(skipped, [entries[0][0]])
            self.assertEqual(result.failures, [])
            self.assertEqual(result.errors, [])
            self.assertTrue(result.wasSuccessful())

    def test_temp_one_byte_change_fails_checked_json_identity(self):
        raw = b'{"probe": true, "n": 1}\n'
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory(prefix="wksim-delivery-byte-", dir=tempfile.gettempdir()) as tmp:
            path = Path(tmp) / "mixed-build.json"
            path.write_bytes(raw)
            self.assertEqual(checked_json(path, expected)["n"], 1)
            mutated = bytearray(raw)
            mutated[2] ^= 0x01
            path.write_bytes(mutated)
            self.assertNotEqual(sha256_file(path), expected)
            with self.assertRaisesRegex(ValueError, "SHA256 differs"):
                checked_json(path, expected)

    def test_temp_duplicate_json_key_fails_checked_json(self):
        with tempfile.TemporaryDirectory(prefix="wksim-delivery-dup-", dir=tempfile.gettempdir()) as tmp:
            path = Path(tmp) / "build.json"
            path.write_bytes(b'{"probe": true, "probe": false}\n')
            digest = sha256_file(path)
            with self.assertRaises(ConfigError):
                checked_json(path, digest)
            legal = Path(tmp) / "legal.json"
            legal.write_bytes(b'{"probe": true}\n')
            self.assertEqual(checked_json(legal, sha256_file(legal)), {"probe": True})


class HistoricalFe3SiblingTests(unittest.TestCase):
    """fe3 is a historical comparison checkout, not the current MAIN entry."""

    def test_historical_fe3_sibling_is_separate_or_explicitly_skipped(self):
        sibling = historical_fe3_root()
        if sibling is None:
            self.skipTest(
                "historical fe3 sibling not reachable; MAIN entry is verified separately"
            )
        sibling_runner = sibling / "tools" / "run_joint_flight.py"
        main_runner = MAIN / "tools" / "run_joint_flight.py"
        self.assertTrue(sibling_runner.is_file())
        self.assertTrue(main_runner.is_file())
        self.assertNotEqual(sibling.resolve(), MAIN.resolve())
        sibling_digest = sha256_file(sibling_runner)
        main_digest = sha256_file(main_runner)
        self.assertEqual(len(sibling_digest), 64)
        self.assertEqual(len(main_digest), 64)
        # Distinct contracts: hashes may differ or later match; equality is not required.

    def test_main_runner_hash_is_read_independently_of_sibling(self):
        digest = sha256_file(MAIN / "tools" / "run_joint_flight.py")
        self.assertEqual(len(digest), 64)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        code, execute = parse_main(mixed_argv())
        self.assertEqual(code, 0)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[0].task_profile, runner.MIXED_PROFILE)


if __name__ == "__main__":
    unittest.main()
