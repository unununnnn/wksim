"""Unit tests for the #59 fail-closed same-source seam (pure parse/align/entry).

These never run MATLAB, never build, never touch the frozen R1 contract, and use only
synthetic in-memory fixtures in a system temp directory. They cover:
  - new-contract schema/identity/budget validation -> blocked, physical_accuracy False;
  - the never-launch guarantee (blocked path returns before any execution stage);
  - the pure parse/alignment layer's strict rejections: 501 samples, time grid,
    120 values, non-finite, boolean, missing terminal, identity mismatch.
"""
import json
import math
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.run_e0_same_source_conformance import (
    ARRAY_LENGTHS,
    FORBIDDEN_CONTRACT,
    FROZEN_METRIC,
    Reject,
    SAMPLES,
    align,
    compare_aligned,
    parse_native_record,
    parse_reference_f64,
    main,
    run,
    validate_contract,
)

TOL = 1e-12


def _source_identity():
    return dict(
        builder='tools/build_generated_e0_major.py', builder_sha256='1' * 64,
        generation_run_id='generation-test', original_cpp_sha256='2' * 64,
        patched_cpp_sha256='3' * 64, header_sha256='4' * 64,
        rtwtypes_sha256='5' * 64, rtw_continuous_sha256='6' * 64,
        rtw_solver_sha256='7' * 64, driver_sha256='8' * 64,
        phase='major root outputs complete; before subsequent explicit Update/ODE',
        output_order=['Vehicle60', 'Sensor30', 'GPS30'],
        root_inputs=['inPWMs[16]', 'TerrainIn15d[15]'], insertion_line=123)


def _reference_rows(width, fn):
    """501 rows of [time, width values] little-endian binary64, written row-major."""
    rows = bytearray()
    for k in range(SAMPLES):
        rows += struct.pack('<' + 'd' * (width + 1), k * 0.001, *[fn(k, i) for i in range(width)])
    return bytes(rows)


def _write_reference(root, fn=lambda k, i: 0.0):
    for array, width in ARRAY_LENGTHS.items():
        (root / (array + '.f64')).write_bytes(_reference_rows(width, fn))


def _record_lines(status='complete', mutate=None, drop_terminal=False, source=None):
    lines = [json.dumps(dict(
        kind='major_recorder_start', schema_version=1,
        source=_source_identity() if source is None else source, input_csv='header\nrow\n',
        expected_calls=SAMPLES, comparison_end_s=0.5, expected_engine_end_s=0.501))]
    for k in range(SAMPLES):
        sample = dict(
            kind='major_recorder_sample', schema_version=1, k=k, call_number=k + 1,
            input_time_s=k * 0.001, engine_before_s=k * 0.001, engine_after_s=(k + 1) * 0.001,
            major_capture_count=1, step_status='complete',
            major_root_outputs={a: [0.0] * w for a, w in ARRAY_LENGTHS.items()},
        )
        if mutate:
            mutate(k, sample)
        lines.append(json.dumps(sample))
    if not drop_terminal:
        lines.append(json.dumps(dict(
            kind='major_recorder_end', schema_version=1, status=status,
            attempted_calls=SAMPLES, returned_calls=SAMPLES, emitted_samples=SAMPLES,
            engine_end_s=0.501, comparison_end_s=0.5)))
    return '\n'.join(lines) + '\n'


def _valid_observables():
    """Fully-provisioned, approved per-scalar observables covering all 120 scalars."""
    obs = []
    for array, width in ARRAY_LENGTHS.items():
        for index in range(width):
            obs.append(dict(
                observable='%s[%d]' % (array, index), array=array, indices=[index],
                source_mapping='cpp:0', unit='1', frame='body', datum='model',
                sample_phase='major', metric=FROZEN_METRIC, abs_budget=0.0, rel_budget=0.0,
                 rms_budget=0.0, derivation='test-fixture', domain='ground_idle',
                 approval='approved', contract_sha256='c' * 64))
    return obs


def _valid_contract(observables=None):
    return dict(
        schema_version=1,
        contract_id='wksim-e0-same-source-v1',
        status='frozen',
        identity=dict(
            reference_revision='SLX model 11.8', target_revision='SLX model 11.8',
            reference_engine='MATLAB R2022b normal', target_profile='g++ -fno-fast-math',
            slx=dict(path='x.slx', sha256='a' * 64),
            init=dict(path='x_init.m', sha256='b' * 64)),
        sampling=dict(fixed_step_s=0.001, k_first=0, k_last=SAMPLES - 1,
                      array_lengths=dict(ARRAY_LENGTHS)),
        observables=_valid_observables() if observables is None else observables,
    )


class ContractValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='e0-same-source-test-'))

    def _write(self, contract):
        path = self.tmp / 'contract.json'
        path.write_text(json.dumps(contract), encoding='utf-8')
        return path

    def test_valid_contract_has_no_blocking_reasons(self):
        contract, reasons = validate_contract(self._write(_valid_contract()))
        self.assertEqual(reasons, [])
        self.assertEqual(len(contract['observables']), 120)

    def test_missing_budget_blocks(self):
        obs = _valid_observables()
        del obs[0]['abs_budget']  # one observable missing a budget
        _, reasons = validate_contract(self._write(_valid_contract(observables=obs)))
        self.assertTrue(any('abs_budget' in r for r in reasons), reasons)

    def test_unapproved_blocks(self):
        obs = _valid_observables()
        obs[5]['approval'] = 'pending'
        _, reasons = validate_contract(self._write(_valid_contract(observables=obs)))
        self.assertTrue(any('approval' in r for r in reasons), reasons)

    def test_incomplete_scalar_coverage_blocks(self):
        obs = _valid_observables()[:-1]  # drop the last scalar -> 119 covered
        _, reasons = validate_contract(self._write(_valid_contract(observables=obs)))
        self.assertTrue(any('coverage' in r for r in reasons), reasons)

    def test_missing_identity_field_blocks(self):
        contract = _valid_contract()
        del contract['identity']['slx']
        _, reasons = validate_contract(self._write(contract))
        self.assertTrue(any('identity.sl' in r for r in reasons), reasons)

    def test_missing_array_is_blocked_without_keyerror(self):
        obs = _valid_observables()
        del obs[0]['array']
        _, reasons = validate_contract(self._write(_valid_contract(observables=obs)))
        self.assertTrue(any('array' in r for r in reasons), reasons)

    def test_boolean_schema_and_empty_identity_are_blocked(self):
        contract = _valid_contract()
        contract['schema_version'] = True
        contract['identity']['reference_revision'] = ''
        _, reasons = validate_contract(self._write(contract))
        self.assertTrue(any('schema_version' in r for r in reasons), reasons)
        self.assertTrue(any('reference_revision' in r for r in reasons), reasons)

    def test_frozen_r1_contract_path_is_rejected(self):
        # Pointing the entry at the frozen R1 contract must raise, never execute.
        with self.assertRaises(Reject):
            validate_contract(FORBIDDEN_CONTRACT)

    def test_r1_contract_id_collision_blocks(self):
        contract = _valid_contract()
        contract['contract_id'] = 'wksim-e0-fixed-reference-native-preservation-v1'
        _, reasons = validate_contract(self._write(contract))
        self.assertTrue(any('collides' in r for r in reasons), reasons)

    def test_non_frozen_metric_blocks_entry(self):
        obs = _valid_observables()
        obs[0]['metric'] = 'pointwise'  # not the frozen formula identifier
        contract, reasons = validate_contract(self._write(_valid_contract(observables=obs)))
        self.assertTrue(any('metric' in r for r in reasons), reasons)
        result = run(self._write(_valid_contract(observables=obs)))
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['matlab_launched'])
        self.assertFalse(result['native_launched'])


class FailClosedEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='e0-same-source-entry-'))

    def _write(self, contract):
        path = self.tmp / 'contract.json'
        path.write_text(json.dumps(contract), encoding='utf-8')
        return path

    def test_missing_budget_returns_blocked_without_execution(self):
        obs = _valid_observables()
        del obs[0]['rel_budget']
        result = run(self._write(_valid_contract(observables=obs)))
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['physical_accuracy'])
        self.assertFalse(result['g6_acceptance'])
        self.assertFalse(result['matlab_launched'])
        self.assertFalse(result['native_launched'])
        self.assertFalse(result['execution_attempted'])
        self.assertTrue(result['blocking_reasons'])

    def test_unapproved_returns_blocked(self):
        obs = _valid_observables()
        for o in obs:
            o['approval'] = 'proposed'
        result = run(self._write(_valid_contract(observables=obs)))
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['physical_accuracy'])

    def test_missing_file_returns_blocked(self):
        result = run(self.tmp / 'does-not-exist.json')
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['physical_accuracy'])

    def test_frozen_r1_path_is_blocked_not_executed(self):
        result = run(FORBIDDEN_CONTRACT)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['matlab_launched'])
        self.assertFalse(result['native_launched'])

    def test_fully_provisioned_never_reports_pass(self):
        # Even a fully-approved contract must NOT report pass from this seam.
        result = run(self._write(_valid_contract()))
        self.assertNotEqual(result['status'], 'pass')
        self.assertNotEqual(result['status'], 'declared_cases_pass')
        self.assertFalse(result['physical_accuracy'])
        self.assertFalse(result['g6_acceptance'])
        self.assertFalse(result['matlab_launched'])
        self.assertFalse(result['native_launched'])
        self.assertEqual(result['status'], 'execution_not_implemented')

    def test_cli_not_implemented_is_nonzero(self):
        path = self._write(_valid_contract())
        with patch('sys.argv', ['run_e0_same_source_conformance.py', str(path)]):
            with redirect_stdout(StringIO()):
                self.assertEqual(main(), 3)


class ParseReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='e0-same-source-ref-'))

    def test_parse_valid_reference(self):
        _write_reference(self.tmp, fn=lambda k, i: k + i * 0.5)
        values = parse_reference_f64(self.tmp / 'Vehicle60.f64', 'Vehicle60', 60)
        self.assertEqual(len(values), SAMPLES)
        self.assertEqual(len(values[0]), 60)
        self.assertAlmostEqual(values[10][4], 10 + 4 * 0.5)

    def test_wrong_byte_length_rejected(self):
        (self.tmp / 'Vehicle60.f64').write_bytes(_reference_rows(60, lambda k, i: 0.0)[:-8])
        with self.assertRaises(Reject):
            parse_reference_f64(self.tmp / 'Vehicle60.f64', 'Vehicle60', 60)

    def test_time_grid_mismatch_rejected(self):
        rows = bytearray()
        for k in range(SAMPLES):
            rows += struct.pack('<' + 'd' * 61, k * 0.001 + (0.1 if k == 250 else 0.0),
                                *([0.0] * 60))
        (self.tmp / 'Vehicle60.f64').write_bytes(bytes(rows))
        with self.assertRaises(Reject):
            parse_reference_f64(self.tmp / 'Vehicle60.f64', 'Vehicle60', 60)

    def test_nonfinite_rejected(self):
        rows = bytearray()
        for k in range(SAMPLES):
            vals = [0.0] * 60
            if k == 100:
                vals[3] = float('nan')
            rows += struct.pack('<' + 'd' * 61, k * 0.001, *vals)
        (self.tmp / 'Vehicle60.f64').write_bytes(bytes(rows))
        with self.assertRaises(Reject):
            parse_reference_f64(self.tmp / 'Vehicle60.f64', 'Vehicle60', 60)


class ParseNativeRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='e0-same-source-nat-'))

    def _write(self, text):
        path = self.tmp / 'record.jsonl'
        path.write_text(text, encoding='utf-8')
        return path

    def test_parse_valid_record(self):
        out = parse_native_record(self._write(_record_lines()))
        self.assertEqual(set(out), set(ARRAY_LENGTHS))
        self.assertEqual(len(out['Vehicle60']), SAMPLES)
        self.assertEqual(len(out['GPS30'][0]), 30)

    def test_missing_terminal_rejected(self):
        with self.assertRaises(Reject):
            parse_native_record(self._write(_record_lines(drop_terminal=True)))

    def test_incomplete_terminal_status_rejected(self):
        with self.assertRaises(Reject):
            parse_native_record(self._write(_record_lines(status='aborted')))

    def test_wrong_sample_count_rejected(self):
        def mut(k, s):
            pass  # shape intact; drop one line below
        lines = _record_lines().splitlines()
        text = '\n'.join(lines[:1] + lines[2:]) + '\n'  # remove k=0 sample
        with self.assertRaises(Reject):
            parse_native_record(self._write(text))

    def test_nonfinite_value_rejected(self):
        def mut(k, s):
            if k == 7:
                s['major_root_outputs']['Vehicle60'][0] = float('inf')
        with self.assertRaises(Reject):
            parse_native_record(self._write(_record_lines(mutate=mut)))

    def test_boolean_value_rejected(self):
        def mut(k, s):
            if k == 3:
                s['major_root_outputs']['Sensor30'][1] = True
        with self.assertRaises(Reject):
            parse_native_record(self._write(_record_lines(mutate=mut)))

    def test_wrong_width_rejected(self):
        def mut(k, s):
            if k == 0:
                s['major_root_outputs']['GPS30'] = [0.0] * 29
        with self.assertRaises(Reject):
            parse_native_record(self._write(_record_lines(mutate=mut)))

    def test_capture_and_post_clock_mismatch_rejected(self):
        def mut(k, sample):
            if k == 9:
                sample['major_capture_count'] = 2
                sample['engine_after_s'] = 99.0
        with self.assertRaises(Reject):
            parse_native_record(self._write(_record_lines(mutate=mut)))

    def test_embedded_source_identity_mismatch_rejected(self):
        expected = _source_identity()
        actual = dict(expected)
        actual['driver_sha256'] = '9' * 64
        with self.assertRaises(Reject):
            parse_native_record(self._write(_record_lines(source=actual)), expected)

    def test_nonfinite_terminal_time_rejected(self):
        lines = _record_lines().splitlines()
        end = json.loads(lines[-1])
        end['engine_end_s'] = float('nan')
        lines[-1] = json.dumps(end)
        with self.assertRaises(Reject):
            parse_native_record(self._write('\n'.join(lines) + '\n'))


class AlignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='e0-same-source-align-'))

    def test_align_matches_shapes_and_identity(self):
        _write_reference(self.tmp, fn=lambda k, i: k * 1.0)
        ref = {a: parse_reference_f64(self.tmp / (a + '.f64'), a, w)
               for a, w in ARRAY_LENGTHS.items()}
        nat = parse_native_record(self._tmp_record())
        aligned = align(ref, nat, _valid_observables())
        self.assertEqual(len(aligned), 120)
        self.assertTrue(all(len(a['reference']) == SAMPLES and len(a['native']) == SAMPLES
                            for a in aligned))

    def _tmp_record(self):
        path = self.tmp / 'record.jsonl'
        path.write_text(_record_lines(), encoding='utf-8')
        return path

    def test_align_rejects_missing_array(self):
        ref = {a: [(0.0,) * w] * SAMPLES for a, w in ARRAY_LENGTHS.items()}
        nat = dict(ref)
        del nat['GPS30']
        with self.assertRaises(Reject):
            align(ref, nat, _valid_observables())

    def test_align_rejects_incomplete_observable_coverage(self):
        ref = {a: [(0.0,) * w] * SAMPLES for a, w in ARRAY_LENGTHS.items()}
        with self.assertRaises(Reject):
            align(ref, ref, _valid_observables()[:-1])


def _aligned_pairs(native_fn):
    """Build aligned (reference=0, native=native_fn(k)) pairs for all 120 scalars."""
    obs = _valid_observables()
    ref = {a: [(0.0,) * w] * SAMPLES for a, w in ARRAY_LENGTHS.items()}
    nat = {a: [tuple(native_fn(k, i) for i in range(w)) for k in range(SAMPLES)]
           for a, w in ARRAY_LENGTHS.items()}
    return align(ref, nat, obs), obs


class CompareAlignedTests(unittest.TestCase):
    """The pure offline per-quantity comparison: frozen formula, RMS cap, strict Reject."""

    def test_identical_zero_is_declared_cases_pass(self):
        aligned, obs = _aligned_pairs(lambda k, i: 0.0)
        result = compare_aligned(aligned, obs)
        self.assertEqual(result['status'], 'declared_cases_pass')
        self.assertEqual(result['aggregate'], 'declared_cases_pass')
        self.assertEqual(result['failed_values'], 0)
        self.assertEqual(result['failed_scalars'], 0)
        self.assertEqual(result['scalar_count'], 120)
        self.assertEqual(result['comparisons'], 120 * SAMPLES)
        self.assertFalse(result['physical_accuracy'])
        self.assertFalse(result['g6_acceptance'])

    def test_pointwise_breach_is_numerical_failed(self):
        # abs_budget=0 everywhere; inject a single nonzero native value -> pointwise fail.
        aligned, obs = _aligned_pairs(lambda k, i: 1e-9 if (k == 5 and i == 0) else 0.0)
        result = compare_aligned(aligned, obs)
        self.assertEqual(result['status'], 'numerical_failed')
        self.assertGreater(result['failed_values'], 0)
        self.assertGreater(result['failed_scalars'], 0)
        # Locate the Vehicle60[0] scalar and check first-failure bookkeeping.
        scalar = next(s for s in result['scalars']
                      if s['array'] == 'Vehicle60' and s['index'] == 0)
        self.assertEqual(scalar['pointwise_failed_count'], 1)
        self.assertEqual(scalar['first_pointwise_failure_k'], 5)
        self.assertAlmostEqual(scalar['max_abs_error'], 1e-9)

    def test_pointwise_within_abs_budget_passes(self):
        aligned, obs = _aligned_pairs(lambda k, i: 0.5 if i == 0 else 0.0)
        for o in obs:
            o['abs_budget'] = 1.0  # A_i = 1.0 covers the constant 0.5 pointwise error
            o['rms_budget'] = 1.0  # and the independent RMS cap must also cover 0.5
        result = compare_aligned(aligned, obs)
        self.assertEqual(result['status'], 'declared_cases_pass')
        self.assertEqual(result['failed_values'], 0)

    def test_relative_budget_uses_abs_reference(self):
        # r=2.0, x=2.4 -> err 0.4; R_i*|r| = 0.1*2 = 0.2; A_i=0 -> fail.
        obs = _valid_observables()
        for o in obs:
            o['rel_budget'] = 0.1
            o['abs_budget'] = 0.0
        ref = {a: [tuple(2.0 for _ in range(w)) for _ in range(SAMPLES)]
               for a, w in ARRAY_LENGTHS.items()}
        nat = {a: [tuple(2.4 if i == 0 else 2.0 for i in range(w)) for _ in range(SAMPLES)]
               for a, w in ARRAY_LENGTHS.items()}
        aligned = align(ref, nat, obs)
        result = compare_aligned(aligned, obs)
        self.assertEqual(result['status'], 'numerical_failed')

    def test_rms_cap_independent_of_pointwise(self):
        # Many tiny errors each within abs_budget, but RMS exceeds a tiny rms_budget.
        aligned, obs = _aligned_pairs(lambda k, i: 0.01 if i == 0 else 0.0)
        for o in obs:
            o['abs_budget'] = 0.1   # each pointwise error 0.01 passes
            o['rms_budget'] = 0.001  # but RMS 0.01 exceeds this
        result = compare_aligned(aligned, obs)
        self.assertEqual(result['status'], 'numerical_failed')
        scalar = next(s for s in result['scalars']
                      if s['array'] == 'Vehicle60' and s['index'] == 0)
        self.assertEqual(scalar['pointwise_failed_count'], 0)  # no pointwise breach
        self.assertTrue(scalar['rms_failed'])                  # RMS cap tripped
        self.assertEqual(scalar['failed_count'], 1)

    def test_boundary_equality_is_pass(self):
        # err exactly equal to A_i + R_i*|r| must pass (rule is <=).
        obs = _valid_observables()
        for o in obs:
            o['abs_budget'] = 0.3
            o['rel_budget'] = 0.1
            o['rms_budget'] = 1.0
        # r=1.0, budget boundary = 0.3 + 0.1*1.0 = 0.4; x=1.4 -> err exactly 0.4.
        ref = {a: [tuple(1.0 for _ in range(w)) for _ in range(SAMPLES)]
               for a, w in ARRAY_LENGTHS.items()}
        nat = {a: [tuple(1.4 if i == 0 else 1.0 for i in range(w)) for _ in range(SAMPLES)]
               for a, w in ARRAY_LENGTHS.items()}
        aligned = align(ref, nat, obs)
        result = compare_aligned(aligned, obs)
        self.assertEqual(result['status'], 'declared_cases_pass')

    def test_nonfinite_native_rejected(self):
        aligned, obs = _aligned_pairs(lambda k, i: float('nan') if (k == 2 and i == 0) else 0.0)
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_boolean_native_rejected(self):
        # Booleans slip past align (which only checks shape); compare must Reject.
        obs = _valid_observables()
        ref = {a: [(0.0,) * w] * SAMPLES for a, w in ARRAY_LENGTHS.items()}
        nat = {a: [tuple(True if i == 0 else 0.0 for i in range(w)) for _ in range(SAMPLES)]
               for a, w in ARRAY_LENGTHS.items()}
        aligned = align(ref, nat, obs)
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_wrong_metric_rejected(self):
        aligned, obs = _aligned_pairs(lambda k, i: 0.0)
        obs[0]['metric'] = 'some_other_formula'
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_missing_budget_rejected(self):
        aligned, obs = _aligned_pairs(lambda k, i: 0.0)
        del obs[0]['rms_budget']
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_negative_budget_rejected(self):
        aligned, obs = _aligned_pairs(lambda k, i: 0.0)
        obs[0]['abs_budget'] = -1.0
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_duplicate_mapping_rejected(self):
        obs = _valid_observables()
        # Give two observables the same (array, index) -> duplicate mapping.
        obs[1]['array'] = obs[0]['array']
        obs[1]['indices'] = list(obs[0]['indices'])
        aligned, _ = _aligned_pairs(lambda k, i: 0.0)
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_duplicate_aligned_scalar_rejected(self):
        aligned, obs = _aligned_pairs(lambda k, i: 0.0)
        aligned[-1] = dict(aligned[0])
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_aligned_observable_identity_mismatch_rejected(self):
        aligned, obs = _aligned_pairs(lambda k, i: 0.0)
        aligned[0]['observable'] = 'wrong-observable'
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)

    def test_unbudgeted_aligned_scalar_rejected(self):
        # aligned covers all 120 but observables budget only 119 -> orphan scalar Reject.
        obs = _valid_observables()[:-1]
        ref = {a: [(0.0,) * w] * SAMPLES for a, w in ARRAY_LENGTHS.items()}
        nat = ref
        # align requires full coverage, so build aligned directly from full observables
        aligned, full_obs = _aligned_pairs(lambda k, i: 0.0)
        with self.assertRaises(Reject):
            compare_aligned(aligned, obs)


if __name__ == '__main__':
    unittest.main()
