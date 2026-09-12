"""Pure behavior tests for tools/early_manager_work_probe.py and its guards.

No native/ROS/model/build.  Clocks/thread CPU are fakes with read counters;
actions are fakes; the CLI gate drives the REAL run_joint_flight.main with
run()/task_main() mocked, and the programmatic run() guard is exercised
directly against the real run() preamble with check_isolation mocked.

Run from the worktree root:
    python3 -B -m unittest validation.test_early_manager_work_probe
"""
import contextlib
import io
import os
import sys
import types
import unittest
import unittest.mock as mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.early_manager_work_probe import (  # noqa: E402
    MAX_DIAGNOSTIC_ERRORS,
    MAX_SAMPLES,
    WARMUP_NS,
    WINDOW_NS,
    EarlyManagerWorkProbe,
)
import run_joint_flight  # noqa: E402

ANCHOR = 1_000_000_000
EPOCH = "e" * 32
PV = run_joint_flight.PV_PROFILE
MIXED = run_joint_flight.MIXED_PROFILE

AP_MIXED = ("/root/wksim-ap-mixed-fhuf05l9/mixed-build.json",
            "1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c")
CONTROL = ("/root/wksim-joint-control-c2IXOr/build.json",
           "6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e")
MESSAGE = ("/root/wksim-ros2-Rzj3Pf/message-build.json",
           "29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219")
AP_CLOCK = ("/root/wksim-ap-clock-stop-0XQqdR/wksim-build.json", "0" * 64)
TIMING_ENVS = {"WKSIM_JOINT_CPU_TIMING": "1",
               "WKSIM_JOINT_RATE_TIMING_PROBE": "1"}


class FakeClocks:
    def __init__(self, wall_values, cpu_values):
        self.wall = list(wall_values)
        self.cpu = list(cpu_values)
        self.wall_reads = 0
        self.cpu_reads = 0

    def monotonic_ns(self):
        self.wall_reads += 1
        return self.wall[min(self.wall_reads - 1, len(self.wall) - 1)]

    def thread_time_ns(self):
        self.cpu_reads += 1
        return self.cpu[min(self.cpu_reads - 1, len(self.cpu) - 1)]


def make_probe(wall_values, cpu_values=None, **kwargs):
    clocks = FakeClocks(wall_values, cpu_values or [0] * 64)
    probe = EarlyManagerWorkProbe(monotonic_ns=clocks.monotonic_ns,
                                  thread_time_ns=clocks.thread_time_ns,
                                  **kwargs)
    return probe, clocks


SEGMENT = 1


def wrap(probe, phase, action, tick=1, epoch=EPOCH, segment=SEGMENT):
    return probe.wrap(phase, lambda: tick, lambda: epoch, lambda: segment,
                      action)


class FakeAction:
    def __init__(self, result=None, error=None):
        self.calls = 0
        self.result = result
        self.error = error

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class WindowTests(unittest.TestCase):
    def test_validation_identity_and_single_latch(self):
        probe, _ = make_probe([ANCHOR])
        with self.assertRaises(ValueError):
            probe.set_window(anchor_wall_ns=1.5, epoch=EPOCH, segment=SEGMENT)
        with self.assertRaises(ValueError):
            probe.set_window(anchor_wall_ns=ANCHOR, epoch="", segment=SEGMENT)
        with self.assertRaises(ValueError):
            probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment="")
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        self.assertEqual(probe.window, (ANCHOR, ANCHOR + WINDOW_NS))
        with self.assertRaises(ValueError):
            probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        with self.assertRaises(ValueError):
            EarlyManagerWorkProbe(max_samples=0)
        with self.assertRaises(ValueError):
            EarlyManagerWorkProbe(max_diagnostic_errors=0)

    def test_no_anchor_no_reads_no_samples(self):
        probe, clocks = make_probe([ANCHOR] * 4)
        action = FakeAction(result="r")
        self.assertEqual(wrap(probe, "manager_health", action), "r")
        self.assertEqual(action.calls, 1)
        self.assertEqual((clocks.wall_reads, clocks.cpu_reads), (0, 0))
        region = probe.begin("manager_health", lambda: 1, lambda: EPOCH, lambda: SEGMENT)
        self.assertIsNone(region)
        self.assertEqual((clocks.wall_reads, clocks.cpu_reads), (0, 0))

    def test_unknown_phase_rejected_before_action(self):
        probe, _ = make_probe([ANCHOR])
        action = FakeAction()
        with self.assertRaises(ValueError):
            wrap(probe, "mystery", action)
        self.assertEqual(action.calls, 0)


class WrapSemanticsTests(unittest.TestCase):
    def test_sample_fields_return_and_warmup_markers(self):
        probe, clocks = make_probe(
            [ANCHOR + 100, ANCHOR + 150, ANCHOR + WARMUP_NS + 5,
             ANCHOR + WARMUP_NS + 6], [10, 25, 30, 40])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        action = FakeAction(result={"ok": True})
        self.assertEqual(wrap(probe, "physics_advance", action, tick=41),
                         {"ok": True})
        wrap(probe, "manager_health", FakeAction(), tick=42)
        samples = probe.report(source_sha256="s", identity={})["samples"]
        first, second = samples
        self.assertEqual(first["phase"], "physics_advance")
        self.assertEqual((first["start_tick"], first["end_tick"]), (41, 41))
        self.assertEqual((first["wall_ns"], first["thread_cpu_ns"]), (50, 15))
        self.assertTrue(first["warmup"])
        self.assertEqual(first["outcome"], "ok")
        self.assertFalse(second["warmup"])  # past the 2 s warmup marker
        self.assertEqual(clocks.wall_reads, 4)

    def test_past_cutoff_runs_without_sample(self):
        probe, clocks = make_probe([ANCHOR + WINDOW_NS + 1, ANCHOR + WINDOW_NS + 2])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        action = FakeAction(result="late")
        self.assertEqual(wrap(probe, "manager_health", action), "late")
        self.assertEqual(action.calls, 1)
        self.assertEqual(clocks.wall_reads, 1)
        self.assertEqual(probe.report(source_sha256="s", identity={})["samples"], [])

    def test_crossing_cutoff_is_marked(self):
        probe, _ = make_probe([ANCHOR + WINDOW_NS - 10, ANCHOR + WINDOW_NS + 5])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        wrap(probe, "physics_advance", FakeAction())
        (sample,) = probe.report(source_sha256="s", identity={})["samples"]
        self.assertTrue(sample["crossing"])

    def test_truncation_is_explicit_and_bounded(self):
        probe, _ = make_probe([ANCHOR + 1] * 16)
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        limited = EarlyManagerWorkProbe(
            monotonic_ns=probe._monotonic_ns,
            thread_time_ns=probe._thread_time_ns, max_samples=3)
        limited.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        action = FakeAction()
        for _ in range(5):
            wrap(limited, "manager_health", action)
        report = limited.report(source_sha256="s", identity={})
        self.assertEqual(len(report["samples"]), 3)
        self.assertTrue(report["truncated"])
        self.assertEqual(report["dropped"], 2)
        self.assertEqual(action.calls, 5)

    def test_readers_outside_cpu_interval_at_end(self):
        """A slow end-side tick callback is excluded from BOTH wall and CPU."""
        tick_cpu_calls = []

        def slow_tick():
            tick_cpu_calls.append(1)
            return 9

        # wall: start 100, end 200; cpu: start 10, end 20.  If the end-side
        # tick callback were inside the CPU interval, cpu_ns would exceed 10.
        probe, _ = make_probe([ANCHOR + 100, ANCHOR + 200], [10, 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        probe.wrap("physics_advance", slow_tick, lambda: EPOCH,
                           lambda: SEGMENT, FakeAction())
        (sample,) = probe.report(source_sha256="s", identity={})["samples"]
        self.assertEqual(sample["thread_cpu_ns"], 10)
        self.assertEqual(sample["wall_ns"], 100)
        self.assertEqual((sample["start_tick"], sample["end_tick"]), (9, 9))
        self.assertEqual(len(tick_cpu_calls), 2)


class ExceptionContractTests(unittest.TestCase):
    """Diagnostic failures never mask the action's exception; cancellation
    types propagate when the action itself succeeded."""

    def setUp(self):
        self.probe, self.clocks = make_probe([ANCHOR + 1] * 8)
        self.probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)

    def test_action_error_sampled_and_propagates_identically(self):
        error = RuntimeError("boom")
        action = FakeAction(error=error)
        with self.assertRaises(RuntimeError) as caught:
            wrap(self.probe, "physics_advance", action)
        self.assertIs(caught.exception, error)
        (sample,) = self.probe.report(source_sha256="s", identity={})["samples"]
        self.assertEqual(sample["outcome"], "error")

    def test_action_error_plus_sampling_error_keeps_action_error(self):
        error = RuntimeError("action-boom")
        action = FakeAction(error=error)
        with mock.patch.object(self.probe, "_monotonic_ns",
                               side_effect=[ANCHOR + 1, RuntimeError("clock-boom")]):
            with self.assertRaises(RuntimeError) as caught:
                wrap(self.probe, "physics_advance", action)
        self.assertIs(caught.exception, error)  # the ACTION's error
        report = self.probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertFalse(report["diagnostic_clean"])
        self.assertIn("clock-boom", report["diagnostic_errors"][0]["error"])

    def test_action_error_plus_sampling_interrupt_keeps_action_error(self):
        error = RuntimeError("action-boom")
        action = FakeAction(error=error)
        with mock.patch.object(self.probe, "_monotonic_ns",
                               side_effect=[ANCHOR + 1, KeyboardInterrupt]):
            with self.assertRaises(RuntimeError) as caught:
                wrap(self.probe, "physics_advance", action)
        self.assertIs(caught.exception, error)  # cancel does not mask it either
        report = self.probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertEqual(report["diagnostic_error_total"], 1)

    def test_action_success_plus_sampling_interrupt_propagates_cancel(self):
        action = FakeAction(result="fine")
        with mock.patch.object(self.probe, "_monotonic_ns",
                               side_effect=[ANCHOR + 1, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                wrap(self.probe, "physics_advance", action)
        report = self.probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertEqual(report["diagnostic_error_total"], 0)  # propagated, not listed

    def test_end_clock_failure_without_action_error_is_explicit(self):
        action = FakeAction(result="fine")
        with mock.patch.object(self.probe, "_monotonic_ns",
                               side_effect=[ANCHOR + 1, RuntimeError("clock-boom")]):
            returned = wrap(self.probe, "physics_advance", action)
        self.assertEqual(returned, "fine")
        report = self.probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertFalse(report["diagnostic_clean"])

    def test_end_tick_failure_does_not_mask_action_error(self):
        error = RuntimeError("action-boom")
        action = FakeAction(error=error)
        with self.assertRaises(RuntimeError) as caught:
            self.probe.wrap("physics_advance",
                            mock.Mock(side_effect=[5, RuntimeError("tick-boom")]),
                            lambda: EPOCH, lambda: SEGMENT, action)
        self.assertIs(caught.exception, error)
        report = self.probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertIn("tick-boom", report["diagnostic_errors"][0]["error"])

    def test_non_monotonic_clocks_produce_no_sample(self):
        action = FakeAction(result="ok")
        with mock.patch.object(self.probe, "_monotonic_ns",
                               side_effect=[ANCHOR + 100, ANCHOR + 50]):
            self.assertEqual(wrap(self.probe, "physics_advance", action), "ok")
        with mock.patch.object(self.probe, "_monotonic_ns",
                               side_effect=[ANCHOR + 100, ANCHOR + 200]):
            with mock.patch.object(self.probe, "_thread_time_ns",
                                   side_effect=[100, 50]):
                self.assertEqual(wrap(self.probe, "physics_advance", action), "ok")
        report = self.probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertEqual(len(report["diagnostic_errors"]), 2)

    def test_epoch_mix_is_a_diagnostic_error_not_a_sample(self):
        self.probe.wrap("physics_advance", lambda: 1, lambda: "other-epoch", lambda: SEGMENT,
                        FakeAction(result="ok"))
        report = self.probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertIn("epoch changed", report["diagnostic_errors"][0]["error"])
        self.assertEqual(report["anchor_epoch"], EPOCH)
        self.assertEqual(report["anchor_segment"], SEGMENT)


class RegionTests(unittest.TestCase):
    """Regions carry real tick/epoch readers, verify identity at close, and
    end() is idempotent."""

    def test_region_real_end_tick_and_identity_check(self):
        ticks = iter([7, 8, 9])
        probe, _ = make_probe([ANCHOR + 10, ANCHOR + 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        region = probe.begin("post_advance_readiness_summary",
                             lambda: next(ticks), lambda: EPOCH,
                             lambda: SEGMENT)
        region.end()
        (sample,) = probe.report(source_sha256="s", identity={})["samples"]
        self.assertEqual((sample["start_tick"], sample["end_tick"]), (7, 8))
        self.assertNotEqual(sample["end_tick"], None)

    def test_region_epoch_change_at_close_is_diagnostic_error(self):
        probe, _ = make_probe([ANCHOR + 10, ANCHOR + 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        region = probe.begin("post_advance_readiness_summary",
                             lambda: 7, lambda: "other-epoch",
                             lambda: SEGMENT)
        region.end()
        report = probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertIn("epoch changed", report["diagnostic_errors"][0]["error"])
        self.assertFalse(report["diagnostic_clean"])

    def test_region_repeated_end_never_appends(self):
        probe, _ = make_probe([ANCHOR + 10, ANCHOR + 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        region = probe.begin("post_advance_readiness_summary",
                             lambda: 7, lambda: EPOCH, lambda: SEGMENT)
        region.end()
        self.assertTrue(region.closed)
        region.end()
        region.end(outcome="error")
        samples = probe.report(source_sha256="s", identity={})["samples"]
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["outcome"], "ok")

    def test_region_error_path_records_then_reraises(self):
        probe, _ = make_probe([ANCHOR + 10, ANCHOR + 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        error = RuntimeError("region-boom")
        region = probe.begin("post_advance_readiness_summary",
                             lambda: 8, lambda: EPOCH, lambda: SEGMENT)
        with self.assertRaises(RuntimeError) as caught:
            try:
                raise error
            except RuntimeError:
                region.end(outcome="error")
                raise
        self.assertIs(caught.exception, error)
        (sample,) = probe.report(source_sha256="s", identity={})["samples"]
        self.assertEqual(sample["outcome"], "error")

    def test_region_none_when_unsampled(self):
        probe, clocks = make_probe([ANCHOR + WINDOW_NS + 1])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        self.assertIsNone(probe.begin("post_advance_readiness_summary",
                                      lambda: 1, lambda: EPOCH, lambda: SEGMENT))
        self.assertEqual(clocks.wall_reads, 1)


class SegmentBindingTests(unittest.TestCase):
    def test_segment_change_produces_no_valid_sample(self):
        probe, _ = make_probe([ANCHOR + 10, ANCHOR + 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        wrap(probe, "physics_advance", FakeAction(result="ok"), segment=2)
        report = probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertIn("segment changed", report["diagnostic_errors"][0]["error"])
        self.assertFalse(report["diagnostic_clean"])

    def test_same_epoch_and_segment_record_valid_sample(self):
        probe, _ = make_probe([ANCHOR + 10, ANCHOR + 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        wrap(probe, "physics_advance", FakeAction(result="ok"))
        report = probe.report(source_sha256="s", identity={})
        self.assertEqual(len(report["samples"]), 1)
        self.assertTrue(report["diagnostic_clean"])
        self.assertEqual(report["anchor_segment"], SEGMENT)

    def test_region_segment_change_at_close_is_diagnostic_error(self):
        probe, _ = make_probe([ANCHOR + 10, ANCHOR + 20])
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        region = probe.begin("post_advance_readiness_summary",
                             lambda: 7, lambda: EPOCH, lambda: 2)
        region.end()
        report = probe.report(source_sha256="s", identity={})
        self.assertEqual(report["samples"], [])
        self.assertIn("segment changed", report["diagnostic_errors"][0]["error"])


class DiagnosticErrorBoundTests(unittest.TestCase):
    def test_error_flood_is_bounded_with_counters(self):
        probe, _ = make_probe([ANCHOR + 1] * 64)
        probe.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        limited = EarlyManagerWorkProbe(
            monotonic_ns=probe._monotonic_ns,
            thread_time_ns=probe._thread_time_ns, max_diagnostic_errors=4)
        limited.set_window(anchor_wall_ns=ANCHOR, epoch=EPOCH, segment=SEGMENT)
        for _ in range(7):
            limited.wrap("manager_health", lambda: 1, lambda: "other-epoch", lambda: SEGMENT,
                         FakeAction(result="ok"))
        report = limited.report(source_sha256="s", identity={})
        self.assertEqual(len(report["diagnostic_errors"]), 4)
        self.assertEqual(report["diagnostic_error_total"], 7)
        self.assertEqual(report["diagnostic_error_dropped"], 3)
        self.assertFalse(report["diagnostic_clean"])
        self.assertEqual(report["samples"], [])
        self.assertEqual(report["max_samples"], MAX_SAMPLES)
        self.assertEqual(MAX_DIAGNOSTIC_ERRORS, 1024)


def pv_argv(*extra):
    return ["run", "--task-profile", PV,
            "--ap-mixed-manifest", AP_MIXED[0], "--ap-mixed-sha256", AP_MIXED[1],
            "--control-manifest", CONTROL[0], "--control-sha256", CONTROL[1],
            "--message-manifest", MESSAGE[0], "--message-sha256", MESSAGE[1],
            *extra]


def position_argv(*extra):
    return ["run", "--task-profile", "position",
            "--ap-manifest", AP_CLOCK[0], "--ap-sha256", AP_CLOCK[1],
            "--control-manifest", CONTROL[0], "--control-sha256", CONTROL[1],
            *extra]


def call_main(argv, env):
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(run_joint_flight, "run") as run_mock, \
            mock.patch.object(run_joint_flight, "task_main"), \
            contextlib.redirect_stderr(io.StringIO()):
        try:
            run_joint_flight.main(argv)
        except SystemExit as exit_:
            return None, exit_.code, run_mock.called
    return run_mock.call_args[0][0] if run_mock.called else None, 0, run_mock.called


class CliGuardTests(unittest.TestCase):
    def test_allowed_with_both_envs_and_default_off(self):
        args, code, ran = call_main(pv_argv("--early-work-timing"), TIMING_ENVS)
        self.assertEqual((code, ran), (0, True))
        self.assertIs(args.early_work_timing, True)
        args, code, ran = call_main(pv_argv(), TIMING_ENVS)
        self.assertEqual((code, ran), (0, True))
        self.assertIs(args.early_work_timing, False)

    def test_refused_without_envs_or_wrong_profile(self):
        for env in ({}, {"WKSIM_JOINT_CPU_TIMING": "1"},
                    {"WKSIM_JOINT_RATE_TIMING_PROBE": "1"},
                    {"WKSIM_JOINT_CPU_TIMING": "0",
                     "WKSIM_JOINT_RATE_TIMING_PROBE": "1"},
                    {"WKSIM_JOINT_CPU_TIMING": "2",
                     "WKSIM_JOINT_RATE_TIMING_PROBE": "1"}):
            args, code, ran = call_main(pv_argv("--early-work-timing"), env)
            self.assertEqual(code, 2, env)
            self.assertFalse(ran, env)
        args, code, ran = call_main(position_argv("--early-work-timing"), TIMING_ENVS)
        self.assertEqual(code, 2)
        self.assertFalse(ran)


class RunGuardTests(unittest.TestCase):
    """Programmatic run(args) cannot bypass the gate: it fires BEFORE
    check_isolation, any tempdir, or any child process."""

    def args(self, profile):
        return types.SimpleNamespace(
            planner_release_proof=False, early_work_timing=True,
            task_profile=profile, async_model_evidence=False,
            model_promotion_flight=False)

    def test_run_guard_before_isolation_wrong_profile(self):
        with mock.patch.object(run_joint_flight, "check_isolation") as iso, \
                mock.patch.object(run_joint_flight, "timing_probe_enabled",
                                  return_value=False):
            with self.assertRaisesRegex(ValueError, "PV/MIXED"):
                run_joint_flight.run(self.args("position"))
        iso.assert_not_called()

    def test_run_guard_before_isolation_missing_envs(self):
        for env in ({}, {"WKSIM_JOINT_CPU_TIMING": "1"},
                    {"WKSIM_JOINT_CPU_TIMING": "0",
                     "WKSIM_JOINT_RATE_TIMING_PROBE": "1"}):
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(run_joint_flight, "check_isolation") as iso, \
                    mock.patch.object(run_joint_flight, "timing_probe_enabled",
                                      return_value=False):
                with self.assertRaisesRegex(ValueError, "WKSIM_JOINT_CPU_TIMING"):
                    run_joint_flight.run(self.args(PV))
            iso.assert_not_called()


import ast
import json as json_module
import subprocess
import tempfile


def _runner_source(revision):
    if revision == "old":
        return subprocess.run(
            ["git", "-C", str(ROOT), "show", "7cb7e84:tools/run_joint_flight.py"],
            check=True, capture_output=True, text=True).stdout
    return (ROOT / "tools" / "run_joint_flight.py").read_text(encoding="utf-8")


def _extract_readiness(text, markers, hoist_names=()):
    """AST-extract the real readiness If blocks (and hoist Assigns for new)."""
    tree = ast.parse(text)
    blocks, hoists = [], []
    matched = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            segment = ast.get_source_segment(text, node)
            if any(marker in segment for marker in markers):
                matched.append(node)
    # Keep only outermost matches: the inner `if not pv_go_paths...` also
    # contains the marker because get_source_segment spans the whole block.
    for node in matched:
        if any(node is not other and other.lineno <= node.lineno
               and node.end_lineno <= other.end_lineno for other in matched):
            continue
        blocks.append(ast.get_source_segment(text, node))
    for node in ast.walk(tree):
        if hoist_names and isinstance(node, ast.Assign):
            name = ast.unparse(node.targets[0])
            if name in hoist_names:
                hoists.append(ast.get_source_segment(text, node))
    assert len(blocks) == 2, blocks
    return [compile(ast.parse(s), "<readiness>", "exec") for s in blocks], \
        [compile(ast.parse(h), "<hoist>", "exec") for h in hoists]


class ReadinessBlockBehaviorTests(unittest.TestCase):
    """Execute the REAL old/new readiness blocks against tempdir fixtures."""

    def blocks(self, revision):
        if revision == "old":
            return _extract_readiness(
                _runner_source("old"), ("live/'go.json'", "pv-go-{leg}"))
        return _extract_readiness(
            _runner_source("new"),
            ("go_path_initial.exists()", "pv_go_paths[leg]"),
            hoist_names=("go_path_initial", "ready_paths_initial",
                         "pv_go_paths", "pv_ready_paths"))

    def fixture(self, root, *, ready=(), offers=None, go=False, pv_go=()):
        live = Path(root)
        for stack in ("arducopter", "px4"):
            (live / stack).mkdir(exist_ok=True)
            if stack in ready:
                (live / stack / "ready.json").write_text(json_module.dumps(
                    {"control_epoch": EPOCH}))
            for leg in (1, 2):
                if offers is not None and stack in ready:
                    offer = dict(offers[stack])
                    offer["leg"] = leg
                    (live / stack / f"pv-ready-{leg}.json").write_text(
                        json_module.dumps(offer))
        if go:
            (live / "go.json").write_text("{}")
        for leg in pv_go:
            (live / f"pv-go-{leg}.json").write_text("{}")
        return live

    def namespace(self, live, tick=0):
        saves = []
        clock = types.SimpleNamespace(
            tick=tick, epoch=EPOCH, STEP_NS=1_000_000,
            snapshot=lambda: {"tick": clock.tick})
        ns = {
            "live": live, "workers": {"arducopter": None, "px4": None},
            "pv": True, "clock": clock, "json": json_module,
            "PV_PROFILE": "full_xyz_pv_yaw_v1",
            "result": {"run_id": "run-micro"},
            "save": lambda path, value: saves.append((Path(path).name, value)),
        }
        return ns, saves, clock

    def run_case(self, revision, *, tick=0, **fixture_kwargs):
        blocks, hoists = self.blocks(revision)
        with tempfile.TemporaryDirectory() as tmp:
            live = self.fixture(tmp, **fixture_kwargs)
            ns, saves, clock = self.namespace(live, tick=tick)
            for hoist in hoists:
                exec(hoist, ns)
            error = None
            try:
                for block in blocks:
                    exec(block, ns)
            except ValueError as exc:
                error = exc
            return saves, error

    def assert_same(self, **fixture_kwargs):
        old = self.run_case("old", **fixture_kwargs)
        new = self.run_case("new", **fixture_kwargs)
        self.assertEqual(
            [name for name, _ in old[0]], [name for name, _ in new[0]])
        self.assertEqual(type(old[1]), type(new[1]))
        return new

    def good_offers(self, leg=1):
        return {stack: dict(version=1, profile="full_xyz_pv_yaw_v1", leg=leg,
                            run_id="run-micro", scene_epoch=EPOCH, uav_id=uid,
                            control_epoch=EPOCH, token="t" * 32)
                for stack, uid in (("arducopter", 1), ("px4", 2))}

    def test_ready_missing_zero_save_zero_exception(self):
        saves, error = self.assert_same(ready=())
        self.assertEqual(saves, [])
        self.assertIsNone(error)

    def test_partial_ready_zero_saves(self):
        saves, error = self.assert_same(ready=("arducopter",),
                                        offers=self.good_offers())
        self.assertEqual(saves, [])
        self.assertIsNone(error)

    def test_existing_go_and_pv_go_zero_saves(self):
        saves, error = self.assert_same(
            ready=("arducopter", "px4"), offers=self.good_offers(),
            go=True, pv_go=(1, 2))
        self.assertEqual(saves, [])
        self.assertIsNone(error)

    def test_legal_two_legs_publish_only_at_grid_tick(self):
        # Off-grid tick: the go gate is tick-independent (publishes once),
        # but the PV legs are grid-gated -- no leg publishes at tick 1.
        saves, error = self.assert_same(
            ready=("arducopter", "px4"), offers=self.good_offers(), tick=1)
        self.assertEqual([name for name, _ in saves], ["go.json"])
        self.assertIsNone(error)
        # Grid tick: go + both legs publish, in order, with exact content.
        saves, error = self.assert_same(
            ready=("arducopter", "px4"), offers=self.good_offers(), tick=0)
        self.assertIsNone(error)
        self.assertEqual([name for name, _ in saves],
                         ["go.json", "pv-go-1.json", "pv-go-2.json"])
        go = dict(saves[0][1])
        self.assertEqual(go, {"tick": 0})
        for name, value in saves[1:]:
            leg = int(name.split("-")[2].split(".")[0])
            self.assertEqual(value["leg"], leg)
            self.assertEqual(value["version"], 1)
            self.assertEqual(value["run_id"], "run-micro")
            self.assertEqual(value["scene_epoch"], EPOCH)
            self.assertEqual(value["issued_tick"], 0)
            self.assertEqual(value["start_ns"], 1000 * 1_000_000)

    def test_bad_offer_rejected_before_pv_save(self):
        bad = self.good_offers()
        bad["px4"] = dict(bad["px4"], profile="wrong")
        saves, error = self.assert_same(ready=("arducopter", "px4"),
                                        offers=bad, tick=0)
        # go.json saves first; the bad offer raises before any pv-go save.
        self.assertEqual([name for name, _ in saves], ["go.json"])
        self.assertIsInstance(error, ValueError)
        self.assertIn("readiness identity", str(error))


if __name__ == "__main__":
    unittest.main()
