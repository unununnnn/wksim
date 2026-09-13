"""Pure tests for the group-work-timing producer fixture.

Executes the AST-extracted orchestration methods with fakes only; tripwires
prove no socket, subprocess or model path is touched.  Standard library only.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import producer_fixture as fixture  # noqa: E402


def kinds_per_tick(run):
    result = {}
    for row in run["wire"]:
        result.setdefault(row["tick"], []).append(row["kind"])
    return result


class ProducerFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Tripwires: any socket or subprocess creation fails the run.
        with patch("socket.socket", side_effect=AssertionError("socket")), \
                patch("subprocess.Popen",
                      side_effect=AssertionError("subprocess")):
            cls.fast = fixture.produce(False)
            cls.census = fixture.produce(True)

    def test_extraction_never_imports_or_constructs_original(self):
        self.assertNotIn("Simulator.wksim_core.joint", sys.modules)
        forbidden = {"socket", "subprocess", "ctypes", "pymavlink", "model"}
        tree = ast.parse(fixture.patch_tool.apply_patch(
            (fixture.ROOT / "Simulator" / "wksim_core" / "joint.py")
            .read_bytes()))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "JointPhysics":
                for item in node.body:
                    if (isinstance(item, ast.FunctionDef)
                            and item.name in fixture.EXTRACTED_METHODS):
                        loads = {n.id for n in ast.walk(item)
                                 if isinstance(n, ast.Name)
                                 and isinstance(n.ctx, ast.Load)}
                        self.assertFalse(loads & forbidden,
                                         (item.name, loads & forbidden))
        namespace = set(self.fast_globals())
        self.assertLessEqual(namespace - {"__builtins__"},
                             set(fixture.FAKE_GLOBALS)
                             | set(fixture.EXTRACTED_METHODS))

    def fast_globals(self):
        methods = fixture.extract_orchestration(fixture.patch_tool.apply_patch(
            (fixture.ROOT / "Simulator" / "wksim_core" / "joint.py")
            .read_bytes()))
        return methods["advance"].__globals__.keys()

    def test_complete_group_rows_and_real_order(self):
        run = self.census
        rate_kinds = [row["kind"] for row in run["rate_rows"]]
        self.assertEqual(rate_kinds, ["rate_request", "rate_anchor",
                                      "rate_group_start", "rate_group_end"])
        start, end = run["rate_rows"][-2], run["rate_rows"][-1]
        self.assertEqual((start["start_tick"], start["end_tick"]), (40, 44))
        self.assertEqual(end["start_tick"], 40)
        self.assertGreater(run["work_ns"], 8_000_000)
        self.assertEqual(run["work_ns"],
                         end["actual_end_ns"] - start["actual_start_ns"])
        per_tick = kinds_per_tick(run)
        for tick in (41, 42, 43):
            self.assertEqual(per_tick[tick],
                             ["sensor", "actuator", "step",
                              "diagnostic_native_input_timing",
                              "diagnostic_step_cpu_timing"])
        self.assertEqual(per_tick[44],
                         ["sensor", "sensor", "actuator", "actuator",
                          "barrier", "step", "diagnostic_native_input_timing",
                          "diagnostic_step_cpu_timing"])
        # real order within a tick: step -> native_input -> step_cpu
        for tick in (41, 42, 43, 44):
            kinds = per_tick[tick]
            self.assertLess(kinds.index("step"),
                            kinds.index("diagnostic_native_input_timing"))
            self.assertLess(kinds.index("diagnostic_native_input_timing"),
                            kinds.index("diagnostic_step_cpu_timing"))

    def test_real_fields_on_wire_and_diagnostics(self):
        for row in self.census["wire"]:
            self.assertIn("epoch", row)
            self.assertIn("tick", row)
            self.assertIn("wall", row)
        cpu = [row for row in self.census["wire"]
               if row["kind"] == "diagnostic_step_cpu_timing"]
        self.assertEqual(len(cpu), 4)
        for row in cpu:
            self.assertEqual(set(row["stages"]),
                             {"health_and_models", "encode_send",
                              "native_inputs"})
            for stage in row["stages"].values():
                self.assertIn("wall_ns", stage)
                self.assertIn("thread_cpu_ns", stage)
        native = [row for row in self.census["wire"]
                  if row["kind"] == "diagnostic_native_input_timing"]
        self.assertEqual(len(native), 4)
        slow = [row for row in native if row["tick"] == 43]
        # the bracket includes the in-wait actuator record (as in production),
        # so the slow tick exceeds the raw bump by a few fake-time quanta
        self.assertGreaterEqual(slow[0]["native_wait_wall_ns"],
                                fixture.SLOW_WAIT_WALL_NS)
        self.assertLess(slow[0]["native_wait_wall_ns"],
                        fixture.SLOW_WAIT_WALL_NS + 10 * fixture.WALL_QUANTUM_NS)
        self.assertEqual(slow[0]["waits"][0]["stack"], "arducopter")
        self.assertIn("wall_ns", slow[0]["waits"][0])
        self.assertIn("thread_cpu_ns", slow[0]["waits"][0])

    def test_sampling_modes(self):
        self.assertEqual(self.census["step_cpu_rows"], 4)
        self.assertEqual(self.census["native_input_rows"], 4)
        # old behaviour: only the >2ms slow tick is sampled (ticks 41..44
        # contain no tick % 250 == 0)
        self.assertEqual(self.fast["step_cpu_rows"], 1)
        self.assertEqual(self.fast["native_input_rows"], 1)
        fast_kinds = kinds_per_tick(self.fast)
        self.assertIn("diagnostic_step_cpu_timing", fast_kinds[43])
        for tick in (41, 42, 44):
            self.assertNotIn("diagnostic_step_cpu_timing", fast_kinds[tick])
            self.assertNotIn("diagnostic_native_input_timing",
                             fast_kinds[tick])

    def test_ordinary_events_and_clock_identical_across_modes(self):
        comparison = fixture.compare_modes(self.fast, self.census)
        for key in ("ordinary_events_identical", "clock_calls_identical",
                    "ap_sends_identical", "protocol_sends_identical",
                    "tick_reached_identical"):
            self.assertTrue(comparison[key], key)
        self.assertEqual(self.fast["sleeps"], [])
        self.assertEqual(self.census["sleeps"], [])

    def test_cli_writes_new_json_only(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "fixture.json"
            with patch("socket.socket", side_effect=AssertionError), \
                    patch("subprocess.Popen", side_effect=AssertionError):
                self.assertEqual(fixture.main(["--output", str(out)]), 0)
                self.assertTrue(out.exists())
                with self.assertRaisesRegex(SystemExit, "refusing"):
                    fixture.main(["--output", str(out)])


if __name__ == "__main__":
    unittest.main()
