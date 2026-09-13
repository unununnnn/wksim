"""Synthetic comparator checks; contains no model execution or acceptance budgets."""
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from compare_model_traces import compare


def fixture():
    identity = {key: 'a' * 64 for key in ('model_sha256', 'configuration_sha256', 'execution_sha256')}
    contract = {'schema': 'model-trace-comparison-v1', 'case': 'synthetic-only', 'epoch': 0,
                'reference': identity, 'candidate': {**identity, 'model_sha256': 'b' * 64},
                'samples': [{'k': 0, 'time': 0.0}, {'k': 1, 'time': 0.001}],
                'quantities': [
                    {'name': 'x', 'reference_index': 0, 'candidate_index': 1, 'unit': 'm',
                     'comparison': 'absolute', 'max_abs_error': 0.1},
                    {'name': 'yaw', 'reference_index': 1, 'candidate_index': 0, 'unit': 'rad',
                     'comparison': 'euler_wrap', 'max_abs_error': 0.03}]}
    traces = {}
    for side in ('reference', 'candidate'):
        traces[side] = [{**sample, 'case': contract['case'], 'epoch': 0, 'identity': contract[side],
                         'values': [1.0, math.pi - 0.01] if side == 'reference' else [-math.pi + 0.01, 1.05],
                         'units': ['m', 'rad'] if side == 'reference' else ['rad', 'm']}
                        for sample in contract['samples']]
    return copy.deepcopy(contract), copy.deepcopy(traces)


def write_fixture(directory, contract, traces):
    directory = Path(directory)
    cpath = directory / 'contract.json'
    cpath.write_text(json.dumps(contract), encoding='utf-8')
    digest = hashlib.sha256(cpath.read_bytes()).hexdigest()
    paths = [cpath]
    for side in ('reference', 'candidate'):
        path = directory / (side + '.jsonl')
        path.write_text(''.join(json.dumps({'contract_sha256': digest, **row}) + '\n'
                                for row in traces[side]), encoding='utf-8')
        paths.append(path)
    return paths


class CompareTests(unittest.TestCase):
    def run_fixture(self, mutate=None):
        c, t = fixture()
        if mutate:
            mutate(c, t)
        with tempfile.TemporaryDirectory() as directory:
            paths = write_fixture(directory, c, t)
            before = [p.read_bytes() for p in paths]
            result = compare(*paths)
            self.assertEqual(before, [p.read_bytes() for p in paths])
            self.assertEqual(result['input_sha256'], dict(zip(('contract', 'reference', 'candidate'),
                             (hashlib.sha256(b).hexdigest() for b in before))))
            return result

    def test_index_units_wrap_and_statistics(self):
        result = self.run_fixture()
        self.assertEqual(result['status'], 'pass')
        self.assertAlmostEqual(result['quantities'][0]['max'], 0.05)
        self.assertAlmostEqual(result['quantities'][0]['rms'], 0.05)
        self.assertAlmostEqual(result['quantities'][1]['max'], 0.02)

    def test_over_budget_preserves_all_failures(self):
        result = self.run_fixture(lambda c, t: c['quantities'][0].update(max_abs_error=0.01))
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['first_failure_k'], 0)
        self.assertEqual([f['k'] for f in result['failures']], [0, 1])

    def test_invalid_inputs(self):
        changes = {
            'index': lambda c, t: c['quantities'][0].update(candidate_index=20),
            'unit': lambda c, t: t['candidate'][0]['units'].__setitem__(1, 'cm'),
            'wrap_unit': lambda c, t: c['quantities'][1].update(unit='deg'),
            'missing': lambda c, t: t['candidate'].pop(),
            'duplicate': lambda c, t: t['candidate'][1].update(k=0),
            'time': lambda c, t: t['candidate'][1].update(time=0.002),
            'case': lambda c, t: t['candidate'][0].update(case='other'),
            'epoch': lambda c, t: t['candidate'][0].update(epoch=True),
            'identity': lambda c, t: t['candidate'][0].update(identity=c['reference']),
            'hash': lambda c, t: t['candidate'][0].update(contract_sha256='0' * 64),
            'type': lambda c, t: t['candidate'][0]['values'].__setitem__(1, True),
            'nan': lambda c, t: t['candidate'][0]['values'].__setitem__(1, math.nan),
            'infinity': lambda c, t: t['candidate'][0]['values'].__setitem__(1, math.inf),
            'missing_budget': lambda c, t: c['quantities'][0].pop('max_abs_error'),
            'budget_type': lambda c, t: c['quantities'][0].update(max_abs_error=True),
            'quaternion': lambda c, t: c['quantities'][1].update(comparison='quaternion'),
            'contract_gap': lambda c, t: c['samples'][1].update(k=2),
            'layout': lambda c, t: t['candidate'][1]['units'].append('m'),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                result = self.run_fixture(change)
                self.assertEqual(result['status'], 'fail')
                self.assertIn('error', result)

    def test_invalid_json_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = write_fixture(directory, *fixture())
            for raw in ('{', '{"schema":1,"schema":2}'):
                paths[0].write_text(raw, encoding='utf-8')
                self.assertEqual(compare(*paths)['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
