"""Unit tests for standalone Linux e0 model build driver (tools/build_generated_e0.py).

Verifies evidence gates, source integrity, containment, dependency auditing,
and WSL compilation orchestration without invoking real MATLAB or UE.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools.build_generated_e0 import (
    COMPILER_FLAGS,
    DISALLOWED_DEP_SUBSTRINGS,
    EXCLUDED_BUILD_SOURCES,
    REQUIRED_BUILD_SOURCES,
    REQUIRED_EVIDENCE_FILES,
    REQUIRED_GENERATED_SOURCES,
    WslRunner,
    audit_ldd_output,
    build_and_evaluate,
    digest,
    to_wsl_path,
    validate_build_id,
    validate_evidence_containment,
    validate_wsl_build_dir,
    verify_external_prerequisites,
    verify_generation_evidence,
    write_json,
)
from tools.generate_model_e0 import REQUIRED_LICENSES, REQUIRED_STAGES


class TestBuildGeneratedE0(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_temp = Path(self.temp_dir.name)

        # Mock project root structure
        self.mock_root = self.base_temp / 'mock-wksim'
        self.mock_validation = self.mock_root / 'validation'
        self.mock_work = self.mock_root / 'work'
        self.mock_core = self.mock_root / 'Simulator/wksim_core'

        self.mock_validation.mkdir(parents=True, exist_ok=True)
        self.mock_work.mkdir(parents=True, exist_ok=True)
        self.mock_core.mkdir(parents=True, exist_ok=True)

        # Create mock model.cpp
        self.mock_wrapper = self.mock_core / 'model.cpp'
        self.mock_wrapper.write_text('// mock model.cpp wrapper\nextern "C" void* wk_model_create() { return nullptr; }\n', encoding='utf-8')

        # Create mock MathWorks include directory
        self.mock_include = self.base_temp / 'matlab-include'
        self.mock_include.mkdir(parents=True, exist_ok=True)
        (self.mock_include / 'rtw_continuous.h').write_text('// mock rtw_continuous.h\n', encoding='utf-8')
        (self.mock_include / 'rtw_solver.h').write_text('// mock rtw_solver.h\n', encoding='utf-8')

        # Setup mock generation run
        self.run_id = 'test-gen-run-01'
        self.gen_evidence_dir = self.mock_validation / 'codegen-e0' / self.run_id
        self.gen_evidence_dir.mkdir(parents=True, exist_ok=True)

        self.mock_codegen_folder = self.mock_work / 'codegen-e0' / self.run_id / 'codegen'
        self.mock_codegen_folder.mkdir(parents=True, exist_ok=True)
        self.gen_source_dir = self.mock_codegen_folder / 'Exp1_MinModelTemp_ert_rtw'
        self.gen_source_dir.mkdir(parents=True, exist_ok=True)

        self.mock_staged_dir = self.mock_work / 'codegen-e0' / self.run_id / 'staged-model'
        self.mock_staged_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.mock_staged_dir / 'codegen_config.json', {
            'codegen_folder': str(self.mock_codegen_folder),
            'cache_folder': str(self.mock_work / 'codegen-e0' / self.run_id / 'cache'),
        })

        # Populate mock command.json
        write_json(self.gen_evidence_dir / 'command.json', {
            'argv': ['matlab', '-batch', 'generate_model_e0'],
            'cwd': str(self.mock_staged_dir),
            'return_code': 0,
            'timed_out': False,
            'cleanup_unverified': False,
        })

        # Populate mock generated sources
        self.mock_gen_files = {
            'Exp1_MinModelTemp.cpp': '// mock Exp1_MinModelTemp.cpp\n',
            'Exp1_MinModelTemp.h': '// mock Exp1_MinModelTemp.h\n',
            'rtwtypes.h': '// mock rtwtypes.h\n',
            'ert_main.cpp': '// mock ert_main.cpp with main()\n',
        }
        sources_manifest = []
        for name, content in self.mock_gen_files.items():
            fpath = self.gen_source_dir / name
            fpath.write_text(content, encoding='utf-8')
            sources_manifest.append({
                'relative_path': f'Exp1_MinModelTemp_ert_rtw\\{name}',
                'sha256': digest(fpath),
                'size_bytes': fpath.stat().st_size,
                'is_empty': False,
            })

        write_json(self.gen_evidence_dir / 'generated-sources-manifest.json', {
            'total_files': 4,
            'sources': sources_manifest,
        })

        write_json(self.gen_evidence_dir / 'summary.json', {
            'status': 'generated',
            'matlab_return_code': 0,
            'stages_ok': True,
            'licenses_ok': True,
            'has_valid_artifacts': True,
            'source_tampered': False,
            'staged_tampered': False,
            'timed_out': False,
            'cleanup_unverified': False,
        })

        write_json(self.gen_evidence_dir / 'post-source-verification.json', [
            {'filename': 'Exp1_MinModelTemp.slx', 'unchanged': True, 'actual_sha256': 'mock_sha', 'expected_sha256': 'mock_sha'},
        ])
        write_json(self.gen_evidence_dir / 'post-staged-verification.json', [
            {'filename': 'Exp1_MinModelTemp.slx', 'unchanged': True, 'actual_sha256': 'mock_sha', 'expected_sha256': 'mock_sha'},
        ])
        write_json(self.gen_evidence_dir / 'codegen-report.json', {
            'status': 'generated',
            'stages': [{'name': s, 'status': 'ok'} for s in REQUIRED_STAGES],
            'licenses': {
                'test': {lic.replace('-', '_'): 1 for lic in REQUIRED_LICENSES},
                'checkout': {lic.replace('-', '_'): 1 for lic in REQUIRED_LICENSES},
            },
        })

        self.evidence_root = self.mock_validation

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validate_build_id_valid_and_invalid(self):
        """Test build_id accepts alphanumeric/hyphen/underscore and rejects traversal or illegal chars."""
        for good in ['build-01', 'run_02', 'BUILD123', 'a']:
            validate_build_id(good)

        for bad in ['../bad', 'run/01', 'run\\02', 'run.id', 'build:01', 'bad*id', '']:
            with self.assertRaises(ValueError):
                validate_build_id(bad)

    def test_validate_evidence_containment(self):
        """Test evidence directory containment constraints."""
        valid_dir = self.mock_validation / 'codegen-e0-build/run-01'
        validate_evidence_containment(valid_dir, project_root=self.mock_root)

        # Cannot equal validation root itself
        with self.assertRaises(ValueError):
            validate_evidence_containment(self.mock_validation, project_root=self.mock_root)

        # Cannot be outside validation
        outside = self.mock_root / 'work/codegen-e0-build/run-01'
        with self.assertRaises(ValueError):
            validate_evidence_containment(outside, project_root=self.mock_root)

        # Cannot reuse non-empty evidence directory
        valid_dir.mkdir(parents=True, exist_ok=True)
        (valid_dir / 'leftover.txt').write_text('leftover', encoding='utf-8')
        with self.assertRaises(ValueError):
            validate_evidence_containment(valid_dir, project_root=self.mock_root)

    def test_to_wsl_path(self):
        """Test Windows to WSL path translation."""
        self.assertEqual(to_wsl_path(Path('C:/Users/PC/Documents/wksim')), '/mnt/c/Users/PC/Documents/wksim')
        self.assertEqual(to_wsl_path(Path('D:/matlab/install date/include')), '/mnt/d/matlab/install date/include')

    def test_audit_ldd_output(self):
        """Test LDD audit cleanly identifies system libs vs prohibited vendor libraries."""
        clean_ldd = (
            "\tlinux-vdso.so.1 (0x00007fffddf6c000)\n"
            "\tlibstdc++.so.6 => /lib/x86_64-linux-gnu/libstdc++.so.6 (0x00007b8d32c00000)\n"
            "\tlibm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007b8d32b19000)\n"
            "\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007b8d32800000)\n"
            "\t/lib64/ld-linux-x86-64.so.2 (0x00007b8d32e8a000)\n"
            "\tlibgcc_s.so.1 => /lib/x86_64-linux-gnu/libgcc_s.so.1 (0x00007b8d32e38000)\n"
        )
        is_clean, deps, violations = audit_ldd_output(clean_ldd)
        self.assertTrue(is_clean)
        self.assertEqual(len(violations), 0)
        self.assertIn('libstdc++.so.6', deps)

        contaminated_ldd = (
            clean_ldd +
            "\tlibmwsl_services.so => /opt/matlab/bin/glnxa64/libmwsl_services.so (0x00007b8d30000000)\n"
        )
        is_clean2, deps2, violations2 = audit_ldd_output(contaminated_ldd)
        self.assertFalse(is_clean2)
        self.assertTrue(any('matlab' in v or 'libmw' in v for v in violations2))

    def test_verify_generation_evidence_success(self):
        """Test generation evidence passes verification when all hashes match and status is generated."""
        result = verify_generation_evidence(
            generation_evidence_dir=self.gen_evidence_dir,
            codegen_source_dir=self.gen_source_dir,
            project_root=self.mock_root,
        )
        self.assertEqual(result['generation_run_id'], self.run_id)
        self.assertIn('Exp1_MinModelTemp.cpp', result['verified_sources'])

    def test_verify_generation_evidence_status_not_generated(self):
        """Test verification rejects generation evidence with status != generated."""
        write_json(self.gen_evidence_dir / 'summary.json', {'status': 'failed'})
        with self.assertRaises(ValueError):
            verify_generation_evidence(
                generation_evidence_dir=self.gen_evidence_dir,
                codegen_source_dir=self.gen_source_dir,
                project_root=self.mock_root,
            )

    def test_verify_generation_evidence_source_tampered(self):
        """Test verification rejects generation evidence if source_tampered flag is set."""
        write_json(self.gen_evidence_dir / 'summary.json', {
            'status': 'generated',
            'matlab_return_code': 0,
            'stages_ok': True,
            'licenses_ok': True,
            'has_valid_artifacts': True,
            'source_tampered': True,
            'staged_tampered': False,
        })
        with self.assertRaises(ValueError):
            verify_generation_evidence(
                generation_evidence_dir=self.gen_evidence_dir,
                codegen_source_dir=self.gen_source_dir,
                project_root=self.mock_root,
            )

    def test_verify_generation_evidence_source_sha_mismatch(self):
        """Test verification detects altered generated source file and raises SHA mismatch error."""
        target_file = self.gen_source_dir / 'Exp1_MinModelTemp.cpp'
        target_file.write_text('// tampered source file\n', encoding='utf-8')
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(
                generation_evidence_dir=self.gen_evidence_dir,
                codegen_source_dir=self.gen_source_dir,
                project_root=self.mock_root,
            )
        self.assertIn('SHA mismatch', str(ctx.exception))

    def test_verify_external_prerequisites_missing_headers(self):
        """Test missing MathWorks headers raise FileNotFoundError."""
        (self.mock_include / 'rtw_continuous.h').unlink()
        with self.assertRaises(FileNotFoundError):
            verify_external_prerequisites(
                matlab_include_dir=self.mock_include,
                wrapper_source=self.mock_wrapper,
            )

    def test_verify_external_prerequisites_missing_wrapper(self):
        """Test missing model.cpp wrapper raises FileNotFoundError."""
        self.mock_wrapper.unlink()
        with self.assertRaises(FileNotFoundError):
            verify_external_prerequisites(
                matlab_include_dir=self.mock_include,
                wrapper_source=self.mock_wrapper,
            )

    def test_mock_wsl_build_and_evaluate_success_with_test(self):
        """Test end-to-end build workflow with mock WSL runner and execution probe."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0"

        # Track file sha256s
        file_hashes = {
            'Exp1_MinModelTemp.cpp': digest(self.gen_source_dir / 'Exp1_MinModelTemp.cpp'),
            'Exp1_MinModelTemp.h': digest(self.gen_source_dir / 'Exp1_MinModelTemp.h'),
            'rtwtypes.h': digest(self.gen_source_dir / 'rtwtypes.h'),
            'model.cpp': digest(self.mock_wrapper),
            'rtw_continuous.h': digest(self.mock_include / 'rtw_continuous.h'),
            'rtw_solver.h': digest(self.mock_include / 'rtw_solver.h'),
        }

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'cp ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd and 'libwksim_e0.so' not in cmd:
                # staged file checksum
                fname = Path(cmd.split()[-1].strip("'")).name
                h = file_hashes.get(fname, 'dummyhash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            if 'g++' in cmd and '-o' in cmd:
                # compilation
                return subprocess.CompletedProcess(cmd, 0, stdout='compiled ok', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' in cmd:
                # library stat
                return subprocess.CompletedProcess(cmd, 0, stdout="mock_lib_sha256\n87312\n", stderr='')
            if 'ldd ' in cmd:
                ldd_out = (
                    "\tlinux-vdso.so.1 (0x00007fffddf6c000)\n"
                    "\tlibstdc++.so.6 => /lib/x86_64-linux-gnu/libstdc++.so.6 (0x00007b8d32c00000)\n"
                    "\tlibm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007b8d32b19000)\n"
                    "\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007b8d32800000)\n"
                    "\t/lib64/ld-linux-x86-64.so.2 (0x00007b8d32e8a000)\n"
                    "\tlibgcc_s.so.1 => /lib/x86_64-linux-gnu/libgcc_s.so.1 (0x00007b8d32e38000)\n"
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=ldd_out, stderr='')
            if 'cat << ' in cmd:
                # deploy probe script
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'python3 ' in cmd and 'probe_runner.py' in cmd:
                probe_json = json.dumps({
                    'success': True,
                    'steps_evaluated': 100,
                    'step_size_seconds': 0.001,
                    'sim_time_seconds': 0.1,
                    'all_outputs_finite': True,
                    'non_finite_step': None,
                    'output_dimension': 120,
                    'copter_id': 1.0,
                    'vehicle_type': 3.0,
                })
                return subprocess.CompletedProcess(cmd, 0, stdout=probe_json + '\n', stderr='')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-build-mock-01'
        summary = build_and_evaluate(
            generation_evidence_dir=self.gen_evidence_dir,
            codegen_source_dir=self.gen_source_dir,
            matlab_include_dir=self.mock_include,
            wrapper_source=self.mock_wrapper,
            build_id=build_id,
            evidence_root=self.evidence_root,
            run_test=True,
            test_steps=100,
            project_root=self.mock_root,
            runner=mock_runner,
        )

        self.assertEqual(summary['status'], 'tested')
        self.assertEqual(summary['build_id'], build_id)
        self.assertTrue(summary['clean_runtime_deps'])
        self.assertTrue(summary['test_passed'])
        self.assertEqual(summary['steps_evaluated'], 100)
        self.assertTrue(summary['all_outputs_finite'])

        ev_dir = Path(summary['evidence_directory'])
        self.assertTrue((ev_dir / 'summary.json').is_file())
        self.assertTrue((ev_dir / 'build-manifest.json').is_file())
        self.assertTrue((ev_dir / 'command.json').is_file())
        self.assertTrue((ev_dir / 'build.stdout.log').is_file())
        self.assertTrue((ev_dir / 'build.stderr.log').is_file())
        self.assertTrue((ev_dir / 'ldd.txt').is_file())
        self.assertTrue((ev_dir / 'test-probe.json').is_file())

        manifest = json.loads((ev_dir / 'build-manifest.json').read_text(encoding='utf-8'))
        self.assertIn('ert_main.cpp', manifest['excluded_files'])
        self.assertEqual(len(manifest['staged_sources']), 6)

    def test_mock_wsl_compilation_failure_handling(self):
        """Test compiler failure logs output, writes failed summary and command.json, without unhandled exceptions."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ 11.4.0"

        file_hashes = {
            'Exp1_MinModelTemp.cpp': digest(self.gen_source_dir / 'Exp1_MinModelTemp.cpp'),
            'Exp1_MinModelTemp.h': digest(self.gen_source_dir / 'Exp1_MinModelTemp.h'),
            'rtwtypes.h': digest(self.gen_source_dir / 'rtwtypes.h'),
            'model.cpp': digest(self.mock_wrapper),
            'rtw_continuous.h': digest(self.mock_include / 'rtw_continuous.h'),
            'rtw_solver.h': digest(self.mock_include / 'rtw_solver.h'),
        }

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd or 'cp ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd and 'libwksim_e0.so' not in cmd:
                fname = Path(cmd.split()[-1].strip("'")).name
                h = file_hashes.get(fname, 'dummyhash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            if 'g++' in cmd and '-o' in cmd:
                return subprocess.CompletedProcess(cmd, 1, stdout='', stderr='syntax error in source')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-build-fail-01'
        summary = build_and_evaluate(
            generation_evidence_dir=self.gen_evidence_dir,
            codegen_source_dir=self.gen_source_dir,
            matlab_include_dir=self.mock_include,
            wrapper_source=self.mock_wrapper,
            build_id=build_id,
            evidence_root=self.evidence_root,
            run_test=False,
            project_root=self.mock_root,
            runner=mock_runner,
        )

        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['compiler_return_code'], 1)
        self.assertIn('syntax error', summary['error'])
        ev_dir = self.mock_validation / f'codegen-e0-build-{build_id}'
        self.assertTrue((ev_dir / 'summary.json').is_file())
        self.assertTrue((ev_dir / 'command.json').is_file())
        self.assertTrue((ev_dir / 'build.stderr.log').is_file())
        cmd_info = json.loads((ev_dir / 'command.json').read_text(encoding='utf-8'))
        self.assertEqual(cmd_info['return_code'], 1)

    def test_missing_evidence_files_rejected(self):
        """Test missing any of the 6 required evidence files raises FileNotFoundError."""
        for fname in REQUIRED_EVIDENCE_FILES:
            target = self.gen_evidence_dir / fname
            temp_backup = self.gen_evidence_dir / f"{fname}.bak"
            target.rename(temp_backup)
            try:
                with self.assertRaises(FileNotFoundError) as ctx:
                    verify_generation_evidence(
                        generation_evidence_dir=self.gen_evidence_dir,
                        codegen_source_dir=self.gen_source_dir,
                        project_root=self.mock_root,
                    )
                self.assertIn(fname, str(ctx.exception))
            finally:
                temp_backup.rename(target)

    def test_command_json_failure_conditions(self):
        """Test command.json non-zero return_code, timed_out, and cleanup_unverified are rejected."""
        base_cmd = {
            'argv': ['matlab'],
            'cwd': str(self.mock_staged_dir),
            'return_code': 0,
            'timed_out': False,
            'cleanup_unverified': False,
        }

        # Non-zero return_code
        bad_rc = dict(base_cmd, return_code=1)
        write_json(self.gen_evidence_dir / 'command.json', bad_rc)
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('return_code is 1', str(ctx.exception))

        # timed_out
        bad_to = dict(base_cmd, timed_out=True)
        write_json(self.gen_evidence_dir / 'command.json', bad_to)
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('timed_out', str(ctx.exception))

        # cleanup_unverified
        bad_cl = dict(base_cmd, cleanup_unverified=True)
        write_json(self.gen_evidence_dir / 'command.json', bad_cl)
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('cleanup_unverified', str(ctx.exception))

        # Restore valid
        write_json(self.gen_evidence_dir / 'command.json', base_cmd)

    def test_staged_codegen_config_binding(self):
        """Test binding between command.json cwd, codegen_config.json, and codegen_source_dir."""
        # Missing codegen_config.json
        cfg_file = self.mock_staged_dir / 'codegen_config.json'
        cfg_backup = self.mock_staged_dir / 'codegen_config.json.bak'
        cfg_file.rename(cfg_backup)
        try:
            with self.assertRaises(FileNotFoundError):
                verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        finally:
            cfg_backup.rename(cfg_file)

        # Mismatched codegen_source_dir override
        mismatched_dir = self.mock_work / 'other_codegen' / 'Exp1_MinModelTemp_ert_rtw'
        mismatched_dir.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, mismatched_dir, self.mock_root)
        self.assertIn('does not match bound staged codegen_config', str(ctx.exception))

    def test_summary_flags_rejected(self):
        """Test summary.json flags: status, return_code, stages_ok, licenses_ok, tampered, timed_out, cleanup."""
        base_summary = {
            'status': 'generated',
            'matlab_return_code': 0,
            'stages_ok': True,
            'licenses_ok': True,
            'has_valid_artifacts': True,
            'source_tampered': False,
            'staged_tampered': False,
            'timed_out': False,
            'cleanup_unverified': False,
        }

        bad_variants = [
            ({'status': 'failed'}, 'status'),
            ({'matlab_return_code': 1}, 'matlab_return_code'),
            ({'stages_ok': False}, 'stages_ok'),
            ({'licenses_ok': False}, 'licenses_ok'),
            ({'has_valid_artifacts': False}, 'has_valid_artifacts'),
            ({'source_tampered': True}, 'source_tampered'),
            ({'staged_tampered': True}, 'staged_tampered'),
            ({'timed_out': True}, 'timed_out'),
            ({'cleanup_unverified': True}, 'cleanup_unverified'),
        ]
        for patch_dict, token in bad_variants:
            cur = dict(base_summary, **patch_dict)
            write_json(self.gen_evidence_dir / 'summary.json', cur)
            with self.assertRaises(ValueError) as ctx:
                verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
            self.assertIn(token, str(ctx.exception))

        write_json(self.gen_evidence_dir / 'summary.json', base_summary)

    def test_post_verification_failures(self):
        """Test post-source and post-staged verification integrity failures."""
        # Empty post-source
        write_json(self.gen_evidence_dir / 'post-source-verification.json', [])
        with self.assertRaises(ValueError):
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)

        # Unchanged False in post-source
        write_json(self.gen_evidence_dir / 'post-source-verification.json', [
            {'filename': 'model.slx', 'unchanged': False, 'actual_sha256': 'a', 'expected_sha256': 'b'},
        ])
        with self.assertRaises(ValueError):
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)

        # Restore post-source
        write_json(self.gen_evidence_dir / 'post-source-verification.json', [
            {'filename': 'model.slx', 'unchanged': True, 'actual_sha256': 'a', 'expected_sha256': 'a'},
        ])

        # Empty post-staged
        write_json(self.gen_evidence_dir / 'post-staged-verification.json', [])
        with self.assertRaises(ValueError):
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)

        # Unchanged False in post-staged
        write_json(self.gen_evidence_dir / 'post-staged-verification.json', [
            {'filename': 'model.slx', 'unchanged': False, 'actual_sha256': 'a', 'expected_sha256': 'b'},
        ])
        with self.assertRaises(ValueError):
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)

        # Restore post-staged
        write_json(self.gen_evidence_dir / 'post-staged-verification.json', [
            {'filename': 'model.slx', 'unchanged': True, 'actual_sha256': 'a', 'expected_sha256': 'a'},
        ])

    def test_codegen_report_stages_and_licenses(self):
        """Test codegen-report.json stages completeness and licenses checkout validation."""
        base_report = {
            'status': 'generated',
            'stages': [{'name': s, 'status': 'ok'} for s in REQUIRED_STAGES],
            'licenses': {
                'test': {lic.replace('-', '_'): 1 for lic in REQUIRED_LICENSES},
                'checkout': {lic.replace('-', '_'): 1 for lic in REQUIRED_LICENSES},
            },
        }

        # Empty stages list
        bad_rep = dict(base_report, stages=[])
        write_json(self.gen_evidence_dir / 'codegen-report.json', bad_rep)
        with self.assertRaises(ValueError):
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)

        # Missing required stage
        bad_stages = [{'name': s, 'status': 'ok'} for s in REQUIRED_STAGES if s != 'slbuild']
        bad_rep = dict(base_report, stages=bad_stages)
        write_json(self.gen_evidence_dir / 'codegen-report.json', bad_rep)
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('slbuild', str(ctx.exception))

        # Failed stage
        bad_stages = [{'name': s, 'status': 'failed' if s == 'slbuild' else 'ok'} for s in REQUIRED_STAGES]
        bad_rep = dict(base_report, stages=bad_stages)
        write_json(self.gen_evidence_dir / 'codegen-report.json', bad_rep)
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('slbuild', str(ctx.exception))

        # License checkout failure
        bad_lic = {
            'test': {lic.replace('-', '_'): 1 for lic in REQUIRED_LICENSES},
            'checkout': {lic.replace('-', '_'): (0 if lic == 'SIMULINK' else 1) for lic in REQUIRED_LICENSES},
        }
        bad_rep = dict(base_report, licenses=bad_lic)
        write_json(self.gen_evidence_dir / 'codegen-report.json', bad_rep)
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('SIMULINK', str(ctx.exception))

        # Restore valid
        write_json(self.gen_evidence_dir / 'codegen-report.json', base_report)

    def test_manifest_path_traversal_and_duplicates(self):
        """Test manifest rejects traversal with '..', leading slashes, and duplicate basenames."""
        manifest_path = self.gen_evidence_dir / 'generated-sources-manifest.json'
        base_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

        # Traversal with '..'
        bad_sources = list(base_manifest['sources'])
        bad_sources.append({
            'relative_path': '..\\outside.cpp',
            'sha256': 'dummy',
            'size_bytes': 10,
        })
        write_json(manifest_path, {'total_files': len(bad_sources), 'sources': bad_sources})
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('traversal', str(ctx.exception))

        # Leading slash
        bad_sources = list(base_manifest['sources'])
        bad_sources.append({
            'relative_path': '/abs/outside.cpp',
            'sha256': 'dummy',
            'size_bytes': 10,
        })
        write_json(manifest_path, {'total_files': len(bad_sources), 'sources': bad_sources})
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('Absolute or leading-slash', str(ctx.exception))

        # Duplicate basename
        bad_sources = list(base_manifest['sources'])
        bad_sources.append({
            'relative_path': 'sub\\Exp1_MinModelTemp.cpp',
            'sha256': 'dummy',
            'size_bytes': 10,
        })
        write_json(manifest_path, {'total_files': len(bad_sources), 'sources': bad_sources})
        with self.assertRaises(ValueError) as ctx:
            verify_generation_evidence(self.gen_evidence_dir, self.gen_source_dir, self.mock_root)
        self.assertIn('Duplicate basename', str(ctx.exception))

        # Restore valid
        write_json(manifest_path, base_manifest)

    def test_wsl_build_dir_security(self):
        """Test validate_wsl_build_dir enforces /root/wksim-codegen-e0-build- pattern and rejects traversal/quotes."""
        valid_dirs = [
            '/root/wksim-codegen-e0-build-01',
            '/root/wksim-codegen-e0-build-short-cycle-01',
            '/root/wksim-codegen-e0-build-test_run_123',
        ]
        for vd in valid_dirs:
            validate_wsl_build_dir(vd)

        invalid_dirs = [
            '/root/wksim-codegen-e0-build-01/../escape',
            '/root/wksim-codegen-e0-build-01; rm -rf /',
            '/root/wksim-codegen-e0-build-01\nnewline',
            "/root/wksim-codegen-e0-build-01'quote",
            '/var/wksim-codegen-e0-build-01',
            '/root/other-prefix-build-01',
            '/root/wksim-codegen-e0-build-spaces not allowed',
        ]
        for inv in invalid_dirs:
            with self.assertRaises(ValueError):
                validate_wsl_build_dir(inv)

    def test_wsl_check_dir_symlink_and_non_empty(self):
        """Test WslRunner.check_dir_empty_or_new rejects symlinks and existing non-empty directories."""
        runner = WslRunner()

        with patch.object(runner, 'run_bash') as mock_bash:
            mock_bash.return_value = subprocess.CompletedProcess('cmd', 0, stdout='SYMLINK\n', stderr='')
            with self.assertRaises(ValueError) as ctx:
                runner.check_dir_empty_or_new('/root/wksim-codegen-e0-build-01')
            self.assertIn('symlink', str(ctx.exception))

        with patch.object(runner, 'run_bash') as mock_bash:
            mock_bash.return_value = subprocess.CompletedProcess('cmd', 0, stdout='NON_EMPTY\n', stderr='')
            with self.assertRaises(ValueError) as ctx:
                runner.check_dir_empty_or_new('/root/wksim-codegen-e0-build-01')
            self.assertIn('non-empty', str(ctx.exception))

        with patch.object(runner, 'run_bash') as mock_bash:
            mock_bash.return_value = subprocess.CompletedProcess('cmd', 0, stdout='OK\n', stderr='')
            runner.check_dir_empty_or_new('/root/wksim-codegen-e0-build-01')

    def test_ldd_audit_missing_dependency(self):
        """Test ldd audit flags 'not found' dynamic dependencies."""
        missing_dep_ldd = (
            "\tlinux-vdso.so.1 (0x00007fffddf6c000)\n"
            "\tlibstdc++.so.6 => /lib/x86_64-linux-gnu/libstdc++.so.6 (0x00007b8d32c00000)\n"
            "\tlibcustom.so.1 => not found\n"
        )
        is_clean, deps, violations = audit_ldd_output(missing_dep_ldd)
        self.assertFalse(is_clean)
        self.assertTrue(any('not found' in v for v in violations))

    def test_pre_compilation_staged_integrity_failure(self):
        """Test pre-compilation integrity check in WSL catches staged file alteration."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ 11.4.0"

        file_hashes = {
            'Exp1_MinModelTemp.cpp': digest(self.gen_source_dir / 'Exp1_MinModelTemp.cpp'),
            'Exp1_MinModelTemp.h': digest(self.gen_source_dir / 'Exp1_MinModelTemp.h'),
            'rtwtypes.h': digest(self.gen_source_dir / 'rtwtypes.h'),
            'model.cpp': digest(self.mock_wrapper),
            'rtw_continuous.h': digest(self.mock_include / 'rtw_continuous.h'),
            'rtw_solver.h': digest(self.mock_include / 'rtw_solver.h'),
        }

        call_count = {}

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd or 'cp ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd and 'libwksim_e0.so' not in cmd:
                fname = Path(cmd.split()[-1].strip("'")).name
                call_count[fname] = call_count.get(fname, 0) + 1
                # On second check (pre-compilation), tamper Exp1_MinModelTemp.cpp hash
                if call_count[fname] > 1 and fname == 'Exp1_MinModelTemp.cpp':
                    return subprocess.CompletedProcess(cmd, 0, stdout="tampered_hash  path\n", stderr='')
                h = file_hashes.get(fname, 'dummyhash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-build-tamper-01'
        with self.assertRaises(RuntimeError) as ctx:
            build_and_evaluate(
                generation_evidence_dir=self.gen_evidence_dir,
                codegen_source_dir=self.gen_source_dir,
                matlab_include_dir=self.mock_include,
                wrapper_source=self.mock_wrapper,
                build_id=build_id,
                evidence_root=self.evidence_root,
                run_test=False,
                project_root=self.mock_root,
                runner=mock_runner,
            )
        self.assertIn('Pre-compilation integrity verification failed', str(ctx.exception))

    def test_ldd_violations_abort_compilation_run(self):
        """Test build aborts and writes failed summary/command.json when ldd audit fails."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ 11.4.0"

        file_hashes = {
            'Exp1_MinModelTemp.cpp': digest(self.gen_source_dir / 'Exp1_MinModelTemp.cpp'),
            'Exp1_MinModelTemp.h': digest(self.gen_source_dir / 'Exp1_MinModelTemp.h'),
            'rtwtypes.h': digest(self.gen_source_dir / 'rtwtypes.h'),
            'model.cpp': digest(self.mock_wrapper),
            'rtw_continuous.h': digest(self.mock_include / 'rtw_continuous.h'),
            'rtw_solver.h': digest(self.mock_include / 'rtw_solver.h'),
        }

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd or 'cp ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd and 'libwksim_e0.so' not in cmd:
                fname = Path(cmd.split()[-1].strip("'")).name
                h = file_hashes.get(fname, 'dummyhash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            if 'g++' in cmd and '-o' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='compiled ok', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mock_lib_sha256\n87312\n", stderr='')
            if 'ldd ' in cmd:
                ldd_out = "\tlibmwsl_services.so => /opt/matlab/bin/libmwsl_services.so (0x1234)\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=ldd_out, stderr='')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-build-ldd-fail-01'
        summary = build_and_evaluate(
            generation_evidence_dir=self.gen_evidence_dir,
            codegen_source_dir=self.gen_source_dir,
            matlab_include_dir=self.mock_include,
            wrapper_source=self.mock_wrapper,
            build_id=build_id,
            evidence_root=self.evidence_root,
            run_test=False,
            project_root=self.mock_root,
            runner=mock_runner,
        )

        self.assertEqual(summary['status'], 'failed')
        self.assertFalse(summary['clean_runtime_deps'])
        ev_dir = self.mock_validation / f'codegen-e0-build-{build_id}'
        self.assertTrue((ev_dir / 'summary.json').is_file())
        self.assertTrue((ev_dir / 'command.json').is_file())
        cmd_info = json.loads((ev_dir / 'command.json').read_text(encoding='utf-8'))
        self.assertEqual(cmd_info['return_code'], 1)

    def test_probe_failure_preserves_summary(self):
        """Test probe execution failure writes test_failed summary and command.json without unhandled exception."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ 11.4.0"

        file_hashes = {
            'Exp1_MinModelTemp.cpp': digest(self.gen_source_dir / 'Exp1_MinModelTemp.cpp'),
            'Exp1_MinModelTemp.h': digest(self.gen_source_dir / 'Exp1_MinModelTemp.h'),
            'rtwtypes.h': digest(self.gen_source_dir / 'rtwtypes.h'),
            'model.cpp': digest(self.mock_wrapper),
            'rtw_continuous.h': digest(self.mock_include / 'rtw_continuous.h'),
            'rtw_solver.h': digest(self.mock_include / 'rtw_solver.h'),
        }

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd or 'cp ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd and 'libwksim_e0.so' not in cmd:
                fname = Path(cmd.split()[-1].strip("'")).name
                h = file_hashes.get(fname, 'dummyhash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            if 'g++' in cmd and '-o' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='compiled ok', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mock_lib_sha256\n87312\n", stderr='')
            if 'ldd ' in cmd:
                ldd_out = "\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1234)\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=ldd_out, stderr='')
            if 'cat << ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'python3 ' in cmd and 'probe_runner.py' in cmd:
                probe_fail = json.dumps({
                    'success': False,
                    'error': 'Clock desync at step 5: sim_time=0.005, expected=0.0051',
                    'step': 5,
                })
                return subprocess.CompletedProcess(cmd, 1, stdout=probe_fail + '\n', stderr='probe error')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-build-probe-fail-01'
        summary = build_and_evaluate(
            generation_evidence_dir=self.gen_evidence_dir,
            codegen_source_dir=self.gen_source_dir,
            matlab_include_dir=self.mock_include,
            wrapper_source=self.mock_wrapper,
            build_id=build_id,
            evidence_root=self.evidence_root,
            run_test=True,
            test_steps=100,
            project_root=self.mock_root,
            runner=mock_runner,
        )

        self.assertEqual(summary['status'], 'test_failed')
        self.assertFalse(summary['test_passed'])
        self.assertIn('Clock desync', summary['error'])
        ev_dir = self.mock_validation / f'codegen-e0-build-{build_id}'
        self.assertTrue((ev_dir / 'summary.json').is_file())
        self.assertTrue((ev_dir / 'test-probe.json').is_file())
        self.assertTrue((ev_dir / 'command.json').is_file())
        cmd_info = json.loads((ev_dir / 'command.json').read_text(encoding='utf-8'))
        self.assertEqual(cmd_info['return_code'], 1)


class CommandLineEntryTests(unittest.TestCase):
    def test_direct_help_works_outside_repository_without_pythonpath(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            script=Path(__file__).resolve().parents[1]/'tools/build_generated_e0.py'
            result=subprocess.run([sys.executable,'-I',str(script),'--help'],cwd=directory,
                capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('--generation-dir',result.stdout)


if __name__ == '__main__':
    unittest.main()
