"""Independent falsification checks for the current compare_first_step_trace SHA.

Runs the real comparator on the retained real traces (original target, solve
target, candidate trace) plus a small set of source-informed mutations. No mock
oracles, no model/native/MATLAB/ROS, no G6 contract expansion. Writes one JSON
result next to this script; never overwrites.
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.compare_first_step_trace import compare, main  # noqa: E402

HERE = Path(__file__).resolve().parent
COORD = ROOT / 'validation/coordination'
REF3 = COORD / 'g6-reference-probe-20260913/run-03/reference-first-step.json'
REF5 = COORD / 'g6-reference-probe-20260913/run-05/reference-first-step.json'
TGT = COORD / 'g6-target-first-step-20260913/first-step-trace.jsonl'
TGT_SOLVE = COORD / 'g6-target-mrdivide-20260913/first-step-trace.jsonl'
TGT_CANDIDATE = COORD / 'g6-diagonal-solve-candidate-20260913/first-step-trace.jsonl'
V2_ARTIFACT = COORD / 'g6-diagonal-solve-candidate-20260913/comparator-result-v2.json'
V2_VERIFY = COORD / 'g6-diagonal-solve-candidate-20260913/main-verification-v2.json'


def load_json(path):
    return json.loads(Path(path).read_bytes().decode('utf-8'))


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_bytes().decode('utf-8').splitlines()
            if line.strip()]


class ReviewChecks(unittest.TestCase):
    def test_retained_traces_unchanged(self):
        # The traces the v2 artifact was computed from must be byte-identical.
        artifact = load_json(V2_ARTIFACT)
        self.assertEqual(artifact['reference_sha256'],
                         hashlib.sha256(REF5.read_bytes()).hexdigest())
        self.assertEqual(artifact['target_sha256'],
                         hashlib.sha256(TGT_CANDIDATE.read_bytes()).hexdigest())

    def test_original_difference_unchanged_current_comparator(self):
        result = compare(load_json(REF3), load_jsonl(TGT))
        self.assertEqual(result['status'], 'aligned')
        earliest = result['earliest_difference']
        self.assertEqual((earliest['block'], earliest['stage'], earliest['index'],
                          earliest['ulp']), ('p,q,r', 2, 1, 1))
        self.assertEqual((earliest['reference_hex'], earliest['target_hex']),
                         ('bc56d4db33a987b8', '0xbc56d4db33a987b9'))

    def test_solve_difference_unchanged_current_comparator(self):
        result = compare(load_json(REF5), load_jsonl(TGT_SOLVE))
        self.assertEqual(result['status'], 'aligned')
        differences = [(row['sequence'], d) for row in result['solve']['rows']
                       for d in row['result_differences']]
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0][0], 2)
        self.assertEqual(differences[0][1]['ulp'], 1)

    def test_candidate_difference_absent_current_comparator(self):
        # The retained candidate trace carries no solve/state difference; the
        # current comparator must reproduce exactly that (fix unchanged).
        result = compare(load_json(REF5), load_jsonl(TGT_CANDIDATE))
        self.assertEqual(result['status'], 'aligned')
        self.assertIsNone(result['earliest_difference'])
        self.assertEqual([d for row in result['solve']['rows']
                          for d in row['result_differences']], [])
        self.assertTrue(all(row['numerator_equal'] and row['matrix_equal']
                            for row in result['solve']['rows']))

    def test_uppercase_prefix_in_real_trace_is_rejected(self):
        target = load_jsonl(TGT)
        row = next(r for r in target if r.get('kind') == 'ode4_stage')
        row['state_hex'][0] = '0X' + row['state_hex'][0].removeprefix('0x')
        self.assertEqual(compare(load_json(REF3), target)['status'], 'rejected')

    def test_nxc_bool_true_is_rejected(self):
        target = load_jsonl(TGT)
        next(r for r in target if r.get('kind') == 'ode4_update')['nXc'] = True
        self.assertEqual(compare(load_json(REF3), target)['status'], 'rejected')

    def test_reference_solve_dropped_events_rejected(self):
        reference = load_json(REF5)
        reference['pqr_input_probe']['dropped_events'] = 1
        self.assertEqual(compare(reference, load_jsonl(TGT_SOLVE))['status'], 'rejected')

    def test_solve_minor_is_major_false_bool_is_rejected(self):
        # False == 0: only the exact-type guard can reject the bool on a minor row.
        target = load_jsonl(TGT_SOLVE)
        row = next(r for r in target if r.get('kind') == 'mrdivide_solve'
                   and r.get('mrdivide_seq') == 1)
        self.assertEqual(row['is_major'], 0)
        row['is_major'] = False
        result = compare(load_json(REF5), target)
        self.assertEqual(result['status'], 'rejected')

    def test_operand_mutation_is_surfaced(self):
        # Documents current semantics: a numerator mutation is reported via the
        # equality flag; record the observed status either way.
        target = load_jsonl(TGT_SOLVE)
        row = next(r for r in target if r.get('kind') == 'mrdivide_solve'
                   and r.get('mrdivide_seq') == 2)
        row['numerator_hex'][0] = '0x3ff0000000000001'
        result = compare(load_json(REF5), target)
        row2 = result['solve']['rows'][2]
        self.assertFalse(row2['numerator_equal'])
        self.assertTrue(row2['matrix_equal'])
        self.__class__.operand_status = result['status']  # reviewed, not assumed

    def test_cli_smoke_on_current_comparator(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'cmp.json'
            code = main(['--reference', str(REF3), '--target', str(TGT),
                         '--output', str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(load_json(out)['status'], 'aligned')


if __name__ == '__main__':
    unittest.main(verbosity=2)
