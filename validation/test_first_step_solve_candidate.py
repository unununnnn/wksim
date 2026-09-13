"""Pure offline tests for tools/build_first_step_solve_candidate.py.

No compile, no model run, no MATLAB, no ROS. Synthetic CRLF fixtures stand in for
the pinned generated cpp for the rejection matrix; in addition the REAL pinned
source (work/quad-parameters-source-review-20260909) and the REAL frozen archive
are used for actual preparation tests when present. These tests verify ONLY that
(1) exactly the diagonal branch (with reciprocal-overflow guard) is inserted,
(2) removing it restores the instrumented source verbatim, (3) wrong anchors,
duplicates, and existing outputs are rejected, (4) written metadata matches the
actual files.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import build_first_step_solve_candidate as cand  # noqa: E402
builder = cand.builder  # shared, read-only

DECL = (
    b'extern void rt_mrdivide_U1d1x3_U2d_9vOrDY9Z(const real_T u0[3], const real_T u1\r\n'
    b'  [9], real_T y[3]);\r\n'
)
DEF = (
    b'void rt_mrdivide_U1d1x3_U2d_9vOrDY9Z(const real_T u0[3], const real_T u1[9],\r\n'
    b'  real_T y[3])\r\n'
    b'{\r\n'
    b'  real_T A[9];\r\n'
    b'  real_T maxval;\r\n'
    b'  maxval = std::abs(u1[0]);\r\n'
    b'  if (std::abs(u1[1]) > maxval) {\r\n'
    b'    maxval = std::abs(u1[1]);\r\n'
    b'  }\r\n'
    b'  y[0] = u0[0] / A[0];\r\n'
    b'  y[1] = u0[1] / A[4];\r\n'
    b'  y[2] = u0[2] / A[8];\r\n'
    b'}\r\n'
)
CALL = (
    b'  rt_mrdivide_U1d1x3_U2d_9vOrDY9Z(rtb_IntegratorSecondOrderLimi_d,\r\n'
    b'    Exp1_MinModelTemp_B.Selector2, Exp1_MinModelTemp_B.Product2);\r\n'
    b'  wk_trace_mrdivide(rtsiGetT(&(&Exp1_MinModelTemp_M)->solverInfo), 0,\r\n'
    b'      rtb_IntegratorSecondOrderLimi_d, Exp1_MinModelTemp_B.Selector2,\r\n'
    b'      Exp1_MinModelTemp_B.Product2);\r\n'
)
FIXTURE = (
    b'#include "Exp1_MinModelTemp.h"\r\n'
    b'#include <cmath>\r\n'
    b'extern void wk_trace_ode4_stage(int wk_stage, double wk_t, const real_T* wk_state, const real_T* wk_deriv, int wk_n);\r\n'
    b'extern void wk_trace_mrdivide(double wk_t, int wk_is_major, const real_T* wk_numer, const real_T* wk_mat, const real_T* wk_result);\r\n'
    + DECL + DEF + CALL
)

REAL_SOURCE = ROOT / 'work/quad-parameters-source-review-20260909/Exp1_MinModelTemp.cpp'
REAL_ARCHIVE = Path('E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip')
REAL_RECORDER = ROOT / 'tools/first_step_trace_recorder.cpp'
REAL_INPUT = ROOT / 'validation/numerical-conformance-gxxh6xhr/C3G/input.csv'


class PatchOnlyBranchTests(unittest.TestCase):
    def test_inserts_only_branch_and_removal_restores_verbatim(self):
        patched = cand.add_diagonal_branch(FIXTURE)
        self.assertEqual(patched.count(cand.INSERTION), 1)
        self.assertEqual(len(patched), len(FIXTURE) + len(cand.INSERTION))  # only insertion
        self.assertEqual(patched.replace(cand.INSERTION, b'', 1), FIXTURE)  # byte-exact restore
        # branch sits inside the definition, after the '{' line, before the original body
        self.assertGreater(patched.index(cand.INSERTION), patched.index(b'real_T y[3])\r\n{'))
        self.assertLess(patched.index(cand.INSERTION), patched.index(b'  real_T A[9];'))
        # original fallback body preserved verbatim; trace hooks untouched
        self.assertIn(b'  y[0] = u0[0] / A[0];\r\n', patched)
        self.assertEqual(patched.count(b'wk_trace_mrdivide('), FIXTURE.count(b'wk_trace_mrdivide('))
        # only CRLF line endings introduced
        for line in cand.INSERTION.split(b'\n')[:-1]:
            self.assertTrue(line.endswith(b'\r'))

    def test_branch_reciprocal_overflow_guard(self):
        ins = cand.INSERTION
        # three reciprocals evaluated first, all-finite check before any use
        self.assertLess(ins.index(b'const real_T reciprocal[3] = {1.0 / u1[0], 1.0 / u1[4], 1.0 / u1[8]};'),
                        ins.index(b'std::isfinite(reciprocal[0])'))
        self.assertLess(ins.index(b'std::isfinite(reciprocal[2])'),
                        ins.index(b'y[0] = u0[0] * reciprocal[0];'))
        # uniform for all three axes; fallback (no return) reaches the original body
        self.assertIn(b'y[1] = u0[1] * reciprocal[1];', ins)
        self.assertIn(b'y[2] = u0[2] * reciprocal[2];', ins)
        self.assertGreater(ins.index(b'return;'), ins.index(b'y[2] = u0[2] * reciprocal[2];'))
        # diagonal pattern prerequisites all present
        for token in (b'u1[1] == 0.0', b'u1[7] == 0.0', b'u1[0] != 0.0', b'u1[8] != 0.0',
                      b'std::isfinite(u0[0])', b'std::isfinite(u1[4])'):
            self.assertIn(token, ins)

    def test_branch_has_no_axis_value_or_time_gating(self):
        for forbidden in (b'0.0211', b'0.0219', b'0.0366', b'rtsiGetT', b'Timing',
                          b'is_major', b'wk_trace'):
            self.assertNotIn(forbidden, cand.INSERTION)


class RejectionTests(unittest.TestCase):
    def test_rejects_missing_declaration(self):
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(FIXTURE.replace(DECL, b''))

    def test_rejects_missing_definition(self):
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(FIXTURE.replace(DEF, b''))

    def test_rejects_duplicate_definition(self):
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(FIXTURE + DEF)

    def test_rejects_duplicate_call(self):
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(FIXTURE + CALL)

    def test_rejects_wrong_signature(self):
        bad = FIXTURE.replace(b'const real_T u1[9],', b'const real_T u2[9],')
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(bad)

    def test_rejects_name_in_comment(self):
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(FIXTURE + b'// rt_mrdivide_U1d1x3_U2d_9vOrDY9Z mention\r\n')

    def test_rejects_brace_not_followed_by_crlf(self):
        bad = FIXTURE.replace(b'real_T y[3])\r\n{\r\n', b'real_T y[3])\r\n{ ')
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(bad)

    def test_rejects_duplicate_patch(self):
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(cand.add_diagonal_branch(FIXTURE))

    def test_rejects_uninstrumented_source(self):
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(FIXTURE.replace(b'wk_trace_mrdivide', b'wk_trace_mrdividX'))

    def test_rejects_source_without_cmath_evidence(self):
        bare = FIXTURE.replace(b'#include <cmath>\r\n', b'').replace(b'std::abs', b'my_abs')
        with self.assertRaises(ValueError):
            cand.add_diagonal_branch(bare)


class OutputRejectionTests(unittest.TestCase):
    def test_rejects_existing_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'candidate'
            existing.mkdir()
            with self.assertRaises(FileExistsError):
                cand.write_outputs(existing, {'x.txt': b'1'}, {})

    def test_rejects_existing_output_file_and_preserves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'x.txt'
            target.write_bytes(b'old')
            with self.assertRaises(FileExistsError):
                cand._exclusive_write(target, b'new')
            self.assertEqual(target.read_bytes(), b'old')

    def test_write_outputs_into_fresh_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'new-dir'
            cand.write_outputs(out, {'a.bin': b'123'}, {'diagnostic_only': True})
            self.assertEqual((out / 'a.bin').read_bytes(), b'123')
            self.assertIn('diagnostic_only', (out / 'build-command.json').read_text())


@unittest.skipUnless(REAL_SOURCE.exists(), 'pinned real source not present')
class RealSourceTests(unittest.TestCase):
    def test_real_source_instrument_patch_restore(self):
        raw = REAL_SOURCE.read_bytes()
        self.assertEqual(cand._sha256(raw), builder.ORIGINAL_CPP_SHA256)
        instrumented = builder.instrument(raw)
        candidate = cand.add_diagonal_branch(instrumented)  # actual call on the real source
        self.assertEqual(candidate.count(cand.INSERTION), 1)
        self.assertEqual(candidate.replace(cand.INSERTION, b'', 1), instrumented)  # removable
        self.assertEqual(candidate.count(cand.FUNC_NAME), 3)  # decl + def + call, no more
        self.assertGreater(candidate.index(cand.INSERTION),
                           candidate.index(b'void ' + cand.FUNC_NAME))
        self.assertLess(candidate.index(cand.INSERTION), candidate.index(b'  real_T A[9];'))


@unittest.skipUnless(REAL_ARCHIVE.exists() and REAL_INPUT.exists() and REAL_RECORDER.exists(),
                     'pinned archive/input/recorder not present')
class RealArchivePrepareTests(unittest.TestCase):
    def test_full_prepare_new_dir_and_metadata_matches_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'candidate-build'
            command = cand.build(REAL_ARCHIVE, REAL_RECORDER, out, REAL_INPUT)
            identity = command['identity']
            # metadata matches actual files on disk
            self.assertEqual(identity['candidate_cpp_sha256'],
                             cand._sha256((out / 'Exp1_MinModelTemp.cpp').read_bytes()))
            self.assertEqual(identity['instrumented_cpp_sha256'],
                             cand._sha256((out / 'Exp1_MinModelTemp.instrumented.cpp').read_bytes()))
            self.assertEqual(identity['original_cpp_sha256'],
                             cand._sha256((out / 'Exp1_MinModelTemp.original.cpp').read_bytes()))
            self.assertEqual(identity['original_cpp_sha256'], builder.ORIGINAL_CPP_SHA256)
            self.assertEqual(identity['archive_sha256'], builder.ARCHIVE_SHA256)
            self.assertEqual(identity['input_csv_sha256'], builder.INPUT_SHA256)
            # candidate = instrumented + exactly the branch
            candidate = (out / 'Exp1_MinModelTemp.cpp').read_bytes()
            instrumented = (out / 'Exp1_MinModelTemp.instrumented.cpp').read_bytes()
            self.assertEqual(candidate.replace(cand.INSERTION, b'', 1), instrumented)
            # diagnostic metadata
            self.assertTrue(command['diagnostic_only'])
            self.assertFalse(command['production_replacement'])
            self.assertTrue(command['insertion_removed_restores_baseline'])
            self.assertIn('nonfinite', command['reciprocal_overflow_policy'])
            on_disk = json.loads((out / 'build-command.json').read_text())
            self.assertEqual(on_disk['identity'], identity)
            # real argv reference the new dir and the distinct candidate binary
            self.assertIn(str(out / 'first_step_solve_candidate'), command['build_argv'][-1])
            self.assertEqual(command['run_argv'][1], '--record')
            # existing output refused
            with self.assertRaises(FileExistsError):
                cand.build(REAL_ARCHIVE, REAL_RECORDER, out, REAL_INPUT)


if __name__ == '__main__':
    unittest.main(verbosity=2)
