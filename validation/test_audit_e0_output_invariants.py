"""Unit tests for tools/audit_e0_output_invariants.py (#59 offline invariant auditor).

Covers:
- Pass with retained public record.jsonl inputs
- Tampered groups (reserved zero slots, interface constants)
- Wrong vector lengths on both major_root_outputs and post_step_api
- Nonfinite values (NaN, Inf)
- Boolean values (even when equal to 1.0 or 0.0 numerically)
- Empty files and zero usable samples
- Missing or invalid terminal records (wrong status, mismatched counts)
- Signed zero (+0.0 vs -0.0) acceptance and count diagnostics
- Multiple input batch auditing
- CLI execution and exit codes (0 on pass, 2 on fail)
- Verified absence of G6 / physical fidelity claims
"""

import io
import json
import math
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_e0_output_invariants import (
    audit_record,
    audit_records,
    format_audit_json,
    main,
    ARRAY_LENGTHS,
    RESERVED_ZERO_SLOTS,
    INTERFACE_METADATA_CONSTANTS,
)

RETAINED_PARENT_FINAL = ROOT / 'validation/e0-major-recorder-parent-final-01/record.jsonl'
RETAINED_TERRAIN = (
    ROOT / 'validation/e0-major-recorder-terrain-01/e0-major-recorder-short-cycle-terrain-31in/record.jsonl'
)


def _make_sample(k=0, mutate_major=None, mutate_post=None):
    """Helper to generate a valid sample dictionary, with optional mutations."""
    major_v60 = [0.0] * 60
    major_v60[0] = 1.0
    major_v60[1] = 3.0
    major_s30 = [0.0] * 30
    major_s30[14] = 8191.0
    major_g30 = [0.0] * 30
    major_g30[11] = 3.0
    major_g30[12] = 10.0

    post_v60 = list(major_v60)
    post_s30 = list(major_s30)
    post_g30 = list(major_g30)

    major_out = {'Vehicle60': major_v60, 'Sensor30': major_s30, 'GPS30': major_g30}
    post_out = {'Vehicle60': post_v60, 'Sensor30': post_s30, 'GPS30': post_g30}

    if mutate_major:
        mutate_major(major_out)
    if mutate_post:
        mutate_post(post_out)

    return {
        'schema_version': 1,
        'kind': 'major_recorder_sample',
        'k': k,
        'call_number': k + 1,
        'input_time_s': k * 0.001,
        'engine_before_s': k * 0.001,
        'engine_after_s': (k + 1) * 0.001,
        'major_capture_count': 1,
        'inPWMs': [0.0] * 16,
        'TerrainIn15d': [0.0] * 15,
        'major_root_outputs': major_out,
        'post_step_api': post_out,
        'step_status': 'complete',
    }


def _make_valid_record_lines(sample_count=2, mutate_sample=None, mutate_end=None):
    """Generate minimal valid record.jsonl lines."""
    lines = [
        json.dumps({
            'schema_version': 1,
            'kind': 'major_recorder_start',
            'expected_calls': sample_count,
            'comparison_end_s': (sample_count - 1) * 0.001,
            'expected_engine_end_s': sample_count * 0.001,
        })
    ]
    for k in range(sample_count):
        sample = _make_sample(k)
        if mutate_sample and k == 0:
            mutate_sample(sample)
        lines.append(json.dumps(sample))

    end_rec = {
        'schema_version': 1,
        'kind': 'major_recorder_end',
        'status': 'complete',
        'attempted_calls': sample_count,
        'returned_calls': sample_count,
        'emitted_samples': sample_count,
        'comparison_end_s': (sample_count - 1) * 0.001,
        'engine_end_s': sample_count * 0.001,
    }
    if mutate_end:
        mutate_end(end_rec)
    lines.append(json.dumps(end_rec))
    return '\n'.join(lines) + '\n'


class TestAuditE0OutputInvariants(unittest.TestCase):
    """Test suite for offline e0 output invariant auditor."""

    def test_retained_public_record_parent_final_pass(self):
        """Verify the retained parent-final-01 record.jsonl passes all invariants."""
        self.assertTrue(RETAINED_PARENT_FINAL.is_file(), f'Missing retained file: {RETAINED_PARENT_FINAL}')
        res = audit_record(RETAINED_PARENT_FINAL)
        self.assertTrue(res['passed'])
        self.assertEqual(res['sample_counts']['usable_samples'], 501)
        self.assertEqual(res['sample_counts']['terminal_emitted_samples'], 501)
        self.assertEqual(res['violations'], [])
        self.assertEqual(res['signed_zero_counts']['negative_zeros'], 0)
        self.assertEqual(res['signed_zero_counts']['positive_zeros'], 59118)
        self.assertEqual(res['invariant_groups']['reserved_numeric_zeros']['status'], 'pass')
        self.assertEqual(res['invariant_groups']['interface_metadata_constants']['status'], 'pass')
        self.assertEqual(res['invariant_groups']['vector_lengths']['status'], 'pass')
        self.assertEqual(res['invariant_groups']['finite_numeric_non_bool']['status'], 'pass')
        self.assertEqual(res['invariant_groups']['terminal_record']['status'], 'pass')
        self.assertEqual(res['invariant_groups']['usable_samples']['status'], 'pass')

    def test_retained_public_record_terrain_pass(self):
        """Verify the retained terrain-01 record.jsonl passes all invariants."""
        self.assertTrue(RETAINED_TERRAIN.is_file(), f'Missing retained file: {RETAINED_TERRAIN}')
        res = audit_record(RETAINED_TERRAIN)
        self.assertTrue(res['passed'])
        self.assertEqual(res['sample_counts']['usable_samples'], 501)
        self.assertEqual(res['violations'], [])
        self.assertEqual(res['signed_zero_counts']['negative_zeros'], 0)
        self.assertEqual(res['signed_zero_counts']['positive_zeros'], 59118)

    def test_synthetic_minimal_valid_pass(self):
        """Verify a synthetic 3-sample record.jsonl passes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(sample_count=3), encoding='utf-8')
            res = audit_record(file_path)
            self.assertTrue(res['passed'])
            self.assertEqual(res['sample_counts']['usable_samples'], 3)
            self.assertEqual(res['violations'], [])
            self.assertEqual(res['signed_zero_counts']['positive_zeros'], 3 * 59 * 2)

    def test_tampered_reserved_zero_vehicle60(self):
        """Tampering Vehicle60[33] to non-zero must fail."""
        def mutate(sample):
            sample['major_root_outputs']['Vehicle60'][33] = 0.001

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['reserved_numeric_zeros']['status'], 'fail')
            self.assertGreaterEqual(res['invariant_groups']['reserved_numeric_zeros']['violations'], 1)
            self.assertTrue(any('Vehicle60[33]' in v for v in res['violations']))

    def test_tampered_reserved_zero_sensor30(self):
        """Tampering Sensor30[15] in post_step_api to non-zero must fail."""
        def mutate(sample):
            sample['post_step_api']['Sensor30'][15] = -0.5

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['reserved_numeric_zeros']['status'], 'fail')
            self.assertTrue(any('Sensor30[15]' in v for v in res['violations']))

    def test_tampered_reserved_zero_gps30(self):
        """Tampering GPS30[29] in major_root_outputs must fail."""
        def mutate(sample):
            sample['major_root_outputs']['GPS30'][29] = 1e-4

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['reserved_numeric_zeros']['status'], 'fail')
            self.assertTrue(any('GPS30[29]' in v for v in res['violations']))

    def test_tampered_constant_vehicle60(self):
        """Tampering Vehicle60[0] (expected 1.0) or [1] (expected 3.0) must fail."""
        def mutate(sample):
            sample['major_root_outputs']['Vehicle60'][0] = 2.0

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['interface_metadata_constants']['status'], 'fail')
            self.assertTrue(any('Vehicle60[0]' in v for v in res['violations']))

    def test_tampered_constant_sensor30(self):
        """Tampering Sensor30[14] (expected 8191.0) must fail."""
        def mutate(sample):
            sample['post_step_api']['Sensor30'][14] = 8190.0

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['interface_metadata_constants']['status'], 'fail')
            self.assertTrue(any('Sensor30[14]' in v for v in res['violations']))

    def test_tampered_constant_gps30(self):
        """Tampering GPS30[11] or GPS30[12] must fail."""
        def mutate(sample):
            sample['major_root_outputs']['GPS30'][12] = 8.0

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['interface_metadata_constants']['status'], 'fail')
            self.assertTrue(any('GPS30[12]' in v for v in res['violations']))

    def test_wrong_vector_length_major(self):
        """Wrong length in major_root_outputs must fail vector_lengths invariant."""
        def mutate(sample):
            sample['major_root_outputs']['Vehicle60'] = sample['major_root_outputs']['Vehicle60'][:59]

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['vector_lengths']['status'], 'fail')
            self.assertTrue(any('Vehicle60 length 59 != 60' in v for v in res['violations']))

    def test_wrong_vector_length_post_step(self):
        """Wrong length in post_step_api must fail vector_lengths invariant."""
        def mutate(sample):
            sample['post_step_api']['Sensor30'].append(0.0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['vector_lengths']['status'], 'fail')
            self.assertTrue(any('Sensor30 length 31 != 30' in v for v in res['violations']))

    def test_nonfinite_nan_rejected(self):
        """NaN values must fail finite_numeric_non_bool invariant."""
        def mutate(sample):
            sample['major_root_outputs']['Vehicle60'][3] = float('nan')

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['finite_numeric_non_bool']['status'], 'fail')

    def test_nonfinite_inf_rejected(self):
        """Inf values must fail finite_numeric_non_bool invariant."""
        def mutate(sample):
            sample['post_step_api']['GPS30'][1] = float('inf')

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['finite_numeric_non_bool']['status'], 'fail')

    def test_boolean_value_rejected(self):
        """Boolean True/False must fail even if numerically equal to expected value."""
        def mutate(sample):
            # True == 1.0 in Python numeric equality, but type is bool
            sample['major_root_outputs']['Vehicle60'][0] = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'record.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['finite_numeric_non_bool']['status'], 'fail')
            self.assertTrue(any('type=bool' in v for v in res['violations']))

    def test_empty_file_fails(self):
        """An empty record.jsonl must fail usable_samples invariant."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'empty.jsonl'
            file_path.write_text('', encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['sample_counts']['total_lines'], 0)
            self.assertEqual(res['invariant_groups']['usable_samples']['status'], 'fail')

    def test_zero_usable_samples_fails(self):
        """File containing start and end records but no sample records must fail."""
        start = {'schema_version': 1, 'kind': 'major_recorder_start', 'expected_calls': 0}
        end = {'schema_version': 1, 'kind': 'major_recorder_end', 'status': 'complete',
               'attempted_calls': 0, 'returned_calls': 0, 'emitted_samples': 0,
               'comparison_end_s': 0.0, 'engine_end_s': 0.0}
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'no_samples.jsonl'
            file_path.write_text(f'{json.dumps(start)}\n{json.dumps(end)}\n', encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['sample_counts']['usable_samples'], 0)
            self.assertEqual(res['invariant_groups']['usable_samples']['status'], 'fail')

    def test_missing_terminal_record_fails(self):
        """Missing terminal major_recorder_end record must fail terminal_record invariant."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'no_end.jsonl'
            lines = _make_valid_record_lines(sample_count=2).splitlines()[:-1]  # strip terminal
            file_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['terminal_record']['status'], 'fail')

    def test_invalid_terminal_status_fails(self):
        """Terminal record with status != 'complete' must fail."""
        def mutate_end(end_rec):
            end_rec['status'] = 'incomplete'

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'bad_end.jsonl'
            file_path.write_text(_make_valid_record_lines(mutate_end=mutate_end), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['terminal_record']['status'], 'fail')

    def test_mismatched_terminal_sample_count_fails(self):
        """Terminal emitted_samples mismatching actual sample count must fail."""
        def mutate_end(end_rec):
            end_rec['emitted_samples'] = 999
            end_rec['attempted_calls'] = 999
            end_rec['returned_calls'] = 999

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'mismatch_end.jsonl'
            file_path.write_text(_make_valid_record_lines(sample_count=2, mutate_end=mutate_end), encoding='utf-8')
            res = audit_record(file_path)
            self.assertFalse(res['passed'])
            self.assertEqual(res['invariant_groups']['usable_samples']['status'], 'fail')

    def test_signed_zero_accepted_and_reported(self):
        """Negative zero (-0.0) in reserved zero slots must pass and increment negative_zeros count."""
        def mutate(sample):
            # Place negative zero in Vehicle60[33] and post_step_api Sensor30[15]
            sample['major_root_outputs']['Vehicle60'][33] = -0.0
            sample['post_step_api']['Sensor30'][15] = -0.0

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / 'signed_zeros.jsonl'
            file_path.write_text(_make_valid_record_lines(sample_count=2, mutate_sample=mutate), encoding='utf-8')
            res = audit_record(file_path)
            self.assertTrue(res['passed'])
            self.assertEqual(res['signed_zero_counts']['negative_zeros'], 2)
            self.assertEqual(res['signed_zero_counts']['positive_zeros'], (2 * 59 * 2) - 2)

    def test_multiple_inputs_batch(self):
        """audit_records on a batch of files reports summary and individual results deterministically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            good_file = Path(tmp_dir) / 'good.jsonl'
            bad_file = Path(tmp_dir) / 'bad.jsonl'
            good_file.write_text(_make_valid_record_lines(sample_count=2), encoding='utf-8')
            bad_file.write_text('not json\n', encoding='utf-8')

            report = audit_records([str(good_file), str(bad_file)])
            self.assertEqual(report['summary']['total_inputs'], 2)
            self.assertEqual(report['summary']['passed_inputs'], 1)
            self.assertEqual(report['summary']['failed_inputs'], 1)
            self.assertFalse(report['summary']['all_passed'])
            self.assertEqual(len(report['results']), 2)
            self.assertTrue(report['results'][0]['passed'])
            self.assertFalse(report['results'][1]['passed'])

    def test_diagnostic_scope_no_g6_or_physical_claim(self):
        """Report must explicitly disclaim G6 and physical completion."""
        report = audit_records([str(RETAINED_PARENT_FINAL)])
        self.assertFalse(report['g6_acceptance'])
        self.assertFalse(report['physical_completion'])
        self.assertEqual(report['scope'], 'offline_invariant_diagnostics_only')

        json_str = format_audit_json(report)
        parsed = json.loads(json_str)
        self.assertFalse(parsed['g6_acceptance'])
        self.assertFalse(parsed['physical_completion'])

    def test_cli_execution_pass(self):
        """CLI invocation returns exit code 0 when all inputs pass."""
        with redirect_stdout(io.StringIO()):
            ret = main([str(RETAINED_PARENT_FINAL)])
        self.assertEqual(ret, 0)

    def test_cli_execution_fail(self):
        """CLI invocation returns exit code 2 when any input fails."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_file = Path(tmp_dir) / 'bad.jsonl'
            bad_file.write_text('bad content\n', encoding='utf-8')
            with redirect_stdout(io.StringIO()):
                ret = main([str(bad_file)])
            self.assertEqual(ret, 2)


if __name__ == '__main__':
    unittest.main()
