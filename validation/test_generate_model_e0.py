"""Unit tests for the isolated MATLAB e0 code generation driver (tools/generate_model_e0.py).

Verifies staging, isolation, error handling, mock orchestration, and immutability gates.
Does NOT invoke real MATLAB, SITL, or UE.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.generate_model_e0 import (
    DEFAULT_SOURCE,
    EXPECTED_SOURCES,
    REQUIRED_LICENSES,
    REQUIRED_STAGES,
    ROOT,
    ProcessTracker,
    audit_and_finalize,
    digest,
    execute_codegen,
    prepare_run,
    run,
    validate_directory_containment,
    validate_run_id,
)


class TestGenerateModelE0(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_temp = Path(self.temp_dir.name)
        self.mock_source = self.base_temp / 'mock-source'
        self.mock_source.mkdir(parents=True, exist_ok=True)
        for name, expected_hash in EXPECTED_SOURCES.items():
            real_file = DEFAULT_SOURCE / name
            if real_file.is_file() and digest(real_file) == expected_hash:
                shutil.copyfile(real_file, self.mock_source / name)
            else:
                raise RuntimeError(f"Expected source file not found at {real_file}")

        self.mock_project_root = self.base_temp / 'mock-wksim'
        (self.mock_project_root / 'work/codegen-e0').mkdir(parents=True, exist_ok=True)
        (self.mock_project_root / 'validation/codegen-e0').mkdir(parents=True, exist_ok=True)

        self.work_root = self.mock_project_root / 'work/codegen-e0'
        self.evidence_root = self.mock_project_root / 'validation/codegen-e0'

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_mock_report(self, status='generated', licenses_override=None, failed_stage=None):
        """Helper to create a standard mock MATLAB codegen report structure."""
        licenses = {
            'test': {feat.replace('-', '_'): 1 for feat in REQUIRED_LICENSES},
            'checkout': {feat.replace('-', '_'): 1 for feat in REQUIRED_LICENSES},
        }
        if licenses_override:
            for k, v in licenses_override.items():
                if k in licenses['checkout']:
                    licenses['checkout'][k] = v

        stages = []
        for st in REQUIRED_STAGES:
            st_status = 'failed' if st == failed_stage else 'ok'
            stages.append({'name': st, 'command': f'mock_{st}', 'status': st_status})

        return {
            'status': status,
            'environment': {
                'version': '9.13.0.2049777 (R2022b)',
                'release': 'R2022b',
                'matlabroot': 'D:\\matlab\\install date',
            },
            'licenses': licenses,
            'solver': {'Solver': 'ode4', 'FixedStep': '0.001', 'SimulationMode': 'normal'},
            'stages': stages,
        }

    def test_dry_prepare_default_does_not_launch_matlab(self):
        """Default execution (run_flag=False) must only stage files and generate manifests."""
        run_id = 'test-dry-run-01'
        with patch('subprocess.Popen') as mock_popen:
            result = run(
                run_flag=False,
                source_dir=self.mock_source,
                work_root=self.work_root,
                evidence_root=self.evidence_root,
                run_id=run_id,
                project_root=self.mock_project_root,
            )
            mock_popen.assert_not_called()

        self.assertEqual(result['status'], 'prepared')
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        staged_dir = work_dir / 'staged-model'
        for name in EXPECTED_SOURCES:
            staged_file = staged_dir / name
            self.assertTrue(staged_file.is_file())
            self.assertEqual(digest(staged_file), EXPECTED_SOURCES[name])

        self.assertTrue((staged_dir / 'generate_model_e0.m').is_file())
        self.assertTrue((staged_dir / 'codegen_config.json').is_file())
        self.assertTrue((evidence_dir / 'source-manifest.json').is_file())
        self.assertTrue((evidence_dir / 'summary.json').is_file())

    def test_invalid_run_id_characters_rejected(self):
        """Run ID containing separators, traversal, or invalid characters must be rejected."""
        invalid_ids = ['../bad', 'run/01', 'run\\02', 'run.name', 'run:bad', 'run*bad', '']
        for bad_id in invalid_ids:
            with self.assertRaises(ValueError):
                validate_run_id(bad_id)

    def test_prepare_run_boundary_violation_has_no_write_side_effects(self):
        """Passing out-of-bounds directories to prepare_run must fail with zero side-effects."""
        outside_work = self.base_temp / 'rogue-work-dir'
        valid_evidence = self.evidence_root / 'valid-evidence-dir'

        # Case 1: work_dir outside project work
        with self.assertRaises(ValueError) as ctx:
            prepare_run(self.mock_source, outside_work, valid_evidence, project_root=self.mock_project_root)
        self.assertIn('work_dir', str(ctx.exception))
        # Ensure ZERO write side-effects (directory was never created)
        self.assertFalse(outside_work.exists())
        self.assertFalse(valid_evidence.exists())

        # Case 2: evidence_dir outside project validation
        valid_work = self.work_root / 'valid-work-dir'
        outside_evidence = self.base_temp / 'rogue-evidence-dir'
        with self.assertRaises(ValueError) as ctx:
            prepare_run(self.mock_source, valid_work, outside_evidence, project_root=self.mock_project_root)
        self.assertIn('evidence_dir', str(ctx.exception))
        self.assertFalse(valid_work.exists())
        self.assertFalse(outside_evidence.exists())

        # Case 3: attempt to use work root itself as work_dir
        with self.assertRaises(ValueError) as ctx:
            prepare_run(self.mock_source, self.mock_project_root / 'work', valid_evidence, project_root=self.mock_project_root)
        self.assertIn('cannot be the work root itself', str(ctx.exception))

        # Case 4: work_dir and evidence_dir overlap or equal
        with self.assertRaises(ValueError):
            prepare_run(self.mock_source, valid_work, valid_work, project_root=self.mock_project_root)

    def test_input_sha_mismatch_rejected(self):
        """Preparation must fail immediately if any source file hash differs from EXPECTED."""
        tampered_source = self.base_temp / 'tampered-source'
        shutil.copytree(self.mock_source, tampered_source)
        (tampered_source / 'Exp1_MinModelTemp.slx').write_bytes(b'tampered binary content')

        run_id = 'test-tampered-prep'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id
        with self.assertRaises(ValueError) as ctx:
            prepare_run(tampered_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        self.assertIn('Source SHA mismatch', str(ctx.exception))

    def test_missing_input_file_rejected(self):
        """Preparation must fail if an expected source file is missing."""
        incomplete_source = self.base_temp / 'incomplete-source'
        incomplete_source.mkdir()
        (incomplete_source / 'Exp1_MinModelTemp.slx').write_bytes(b'xyz')

        run_id = 'test-missing-prep'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id
        with self.assertRaises(FileNotFoundError):
            prepare_run(incomplete_source, work_dir, evidence_dir, project_root=self.mock_project_root)

    def test_reuse_nonempty_directory_rejected(self):
        """Driver must refuse to reuse an existing non-empty work or evidence directory."""
        run_id = 'test-reuse-dir'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / 'existing_file.txt').write_text('dirty content')

        with self.assertRaises(ValueError) as ctx:
            prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        self.assertIn('Refusing to reuse non-empty work directory', str(ctx.exception))

    def test_mock_successful_generation(self):
        """Mock successful slbuild: verifies artifact audit, manifest generation, and 'generated' status."""
        run_id = 'test-mock-success'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        staged_dir = Path(prep['staged_dir'])
        codegen_dir = work_dir / 'codegen'

        model_build_dir = codegen_dir / 'Exp1_MinModelTemp_ert_rtw'
        model_build_dir.mkdir(parents=True, exist_ok=True)
        (model_build_dir / 'Exp1_MinModelTemp.cpp').write_text('// Mock generated C++ code\nvoid step() {}\n')
        (model_build_dir / 'Exp1_MinModelTemp.h').write_text('// Mock generated header\n')

        matlab_report = self._create_mock_report()
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 0, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, staged_dir, codegen_dir, evidence_dir, exec_res)

        self.assertEqual(summary['status'], 'generated')
        self.assertEqual(summary['cpp_count'], 1)
        self.assertEqual(summary['header_count'], 1)
        self.assertTrue(summary['licenses_ok'])
        self.assertTrue(summary['stages_ok'])
        self.assertTrue(summary['slbuild_ok'])
        self.assertFalse(summary['source_tampered'])
        self.assertFalse(summary['staged_tampered'])

        manifest_path = evidence_dir / 'generated-sources-manifest.json'
        self.assertTrue(manifest_path.is_file())
        manifest_data = json.loads(manifest_path.read_text())
        self.assertEqual(manifest_data['total_files'], 2)
        for entry in manifest_data['sources']:
            self.assertIn('sha256', entry)
            self.assertIn('size_bytes', entry)
            self.assertNotIn('code', entry)
            self.assertNotIn('content', entry)

    def test_matlab_failure_exit_code_rejected(self):
        """A non-zero return code from MATLAB must cause status='failed'."""
        run_id = 'test-mock-fail'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        exec_res = {'return_code': 1, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), work_dir / 'codegen', evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'failed')

    def test_missing_artifacts_rejected(self):
        """Exit code 0 but missing C++ files must be rejected as missing_artifacts."""
        run_id = 'test-mock-missing-art'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        matlab_report = self._create_mock_report()
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 0, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), work_dir / 'codegen', evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'rejected_missing_artifacts')

    def test_empty_artifact_rejected(self):
        """A generated .cpp file with 0 bytes must be rejected."""
        run_id = 'test-mock-empty-art'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        codegen_dir = work_dir / 'codegen'
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / 'model.cpp').write_bytes(b'')
        (codegen_dir / 'model.h').write_text('// non-empty\n')

        matlab_report = self._create_mock_report()
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 0, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), codegen_dir, evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'rejected_missing_artifacts')

    def test_license_failure_rejected(self):
        """If Real-Time_Workshop checkout fails, status must be rejected_license_failure."""
        run_id = 'test-mock-rtw-fail'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        codegen_dir = work_dir / 'codegen'
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / 'model.cpp').write_text('// non-empty\n')
        (codegen_dir / 'model.h').write_text('// non-empty\n')

        matlab_report = self._create_mock_report(
            status='license_failed',
            licenses_override={'Real_Time_Workshop': 0},
            failed_stage='license_verification',
        )
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 1, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), codegen_dir, evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'rejected_license_failure')

    def test_embedded_coder_feature_required_and_rejected_on_failure(self):
        """RTW_Embedded_Coder must be checked; if its checkout fails, must reject."""
        self.assertIn('RTW_Embedded_Coder', REQUIRED_LICENSES)
        run_id = 'test-mock-ec-fail'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        codegen_dir = work_dir / 'codegen'
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / 'model.cpp').write_text('// non-empty\n')
        (codegen_dir / 'model.h').write_text('// non-empty\n')

        matlab_report = self._create_mock_report(
            status='license_failed',
            licenses_override={'RTW_Embedded_Coder': 0},
            failed_stage='license_verification',
        )
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 1, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), codegen_dir, evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'rejected_license_failure')

    def test_slbuild_stage_missing_or_failed_rejected(self):
        """If slbuild stage failed, driver must reject even if status='generated' and files exist."""
        run_id = 'test-mock-slbuild-fail'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        codegen_dir = work_dir / 'codegen'
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / 'model.cpp').write_text('// non-empty\n')
        (codegen_dir / 'model.h').write_text('// non-empty\n')

        matlab_report = self._create_mock_report(status='generated', failed_stage='slbuild')
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 0, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), codegen_dir, evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'failed')
        self.assertFalse(summary['slbuild_ok'])

    def test_verify_solver_stage_failed_rejected(self):
        """If solver check failed, driver must reject."""
        run_id = 'test-mock-solver-fail'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        codegen_dir = work_dir / 'codegen'
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / 'model.cpp').write_text('// non-empty\n')
        (codegen_dir / 'model.h').write_text('// non-empty\n')

        matlab_report = self._create_mock_report(status='failed', failed_stage='verify_solver')
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 1, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), codegen_dir, evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'failed')
        self.assertFalse(summary['stages_ok'])

    def test_source_tampered_during_run_rejected(self):
        """If original source files are modified during run, post-check must reject."""
        run_id = 'test-mock-tampered-source'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        codegen_dir = work_dir / 'codegen'
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / 'model.cpp').write_text('// non-empty\n')
        (codegen_dir / 'model.h').write_text('// non-empty\n')

        (self.mock_source / 'Exp1_MinModelTemp.slx').write_bytes(b'modified in source dir')

        matlab_report = self._create_mock_report()
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 0, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, Path(prep['staged_dir']), codegen_dir, evidence_dir, exec_res)
        self.assertEqual(summary['status'], 'rejected_input_tampered')
        self.assertTrue(summary['source_tampered'])

    def test_staged_input_tampered_during_run_rejected(self):
        """If staged private inputs are modified while original sources are untouched, must reject."""
        run_id = 'test-mock-tampered-staged'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        staged_dir = Path(prep['staged_dir'])
        codegen_dir = work_dir / 'codegen'
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / 'model.cpp').write_text('// non-empty\n')
        (codegen_dir / 'model.h').write_text('// non-empty\n')

        (staged_dir / 'Exp1_MinModelTemp_init.m').write_text('% modified in staged\n')

        matlab_report = self._create_mock_report()
        (evidence_dir / 'codegen-report.json').write_text(json.dumps(matlab_report))

        exec_res = {'return_code': 0, 'timed_out': False, 'cleanup_unverified': False}
        summary = audit_and_finalize(self.mock_source, staged_dir, codegen_dir, evidence_dir, exec_res)

        self.assertEqual(summary['status'], 'rejected_input_tampered')
        self.assertFalse(summary['source_tampered'])
        self.assertTrue(summary['staged_tampered'])
        self.assertTrue((evidence_dir / 'post-staged-verification.json').is_file())

    def test_timeout_and_process_cleanup(self):
        """Timeout must terminate process tree and record cleanup status."""
        run_id = 'test-mock-timeout'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        staged_dir = Path(prep['staged_dir'])

        fake_matlab = self.base_temp / 'fake_matlab.exe'
        fake_matlab.write_bytes(b'fake binary')

        mock_proc = MagicMock()
        mock_proc.pid = 999999
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd='fake', timeout=1.0)

        with patch('subprocess.Popen', return_value=mock_proc), \
             patch.object(ProcessTracker, 'terminate', return_value=True) as mock_term:
            exec_res = execute_codegen(fake_matlab, staged_dir, work_dir, evidence_dir, timeout_seconds=1.0)
            mock_term.assert_called_once_with(timeout=15.0)

        self.assertTrue(exec_res['timed_out'])
        self.assertEqual(exec_res['return_code'], -1)
        self.assertFalse(exec_res['cleanup_unverified'])

    def test_execution_exception_preserves_evidence(self):
        """Unexpected execution exceptions must be recorded into command.json rather than dropped."""
        run_id = 'test-mock-exception'
        work_dir = self.work_root / run_id
        evidence_dir = self.evidence_root / run_id

        prep = prepare_run(self.mock_source, work_dir, evidence_dir, project_root=self.mock_project_root)
        staged_dir = Path(prep['staged_dir'])

        fake_matlab = self.base_temp / 'fake_matlab.exe'
        fake_matlab.write_bytes(b'fake binary')

        mock_proc = MagicMock()
        mock_proc.pid = 888888
        mock_proc.wait.side_effect = OSError("Simulated system pipe failure")

        with patch('subprocess.Popen', return_value=mock_proc), \
             patch.object(ProcessTracker, 'terminate', return_value=False):
            exec_res = execute_codegen(fake_matlab, staged_dir, work_dir, evidence_dir, timeout_seconds=1.0)

        self.assertIn("Simulated system pipe failure", exec_res['exec_error'])
        self.assertTrue(exec_res['cleanup_unverified'])
        command_json = json.loads((evidence_dir / 'command.json').read_text())
        self.assertIn('exec_error', command_json)


if __name__ == '__main__':
    unittest.main()
