"""Contract tests for the offline 1x readiness-latency analyzer (v2, dual-run).

Pure Python: no ROS, no SITL, no builds.  Synthetic fixtures declare runs with
paths and pins relative to a temporary evidence root (no fixed repository
prefix); the final class re-derives the known failure facts of both sealed
#62 runs from the real retained inputs when present.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import analyze_joint_readiness_latency as analyzer

EVIDENCE = ROOT / "validation/lunar-20-epoch-1"
PERIOD = 4_000_000
SECOND_EPOCH = "2a8d5df1dd4244c3868dc7f38e85a369"
FIXTURE_RUN_ID = "fixture-rate61"
SEGMENT_KEYS = ("requested_rate", "request_id", "segment_id", "latched", "anchor",
                "measured_rate", "measurement", "completed_groups",
                "worst_lateness_ns", "steady_after_ns")


def _group_rows(epoch, wall, index, start_lateness, work_ns, earliest):
    start_tick = 40 + index * 4
    ideal_start = wall + index * PERIOD
    actual_start = ideal_start + start_lateness
    actual_end = actual_start + work_ns
    base = dict(epoch=epoch, segment_id=1, request_id="config", requested_rate=1.0,
                transition=False, start_tick=start_tick, end_tick=start_tick + 4,
                ideal_start_ns=ideal_start, ideal_end_ns=ideal_start + PERIOD,
                actual_start_ns=actual_start)
    start = dict(base, kind="rate_group_start", tick=start_tick,
                 issued_monotonic_ns=actual_start, earliest_start_ns=earliest,
                 lateness_ns=start_lateness)
    end = dict(base, kind="rate_group_end", tick=start_tick + 4,
               issued_monotonic_ns=actual_end, earliest_start_ns=earliest,
               actual_end_ns=actual_end,
               lateness_ns=max(0, actual_end - (ideal_start + PERIOD)))
    return start, end


def _trace_rows(epoch, wall, latch_tick, latch_lateness,
                latenesses=(1_000, 2_000, 3_000), work_ns=2_000_000):
    rows = [
        dict(kind="rate_request", epoch=epoch, tick=0, issued_monotonic_ns=1,
             request_id="config", requested_rate=1.0),
        dict(kind="rate_bootstrap", epoch=epoch, tick=0, issued_monotonic_ns=2,
             classification="untimed_until_first_synchronized_barrier"),
        dict(kind="transport_initialized", epoch=epoch, tick=0, issued_monotonic_ns=3,
             physical_tick=0, task_execution_requires_explicit_go=True),
        dict(kind="untimed_group_start", epoch=epoch, tick=0, issued_monotonic_ns=4,
             classification="bootstrap", start_tick=0, end_tick=4, actual_start_ns=10),
        dict(kind="untimed_group_end", epoch=epoch, tick=4, issued_monotonic_ns=5,
             classification="bootstrap", actual_end_ns=20),
    ]
    anchor_body = {"tick": 40, "wall_ns": wall, "transition": False}
    rows.append(dict(kind="rate_anchor", epoch=epoch, tick=40, issued_monotonic_ns=6,
                     reason="synchronized_boundary", requested_rate=1.0,
                     request_id="config", segment_id=1, latched=False, anchor=anchor_body,
                     measured_rate=None, measurement="timed_segment", completed_groups=0,
                     worst_lateness_ns=0, steady_after_ns=wall + 2_000_000_000))
    previous_start = None
    for index, lateness in enumerate(latenesses):
        ideal_start = wall + index * PERIOD
        earliest = ideal_start if previous_start is None else max(
            ideal_start, previous_start + PERIOD)
        start, end = _group_rows(epoch, wall, index, lateness, work_ns, earliest)
        previous_start = start["actual_start_ns"]
        rows.extend((start, end))
    completed = len(latenesses)
    last_end = rows[-1]
    worst = max([latch_lateness] + [r["lateness_ns"] for r in rows
                if r["kind"] in ("rate_group_start", "rate_group_end")])
    measured = completed * PERIOD / (last_end["actual_end_ns"] - wall)
    summary = dict(epoch=epoch, tick=latch_tick, requested_rate=1.0, request_id="config",
                   segment_id=1, latched=True, anchor=anchor_body, measured_rate=measured,
                   measurement="timed_segment", completed_groups=completed,
                   worst_lateness_ns=worst, steady_after_ns=wall + 2_000_000_000)
    rows.append(dict(summary, kind="rate_unmet", issued_monotonic_ns=9,
                     reason="resource_insufficient", lateness_ns=latch_lateness))
    rows.append(dict(summary, kind="rate_segment_end", issued_monotonic_ns=10,
                     reason="fault"))
    return rows


def _write_run(root, directory, epoch, wall, latch_tick, latch_lateness,
               expected_run_id, **kwargs):
    path = root / directory
    path.mkdir(parents=True)
    rows = _trace_rows(epoch, wall, latch_tick, latch_lateness, **kwargs)
    files = {
        "rate.jsonl": [json.dumps(r) for r in rows],
        "clock.jsonl": [json.dumps(dict(version=1, epoch=epoch, tick=t,
                                        time_ns=t * 1_000_000, phase="running"))
                        for t in range(latch_tick + 1)],
        "scene-lifecycle.jsonl": [
            json.dumps(dict(kind="permission", epoch=epoch, tick=0, phase="running",
                            message=dict(run_id=expected_run_id))),
            json.dumps(dict(kind="permission", epoch=epoch, tick=latch_tick,
                            phase="faulted", message=dict(run_id=expected_run_id))),
            json.dumps(dict(kind="faulted_clock", epoch=epoch, tick=latch_tick,
                            phase="faulted")),
            json.dumps(dict(kind="fault_latched", epoch=epoch, tick=latch_tick,
                            phase="faulted")),
        ],
    }
    for name, lines in files.items():
        (path / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (path / "faults.json").write_text(json.dumps([dict(
        error="RateUnmet('rate_unmet/resource_insufficient')", type="RateUnmet",
        authority=dict(version=1, epoch=epoch, tick=latch_tick, phase="faulted",
                       fault="rate_unmet/resource_insufficient"))]), encoding="utf-8")
    segment_end = [r for r in rows if r["kind"] == "rate_segment_end"][0]
    last_segment = {key: segment_end[key] for key in SEGMENT_KEYS}
    (path / "result.json").write_text(json.dumps(dict(
        status="failed", epoch=epoch, run_id=expected_run_id,
        error="InterruptedError('Owned joint epoch interrupted')",
        authority=dict(version=1, epoch=epoch, tick=latch_tick, phase="faulted",
                       fault="Owned joint epoch interrupted"),
        rate=dict(last_segment=last_segment))), encoding="utf-8")
    pins = {name: hashlib.sha256((path / name).read_bytes()).hexdigest()
            for name in analyzer.CONSUMED}
    measured = [r for r in rows if r["kind"] == "rate_unmet"][0]["measured_rate"]
    expect = {"tick": latch_tick, "lateness_ns": latch_lateness,
              "completed_groups": len(kwargs.get("latenesses", (1_000, 2_000, 3_000))),
              "measured_rate": measured}
    return {"evidence_id": directory.replace("/", "@") + "@" + epoch,
            "expected_run_id": expected_run_id, "epoch": epoch, "directory": directory,
            "expect": expect, "sha256": pins}


def _write_evidence(target, mutate_facts=None):
    runs = [
        _write_run(target, "epoch-raw", "de6ba7f2530e4607b91e154f9b8f79a3",
                   174232624670, 52, 100_000_001, expected_run_id=FIXTURE_RUN_ID),
        _write_run(target, "case/run/epochs/" + "a" * 32, "a" * 32,
                   68961050621, 96, 101_000_000, expected_run_id=FIXTURE_RUN_ID,
                   latenesses=(2_000, 3_000, 4_000, 5_000)),
    ]
    facts = {"issue": 62, "fault": "RateUnmet", "epochs_run": 1, "runs": runs}
    if mutate_facts:
        mutate_facts(facts)
    (target / "failure-facts.json").write_text(json.dumps(facts), encoding="utf-8")
    return target


class ReadinessLatencyTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="readiness-latency-"))
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))

    def analyze(self, **kwargs):
        return analyzer.analyze(_write_evidence(self.dir), **kwargs)

    def repin(self, directory, name):
        path = self.dir / directory / name
        facts = json.loads((self.dir / "failure-facts.json").read_text())
        for run in facts["runs"]:
            if run["directory"] == directory:
                run["sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.dir / "failure-facts.json").write_text(json.dumps(facts))

    def rewrite_rows(self, directory, mutate, name="rate.jsonl"):
        path = self.dir / directory / name
        if name.endswith(".jsonl"):
            rows = [json.loads(l) for l in path.read_text().splitlines()]
            mutate(rows)
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        else:
            value = json.loads(path.read_text())
            mutate(value)
            path.write_text(json.dumps(value))
        self.repin(directory, name)

    def test_dual_run_decomposition_and_closure(self):
        result = self.analyze()
        self.assertEqual(result["status"], "analyzed")
        self.assertEqual([r["run_id"] for r in result["runs"]],
                         [FIXTURE_RUN_ID, FIXTURE_RUN_ID])
        self.assertEqual([r["epoch"] for r in result["runs"]],
                         ["de6ba7f2530e4607b91e154f9b8f79a3", "a" * 32])
        self.assertEqual(len({r["evidence_id"] for r in result["runs"]}), 2)
        first, second = result["runs"]
        self.assertEqual(first["latch"]["tick"], 52)
        self.assertEqual(first["latch"]["lateness_ns"], 100_000_001)
        self.assertEqual(first["raw_clock_phase_at_latch"], "running")
        self.assertEqual(first["scene_faulted_clock_phase"], "faulted")
        self.assertEqual(first["timed_groups"], 3)
        self.assertEqual(second["latch"]["tick"], 96)
        self.assertEqual(second["timed_groups"], 4)
        for run in result["runs"]:
            self.assertEqual(run["creep_total_ns"],
                             run["work_over_total_ns"] + run["release_excess_total_ns"])
            self.assertEqual(set(run["per_phase"]), {"running/stabilization"})
        self.assertEqual(first["creep_total_ns"], 2_000)  # 1000ns lateness steps
        self.assertEqual(first["bootstrap_groups"]["count"], 1)

    def test_deterministic_output_bytes(self):
        first = json.dumps(self.analyze(), sort_keys=True, allow_nan=False)
        shutil.rmtree(self.dir)
        self.dir.mkdir()
        second = json.dumps(self.analyze(), sort_keys=True, allow_nan=False)
        self.assertEqual(first, second)

    def test_cli_stdout_and_output_bytes_match_recompute(self):
        _write_evidence(self.dir)
        output = self.dir / "report.json"
        tool = ROOT / "tools" / "analyze_joint_readiness_latency.py"
        completed = subprocess.run(
            [sys.executable, "-B", str(tool), str(self.dir), "--output", str(output)],
            capture_output=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        expected = (json.dumps(analyzer.analyze(self.dir), indent=2,
                               sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        self.assertEqual(completed.stdout, expected)
        self.assertEqual(output.read_bytes(), expected)
        again = subprocess.run(
            [sys.executable, "-B", str(tool), str(self.dir), "--output", str(output)],
            capture_output=True, timeout=60)
        self.assertEqual(again.returncode, 0, again.stderr.decode())  # idempotent

    def test_atomic_output_refuses_clobber(self):
        _write_evidence(self.dir)
        result = analyzer.analyze(self.dir)
        raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        output = self.dir / "report.json"
        analyzer._write_output(output, raw)
        analyzer._write_output(output, raw)  # identical bytes: idempotent
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            analyzer._write_output(output, raw + "\n")
        leftovers = [p for p in self.dir.iterdir() if p.name.startswith("report.json.")]
        self.assertEqual(leftovers, [])

    def test_atomic_output_refuses_raced_clobber_and_accepts_raced_same_bytes(self):
        _write_evidence(self.dir)
        result = analyzer.analyze(self.dir)
        raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        original_link = analyzer.os.link

        raced_same = self.dir / "same.json"
        def create_same_then_link(source, destination, *args, **kwargs):
            Path(destination).write_bytes(raw.encode("utf-8"))
            return original_link(source, destination, *args, **kwargs)
        analyzer.os.link = create_same_then_link
        try:
            analyzer._write_output(raced_same, raw)
        finally:
            analyzer.os.link = original_link
        self.assertEqual(raced_same.read_bytes(), raw.encode("utf-8"))

        raced_different = self.dir / "different.json"
        def create_different_then_link(source, destination, *args, **kwargs):
            Path(destination).write_bytes(b"concurrent bytes")
            return original_link(source, destination, *args, **kwargs)
        analyzer.os.link = create_different_then_link
        try:
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                analyzer._write_output(raced_different, raw)
        finally:
            analyzer.os.link = original_link
        self.assertEqual(raced_different.read_bytes(), b"concurrent bytes")
        self.assertEqual([p for p in self.dir.iterdir()
                          if p.name.startswith("same.json.") or p.name.startswith("different.json.")], [])

    def test_pinned_input_drift_is_rejected(self):
        _write_evidence(self.dir)
        path = self.dir / "epoch-raw" / "rate.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "pinned input drifted"):
            analyzer.analyze(self.dir)

    def test_missing_input_and_pin_set_shape_are_rejected(self):
        _write_evidence(self.dir)
        (self.dir / "epoch-raw" / "clock.jsonl").unlink()
        with self.assertRaisesRegex(ValueError, "missing or linked"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        def drop_pin(facts):
            del facts["runs"][0]["sha256"]["clock.jsonl"]
        _write_evidence(self.dir, mutate_facts=drop_pin)
        with self.assertRaisesRegex(ValueError, "pin set must cover exactly"):
            analyzer.analyze(self.dir)

    def test_run_directory_escape_is_rejected(self):
        def escape(facts):
            facts["runs"][0]["directory"] = "../epoch-raw"
        _write_evidence(self.dir, mutate_facts=escape)
        with self.assertRaisesRegex(ValueError, "escapes the evidence root"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        def absolute(facts):
            facts["runs"][0]["directory"] = str(self.dir / "epoch-raw")
        _write_evidence(self.dir, mutate_facts=absolute)
        with self.assertRaisesRegex(ValueError, "escapes the evidence root"):
            analyzer.analyze(self.dir)

    def test_symlinked_run_directory_is_rejected(self):
        _write_evidence(self.dir)
        link = self.dir / "linked"
        try:
            os.symlink(self.dir / "epoch-raw", link, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink unavailable: {error}")
        facts = json.loads((self.dir / "failure-facts.json").read_text())
        facts["runs"][0]["directory"] = "linked"
        facts["runs"][0]["evidence_id"] = "linked-run"
        (self.dir / "failure-facts.json").write_text(json.dumps(facts))
        with self.assertRaisesRegex(ValueError, "symlink|through links"):
            analyzer.analyze(self.dir)

    def test_legacy_top_level_pins_are_rejected(self):
        def legacy(facts):
            facts["sha256"] = {"anything": "0" * 64}
        _write_evidence(self.dir, mutate_facts=legacy)
        with self.assertRaisesRegex(ValueError, "legacy top-level pin set"):
            analyzer.analyze(self.dir)

    def test_run_cardinality_and_epochs_run_are_enforced(self):
        def three_runs(facts):
            facts["runs"] = facts["runs"] + [dict(facts["runs"][1], evidence_id="third",
                                                     epoch="b" * 32, directory="third")]
        _write_evidence(self.dir, mutate_facts=three_runs)
        with self.assertRaisesRegex(ValueError, "exactly two runs"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        def epoch_two(facts):
            facts["epochs_run"] = 2
        _write_evidence(self.dir, mutate_facts=epoch_two)
        with self.assertRaisesRegex(ValueError, "epochs_run must stay 1"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        def same_directory(facts):
            facts["runs"][1]["directory"] = "epoch-raw"
        _write_evidence(self.dir, mutate_facts=same_directory)
        with self.assertRaisesRegex(ValueError, "directories must be distinct"):
            analyzer.analyze(self.dir)

    def test_expectation_mismatch_is_rejected(self):
        def wrong_tick(facts):
            facts["runs"][1]["expect"]["tick"] += 4
        _write_evidence(self.dir, mutate_facts=wrong_tick)
        with self.assertRaisesRegex(ValueError, "pinned expectation"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        def wrong_rate(facts):
            facts["runs"][0]["expect"]["measured_rate"] = 0.5
        _write_evidence(self.dir, mutate_facts=wrong_rate)
        with self.assertRaisesRegex(ValueError, "pinned expectation"):
            analyzer.analyze(self.dir)

    def test_wrong_period_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "requested rate differs|ideal group period"):
            self.analyze(period_ns=8_000_000)

    def test_raw_clock_must_end_at_latch_and_reject_latch_plus_one(self):
        _write_evidence(self.dir)

        def append_after_latch(rows):
            last = rows[-1]
            rows.append(dict(last, tick=last["tick"] + 1,
                             time_ns=last["time_ns"] + 1_000_000))

        self.rewrite_rows("epoch-raw", append_after_latch, name="clock.jsonl")
        with self.assertRaisesRegex(ValueError, "last/max tick must equal"):
            analyzer.analyze(self.dir)

    def test_raw_clock_paused_and_unknown_phases_are_rejected_after_repin(self):
        for phase in ("paused", "unknown"):
            with self.subTest(phase=phase):
                shutil.rmtree(self.dir)
                self.dir.mkdir()
                _write_evidence(self.dir)

                def phase_tamper(rows):
                    rows[0] = dict(rows[0], phase=phase)

                self.rewrite_rows("epoch-raw", phase_tamper, name="clock.jsonl")
                with self.assertRaisesRegex(ValueError, "raw clock phase must be running or faulted"):
                    analyzer.analyze(self.dir)

    def test_scene_paused_and_unknown_phases_are_rejected_after_repin(self):
        for phase in ("paused", "unknown"):
            with self.subTest(phase=phase):
                shutil.rmtree(self.dir)
                self.dir.mkdir()
                _write_evidence(self.dir)

                def phase_tamper(rows):
                    rows[0] = dict(rows[0], phase=phase)

                self.rewrite_rows("epoch-raw", phase_tamper,
                                  name="scene-lifecycle.jsonl")
                with self.assertRaisesRegex(ValueError, "scene phase must be running or faulted"):
                    analyzer.analyze(self.dir)

    def test_scene_faulted_permission_is_before_adjacent_terminal_events(self):
        _write_evidence(self.dir)

        def permission_after_clock(rows):
            rows[1], rows[2] = rows[2], rows[1]

        self.rewrite_rows("epoch-raw", permission_after_clock,
                          name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "same-tick faulted permission"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)

        def insert_between_terminal_events(rows):
            rows.insert(-1, dict(rows[-1], kind="scene_observation"))

        self.rewrite_rows("epoch-raw", insert_between_terminal_events,
                          name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "must be adjacent"):
            analyzer.analyze(self.dir)

    def test_exact_100ms_cannot_latch(self):
        _write_evidence(self.dir)
        def cap_latch(rows):
            for index, row in enumerate(rows):
                if row["kind"] == "rate_unmet":
                    rows[index] = dict(row, lateness_ns=100_000_000,
                                       worst_lateness_ns=100_000_000)
        self.rewrite_rows("epoch-raw", cap_latch)
        with self.assertRaisesRegex(ValueError, "pseudo-fault"):
            analyzer.analyze(self.dir)

    def test_catch_up_and_earliest_start_tamper_are_rejected(self):
        _write_evidence(self.dir)
        def earliest_tamper(rows):
            for index, row in enumerate(rows):
                if row["kind"] in ("rate_group_start", "rate_group_end") \
                        and row["start_tick"] == 44:
                    rows[index] = dict(row, earliest_start_ns=row["ideal_start_ns"])
        self.rewrite_rows("epoch-raw", earliest_tamper)
        with self.assertRaisesRegex(ValueError, "changes release scheduling"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def catch_up(rows):
            for index, row in enumerate(rows):
                if row["kind"] in ("rate_group_start", "rate_group_end") \
                        and row["start_tick"] == 48:
                    rows[index] = dict(row, actual_start_ns=row["ideal_start_ns"],
                                       earliest_start_ns=row["ideal_start_ns"])
                if row["kind"] == "rate_group_end" and row["start_tick"] == 48:
                    rows[index] = dict(rows[index], lateness_ns=0,
                                       actual_end_ns=row["ideal_start_ns"] + 2_000_000)
        self.rewrite_rows("epoch-raw", catch_up)
        with self.assertRaisesRegex(ValueError, "catches up|changes release scheduling|lateness is inconsistent"):
            analyzer.analyze(self.dir)

    def test_result_authority_and_last_segment_tamper_are_rejected(self):
        _write_evidence(self.dir)
        def authority_tamper(value):
            value["authority"]["tick"] += 4
        self.rewrite_rows("epoch-raw", authority_tamper, name="result.json")
        with self.assertRaisesRegex(ValueError, "result.json authority"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def segment_tamper(value):
            value["rate"]["last_segment"]["completed_groups"] += 1
        self.rewrite_rows("epoch-raw", segment_tamper, name="result.json")
        with self.assertRaisesRegex(ValueError, "last_segment"):
            analyzer.analyze(self.dir)

    def test_rate_summary_cross_record_tamper_is_rejected(self):
        _write_evidence(self.dir)
        def unmet_anchor_tamper(rows):
            for row in rows:
                if row["kind"] == "rate_unmet":
                    row["anchor"]["wall_ns"] += 1_000_000
        self.rewrite_rows("epoch-raw", unmet_anchor_tamper)
        with self.assertRaisesRegex(ValueError, "rate_anchor|rate_unmet.*anchor"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def segment_count_tamper(rows):
            for row in rows:
                if row["kind"] == "rate_segment_end":
                    row["completed_groups"] = 999
        self.rewrite_rows("epoch-raw", segment_count_tamper)
        def result_count_tamper(value):
            value["rate"]["last_segment"]["completed_groups"] = 999
        self.rewrite_rows("epoch-raw", result_count_tamper, name="result.json")
        with self.assertRaisesRegex(ValueError, "rate_unmet.*completed_groups|rate_segment_end"):
            analyzer.analyze(self.dir)

    def test_scene_fault_tick_and_phase_tamper_are_rejected(self):
        _write_evidence(self.dir)
        def scene_tamper(rows):
            for index, row in enumerate(rows):
                if row["kind"] == "fault_latched":
                    rows[index] = dict(row, tick=48)
        self.rewrite_rows("epoch-raw", scene_tamper, name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "scene faulted events|scene event ticks"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def phase_tamper(rows):
            for index, row in enumerate(rows):
                if row["kind"] == "fault_latched":
                    rows[index] = dict(row, phase="running")
        self.rewrite_rows("epoch-raw", phase_tamper, name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "scene faulted events|fault_latched"):
            analyzer.analyze(self.dir)

    def test_evidence_identity_is_bound_to_result_and_scene(self):
        def wrong_declaration(facts):
            facts["runs"][1]["expected_run_id"] = "foreign-run"
        _write_evidence(self.dir, mutate_facts=wrong_declaration)
        with self.assertRaisesRegex(ValueError, "result.json.*run_id"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def wrong_result(value):
            value["run_id"] = "foreign-run"
        self.rewrite_rows("epoch-raw", wrong_result, name="result.json")
        with self.assertRaisesRegex(ValueError, "result.json.*run_id"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def wrong_scene_message(rows):
            for row in rows:
                if row.get("message"):
                    row["message"]["run_id"] = "foreign-run"
                    break
        self.rewrite_rows("epoch-raw", wrong_scene_message, name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "message.run_id"):
            analyzer.analyze(self.dir)

    def test_scene_latch_order_and_ticks_are_strict(self):
        _write_evidence(self.dir)
        def pre_latch_fault(rows):
            rows[0] = dict(rows[0], phase="faulted")
        self.rewrite_rows("epoch-raw", pre_latch_fault, name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "scene faulted events"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def reversed_terminal_events(rows):
            rows[-2], rows[-1] = rows[-1], rows[-2]
        self.rewrite_rows("epoch-raw", reversed_terminal_events, name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "must be adjacent|faulted_clock.*precede"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def duplicate_latch(rows):
            rows.append(dict(rows[-1]))
        self.rewrite_rows("epoch-raw", duplicate_latch, name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "fault_latched"):
            analyzer.analyze(self.dir)

        shutil.rmtree(self.dir)
        self.dir.mkdir()
        _write_evidence(self.dir)
        def decreasing_tick(rows):
            rows[1] = dict(rows[1], tick=52)
            rows[2] = dict(rows[2], tick=0)
        self.rewrite_rows("epoch-raw", decreasing_tick, name="scene-lifecycle.jsonl")
        with self.assertRaisesRegex(ValueError, "non-decreasing"):
            analyzer.analyze(self.dir)

    def test_measured_rate_mismatch_is_rejected(self):
        _write_evidence(self.dir)
        def measured_tamper(rows):
            for index, row in enumerate(rows):
                if row["kind"] == "rate_unmet":
                    rows[index] = dict(row, measured_rate=0.5)
        self.rewrite_rows("epoch-raw", measured_tamper)
        with self.assertRaisesRegex(ValueError, "measured_rate"):
            analyzer.analyze(self.dir)

    def test_epoch_change_is_rejected(self):
        _write_evidence(self.dir)
        def epoch_tamper(rows):
            rows[7] = dict(rows[7], epoch="0" * 32)
        self.rewrite_rows("epoch-raw", epoch_tamper)
        with self.assertRaisesRegex(ValueError, "epoch changed"):
            analyzer.analyze(self.dir)

    def test_cross_record_mismatch_is_rejected(self):
        _write_evidence(self.dir)
        def faults_tamper(value):
            value[0]["authority"]["tick"] = 56
        self.rewrite_rows("epoch-raw", faults_tamper, name="faults.json")
        with self.assertRaisesRegex(ValueError, "faults.json authority"):
            analyzer.analyze(self.dir)


@unittest.skipUnless((EVIDENCE / "failure-facts.json").is_file(),
                     "sealed #62 epoch-1 evidence not present")
class RetainedEvidenceReproductionTests(unittest.TestCase):
    """Re-derive the published #62 failure facts of both sealed runs."""

    @classmethod
    def setUpClass(cls):
        cls.result = analyzer.analyze(EVIDENCE)

    def test_both_known_failures_reproduce_exactly(self):
        self.assertEqual(self.result["status"], "analyzed")
        self.assertEqual(len(self.result["runs"]), 2)
        first, second = self.result["runs"]
        self.assertEqual(first["latch"],
                         {"tick": 7588, "lateness_ns": 100_312_171,
                          "completed_groups": 1887,
                          "measured_rate": 0.9871539539890174})
        self.assertEqual(first["epoch"], "de6ba7f2530e4607b91e154f9b8f79a3")
        self.assertEqual(first["timed_groups"], 1887)
        self.assertEqual(first["max_group_start_lateness_ns"], 99_636_364)
        self.assertEqual(second["latch"],
                         {"tick": 19608, "lateness_ns": 105_497_865,
                          "completed_groups": 4892,
                          "measured_rate": 0.994637564416662})
        self.assertEqual(second["epoch"], SECOND_EPOCH)
        self.assertEqual(second["run_id"], "rate61-cpu8-20260909-e1-e2561e27")
        self.assertEqual(second["evidence_id"],
                         "case-20260909@2a8d5df1dd4244c3868dc7f38e85a369")
        self.assertEqual(second["timed_groups"], 4892)
        for run in self.result["runs"]:
            self.assertEqual(run["creep_total_ns"],
                             run["work_over_total_ns"] + run["release_excess_total_ns"])
            self.assertEqual(set(run["per_phase"]),
                             {"running/stabilization", "running/steady"})

    def test_output_file_matches_recompute(self):
        output = EVIDENCE / "readiness-latency.json"
        if not output.is_file():
            self.skipTest("readiness-latency.json not generated")
        retained = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(retained, self.result)


if __name__ == "__main__":
    unittest.main()
