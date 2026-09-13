"""Pure tests for the timing-census patch preparation tool.

Runs the real transformation against the frozen joint.py source (SHA pinned),
validates the patch structurally via ast (no import/execution of the module:
its constructor opens sockets), and exercises every rejection path.  Windows
and WSL alike; standard library only.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN = ROOT / "Simulator" / "wksim_core" / "joint.py"

spec = importlib.util.spec_from_file_location(
    "prepare_group_work_timing_patch", HERE / "prepare_group_work_timing_patch.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def init_def(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "JointPhysics":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    return item
    raise AssertionError("JointPhysics.__init__ not found")


class TimingCensusPatchTests(unittest.TestCase):
    def setUp(self):
        self.source = FROZEN.read_bytes()
        if hashlib.sha256(self.source).hexdigest() != tool.EXPECTED_INPUT_SHA256:
            self.skipTest("live joint.py no longer equals the frozen snapshot")

    def test_frozen_source_has_no_marker_and_four_unique_anchors(self):
        text = self.source.decode("utf-8")
        self.assertNotIn("timing_census", text)
        for original, patched in tool.PATCHES:
            self.assertEqual(text.count(original), 1, original[:60])
            self.assertEqual(text.count(patched), 0, patched[:60])

    def test_apply_is_structurally_minimal_and_reversible(self):
        patched = tool.apply_patch(self.source)
        tree = ast.parse(patched)
        signature = init_def(tree).args
        names = [arg.arg for arg in signature.kwonlyargs]
        index = names.index("timing_census")
        default = signature.kw_defaults[index]
        self.assertIsInstance(default, ast.Constant)
        self.assertIs(default.value, False)
        # plain-bool runtime guard raising TypeError
        raises = [node for node in ast.walk(tree)
                  if isinstance(node, ast.Raise)
                  and isinstance(node.exc, ast.Call)
                  and getattr(node.exc.func, "id", "") == "TypeError"]
        self.assertEqual(len(raises), 1)
        # both sampling conditions now start with `self.timing_census or`
        lifted = [node for node in ast.walk(tree)
                  if isinstance(node, ast.If)
                  and isinstance(node.test, ast.BoolOp)
                  and isinstance(node.test.op, ast.Or)
                  and isinstance(node.test.values[0], ast.Attribute)
                  and node.test.values[0].attr == "timing_census"]
        self.assertEqual(len(lifted), 2)
        # GC gate `if self.cpu_timing:` unchanged and unique
        gc_gates = [node for node in ast.walk(tree)
                    if isinstance(node, ast.If)
                    and isinstance(node.test, ast.Attribute)
                    and node.test.attr == "cpu_timing"]
        self.assertEqual(len(gc_gates), 1)
        # removal restores the frozen bytes exactly
        self.assertEqual(tool.remove_patch(patched), self.source)

    def test_apply_rejects_double_insert_and_bad_anchor(self):
        patched = tool.apply_patch(self.source)
        with self.assertRaisesRegex(tool.PatchError, "double apply"):
            tool.apply_patch(patched)
        duplicated = self.source.decode("utf-8").replace(
            tool.PATCHES[2][0], tool.PATCHES[2][0] + "\n" + tool.PATCHES[2][0])
        with self.assertRaisesRegex(tool.PatchError, "not unique"):
            tool.apply_patch(duplicated.encode("utf-8"))

    def test_remove_rejects_unpatched_or_partial_source(self):
        with self.assertRaisesRegex(tool.PatchError, "not unique"):
            tool.remove_patch(self.source)
        patched = tool.apply_patch(self.source).decode("utf-8")
        partial = patched.replace(
            "if self.timing_census or marks", "if marks")  # undo one site
        with self.assertRaisesRegex(tool.PatchError, "not unique"):
            tool.remove_patch(partial.encode("utf-8"))

    def test_cli_rejects_wrong_sha_existing_output_and_never_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            out = directory / "patched.py"
            with self.assertRaisesRegex(SystemExit, "SHA-256"):
                tool.main(["apply", "--input", __file__, "--output", str(out)])
            self.assertFalse(out.exists())
            self.assertEqual(tool.main(
                ["apply", "--input", str(FROZEN), "--output", str(out)]), 0)
            with self.assertRaisesRegex(SystemExit, "already exists"):
                tool.main(["apply", "--input", str(FROZEN),
                           "--output", str(out)])
            with self.assertRaisesRegex(SystemExit, "SHA-256"):
                tool.main(["apply", "--input", str(out),
                           "--output", str(directory / "again.py")])
            back = directory / "restored.py"
            self.assertEqual(tool.main(
                ["remove", "--input", str(out), "--output", str(back)]), 0)
            self.assertEqual(back.read_bytes(), self.source)
        self.assertNotIn("Simulator.wksim_core.joint", sys.modules)
        self.assertNotIn("joint", sys.modules)


if __name__ == "__main__":
    unittest.main()
