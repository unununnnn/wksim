"""Pure tests for tools/analyze_early_manager_work.py.

Fixtures are REAL reports produced by the actual EarlyManagerWorkProbe
(Linux worktree) with controllable fake clocks; no native/ROS/build.

Run from the repo root:  python -B -m unittest validation.test_analyze_early_manager_work
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.analyze_early_manager_work import analyze, main  # noqa: E402


FROZEN_HELPER = (ROOT / "validation" / "coordination"
                 / "early-work-delivery-20260913"
                 / "tools__early_manager_work_probe.py")
HELPER_ROOT = ROOT if FROZEN_HELPER.is_file() else None
if HELPER_ROOT is not None:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "frozen_early_manager_work_probe", FROZEN_HELPER)
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    EarlyManagerWorkProbe = _module.EarlyManagerWorkProbe
    WINDOW_NS = _module.WINDOW_NS
    WARMUP_NS = _module.WARMUP_NS

ANCHOR = 1_000_000_000
EPOCH = "e" * 32
SEGMENT = 1
IDENTITY = {"run_id": "run-test", "scene_epoch": EPOCH, "segment": SEGMENT}


class FakeClocks:
    def __init__(self, wall, cpu):
        self.wall = list(wall)
        self.cpu = list(cpu)
        self.wall_reads = 0
        self.cpu_reads = 0

    def monotonic_ns(self):
        self.wall_reads += 1
        return self.wall[min(self.wall_reads - 1, len(self.wall) - 1)]

    def thread_time_ns(self):
        self.cpu_reads += 1
        return self.cpu[min(self.cpu_reads - 1, len(self.cpu) - 1)]


def make_report(*, phases=5, max_samples=32768):
    """A REAL probe report: interleaved phase samples with known values."""
    wall, cpu = [ANCHOR + 100 + 10 * i for i in range(phases * 2)], \
        [10 + 5 * i for i in range(phases * 2)]
    clocks = FakeClocks(wall, cpu)
    probe = EarlyManagerWorkProbe(monotonic_ns=clocks.monotonic_ns,
                                  thread_time_ns=clocks.thread_time_ns,
                                  max_samples=max_samples)
    probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
    names = ("manager_health", "rate_begin_group", "physics_advance",
             "clock_publication_log", "post_advance_readiness_summary")
    for index in range(phases):
        probe.wrap(names[index % len(names)], lambda: 40 + index,
                   lambda: EPOCH, lambda: SEGMENT, lambda: "ok")
    return probe.report(source_sha256="a" * 64, identity=IDENTITY)


@unittest.skipUnless(HELPER_ROOT is not None, "real helper not reachable")
class AnalyzeLegalTests(unittest.TestCase):
    def test_legal_report_passes_with_exact_distributions(self):
        report = make_report()
        analysis = analyze(report)
        self.assertEqual(analysis["status"], "pass")
        self.assertEqual(analysis["reasons"], [])
        self.assertEqual(analysis["identity"], IDENTITY)
        self.assertEqual(analysis["anchor_epoch"], EPOCH)
        self.assertEqual(analysis["anchor_segment"], SEGMENT)
        self.assertEqual(analysis["states"]["valid_samples"], 5)
        self.assertEqual(analysis["states"]["invalid_samples"], 0)
        for phase, stats in analysis["per_phase"].items():
            self.assertEqual(stats["wall"]["count"], 1)
            self.assertEqual(stats["wall"]["min_ns"], 10)
            self.assertEqual(stats["thread_cpu"]["min_ns"], 5)
            self.assertIsNotNone(stats["last_sample_tick"])
            self.assertEqual(stats["error_outcome"], 0)
            self.assertEqual(stats["crossing"], 0)
        ticks = [s["last_sample_tick"] for s in analysis["per_phase"].values()]
        self.assertEqual(max(ticks), 44)
        # Every phase's peak records are complete samples of the SAME event.
        for stats in analysis["per_phase"].values():
            wall_peak = stats["wall_peak_sample"]
            cpu_peak = stats["cpu_peak_sample"]
            self.assertEqual(wall_peak["wall_ns"], 10)
            self.assertEqual(wall_peak["thread_cpu_ns"], 5)
            self.assertIsNotNone(wall_peak["start_tick"])
            self.assertEqual(cpu_peak["thread_cpu_ns"], 5)
        for statement in analysis["non_claims"]:
            self.assertTrue(statement)

    def test_peak_sample_is_not_the_last_tick(self):
        wall = [ANCHOR + 100, ANCHOR + 200,       # physics 1: wall 100, cpu 15
                ANCHOR + 300, ANCHOR + 400,       # physics 2: wall 100, cpu 15
                ANCHOR + 500, ANCHOR + 9999,      # physics 3 (LAST tick): wall 9499, cpu 20
                ANCHOR + 20000, ANCHOR + 21000]   # padding reads
        cpu = [10, 25, 30, 45, 50, 70]
        clocks = FakeClocks(wall, cpu)
        probe = EarlyManagerWorkProbe(monotonic_ns=clocks.monotonic_ns,
                                      thread_time_ns=clocks.thread_time_ns)
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        probe.wrap("physics_advance", lambda: 41, lambda: EPOCH,
                   lambda: SEGMENT, lambda: "ok")
        probe.wrap("physics_advance", lambda: 42, lambda: EPOCH,
                   lambda: SEGMENT, lambda: "ok")
        probe.wrap("physics_advance", lambda: 43, lambda: EPOCH,
                   lambda: SEGMENT, lambda: "ok")
        analysis = analyze(probe.report(source_sha256="a" * 64, identity=IDENTITY))
        stats = analysis["per_phase"]["physics_advance"]
        self.assertEqual(stats["last_sample_tick"], 43)
        # wall peak is the last sample here; cpu peak is the FIRST sample
        # (cpu 15 > cpu 5 and cpu 20? -> per fixture below we assert the
        # actual same-sample record, not the max of independent columns).
        self.assertEqual(stats["wall_peak_sample"]["start_tick"], 43)
        self.assertEqual(stats["wall_peak_sample"]["wall_ns"], 9499)
        self.assertEqual(stats["wall_peak_sample"]["thread_cpu_ns"], 20)
        self.assertEqual(stats["cpu_peak_sample"]["start_tick"], 43)
        self.assertEqual(stats["cpu_peak_sample"]["thread_cpu_ns"], 20)
        self.assertEqual(stats["cpu_peak_sample"]["wall_ns"], 9499)

    def test_truncated_state_preserved_not_failed(self):
        report = make_report(phases=7, max_samples=3)
        self.assertTrue(report["truncated"])
        analysis = analyze(report)
        self.assertEqual(analysis["status"], "pass")
        self.assertTrue(analysis["states"]["truncated"])
        self.assertEqual(analysis["states"]["dropped"], 4)

    def test_crossing_and_error_outcome_preserved(self):
        report = make_report()
        # Crossing sample (produced by the real probe across the cutoff).
        clocks = FakeClocks([ANCHOR + WINDOW_NS - 5, ANCHOR + WINDOW_NS + 5],
                            [0, 0])
        probe = EarlyManagerWorkProbe(monotonic_ns=clocks.monotonic_ns,
                                      thread_time_ns=clocks.thread_time_ns)
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        probe.wrap("physics_advance", lambda: 99, lambda: EPOCH,
                   lambda: SEGMENT, lambda: "ok")
        report2 = probe.report(source_sha256="a" * 64, identity=IDENTITY)
        report["samples"] = report["samples"] + report2["samples"]
        # An error-outcome sample produced by the real probe.
        clocks = FakeClocks([ANCHOR + 500, ANCHOR + 600], [0, 0])
        probe = EarlyManagerWorkProbe(monotonic_ns=clocks.monotonic_ns,
                                      thread_time_ns=clocks.thread_time_ns)
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)

        def boom():
            raise RuntimeError("x")

        with self.assertRaises(RuntimeError):
            probe.wrap("manager_health", lambda: 50, lambda: EPOCH,
                       lambda: SEGMENT, boom)
        report3 = probe.report(source_sha256="a" * 64, identity=IDENTITY)
        report["samples"] = report["samples"] + report3["samples"]
        analysis = analyze(report)
        self.assertEqual(analysis["status"], "pass")
        self.assertEqual(analysis["states"]["crossing_total"], 1)
        self.assertEqual(analysis["states"]["error_outcome_total"], 1)
        # error-outcome samples never enter distributions
        self.assertEqual(
            analysis["per_phase"]["manager_health"]["wall"]["count"], 1)


@unittest.skipUnless(HELPER_ROOT is not None, "real helper not reachable")
class AnalyzeIdentityTests(unittest.TestCase):
    def analysis_of(self, report, **mutations):
        value = json.loads(json.dumps(report))
        for key, replacement in mutations.items():
            value[key] = replacement
        return analyze(value)

    def test_window_identity_mismatch_fails(self):
        report = make_report()
        for mutations in (
                {"window_ns": 5_000_000_000},
                {"warmup_ns": 1_000_000_000},
                {"anchor_epoch": "other"},
                {"anchor_segment": 2},
                {"identity": dict(IDENTITY, scene_epoch="other")},
                {"identity": dict(IDENTITY, segment=2)},
                {"identity": dict(IDENTITY, segment=True)},
                {"anchor_segment": True},
                {"diagnostic_error_total": 3},
                {"diagnostic_error_dropped": 1},
                {"diagnostic_only": False},
                {"production_performance": True},
                {"source_sha256": "bad"},
                {"window": {"anchor_wall_ns": ANCHOR,
                            "cutoff_wall_ns": ANCHOR + 1,
                            "warmup_after_ns": ANCHOR + WARMUP_NS}},
                {"window": {"anchor_wall_ns": ANCHOR,
                            "cutoff_wall_ns": ANCHOR + WINDOW_NS,
                            "warmup_after_ns": ANCHOR + 1}},
        ):
            analysis = self.analysis_of(report, **mutations)
            self.assertEqual(analysis["status"], "failed", mutations)
            self.assertTrue(analysis["reasons"], mutations)

    def test_missing_fields_fail(self):
        report = make_report()
        for key in ("diagnostic", "source_sha256", "window", "identity",
                    "samples"):
            value = json.loads(json.dumps(report))
            del value[key]
            analysis = analyze(value)
            self.assertEqual(analysis["status"], "failed", key)


@unittest.skipUnless(HELPER_ROOT is not None, "real helper not reachable")
class AnalyzeSampleValidationTests(unittest.TestCase):
    def test_invalid_total_counts_every_bad_sample_not_the_bounded_list(self):
        report = make_report()
        bad_cases = []
        for index in range(200):
            value = json.loads(json.dumps(report["samples"][0]))
            value["wall_ns"] = -index - 1
            bad_cases.append(value)
        report["samples"] = bad_cases
        analysis = analyze(report)
        self.assertEqual(analysis["status"], "failed")
        self.assertEqual(analysis["states"]["invalid_samples"], 200)
        self.assertLessEqual(len(analysis["states"]["diagnostic_errors"]), 0)

    def test_negative_and_inconsistent_samples_preserved_as_invalid(self):
        report = make_report()
        bad_cases = []
        for mutate in (
                lambda s: s.update(wall_ns=-1),
                lambda s: s.update(thread_cpu_ns=-1),
                lambda s: s.update(wall_ns=999),
                lambda s: s.update(start_ns=ANCHOR - 1),
                lambda s: s.update(start_ns=ANCHOR + WINDOW_NS + 1),
                lambda s: s.update(crossing=True),
                lambda s: s.update(warmup=False),
                lambda s: s.update(end_tick=0),
                lambda s: s.update(outcome="maybe"),
                lambda s: s.update(phase="mystery"),
        ):
            value = json.loads(json.dumps(report["samples"][0]))
            mutate(value)
            bad_cases.append(value)
        report["samples"] = bad_cases
        analysis = analyze(report)
        self.assertEqual(analysis["status"], "failed")
        self.assertEqual(analysis["states"]["invalid_samples"], len(bad_cases))
        self.assertEqual(analysis["states"]["valid_samples"], 0)


@unittest.skipUnless(HELPER_ROOT is not None, "real helper not reachable")
class CliTests(unittest.TestCase):
    def test_cli_writes_once_and_refuses_overwrite(self):
        report = make_report()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "early-manager-work.json"
            output_path = Path(tmp) / "analysis.json"
            input_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(main([str(input_path), "--output", str(output_path)]), 0)
            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(written["status"], "pass")
            import hashlib
            self.assertEqual(written["input_sha256"],
                             hashlib.sha256(input_path.read_bytes()).hexdigest())
            # Second run on the same output must refuse (exclusive create).
            self.assertEqual(main([str(input_path), "--output", str(output_path)]), 1)
            self.assertTrue(output_path.is_file())  # untouched


if __name__ == "__main__":
    unittest.main()
