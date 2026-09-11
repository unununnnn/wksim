"""Focused standard-library tests for #20 offline rate failure audit seam.

Verifies:
1. Existing success / schedule compliance.
2. Genuine >100ms RateUnmet failure audit producing structured non-PASS output.
3. Missing flow.json rejected in steady mode, accepted only in explicit failure mode.
4. Fail-closed rejection on <=100ms falsely labeled failures.
5. Fail-closed rejection on epoch, order, and timing tampering.
6. Fail-closed rejection on terminal status mismatch / using failure mode as acceptance.
7. CLI exit and status codes.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.audit_joint_rate import (
    TIMING_PROBE_IDENTITY,
    audit,
    audit_failure,
    measurement,
    schedule,
    timing_probe_identity,
)
from tools.audit_joint_rate_lifecycle import closed_rate_schedule
from Simulator.wksim_runtime.joint_rate_probe import timing_probe_identity as runtime_probe_identity


def make_synthetic_case(root, epoch="a" * 32, requested_rate=1.0, lateness_ns=105_000_000,
                        *, status="failed", fault_type="RateUnmet", tamper=None):
    root = Path(root)
    wrapper = dict(
        manager_returncode=1 if status == "failed" else 0,
        remaining_manager_group=[],
        requested_rate=requested_rate,
        mode="steady"
    )
    (root / "wrapper.json").write_text(json.dumps(wrapper))

    epoch_res = dict(
        status=status,
        run_id="synthetic-run-1",
        epoch=epoch,
        faults=[dict(type=fault_type, fault="rate_unmet/resource_insufficient",
                     authority=dict(epoch=epoch, tick=44, phase="faulted",
                                    fault="rate_unmet/resource_insufficient"))] if fault_type else [],
        source_sha256={"dummy.py": "0" * 64}
    )
    run_res = dict(
        status=status,
        run_id="synthetic-run-1",
        config=dict(requested_rate=requested_rate),
        epochs=[dict(epoch=epoch, result=epoch_res)]
    )
    run_dir = root / "run"
    epochs_dir = run_dir / "epochs" / epoch
    epochs_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(json.dumps(run_res))
    (epochs_dir / "result.json").write_text(json.dumps(epoch_res))
    (epochs_dir / "faults.json").write_text(json.dumps(epoch_res["faults"]))

    # Rate trace rows
    period = int(4_000_000 / requested_rate)
    wall_start = 1_000_000_000
    rows = [
        dict(kind="rate_anchor", epoch=epoch, segment_id=1, requested_rate=requested_rate,
             request_id="config", anchor=dict(tick=40, wall_ns=wall_start, transition=False),
             steady_after_ns=wall_start + 2_000_000_000)
    ]
    # Group 0: tick 40 -> 44
    ideal_start = wall_start
    ideal_end = wall_start + period
    actual_start = ideal_start
    actual_end = ideal_end + lateness_ns

    if tamper == "foreign_epoch":
        epoch_for_rows = "b" * 32
    else:
        epoch_for_rows = epoch

    g_start = dict(
        kind="rate_group_start", epoch=epoch_for_rows, segment_id=1, request_id="config",
        requested_rate=requested_rate, transition=False, tick=40, start_tick=40, end_tick=44,
        ideal_start_ns=ideal_start if tamper != "ideal_timing" else ideal_start + 999,
        ideal_end_ns=ideal_end,
        earliest_start_ns=ideal_start,
        actual_start_ns=actual_start if tamper != "nonmonotonic_order" else actual_start - 5_000_000,
        lateness_ns=0
    )
    g_end = dict(
        kind="rate_group_end", epoch=epoch_for_rows, segment_id=1, request_id="config",
        requested_rate=requested_rate, transition=False, tick=44, start_tick=40, end_tick=44,
        ideal_start_ns=ideal_start if tamper != "ideal_timing" else ideal_start + 999,
        ideal_end_ns=ideal_end,
        earliest_start_ns=ideal_start,
        actual_start_ns=actual_start if tamper != "nonmonotonic_order" else actual_start - 5_000_000,
        actual_end_ns=actual_end,
        lateness_ns=lateness_ns
    )
    rows.append(g_start)
    if tamper == "duplicate_group":
        rows.append(dict(g_start))
    rows.append(g_end)

    if fault_type == "RateUnmet":
        rows.append(dict(
            kind="rate_unmet", epoch=epoch_for_rows, segment_id=1, reason="resource_insufficient",
            lateness_ns=lateness_ns, requested_rate=requested_rate, request_id="config",
            tick=44, anchor=dict(tick=40, wall_ns=wall_start, transition=False)
        ))
        rows.append(dict(
            kind="rate_segment_end", epoch=epoch_for_rows, segment_id=1, completed_groups=1,
            worst_lateness_ns=lateness_ns, reason="fault"
        ))
    else:
        rows.append(dict(
            kind="rate_segment_end", epoch=epoch_for_rows, segment_id=1, completed_groups=1,
            worst_lateness_ns=lateness_ns, reason="completed"
        ))

    rate_text = "".join(json.dumps(r) + "\n" for r in rows)
    (epochs_dir / "rate.jsonl").write_text(rate_text)
    return root


class TestAuditJointRate(unittest.TestCase):

    def test_timing_probe_identity_is_exact_and_opt_in(self):
        self.assertEqual(TIMING_PROBE_IDENTITY, runtime_probe_identity())
        self.assertFalse(timing_probe_identity({"kind": "rate_group_start"}))
        self.assertTrue(timing_probe_identity({
            "kind": "rate_group_start",
            "rate_timing_probe": dict(TIMING_PROBE_IDENTITY),
        }))

        for record in (
            {"kind": "rate_timing_probe"},
            {"kind": "rate_timing_probe", "rate_timing_probe": {}},
            {"kind": "rate_group_start", "rate_timing_probe": {
                **TIMING_PROBE_IDENTITY,
                "production_performance": True,
            }},
            {"kind": "rate_group_start", "rate_timing_probe": {
                **TIMING_PROBE_IDENTITY,
                "classification": "production",
            }},
        ):
            with self.subTest(record=record), self.assertRaises((AssertionError, ValueError)):
                timing_probe_identity(record)

    def test_schedule_validates_probe_identity_without_rejecting_other_events(self):
        epoch = "d" * 32
        rows = [
            {"kind": "unrelated_diagnostic", "epoch": epoch},
            {"kind": "rate_anchor", "epoch": epoch, "segment_id": 1,
             "requested_rate": 1.0, "request_id": "config",
             "anchor": {"tick": 40, "wall_ns": 1_000_000_000, "transition": False},
             "steady_after_ns": 3_000_000_000},
            {"kind": "rate_group_start", "epoch": epoch, "segment_id": 1,
             "request_id": "config", "requested_rate": 1.0, "transition": False,
             "tick": 40, "start_tick": 40, "end_tick": 44,
             "ideal_start_ns": 1_000_000_000, "ideal_end_ns": 1_004_000_000,
             "earliest_start_ns": 1_000_000_000, "actual_start_ns": 1_000_000_000,
             "lateness_ns": 0},
            {"kind": "rate_timing_probe", "epoch": epoch,
             "rate_timing_probe": dict(TIMING_PROBE_IDENTITY)},
            {"kind": "rate_group_end", "epoch": epoch, "segment_id": 1,
             "request_id": "config", "requested_rate": 1.0, "transition": False,
             "tick": 44, "start_tick": 40, "end_tick": 44,
             "ideal_start_ns": 1_000_000_000, "ideal_end_ns": 1_004_000_000,
             "earliest_start_ns": 1_000_000_000, "actual_start_ns": 1_000_000_000,
             "actual_end_ns": 1_004_000_000, "lateness_ns": 0},
            {"kind": "rate_segment_end", "epoch": epoch, "segment_id": 1,
             "completed_groups": 1, "worst_lateness_ns": 0, "reason": "completed"},
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False) as handle:
            handle.write("".join(json.dumps(row) + "\n" for row in rows))
            path = Path(handle.name)
        try:
            self.assertEqual(len(schedule(path, epoch)), 1)
            rows[3]["rate_timing_probe"]["production_performance"] = True
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaises((AssertionError, ValueError)):
                schedule(path, epoch)
        finally:
            path.unlink(missing_ok=True)

    def test_genuine_rate_unmet_failure_audit_synthetic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, lateness_ns=105_000_000)
            result = audit(case_dir, allow_failure=True)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["classification"], "rate_unmet")
            self.assertEqual(result["reason"], "resource_insufficient")
            self.assertEqual(result["lateness_ns"], 105_000_000)
            self.assertEqual(result["worst_lateness_ns"], 105_000_000)
            self.assertEqual(result["failure_tick"], 44)
            self.assertEqual(result["completed_groups"], 1)
            self.assertIn("Certified RateUnmet failure", result["limitations"][0])

    def test_genuine_rate_unmet_failure_audit_retained_case(self):
        case_path = REPO / "validation/lunar-20-epoch-1/case"
        if not case_path.exists():
            self.skipTest("Retained case directory missing")
        result = audit(case_path, allow_failure=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["classification"], "rate_unmet")
        self.assertEqual(result["reason"], "resource_insufficient")
        self.assertEqual(result["epoch"], "2a8d5df1dd4244c3868dc7f38e85a369")
        self.assertGreater(result["lateness_ns"], 100_000_000)
        self.assertEqual(result["failure_tick"], 19608)
        self.assertEqual(result["completed_groups"], 4892)

    def test_missing_flow_accepted_only_in_explicit_failure_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, lateness_ns=105_000_000)
            # In steady mode (default), missing flow.json MUST raise ValueError
            with self.assertRaises(ValueError) as ctx:
                audit(case_dir, mode="steady", allow_failure=False)
            self.assertIn("Steady formal flight requires flow.json", str(ctx.exception))

            # In explicit failure mode, missing flow.json is accepted and audited
            res_failure = audit(case_dir, mode="failure")
            self.assertEqual(res_failure["status"], "failed")
            self.assertEqual(res_failure["classification"], "rate_unmet")

            res_allow = audit(case_dir, allow_failure=True)
            self.assertEqual(res_allow["status"], "failed")
            self.assertEqual(res_allow["classification"], "rate_unmet")

    def test_sub_100ms_rejection(self):
        # A run that falsely labels <=100ms lateness as rate_unmet must fail closed
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, lateness_ns=99_000_000)
            with self.assertRaises((AssertionError, ValueError)):
                audit_failure(case_dir)

        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, lateness_ns=100_000_000)
            with self.assertRaises((AssertionError, ValueError)):
                audit_failure(case_dir)

    def test_success_lifecycle_schedule_never_accepts_rate_unmet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, lateness_ns=105_000_000)
            epoch = 'a' * 32
            with self.assertRaises((AssertionError, ValueError)) as ctx:
                closed_rate_schedule(Path(case_dir) / 'run/epochs' / epoch / 'rate.jsonl', epoch,
                                     expected_terminal_reasons=('set-rate',))
            self.assertIn('rate_unmet', str(ctx.exception))

    def test_closed_schedule_rejects_empty_segment(self):
        epoch = 'e' * 32
        rows = [
            dict(kind='rate_anchor', epoch=epoch, segment_id=1, requested_rate=1.0,
                 request_id='r', reason='synchronized_boundary',
                 anchor=dict(tick=40, wall_ns=1_000_000_000, transition=False)),
            dict(kind='rate_segment_end', epoch=epoch, segment_id=1,
                 completed_groups=0, worst_lateness_ns=0, reason='completed'),
        ]
        with tempfile.NamedTemporaryFile('w+', delete=False) as handle:
            handle.write(''.join(json.dumps(row) + '\n' for row in rows))
            path = Path(handle.name)
        try:
            with self.assertRaisesRegex((AssertionError, ValueError), 'without a group'):
                closed_rate_schedule(path, epoch, expected_terminal_reasons=('set-rate',))
        finally:
            path.unlink(missing_ok=True)

    def test_closed_schedule_rejects_bad_terminal_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, status='pass', fault_type=None, lateness_ns=0)
            epoch = 'a' * 32
            path = Path(case_dir) / 'run/epochs' / epoch / 'rate.jsonl'
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[-1]['reason'] = 'set-rate'
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            self.assertEqual(len(closed_rate_schedule(path, epoch,
                                                      expected_terminal_reasons=('set-rate',))), 1)
            rows[-1]['reason'] = 'stop'
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            with self.assertRaisesRegex(ValueError, 'does not match production close/reanchor'):
                closed_rate_schedule(path, epoch, expected_terminal_reasons=('set-rate',))
            rows[-1]['reason'] = 'forged'
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            with self.assertRaisesRegex(ValueError, 'unknown or failure terminal reason'):
                closed_rate_schedule(path, epoch, expected_terminal_reasons=('set-rate',))

    def test_schedule_rejects_overdue_second_group_without_catch_up(self):
        epoch = 'd' * 32
        wall = 1_000_000_000
        period = 4_000_000
        first_start = wall + 10_000_000
        second_start = wall + period
        rows = [dict(kind='rate_anchor', epoch=epoch, segment_id=1, requested_rate=1.0,
                     request_id='r', anchor=dict(tick=40, wall_ns=wall, transition=False))]
        for index, actual_start in enumerate((first_start, second_start)):
            tick = 40 + index * 4
            ideal = wall + index * period
            earliest = ideal if index == 0 else first_start + period
            rows.extend([
                dict(kind='rate_group_start', epoch=epoch, segment_id=1, request_id='r',
                     requested_rate=1.0, transition=False, tick=tick, start_tick=tick,
                     end_tick=tick + 4, ideal_start_ns=ideal, ideal_end_ns=ideal + period,
                     earliest_start_ns=earliest, actual_start_ns=actual_start,
                     lateness_ns=max(0, actual_start - ideal)),
                dict(kind='rate_group_end', epoch=epoch, segment_id=1, request_id='r',
                     requested_rate=1.0, transition=False, tick=tick + 4, start_tick=tick,
                     end_tick=tick + 4, ideal_start_ns=ideal, ideal_end_ns=ideal + period,
                     earliest_start_ns=earliest, actual_start_ns=actual_start,
                     actual_end_ns=actual_start + period,
                     lateness_ns=max(0, actual_start - ideal)),
            ])
        rows.append(dict(kind='rate_segment_end', epoch=epoch, segment_id=1,
                         completed_groups=2, worst_lateness_ns=10_000_000,
                         reason='completed'))
        with tempfile.NamedTemporaryFile('w+', delete=False) as handle:
            handle.write(''.join(json.dumps(row) + '\n' for row in rows))
            path = Path(handle.name)
        try:
            with self.assertRaisesRegex(ValueError, 'caught up an overdue group'):
                schedule(path, epoch, allow_failure=False)
        finally:
            path.unlink(missing_ok=True)

    def test_epoch_mismatch_rejection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, tamper="foreign_epoch")
            with self.assertRaises((AssertionError, ValueError)):
                audit_failure(case_dir)

    def test_timing_and_order_tampering_rejection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, tamper="ideal_timing")
            with self.assertRaises((AssertionError, ValueError)):
                audit_failure(case_dir)

        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, tamper="nonmonotonic_order")
            with self.assertRaises((AssertionError, ValueError)):
                audit_failure(case_dir)

        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, tamper="duplicate_group")
            with self.assertRaises((AssertionError, ValueError)):
                audit_failure(case_dir)

    def test_malformed_terminal_status_and_no_acceptance(self):
        # 1. Failure audit requires failed run status
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, status="failed")
            run_path = Path(case_dir) / "run/result.json"
            run = json.loads(run_path.read_text())
            run["status"] = "pass"
            run_path.write_text(json.dumps(run))
            with self.assertRaises((AssertionError, ValueError)) as ctx:
                audit_failure(case_dir)
            self.assertIn("Failure audit requires failed run status", str(ctx.exception))

        # 2. Failure audit mode cannot be used to accept a passing run (with flow.json)
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = make_synthetic_case(temp_dir, status="pass")
            (Path(case_dir) / "flow.json").write_text(json.dumps(dict(status="behavior_pass", mode="steady")))
            with self.assertRaises(ValueError) as ctx:
                audit(case_dir, mode="failure")
            self.assertIn("Failure audit mode cannot be used to accept a passing run", str(ctx.exception))

    def test_synthetic_steady_success_schedule(self):
        epoch = "c" * 32
        rows = [
            dict(kind="rate_anchor", epoch=epoch, segment_id=1, requested_rate=1.0,
                 request_id="config", anchor=dict(tick=40, wall_ns=1_000_000_000, transition=False),
                 steady_after_ns=3_000_000_000)
        ]
        wall = 1_000_000_000
        for i in range(10):
            tick = 40 + i * 4
            ideal_s = wall + i * 4_000_000
            ideal_e = ideal_s + 4_000_000
            rows.append(dict(kind="rate_group_start", epoch=epoch, segment_id=1, request_id="config",
                             requested_rate=1.0, transition=False, tick=tick, start_tick=tick,
                             end_tick=tick + 4, ideal_start_ns=ideal_s, ideal_end_ns=ideal_e,
                             earliest_start_ns=ideal_s, actual_start_ns=ideal_s, lateness_ns=0))
            rows.append(dict(kind="rate_group_end", epoch=epoch, segment_id=1, request_id="config",
                             requested_rate=1.0, transition=False, tick=tick + 4, start_tick=tick,
                             end_tick=tick + 4, ideal_start_ns=ideal_s, ideal_end_ns=ideal_e,
                             earliest_start_ns=ideal_s, actual_start_ns=ideal_s, actual_end_ns=ideal_e,
                             lateness_ns=0))
        rows.append(dict(kind="rate_segment_end", epoch=epoch, segment_id=1, completed_groups=10,
                         worst_lateness_ns=0, reason="completed"))
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
            f.flush()
            temp_path = Path(f.name)
        try:
            segments = schedule(temp_path, epoch, allow_failure=False)
            self.assertEqual(len(segments), 1)
            self.assertEqual(segments[1]["worst_ns"], 0)
        finally:
            temp_path.unlink(missing_ok=True)

    def test_cli_exit_and_status(self):
        case_path = REPO / "validation/lunar-20-epoch-1/case"
        if not case_path.exists():
            self.skipTest("Retained case directory missing")

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "cli_audit.json"

            # 1. Steady mode on failed case: exit code must be 1, status must be failed
            cmd_steady = [sys.executable, "-B", str(REPO / "tools/audit_joint_rate.py"),
                          str(case_path), "--output", str(out_path), "--mode", "steady"]
            proc_steady = subprocess.run(cmd_steady, capture_output=True, text=True)
            self.assertEqual(proc_steady.returncode, 1)
            data_steady = json.loads(out_path.read_text())
            self.assertEqual(data_steady["status"], "failed")
            self.assertIn("flow.json", data_steady["runs"][0]["error"])

            # 2. Failure mode on genuine RateUnmet: exit code must be 1 (non-PASS),
            # but audit succeeds in generating structured failure facts
            failure_out = Path(temp_dir) / "failure_audit.json"
            cmd_failure = [sys.executable, "-B", str(REPO / "tools/audit_joint_rate.py"),
                           str(case_path), "--output", str(failure_out), "--mode", "failure"]
            proc_failure = subprocess.run(cmd_failure, capture_output=True, text=True)
            self.assertEqual(proc_failure.returncode, 1)
            data_failure = json.loads(failure_out.read_text())
            self.assertEqual(data_failure["status"], "failed")
            run0 = data_failure["runs"][0]
            self.assertEqual(run0["status"], "failed")
            self.assertEqual(run0["classification"], "rate_unmet")
            self.assertEqual(run0["epoch"], "2a8d5df1dd4244c3868dc7f38e85a369")
            self.assertGreater(run0["lateness_ns"], 100_000_000)

            # 3. Allow-failure flag: exit code must be 1 (non-PASS), structured failure written
            allow_out = Path(temp_dir) / "allow_failure_audit.json"
            cmd_allow = [sys.executable, "-B", str(REPO / "tools/audit_joint_rate.py"),
                         str(case_path), "--output", str(allow_out), "--allow-failure"]
            proc_allow = subprocess.run(cmd_allow, capture_output=True, text=True)
            self.assertEqual(proc_allow.returncode, 1)
            data_allow = json.loads(allow_out.read_text())
            self.assertEqual(data_allow["status"], "failed")
            self.assertEqual(data_allow["runs"][0]["classification"], "rate_unmet")

            # A structured failure audit is retained evidence and may not be overwritten.
            repeat = subprocess.run(cmd_failure, capture_output=True, text=True)
            self.assertNotEqual(repeat.returncode, 0)
            self.assertIn("refusing to overwrite", repeat.stderr)


if __name__ == "__main__":
    unittest.main()
