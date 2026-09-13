"""Focused tests for the function-token boundary rule in the solve-candidate builder.

Owner: validation/coordination/g6-token-boundary-20260913-01.
Pure Python. The OLD side of every before/after assertion is the immutable pre-fix
baseline pinned by commit `5165781dc3607d08179c26f11b9af13f152fbf17` (blob sha256
`0f3a79a4b5bf7d96a71f3337ee6f2e3b3c0ac767e59d8a2cd7aab7d742e3e3bd`), never `HEAD`, so
the evidence cannot drift once the fix is committed. The baseline bytes are executed in
an isolated module namespace with `__file__` set to the real tool path, so no scratch
file is written into `tools/`. No compile, model, MATLAB, ROS or native execution.

Fixture discipline:
  * every fixture has exactly THREE occurrences of the audited name;
  * the valid POSITIVE fixture (declaration + real definition + real call) is asserted
    accepted by both implementations BEFORE any mutation is examined;
  * the mutations replace exactly one anchor with a prefixed name.

Run:
    python -B -m pytest validation/coordination/g6-token-boundary-20260913-01/test_token_boundary.py -q
"""
import hashlib
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL_REL = 'tools/build_first_step_solve_candidate.py'
TOOL = ROOT / TOOL_REL
BASELINE_REF = '5165781dc3607d08179c26f11b9af13f152fbf17'
BASELINE_SHA256 = '0f3a79a4b5bf7d96a71f3337ee6f2e3b3c0ac767e59d8a2cd7aab7d742e3e3bd'
BASELINE_BLOB = 'df15d795856583eae101e3d1f549ecfc29f4e2e7'
sys.path.insert(0, str(ROOT / 'tools'))

_spec = importlib.util.spec_from_file_location('candidate_tool', TOOL)
cand = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cand)

NAME = cand.FUNC_NAME
SIG = b'(const real_T u0[3], const real_T u1[9],\r\n  real_T y[3])\r\n'
DECL = (b'extern void ' + NAME + b'(const real_T u0[3], const real_T u1\r\n'
        b'  [9], real_T y[3]);\r\n')
DEF = b'void ' + NAME + SIG + b'{\r\n  real_T A[9];\r\n  y[0] = u0[0] / A[0];\r\n}\r\n'
CALL = (b'  ' + NAME + b'(rtb_IntegratorSecondOrderLimi_d,\r\n'
        b'    Exp1_MinModelTemp_B.Selector2, Exp1_MinModelTemp_B.Product2);\r\n')
WRAPPER_DEF = b'void outer_' + NAME + SIG + b'{\r\n  Real2 A;\r\n  A = A;\r\n}\r\n'
PREFIXED_CALL = (b'  outer_' + NAME + b'(rtb_IntegratorSecondOrderLimi_d,\r\n'
                 b'    Exp1_MinModelTemp_B.Selector2, Exp1_MinModelTemp_B.Product2);\r\n')
HEAD = (b'#include "Exp1_MinModelTemp.h"\r\n'
        b'#include <cmath>\r\n'
        b'extern void wk_trace_ode4_stage(int, double, const real_T*, const real_T*, int);\r\n'
        b'extern void wk_trace_mrdivide(double, int, const real_T*, const real_T*,'
        b' const real_T*);\r\n')

POSITIVE = HEAD + DECL + DEF + CALL
REPLACED_DEF = HEAD + DECL + WRAPPER_DEF + CALL
REPLACED_CALL = HEAD + DECL + DEF + PREFIXED_CALL

PINNED_SOURCE = ROOT / 'work/quad-parameters-source-review-20260909/Exp1_MinModelTemp.cpp'
PINNED_SOURCE_SHA256 = 'a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019'
PINNED_INSTRUMENTED_SHA256 = \
    '3e271d64f46191a1e5dd41c92ae215ea5321ec42ece31dd1ada389be3ece9182'
PINNED_CANDIDATE_SHA256 = \
    '0107001b1a4aeef4591b2516ffad338866e4645a59c519c3c3e367073acac001'
RETAINED_CANDIDATE_COMMAND = (ROOT / 'validation/coordination/g6-diagonal-solve-candidate-20260913'
                              / 'candidate-command.json')
RETAINED_BUILD_COMMAND = (ROOT / 'validation/coordination/g6-diagonal-solve-candidate-20260913'
                          / 'build-command.json')


def baseline_bytes():
    """Bytes of the pinned pre-fix baseline; None when git or the ref is unavailable."""
    completed = subprocess.run(['git', 'cat-file', 'blob', BASELINE_REF + ':' + TOOL_REL],
                               cwd=str(ROOT), capture_output=True)
    if completed.returncode != 0 or not completed.stdout:
        return None
    return completed.stdout


def load_old_tool():
    """Load the pinned baseline bytes in an isolated namespace with __file__ pointing at
    the real tool, so the shared-builder lookup resolves without a scratch file."""
    raw = baseline_bytes()
    if raw is None:
        return None
    text = raw.decode('utf-8')
    if 'def _at_identifier_boundary' in text:
        return 'BASELINE_ALREADY_FIXED'
    module = type(sys)('candidate_old_baseline')
    module.__file__ = str(TOOL)
    exec(compile(text, str(TOOL), 'exec'), module.__dict__)
    return module


OLD = load_old_tool()


def occurrences(source):
    positions = []
    start = 0
    while True:
        pos = source.find(NAME, start)
        if pos < 0:
            return positions
        positions.append(pos)
        start = pos + 1


class BaselinePinTests(unittest.TestCase):
    def test_pinned_baseline_ref_and_blob_hash(self):
        raw = baseline_bytes()
        if raw is None:
            self.skipTest('git or the pinned ref is unavailable')
        # the ref is a commit id, never HEAD, so a future commit cannot change the old side
        self.assertNotEqual(BASELINE_REF, 'HEAD')
        self.assertRegex(BASELINE_REF, r'^[0-9a-f]{40}$')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), BASELINE_SHA256)
        blob = subprocess.run(['git', 'rev-parse', BASELINE_REF + ':' + TOOL_REL],
                              cwd=str(ROOT), capture_output=True, check=True)
        self.assertEqual(blob.stdout.decode('utf-8').strip(), BASELINE_BLOB)


@unittest.skipUnless(OLD is not None and OLD != 'BASELINE_ALREADY_FIXED',
                     'pinned baseline unavailable or already contains the boundary rule')
class OldVersusNewBoundaryTests(unittest.TestCase):
    def test_positive_fixture_has_three_occurrences_and_both_accept_it(self):
        self.assertEqual(len(occurrences(POSITIVE)), 3)
        real_definition = POSITIVE.index(DEF)
        old_patched = OLD.add_diagonal_branch(POSITIVE)
        self.assertEqual(old_patched.index(OLD.INSERTION),
                         real_definition + DEF.index(b'{\r\n') + 3)
        new_patched = cand.add_diagonal_branch(POSITIVE)
        self.assertEqual(new_patched.index(cand.INSERTION), real_definition + DEF.index(b'{\r\n') + 3)
        self.assertEqual(old_patched, new_patched)

    def test_replaced_definition_old_accepts_new_rejects(self):
        # Mutation: the real definition is REPLACED by a prefixed wrapper whose
        # parameter list is the canonical one. Still exactly three occurrences.
        fixture = REPLACED_DEF
        positions = occurrences(fixture)
        self.assertEqual(len(positions), 3)
        self.assertEqual([fixture[p - 1:p] for p in positions], [b' ', b'_', b' '])
        old_classification = [OLD._classify_occurrence(fixture, p) for p in positions]
        self.assertEqual([k for k, _ in old_classification],
                         ['declaration', 'definition', 'call'])
        old_patched = OLD.add_diagonal_branch(fixture)
        self.assertEqual(old_patched.count(OLD.INSERTION), 1)
        wrapper_start = fixture.index(WRAPPER_DEF)
        wrapper_brace = wrapper_start + WRAPPER_DEF.index(b'{\r\n') + 3
        self.assertEqual(old_patched.index(OLD.INSERTION), wrapper_brace)
        self.assertLess(old_patched.index(OLD.INSERTION),
                        fixture.index(b'  A = A;'))  # before the wrapper body's last line
        self.assertEqual(old_patched.replace(OLD.INSERTION, b'', 1), fixture)
        with self.assertRaises(ValueError) as caught:
            cand.add_diagonal_branch(fixture)
        self.assertIn('longer identifier', str(caught.exception))

    def test_replaced_call_old_accepts_new_rejects(self):
        # Mutation: the real call is REPLACED by a call to a prefixed name. The old
        # helper still sees one declaration, one definition and one call.
        fixture = REPLACED_CALL
        positions = occurrences(fixture)
        self.assertEqual(len(positions), 3)
        old_classification = [OLD._classify_occurrence(fixture, p) for p in positions]
        self.assertEqual([k for k, _ in old_classification],
                         ['declaration', 'definition', 'call'])
        old_patched = OLD.add_diagonal_branch(fixture)
        self.assertEqual(old_patched.count(OLD.INSERTION), 1)
        with self.assertRaises(ValueError) as caught:
            cand.add_diagonal_branch(fixture)
        self.assertIn('longer identifier', str(caught.exception))

    def test_both_reject_a_second_genuine_definition(self):
        # Regression guard: the ordinary two-definition case was already rejected by
        # the occurrence-count rule, so it is not part of the fixed gap.
        fixture = HEAD + DECL + DEF + DEF + CALL
        self.assertEqual(len(occurrences(fixture)), 4)
        for module in (OLD, cand):
            with self.assertRaises(ValueError, msg=module.__name__):
                module.add_diagonal_branch(fixture)


class BoundaryRuleTests(unittest.TestCase):
    def test_boundary_helper_rejects_matches_inside_longer_identifiers(self):
        source = b'x outer_' + NAME + b'(a) prefix' + NAME + b'_suffix(b)'
        positions = occurrences(source)
        self.assertEqual(len(positions), 2)
        self.assertEqual([cand._at_identifier_boundary(source, p) for p in positions],
                         [False, False])
        self.assertTrue(cand._at_identifier_boundary(b'void ' + NAME + b'(', 5))

    def test_comment_and_string_pseudo_calls_are_rejected_by_counting(self):
        # These are rejected by the occurrence-count rule, not by lexical parsing.
        for extra in (b'/* old: ' + NAME + b'(a, b); */\r\n',
                      b'static const char* kOld = "' + NAME + b'(a, b);";\r\n'):
            with self.subTest(extra=extra[:20]):
                with self.assertRaises(ValueError):
                    cand.add_diagonal_branch(POSITIVE + extra)

    def test_missing_anchors_are_rejected(self):
        for fixture in (HEAD + DECL + DEF, HEAD + DEF + CALL, HEAD + DECL + CALL):
            with self.subTest(length=len(fixture)):
                with self.assertRaises(ValueError):
                    cand.add_diagonal_branch(fixture)


class PinnedSourceTests(unittest.TestCase):
    """The boundary rule must not change behaviour on the pinned generated source:
    three whole-identifier occurrences, and prepared candidate bytes unchanged."""

    def setUp(self):
        if not PINNED_SOURCE.is_file():
            self.skipTest('pinned generated source not present')
        self.raw = PINNED_SOURCE.read_bytes()
        self.instrumented = cand.builder.instrument(self.raw)

    def test_pinned_hashes_unchanged(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), PINNED_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(self.instrumented).hexdigest(),
                         PINNED_INSTRUMENTED_SHA256)

    def test_exactly_three_whole_identifier_occurrences_each_classified_once(self):
        positions = occurrences(self.instrumented)
        self.assertEqual(len(positions), 3)
        self.assertEqual([cand._at_identifier_boundary(self.instrumented, p)
                          for p in positions], [True, True, True])
        self.assertEqual([cand._classify_occurrence(self.instrumented, p)[0]
                          for p in positions],
                         ['declaration', 'definition', 'call'])

    def test_prepared_candidate_still_matches_the_retained_identity(self):
        patched = cand.add_diagonal_branch(self.instrumented)
        self.assertEqual(hashlib.sha256(patched).hexdigest(), PINNED_CANDIDATE_SHA256)
        self.assertEqual(patched.replace(cand.INSERTION, b'', 1), self.instrumented)
        if RETAINED_CANDIDATE_COMMAND.is_file():
            import json
            recorded = json.loads(RETAINED_CANDIDATE_COMMAND.read_text(encoding='utf-8'))
            self.assertEqual(recorded['identity']['instrumented_cpp_sha256'],
                             hashlib.sha256(patched).hexdigest())
            self.assertEqual(recorded['identity']['baseline_instrumented_cpp_sha256'],
                             PINNED_INSTRUMENTED_SHA256)

    def test_retained_build_command_records_the_same_pins(self):
        if not RETAINED_BUILD_COMMAND.is_file():
            self.skipTest('retained build command not present')
        import json
        recorded = json.loads(RETAINED_BUILD_COMMAND.read_text(encoding='utf-8'))
        self.assertEqual(recorded['identity']['original_cpp_sha256'], PINNED_SOURCE_SHA256)
        self.assertEqual(recorded['identity']['instrumented_cpp_sha256'],
                         PINNED_INSTRUMENTED_SHA256)

    def test_insertion_bytes_are_unchanged(self):
        self.assertTrue(cand.INSERTION.startswith(
            b'  // Diagnostic-only uniform diagonal solve; original general solve follows.\r\n'))
        self.assertEqual(cand.INSERTION.count(b'return;'), 1)
        self.assertIn(b'const real_T reciprocal[3] = {1.0 / u1[0], 1.0 / u1[4], 1.0 / u1[8]};',
                      cand.INSERTION)


if __name__ == '__main__':
    unittest.main(verbosity=2)
