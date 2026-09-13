"""Offline tests for the G6 first-divergence locator.

Pure offline numerical comparison against already-pinned R1 evidence (or small
synthetic fixtures). No model, MATLAB, native process, ROS node, or build is
run; the tool only reads retained artifacts, verifies their integrity, and
reports the earliest binary64 divergence as an unproven hypothesis. No
acceptance gate or frozen evidence is changed. The CLI writes its report with an
exclusive create and refuses to overwrite any retained report.
"""
import hashlib
import io
import json
import math
import os
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import diagnose_g6_first_divergence as diag

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / 'validation' / 'numerical-conformance-gxxh6xhr'
CONTRACT = REPO / 'Simulator' / 'wksim_core' / 'numerical-conformance-v1.json'
REFUSAL_EXIT = 2

# The pinned earliest divergence (confirmed against all-failures.jsonl):
# case C3G, k=1, Vehicle60[3] velocity_ned (m/s). C2G shows the bit-identical
# value at k=101, i.e. the first step after each case's motor-input onset.
EARLIEST_REF_HEX = '0x1.fb743384c5850p-98'
EARLIEST_TGT_HEX = '0x1.fb743384c584ep-98'
EARLIEST_REF = 6.254852369965466e-30
EARLIEST_TGT = 6.2548523699654644e-30


class UlpDistanceTests(unittest.TestCase):
    def test_known_pair_is_two_ulp(self):
        self.assertEqual(diag.ulp_distance(EARLIEST_REF_HEX, EARLIEST_TGT_HEX), 2)

    def test_identical_is_zero_and_symmetric(self):
        self.assertEqual(diag.ulp_distance(EARLIEST_REF_HEX, EARLIEST_REF_HEX), 0)
        self.assertEqual(diag.ulp_distance(EARLIEST_REF_HEX, EARLIEST_TGT_HEX),
                         diag.ulp_distance(EARLIEST_TGT_HEX, EARLIEST_REF_HEX))

    def test_negative_pair_counts_magnitude_ulp(self):
        self.assertEqual(diag.ulp_distance('-0x1.040ed53eaf759p-160',
                                           '-0x1.040ed53eaf75ap-160'), 1)


def _row(case, array, index, k, reference, target, contract_sha, epoch=None,
         reference_hex=None):
    return {
        'case': case, 'epoch': epoch if epoch is not None else 'epoch-' + case,
        'contract_sha256': contract_sha,
        'array': array, 'index': index, 'k': k,
        'reference': reference, 'target': target,
        'reference_hex': reference_hex if reference_hex is not None else float(reference).hex(),
        'target_hex': float(target).hex(),
        'absolute_error': abs(target - reference),
    }


def _write_fixture(root):
    """A valid synthetic R1-shaped evidence set with internally consistent hashes.

    Layout mirrors the real evidence (run-index two levels under the root) so the
    case manifest resolves the same way.
    """
    evidence = root / 'validation' / 'g6fix'
    (evidence / 'C3G').mkdir(parents=True)
    contract = {
        'identity': {'reference_engine': 'MATLAB test normal',
                     'target_profile': 'test g++ -O2 -fno-fast-math'},
        'observables': [
            {'id': 'velocity_ned', 'array': 'Vehicle60', 'indices': [3, 4, 5],
             'native_unit': 'm/s', 'semantic_status': 'mapped_physical_observable',
             'source': 'cpp:7823-7827', 'absolute_budget': 0, 'relative_budget': 0},
            {'id': 'euler_components', 'array': 'Vehicle60', 'indices': [9, 10, 11],
             'native_unit': 'rad', 'semantic_status': 'encoded_orientation_components_only',
             'source': 'cpp:4301', 'absolute_budget': 0, 'relative_budget': 0},
            {'id': 'absolute_pressure', 'array': 'Sensor30', 'indices': [10],
             'native_unit': 'hPa', 'semantic_status': 'mapped_physical_observable',
             'source': 'cpp:7617', 'absolute_budget': 0, 'relative_budget': 0},
        ],
        'cases': [
            {'id': 'C0', 'input': {'path': 'inputs/C0.csv', 'sha256': 'sha-c0'},
             'events': [{'first_k': 0, 'last_k': 500, 'inPWMs0_to_3': [0, 0, 0, 0]}]},
            {'id': 'C2G', 'input': {'path': 'inputs/C2G.csv', 'sha256': 'sha-c2g'},
             'events': [{'first_k': 0, 'last_k': 99, 'inPWMs0_to_3': [0, 0, 0, 0]},
                        {'first_k': 100, 'last_k': 500, 'inPWMs0_to_3': [.6, .6, .6, .6]}]},
            {'id': 'C3G', 'input': {'path': 'inputs/C3G.csv', 'sha256': 'sha-c3g'},
             'events': [{'first_k': 0, 'last_k': 99, 'inPWMs0_to_3': [.6, .6, .6, .6]},
                        {'first_k': 100, 'last_k': 500, 'inPWMs0_to_3': [.65, .6, .6, .6]}]},
        ],
    }
    contract_bytes = (json.dumps(contract, indent=2) + '\n').encode()
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    (evidence / 'contract.json').write_bytes(contract_bytes)

    failures = [
        _row('C3G', 'Vehicle60', 3, 1, EARLIEST_REF, EARLIEST_TGT, contract_sha),
        _row('C3G', 'Vehicle60', 11, 5, -1.0e-49, -1.0000000000000002e-49, contract_sha),
        _row('C2G', 'Vehicle60', 3, 101, EARLIEST_REF, EARLIEST_TGT, contract_sha),
        _row('C0', 'Sensor30', 10, 153, 1007.2510342146562, 1007.2510342146564, contract_sha),
    ]
    (evidence / 'all-failures.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in failures))

    manifest = {'target_hashes': {'/t/major_model_recorder': 'sha-exe',
                                  '/t/Exp1_MinModelTemp.cpp': 'sha-gen'}}
    manifest_bytes = (json.dumps(manifest, indent=2) + '\n').encode()
    (evidence / 'C3G' / 'manifest.json').write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    run_index = {
        'contract_sha256': contract_sha,
        'failed_values': len(failures),
        'results': [{'case': 'C0', 'epoch': 'epoch-C0', 'failed_values': 1},
                    {'case': 'C2G', 'epoch': 'epoch-C2G', 'failed_values': 1},
                    {'case': 'C3G', 'epoch': 'epoch-C3G', 'failed_values': 2}],
        'artifacts': {
            'validation/g6fix/C3G/manifest.json': manifest_sha,
            'validation/g6fix/C3G/build.json': 'sha-build',
            'validation/g6fix/C3G/major_model_recorder.cpp': 'sha-recorder',
            'validation/g6fix/C3G/applied-input.f64': 'sha-applied',
        },
    }
    (evidence / 'run-index.json').write_text(json.dumps(run_index, indent=2) + '\n')
    return evidence


def _diagnose(evidence):
    return diag.diagnose(evidence / 'all-failures.jsonl',
                         evidence / 'contract.json',
                         evidence / 'run-index.json')


class IntegrityTests(unittest.TestCase):
    """Tampering with any verified input must be refused, never localized as success."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.evidence = _write_fixture(self.root)

    def test_valid_fixture_passes(self):
        self.assertEqual(_diagnose(self.evidence)['earliest_k'], 1)

    def test_equal_values_and_signed_zeros_cannot_be_reported_as_failures(self):
        path = self.evidence / 'all-failures.jsonl'
        original = [json.loads(line) for line in path.read_text().splitlines()]
        for reference, target in ((1., 1.), (-0., 0.)):
            with self.subTest(reference=reference, target=target):
                rows = [dict(row) for row in original]
                rows[0].update(reference=reference, target=target,
                               reference_hex=reference.hex(), target_hex=target.hex())
                path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
                with self.assertRaisesRegex(ValueError, 'not a strict binary64 inequality'):
                    _diagnose(self.evidence)

    def test_nonfinite_or_boolean_values_are_not_finite_binary64_failures(self):
        path = self.evidence / 'all-failures.jsonl'
        original = [json.loads(line) for line in path.read_text().splitlines()]
        for value in (math.inf, math.nan, True):
            with self.subTest(value=value):
                rows = [dict(row) for row in original]
                rows[0].update(reference=value, reference_hex=float(value).hex())
                path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
                with self.assertRaisesRegex(ValueError, 'finite JSON numbers'):
                    _diagnose(self.evidence)

    def test_contract_bytes_mismatch_refused(self):
        path = self.evidence / 'contract.json'
        path.write_bytes(path.read_bytes() + b' ')  # change bytes, not the recorded sha
        with self.assertRaises(ValueError):
            _diagnose(self.evidence)

    def test_failure_count_mismatch_refused(self):
        path = self.evidence / 'run-index.json'
        index = json.loads(path.read_text())
        index['failed_values'] = 999
        path.write_text(json.dumps(index))
        with self.assertRaises(ValueError):
            _diagnose(self.evidence)

    def test_failure_row_contract_mismatch_refused(self):
        path = self.evidence / 'all-failures.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['contract_sha256'] = 'tampered'
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        # keep run-index count consistent so only the per-row binding fails
        with self.assertRaises(ValueError):
            _diagnose(self.evidence)

    def test_hex_decimal_mismatch_refused(self):
        path = self.evidence / 'all-failures.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['reference_hex'] = '0x1.0p+0'  # no longer decodes to `reference`
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        with self.assertRaises(ValueError):
            _diagnose(self.evidence)

    def test_manifest_bytes_tamper_refused(self):
        path = self.evidence / 'C3G' / 'manifest.json'
        path.write_bytes(path.read_bytes() + b' ')  # change bytes, not run-index sha
        with self.assertRaises(ValueError):
            _diagnose(self.evidence)


class DiagnoseSyntheticTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.evidence = _write_fixture(Path(self._tmp.name))
        self.result = _diagnose(self.evidence)

    def test_earliest_is_planted_row(self):
        self.assertEqual(self.result['earliest_k'], 1)
        rep = self.result['representative']
        self.assertEqual((rep['case'], rep['array'], rep['index'], rep['k']),
                         ('C3G', 'Vehicle60', 3, 1))
        self.assertEqual(rep['ulp_distance'], 2)

    def test_co_earliest_and_count_reconciled(self):
        self.assertEqual(self.result['total_failed_values'], 4)
        self.assertEqual([r['index'] for r in self.result['co_earliest']], [3])

    def test_determinism_locked_across_cases(self):
        det = self.result['determinism']
        self.assertTrue(det['same_value_bit_identical'])
        self.assertEqual(det['first_failure_after_input_onset'], {'C2G': 101, 'C3G': 1})

    def test_aggregate_reports_ulp_scale_observations(self):
        agg = self.result['aggregate']
        self.assertEqual(agg['sign_flip_count'], 0)
        self.assertEqual(agg['ratio_outside_half_to_two_count'], 0)
        self.assertLessEqual(agg['max_relative_error'], 1e-9)

    def test_verdict_is_unproven_hypothesis_not_conclusion(self):
        verdict = json.dumps(self.result['verdict'])
        self.assertEqual(self.result['verdict']['hypothesis_status'], 'unproven')
        self.assertIn('consistent with', self.result['verdict']['hypothesis'])
        # no hardcoded proof-of-exclusion or physical-magnitude claim
        self.assertNotIn('contract_error_excluded', verdict)
        self.assertNotIn('physically_zero', verdict)

    def test_provenance_pulled(self):
        prov = self.result['representative']['provenance']
        self.assertEqual(prov['input_csv_sha256'], 'sha-c3g')
        self.assertEqual(prov['build_sha256'], 'sha-build')
        self.assertEqual(prov['executable_sha256'], 'sha-exe')
        self.assertEqual(prov['generated_cpp_sha256'], 'sha-gen')
        self.assertEqual(prov['reference_engine'], 'MATLAB test normal')


class CliOutputTests(unittest.TestCase):
    """The report write must be an exclusive create that never overwrites."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.evidence = _write_fixture(self.root)
        self.out_dir = self.root / 'out'

    def invoke(self, out_dir=None, no_write=False, evidence=None):
        evidence = self.evidence if evidence is None else evidence
        argv = ['diagnose_g6_first_divergence.py',
                '--failures', str(evidence / 'all-failures.jsonl'),
                '--contract', str(evidence / 'contract.json'),
                '--run-index', str(evidence / 'run-index.json'),
                '--out-dir', str(self.out_dir if out_dir is None else out_dir)]
        if no_write:
            argv += ['--no-write']
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', argv), redirect_stdout(out), redirect_stderr(err):
            try:
                code = diag.main()
            except SystemExit as error:
                code = error.code
        return code, out.getvalue(), err.getvalue()

    def test_fresh_report_written_and_exit_zero(self):
        code, out, err = self.invoke()
        self.assertEqual(code, 0)
        report = self.out_dir / 'diagnosis.json'
        self.assertTrue(report.is_file())
        self.assertEqual(json.loads(report.read_text())['earliest_k'], 1)

    def test_existing_report_preserved_verbatim(self):
        self.out_dir.mkdir()
        target = self.out_dir / 'diagnosis.json'
        sentinel = b'PREVIOUS DIAGNOSIS\x00verbatim\n'
        target.write_bytes(sentinel)
        code, out, err = self.invoke()
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertEqual(target.read_bytes(), sentinel)
        self.assertIn('refusing to overwrite', err)

    def test_dangling_symlink_report_refused(self):
        self.out_dir.mkdir()
        target = self.out_dir / 'diagnosis.json'
        try:
            os.symlink(str(self.out_dir / 'missing.json'), str(target))
        except OSError as error:
            self.skipTest(f'symlink unavailable: {error}')
        code, out, err = self.invoke()
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertTrue(target.is_symlink())

    def test_exclusive_create_race_does_not_overwrite(self):
        """If the target appears after the pre-check, open(...,'x') must refuse."""
        self.out_dir.mkdir()
        target = self.out_dir / 'diagnosis.json'
        sentinel = b'RACE WINNER\n'
        target.write_bytes(sentinel)
        real_lexists = os.path.lexists
        # Force the pre-check to pass so the exclusive create is the only guard.
        with patch.object(os.path, 'lexists',
                          lambda p: False if Path(p) == target else real_lexists(p)):
            code, out, err = self.invoke()
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertEqual(target.read_bytes(), sentinel)
        self.assertIn('refusing to overwrite', err)

    def test_no_write_produces_no_file(self):
        code, out, err = self.invoke(no_write=True)
        self.assertEqual(code, 0)
        self.assertFalse((self.out_dir / 'diagnosis.json').exists())

    def test_integrity_failure_refuses_without_writing(self):
        path = self.evidence / 'run-index.json'
        index = json.loads(path.read_text())
        index['failed_values'] = 999
        path.write_text(json.dumps(index))
        code, out, err = self.invoke()
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertIn('refused', err)
        self.assertFalse((self.out_dir / 'diagnosis.json').exists())


class DiagnoseRealEvidenceTests(unittest.TestCase):
    """Regression-lock the located first divergence against the pinned R1 set."""

    def setUp(self):
        if not (EVIDENCE / 'all-failures.jsonl').is_file() or not CONTRACT.is_file():
            self.skipTest('pinned R1 evidence not present')
        self.result = diag.diagnose(
            EVIDENCE / 'all-failures.jsonl', CONTRACT, EVIDENCE / 'run-index.json')

    def test_total_is_the_documented_5684(self):
        self.assertEqual(self.result['total_failed_values'], 5684)
        self.assertEqual(self.result['run_index_failed_values'], 5684)

    def test_earliest_is_c3g_k1_velocity(self):
        self.assertEqual(self.result['earliest_k'], 1)
        rep = self.result['representative']
        self.assertEqual((rep['case'], rep['array'], rep['index'], rep['k']),
                         ('C3G', 'Vehicle60', 3, 1))
        self.assertEqual(rep['reference'], EARLIEST_REF)
        self.assertEqual(rep['target'], EARLIEST_TGT)
        self.assertEqual(rep['reference_hex'], EARLIEST_REF_HEX)
        self.assertEqual(rep['target_hex'], EARLIEST_TGT_HEX)
        self.assertEqual(rep['ulp_distance'], 2)
        self.assertEqual(rep['native_unit'], 'm/s')
        self.assertEqual(rep['semantic_status'], 'mapped_physical_observable')

    def test_co_earliest_axes_and_ulp(self):
        got = {(r['array'], r['index']): r['ulp_distance'] for r in self.result['co_earliest']}
        self.assertEqual(got, {('Vehicle60', 3): 2, ('Vehicle60', 11): 1, ('Vehicle60', 15): 64})

    def test_determinism_bit_identical_to_c2g(self):
        det = self.result['determinism']
        self.assertTrue(det['same_value_bit_identical'])
        self.assertEqual(det['first_failure_after_input_onset'], {'C2G': 101, 'C3G': 1})

    def test_all_failures_ulp_scale_observations(self):
        agg = self.result['aggregate']
        self.assertEqual(agg['sign_flip_count'], 0)
        self.assertEqual(agg['ratio_outside_half_to_two_count'], 0)
        self.assertLessEqual(agg['max_relative_error'], 1e-9)

    def test_provenance_shas(self):
        prov = self.result['representative']['provenance']
        self.assertEqual(prov['input_csv_sha256'],
                         '721c88bf3f621923b98bb43251c50bae7817106a984be64345c0528d34d3adcf')
        self.assertEqual(prov['build_sha256'],
                         '6e16102ae1197a899eef554b9c938f5ca32220516fdd8630c7b8b1b19267cce3')
        self.assertEqual(prov['executable_sha256'],
                         'c685817a974471113793fde3c78eeed26f7c7b56eef1194f9df1fd2ecf7e8d49')
        self.assertEqual(prov['generated_cpp_sha256'],
                         'a3eba68e1a4a5cefc772fb502a63eac1e7475548688adebb83cbc9390086a073')


class ReadOnceTests(unittest.TestCase):
    """The tool must read each evidence file once: the parsed data and the
    reported SHA256 must come from the same captured bytes."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.evidence = _write_fixture(Path(self._tmp.name))
        self.failures = self.evidence / 'all-failures.jsonl'
        self.contract = self.evidence / 'contract.json'
        self.run_index = self.evidence / 'run-index.json'

    def test_reported_hash_matches_parsed_bytes_despite_mid_run_mutation(self):
        original_failures = self.failures.read_bytes()
        original_run_index = self.run_index.read_bytes()
        real_manifest = diag._verified_manifest

        def mutating_manifest(artifacts, case, run_index_path):
            # A concurrent writer changes the evidence on disk AFTER it was read
            # and parsed but BEFORE the manifest check completes.
            with self.failures.open('ab') as fh:
                fh.write(b'\n')
            with self.run_index.open('ab') as fh:
                fh.write(b' ')
            return real_manifest(artifacts, case, run_index_path)

        with patch.object(diag, '_verified_manifest', mutating_manifest):
            result = diag.diagnose(self.failures, self.contract, self.run_index)
        # Reported hashes must correspond to the actually-parsed original bytes.
        self.assertEqual(result['inputs_sha256']['failures'],
                         hashlib.sha256(original_failures).hexdigest())
        self.assertEqual(result['inputs_sha256']['run_index'],
                         hashlib.sha256(original_run_index).hexdigest())
        # Guard against a vacuous test: the on-disk files really did change.
        self.assertNotEqual(hashlib.sha256(self.failures.read_bytes()).hexdigest(),
                            result['inputs_sha256']['failures'])
        self.assertNotEqual(hashlib.sha256(self.run_index.read_bytes()).hexdigest(),
                            result['inputs_sha256']['run_index'])
        # And the diagnosis itself used the original bytes.
        self.assertEqual(result['earliest_k'], 1)

    def test_each_evidence_file_is_opened_exactly_once(self):
        real_open = Path.open
        opens = []

        def counting_open(p, *args, **kwargs):
            opens.append(Path(p).name)
            return real_open(p, *args, **kwargs)

        # Path.open funnels both read_bytes() and the sha256(path) helper's open(),
        # so this counts every underlying open, not just read_bytes calls.
        with patch.object(Path, 'open', counting_open):
            diag.diagnose(self.failures, self.contract, self.run_index)
        counts = Counter(opens)
        for name in ('all-failures.jsonl', 'contract.json', 'run-index.json', 'manifest.json'):
            self.assertEqual(counts.get(name, 0), 1,
                             f'{name} opened {counts.get(name, 0)} times (expected once)')


if __name__ == '__main__':
    unittest.main()
