"""Pure offline tests for tools/build_first_step_trace.py.

The instrumentation is a pure byte transformation; these tests run it against the
real pinned generated cpp (read-only) and synthetic fixtures. No compiler, model,
MATLAB, or ROS is run; the builder never compiles. Covers: hooks inserted at the
real ODE4 stage/update points, original multiply-add expressions unchanged,
byte-verbatim restoration after marker removal, refusal on tampered/non-unique/
already-instrumented source, and refuse-overwrite on the output directory.
"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import build_first_step_trace as bfst

REPO = Path(__file__).resolve().parents[1]
REAL_CPP = REPO / 'work' / 'quad-parameters-source-review-20260909' / 'Exp1_MinModelTemp.cpp'
REAL_ARCHIVE = Path(r'E:\rflysimtools\RflySimAPIs\4.RflySimModel\1.BasicExps\e0_MinModelTemp\MulticopterModel.zip')
REAL_INPUT = REPO / 'validation' / 'numerical-conformance-gxxh6xhr' / 'C3G' / 'input.csv'
RECORDER = REPO / 'tools' / 'first_step_trace_recorder.cpp'

HOOKS = (bfst.STAGE0_HOOK, bfst.STAGE1_HOOK, bfst.STAGE2_HOOK, bfst.STAGE3_HOOK, bfst.UPDATE_HOOK)


def _synthetic_cpp():
    return (bfst.INCLUDE + b'real_T dummy;\r\n'
            + bfst.STAGE0_CTX + bfst.STAGE1_CTX + bfst.STAGE2_CTX + bfst.STAGE3_CTX
            + bfst.UPDATE_CTX + b'  rtsiSetSimTimeStep(si,MAJOR_TIME_STEP);\r\n}\r\n'
            + bfst.MRDIVIDE_CTX
            + bfst.OUTPUT_END + bfst.NEXT_CONTEXT)


class InstrumentRealTests(unittest.TestCase):
    def setUp(self):
        if not REAL_CPP.is_file():
            self.skipTest('pinned original generated cpp not present')
        self.raw = REAL_CPP.read_bytes()
        self.patched = bfst.instrument(self.raw)

    def test_inserts_declaration_and_all_hooks(self):
        self.assertIn(bfst.DECL, self.patched)
        for hook in HOOKS:
            self.assertIn(hook, self.patched)

    def test_removing_markers_restores_original_verbatim(self):
        restored = self.patched
        for snippet in bfst.INSERTIONS:
            restored = restored.replace(snippet, b'', 1)
        self.assertEqual(restored, self.raw)

    def test_original_multiply_add_expressions_unchanged(self):
        # The ODE4 weighted update and stage updates must be byte-identical.
        self.assertIn(b'x[i] = y[i] + temp*(f0[i] + 2.0*f1[i] + 2.0*f2[i] + f3[i]);', self.patched)
        self.assertIn(b'x[i] = y[i] + (temp*f0[i]);', self.patched)
        self.assertIn(b'x[i] = y[i] + (h*f2[i]);', self.patched)
        # Exactly four derivatives() CALL sites (the `extern void` declaration at the
        # top is excluded by the leading newlines+indent), and instrumentation adds none.
        call = b'\r\n  Exp1_MinModelTemp_derivatives();\r\n'
        self.assertEqual(self.raw.count(call), 4)
        self.assertEqual(self.patched.count(call), self.raw.count(call))
        # Capture happens after each derivatives() call (hooks ordered stage 0..3).
        order = [self.patched.index(h) for h in HOOKS[:4]]
        self.assertEqual(order, sorted(order))
        # Each stage hook appears exactly once.
        for hook in HOOKS:
            self.assertEqual(self.patched.count(hook), 1)

    def test_hooks_reference_real_locals(self):
        self.assertIn(b'wk_trace_ode4_stage(0, t, y, f0, nXc);', self.patched)
        self.assertIn(b'wk_trace_ode4_stage(3, rtsiGetT(si), x, f3, nXc);', self.patched)
        self.assertIn(b'wk_trace_ode4_update(rtsiGetT(si), y, x, nXc);', self.patched)

    def test_mrdivide_hook_inserted_after_solve(self):
        # the call hook appears exactly once (the extern declaration in DECL differs)
        self.assertEqual(self.patched.count(bfst.MRDIVIDE_HOOK), 1)
        # hook sits immediately after the mrdivide call
        ctx_end = self.patched.index(bfst.MRDIVIDE_CTX) + len(bfst.MRDIVIDE_CTX)
        self.assertEqual(self.patched[ctx_end:ctx_end + len(b'  wk_trace_mrdivide')],
                         b'  wk_trace_mrdivide')
        # captures numerator (residual), matrix (Selector2), result (Product2)
        self.assertIn(b'rtb_IntegratorSecondOrderLimi_d, Exp1_MinModelTemp_B.Selector2,',
                      self.patched)
        self.assertIn(b'Exp1_MinModelTemp_B.Product2);', self.patched)
        # time uses solver-info (minor-stage) time; major/minor via rtmIsMajorTimeStep
        self.assertIn(b'rtsiGetT(&(&Exp1_MinModelTemp_M)->solverInfo)', self.patched)
        self.assertIn(b'rtmIsMajorTimeStep((&Exp1_MinModelTemp_M))', self.patched)
        # the solve expression itself is unchanged
        self.assertIn(b'rt_mrdivide_U1d1x3_U2d_9vOrDY9Z(rtb_IntegratorSecondOrderLimi_d,',
                      self.patched)


class InstrumentRefusalTests(unittest.TestCase):
    def test_wrong_sha_refused(self):
        with self.assertRaises(ValueError):
            bfst.instrument(b'not the pinned source')

    def test_already_instrumented_refused(self):
        raw = _synthetic_cpp()
        with patch.object(bfst, 'ORIGINAL_CPP_SHA256', hashlib.sha256(raw).hexdigest()):
            once = bfst.instrument(raw)
            with self.assertRaises(ValueError):
                bfst.instrument(once)  # markers already present

    def test_nonunique_anchor_refused(self):
        raw = _synthetic_cpp() + bfst.STAGE0_CTX  # duplicate a stage anchor
        with patch.object(bfst, 'ORIGINAL_CPP_SHA256', hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(ValueError):
                bfst.instrument(raw)

    def test_missing_anchor_refused(self):
        raw = bfst.INCLUDE + bfst.STAGE0_CTX + b'}\r\n'  # missing most anchors
        with patch.object(bfst, 'ORIGINAL_CPP_SHA256', hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(ValueError):
                bfst.instrument(raw)

    def test_missing_mrdivide_anchor_refused(self):
        raw = (bfst.INCLUDE + b'real_T d;\r\n' + bfst.STAGE0_CTX + bfst.STAGE1_CTX
               + bfst.STAGE2_CTX + bfst.STAGE3_CTX + bfst.UPDATE_CTX + b'}\r\n'
               + bfst.OUTPUT_END + bfst.NEXT_CONTEXT)  # no MRDIVIDE_CTX
        with patch.object(bfst, 'ORIGINAL_CPP_SHA256', hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(ValueError):
                bfst.instrument(raw)

    def test_double_instrument_including_mrdivide_refused(self):
        raw = _synthetic_cpp()
        with patch.object(bfst, 'ORIGINAL_CPP_SHA256', hashlib.sha256(raw).hexdigest()):
            once = bfst.instrument(raw)
            self.assertIn(b'wk_trace_mrdivide(', once)
            with self.assertRaises(ValueError):
                bfst.instrument(once)


class ExclusiveWriteTests(unittest.TestCase):
    def test_refuses_overwrite_and_symlink(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'f.bin'
            bfst._exclusive_write(target, b'data')
            self.assertEqual(target.read_bytes(), b'data')
            with self.assertRaises(FileExistsError):
                bfst._exclusive_write(target, b'again')
            self.assertEqual(target.read_bytes(), b'data')


class BuildRealTests(unittest.TestCase):
    def setUp(self):
        for p in (REAL_ARCHIVE, REAL_INPUT, RECORDER):
            if not Path(p).is_file() and not Path(p).exists():
                self.skipTest('pinned build input not present: ' + str(p))
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = Path(self._tmp.name) / 'trace-build'

    def test_build_writes_sources_and_command_then_refuses(self):
        command = bfst.build(REAL_ARCHIVE, RECORDER, self.out, REAL_INPUT)
        # instrumented + original + headers + recorder + input + command
        for name in ('Exp1_MinModelTemp.cpp', 'Exp1_MinModelTemp.original.cpp',
                     'Exp1_MinModelTemp.h', 'rtwtypes.h', 'rtw_continuous.h',
                     'rtw_solver.h', 'first_step_trace_recorder.cpp', 'input.csv',
                     'build-command.json'):
            self.assertTrue((self.out / name).is_file(), name)
        ident = command['identity']
        self.assertEqual(ident['archive_sha256'], bfst.ARCHIVE_SHA256)
        self.assertEqual(ident['original_cpp_sha256'], bfst.ORIGINAL_CPP_SHA256)
        self.assertEqual(ident['input_csv_sha256'],
                         '721c88bf3f621923b98bb43251c50bae7817106a984be64345c0528d34d3adcf')
        self.assertEqual(command['nXc'], 36)
        # original bytes preserved alongside the instrumented copy
        original = (self.out / 'Exp1_MinModelTemp.original.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), bfst.ORIGINAL_CPP_SHA256)
        # refuse to reuse the same output directory
        with self.assertRaises(FileExistsError):
            bfst.build(REAL_ARCHIVE, RECORDER, self.out, REAL_INPUT)


if __name__ == '__main__':
    unittest.main()
