"""Unit tests for standalone Linux major model recorder driver (tools/build_generated_e0_major.py).

Verifies source instrumentation invariants, WSL directory security, dependency auditing,
record orchestration, and post-step parity verification without executing real MATLAB or UE.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools.build_generated_e0 import (
    WslRunner,
    digest,
    write_json,
)
from tools.build_generated_e0_major import (
    CPP_11_8_SHA256,
    DECLARATION,
    DEFAULT_POST_REFERENCE_SOURCE,
    EXPECTED_INSERTION_LINE,
    HOOK,
    INCLUDE,
    NEXT_CONTEXT,
    OUTPUT_END,
    PATCHED_CPP_11_8_SHA256,
    build_and_record,
    check_parity,
    instrument,
    validate_and_create_staging_dir,
    validate_wsl_major_dir,
    verify_reference_artifact,
)
from tools.generate_model_e0 import REQUIRED_LICENSES, REQUIRED_STAGES


class TestGeneratedE0Major(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_temp = Path(self.temp_dir.name)

        # Mock project root structure
        self.mock_root = self.base_temp / 'mock-wksim'
        self.mock_validation = self.mock_root / 'validation'
        self.mock_work = self.mock_root / 'work'
        self.mock_tools = self.mock_root / 'tools'

        self.mock_validation.mkdir(parents=True, exist_ok=True)
        self.mock_work.mkdir(parents=True, exist_ok=True)
        self.mock_tools.mkdir(parents=True, exist_ok=True)

        # Mock recorder source
        self.mock_recorder_source = self.mock_tools / 'major_model_recorder.cpp'
        self.mock_recorder_source.write_text('// mock recorder source\nint main() { return 0; }\n', encoding='utf-8')

        # Mock MathWorks include directory
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

        write_json(self.gen_evidence_dir / 'command.json', {
            'argv': ['matlab', '-batch', 'generate_model_e0'],
            'cwd': str(self.mock_staged_dir),
            'return_code': 0,
            'timed_out': False,
            'cleanup_unverified': False,
        })

        # Synthesize mock Exp1_MinModelTemp.cpp with exact line boundary
        prefix_lines = [f'// line {i+1}\r\n'.encode('ascii') for i in range(18)]
        include_line = INCLUDE
        middle_lines = [f'// line {i+20}\r\n'.encode('ascii') for i in range(7919 - 20 - 1)]
        target_context = OUTPUT_END + NEXT_CONTEXT
        suffix_lines = [f'// line {i+7924}\r\n'.encode('ascii') for i in range(100)]
        self.mock_cpp_bytes = b''.join(prefix_lines) + include_line + b''.join(middle_lines) + target_context + b''.join(suffix_lines)
        self.mock_cpp_sha = hashlib.sha256(self.mock_cpp_bytes).hexdigest()

        # Write generated sources
        (self.gen_source_dir / 'Exp1_MinModelTemp.cpp').write_bytes(self.mock_cpp_bytes)
        (self.gen_source_dir / 'Exp1_MinModelTemp.h').write_text('// mock Exp1_MinModelTemp.h\n', encoding='utf-8')
        (self.gen_source_dir / 'rtwtypes.h').write_text('// mock rtwtypes.h\n', encoding='utf-8')
        (self.gen_source_dir / 'ert_main.cpp').write_text('// mock ert_main.cpp\n', encoding='utf-8')

        sources_manifest = [
            {'relative_path': f'Exp1_MinModelTemp_ert_rtw\\{name}', 'sha256': digest(self.gen_source_dir / name), 'size_bytes': (self.gen_source_dir / name).stat().st_size}
            for name in ('Exp1_MinModelTemp.cpp', 'Exp1_MinModelTemp.h', 'rtwtypes.h', 'ert_main.cpp')
        ]
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
            {'filename': 'Exp1_MinModelTemp.slx', 'unchanged': True, 'actual_sha256': 'a', 'expected_sha256': 'a'},
        ])
        write_json(self.gen_evidence_dir / 'post-staged-verification.json', [
            {'filename': 'Exp1_MinModelTemp.slx', 'unchanged': True, 'actual_sha256': 'a', 'expected_sha256': 'a'},
        ])
        write_json(self.gen_evidence_dir / 'codegen-report.json', {
            'status': 'generated',
            'stages': [{'name': s, 'status': 'ok'} for s in REQUIRED_STAGES],
            'licenses': {
                'test': {lic.replace('-', '_'): 1 for lic in REQUIRED_LICENSES},
                'checkout': {lic.replace('-', '_'): 1 for lic in REQUIRED_LICENSES},
            },
        })

        # Create mock 501-row input CSV
        self.mock_csv = self.mock_validation / 'mock_input.csv'
        header = "k,time_s" + "".join(f",inPWMs{i}" for i in range(16)) + "".join(f",TerrainIn15d{i}" for i in range(15)) + "\n"
        rows = [header]
        for k in range(501):
            t = k * 0.001
            row_str = f"{k},{t:.3f}" + ",0" * 31 + "\n"
            rows.append(row_str)
        self.mock_csv.write_text("".join(rows), encoding='ascii')

        # Setup mock reference manifest
        self.mock_ref_manifest_dir = self.mock_validation / 'codegen-e0-build-mock-ref'
        self.mock_ref_manifest_dir.mkdir(parents=True, exist_ok=True)
        self.mock_ref_manifest = self.mock_ref_manifest_dir / 'build-manifest.json'
        self.mock_ref_so_sha = '7da6853201b89238c273f2e1360ad21fe479e267d0ed08cf3500f98bf535505e'
        write_json(self.mock_ref_manifest, {
            'build_id': 'mock-ref-01',
            'generation_run_id': self.run_id,
            'staged_sources': {
                'Exp1_MinModelTemp.cpp': {'sha256': self.mock_cpp_sha}
            },
            'output_library': {
                'filename': 'mock_ref.so',
                'sha256': self.mock_ref_so_sha,
            }
        })

        self.file_hashes = {
            'Exp1_MinModelTemp.original.cpp': self.mock_cpp_sha,
            'Exp1_MinModelTemp.h': digest(self.gen_source_dir / 'Exp1_MinModelTemp.h'),
            'rtwtypes.h': digest(self.gen_source_dir / 'rtwtypes.h'),
            'rtw_continuous.h': digest(self.mock_include / 'rtw_continuous.h'),
            'rtw_solver.h': digest(self.mock_include / 'rtw_solver.h'),
            'major_model_recorder.cpp': digest(self.mock_recorder_source),
            'generated_e0_post_reference.cpp': digest(DEFAULT_POST_REFERENCE_SOURCE) if DEFAULT_POST_REFERENCE_SOURCE.is_file() else 'mock_post_ref',
        }

        self.evidence_root = self.mock_validation

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_instrument_success_and_invariants(self):
        """Test instrumentation accurately places callback at line 7919 and satisfies round-trip reversion."""
        patched = instrument(self.mock_cpp_bytes, expected_sha=self.mock_cpp_sha)
        self.assertIn(b'wk_capture_major', patched)
        self.assertIn(DECLARATION, patched)
        self.assertIn(HOOK, patched)

        # Invariant: Reverting declaration and hook yields identical original bytes
        reverted = patched.replace(DECLARATION, b'', 1).replace(HOOK, b'', 1)
        self.assertEqual(reverted, self.mock_cpp_bytes)

    def test_instrument_unreviewed_sha_rejected(self):
        """Test instrument raises ValueError if source SHA does not match expected."""
        tampered = self.mock_cpp_bytes + b'\r\n// trailing comment'
        with self.assertRaises(ValueError) as ctx:
            instrument(tampered, expected_sha=self.mock_cpp_sha)
        self.assertIn('Unreviewed generated CPP SHA256', str(ctx.exception))

    def test_instrument_non_unique_or_missing_context_rejected(self):
        """Test instrument rejects missing or non-unique insertion context."""
        # Missing context
        missing = self.mock_cpp_bytes.replace(OUTPUT_END, b'')
        with self.assertRaises(ValueError):
            instrument(missing, expected_sha=hashlib.sha256(missing).hexdigest())

        # Duplicate context
        dup = self.mock_cpp_bytes.replace(OUTPUT_END, OUTPUT_END + OUTPUT_END)
        with self.assertRaises(ValueError):
            instrument(dup, expected_sha=hashlib.sha256(dup).hexdigest())

    def test_instrument_line_boundary_moved_rejected(self):
        """Test instrument rejects source file if insertion context line boundary shifted from 7919."""
        shifted = b'// extra line\r\n' + self.mock_cpp_bytes
        with self.assertRaises(ValueError) as ctx:
            instrument(shifted, expected_sha=hashlib.sha256(shifted).hexdigest())
        self.assertIn('Reviewed root output boundary moved', str(ctx.exception))

    def test_instrument_already_patched_rejected(self):
        """Test instrument rejects source file if wk_capture_major is already present."""
        already = self.mock_cpp_bytes.replace(b'// line 1\r\n', b'// wk_capture_major\r\n')
        with self.assertRaises(ValueError) as ctx:
            instrument(already, expected_sha=hashlib.sha256(already).hexdigest())
        self.assertIn('already contains wk_capture_major', str(ctx.exception))

    def test_validate_wsl_major_dir(self):
        """Test validate_wsl_major_dir enforces ^/root/wksim-e0-major-[a-zA-Z0-9_-]+$."""
        valid_dirs = [
            '/root/wksim-e0-major-01',
            '/root/wksim-e0-major-short-cycle-01',
            '/root/wksim-e0-major-test_run_123',
        ]
        for vd in valid_dirs:
            validate_wsl_major_dir(vd)

        invalid_dirs = [
            '/root/wksim-e0-major-01/../escape',
            '/root/wksim-e0-major-01; rm -rf /',
            '/root/wksim-e0-major-01\nnewline',
            "/root/wksim-e0-major-01'quote",
            '/var/wksim-e0-major-01',
            '/root/wksim-codegen-e0-build-01',
            '/root/wksim-e0-major-has spaces',
        ]
        for inv in invalid_dirs:
            with self.assertRaises(ValueError):
                validate_wsl_major_dir(inv)

    def test_mock_build_and_record_workflow_with_parity(self):
        """Test end-to-end major build and record workflow with mock WSL runner and parity check."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0"

        # Mock file hashes
        file_hashes = {
            'Exp1_MinModelTemp.original.cpp': self.mock_cpp_sha,
            'Exp1_MinModelTemp.h': digest(self.gen_source_dir / 'Exp1_MinModelTemp.h'),
            'rtwtypes.h': digest(self.gen_source_dir / 'rtwtypes.h'),
            'rtw_continuous.h': digest(self.mock_include / 'rtw_continuous.h'),
            'rtw_solver.h': digest(self.mock_include / 'rtw_solver.h'),
            'major_model_recorder.cpp': digest(self.mock_recorder_source),
            'generated_e0_post_reference.cpp': digest(DEFAULT_POST_REFERENCE_SOURCE) if DEFAULT_POST_REFERENCE_SOURCE.is_file() else 'mock_post_ref',
        }

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd or 'cp ' in cmd or 'cat << ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mock_exe_sha256\n123456\n", stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd:
                if 'mock_ref.so' in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout=f"{self.mock_ref_so_sha}  /root/mock_ref.so\n", stderr='')
                fname = Path(cmd.split()[-1].strip("'")).name
                if fname == 'Exp1_MinModelTemp.cpp':
                    patched_raw = instrument(self.mock_cpp_bytes, expected_sha=self.mock_cpp_sha)
                    h = hashlib.sha256(patched_raw).hexdigest()
                elif fname == 'Exp1_MinModelTemp.original.cpp':
                    h = self.mock_cpp_sha
                elif fname == 'major_model_recorder.cpp':
                    h = digest(self.mock_recorder_source)
                else:
                    h = file_hashes.get(fname, 'mock_hash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            if 'g++' in cmd and '-o' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='compiled ok', stderr='')
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
            if '--validate-input' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='{"status":"input_valid","rows":501}\n', stderr='')
            if '--record' in cmd:
                if 'generated_e0_post_reference' in cmd:
                    lines = ['{"schema_version":1,"kind":"post_reference_start"}']
                    for k in range(501):
                        lines.append(json.dumps({
                            "schema_version": 1,
                            "kind": "post_reference_sample",
                            "k": k,
                            "call_number": k + 1,
                            "input_time_s": k * 0.001,
                            "engine_before_s": k * 0.001,
                            "engine_after_s": (k + 1) * 0.001,
                            "inPWMs": [0.0]*16,
                            "TerrainIn15d": [0.0]*15,
                            "post_step_api": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                            "step_status": "complete"
                        }))
                    lines.append('{"schema_version":1,"kind":"post_reference_end","status":"complete","attempted_calls":501,"returned_calls":501,"emitted_samples":501,"engine_end_s":0.501,"comparison_end_s":0.500}')
                    return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(lines) + "\n", stderr='')
                else:
                    lines = ['{"schema_version":1,"kind":"major_recorder_start"}']
                    for k in range(501):
                        lines.append(json.dumps({
                            "schema_version": 1,
                            "kind": "major_recorder_sample",
                            "k": k,
                            "call_number": k + 1,
                            "input_time_s": k * 0.001,
                            "engine_before_s": k * 0.001,
                            "engine_after_s": (k + 1) * 0.001,
                            "major_capture_count": 1,
                            "inPWMs": [0.0]*16,
                            "TerrainIn15d": [0.0]*15,
                            "major_root_outputs": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                            "post_step_api": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                            "step_status": "complete"
                        }))
                    lines.append('{"schema_version":1,"kind":"major_recorder_end","status":"complete","attempted_calls":501,"returned_calls":501,"emitted_samples":501,"engine_end_s":0.501,"comparison_end_s":0.500}')
                    return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(lines) + "\n", stderr='')
            if 'python3' in cmd and 'parity_checker.py' in cmd:
                parity_res = json.dumps({
                    'success': True,
                    'steps_checked': 501,
                    'dimensions_checked': 120,
                    'total_values_checked': 501 * 120,
                    'max_discrepancy': 0.0,
                    'discrepancies_count': 0,
                    'sample_discrepancies': [],
                    'error': None
                })
                return subprocess.CompletedProcess(cmd, 0, stdout=parity_res + '\n', stderr='')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-major-01'
        with patch('tools.build_generated_e0_major.CPP_11_8_SHA256', self.mock_cpp_sha):
            summary = build_and_record(
                generation_evidence_dir=self.gen_evidence_dir,
                codegen_source_dir=self.gen_source_dir,
                matlab_include_dir=self.mock_include,
                recorder_source=self.mock_recorder_source,
                build_id=build_id,
                evidence_root=self.evidence_root,
                record_input=self.mock_csv,
                reference_lib='/root/mock_ref.so',
                reference_manifest=self.mock_ref_manifest,
                verify_parity=True,
                project_root=self.mock_root,
                runner=mock_runner,
            )

        self.assertEqual(summary['status'], 'verified')
        self.assertTrue(summary['clean_runtime_deps'])
        self.assertTrue(summary['parity_verified'])
        self.assertEqual(summary['max_discrepancy'], 0.0)

        ev_dir = Path(summary['evidence_directory'])
        self.assertTrue((ev_dir / 'summary.json').is_file())
        self.assertTrue((ev_dir / 'build-manifest.json').is_file())
        self.assertTrue((ev_dir / 'command.json').is_file())
        self.assertTrue((ev_dir / 'patch-recipe.json').is_file())
        self.assertTrue((ev_dir / 'record.jsonl').is_file())
        self.assertTrue((ev_dir / 'post_reference.jsonl').is_file())
        self.assertTrue((ev_dir / 'parity-verification.json').is_file())
        self.assertTrue((ev_dir / 'ldd.txt').is_file())
        self.assertTrue((ev_dir / 'ref_ldd.txt').is_file())
        self.assertEqual(summary['reference_executable']['executable_name'], 'generated_e0_post_reference')

        recipe = json.loads((ev_dir / 'patch-recipe.json').read_text(encoding='utf-8'))
        self.assertEqual(recipe['insertion_line'], 7919)
        self.assertTrue(recipe['reversion_verified'])
        self.assertFalse(recipe['equations_modified'])

    def test_compilation_failure_preserves_logs_and_summary(self):
        """Test compiler error returns failed summary and preserves command and error logs."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ 11.4.0"

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd or 'cp ' in cmd or 'cat << ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd:
                fname = Path(cmd.split()[-1].strip("'")).name
                if fname == 'Exp1_MinModelTemp.cpp':
                    patched_raw = instrument(self.mock_cpp_bytes, expected_sha=self.mock_cpp_sha)
                    h = hashlib.sha256(patched_raw).hexdigest()
                else:
                    h = self.file_hashes.get(fname, 'mock_hash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            if 'g++' in cmd and '-o' in cmd:
                return subprocess.CompletedProcess(cmd, 1, stdout='', stderr='g++ error: syntax error')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-major-fail-01'
        with patch('tools.build_generated_e0_major.CPP_11_8_SHA256', self.mock_cpp_sha):
            summary = build_and_record(
                generation_evidence_dir=self.gen_evidence_dir,
                codegen_source_dir=self.gen_source_dir,
                matlab_include_dir=self.mock_include,
                recorder_source=self.mock_recorder_source,
                build_id=build_id,
                evidence_root=self.evidence_root,
                project_root=self.mock_root,
                runner=mock_runner,
            )

        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['compiler_return_code'], 1)
        self.assertIn('syntax error', summary['error'])
        ev_dir = self.mock_validation / f'e0-major-recorder-{build_id}'
        self.assertTrue((ev_dir / 'summary.json').is_file())
        self.assertTrue((ev_dir / 'command.json').is_file())
        self.assertTrue((ev_dir / 'build.stderr.log').is_file())

    def test_parity_discrepancy_fails_cleanly(self):
        """Test parity discrepancy causes parity_failed status without relaxing tolerance."""
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.get_toolchain_version.return_value = "g++ 11.4.0"

        def mock_bash(cmd, timeout=120.0):
            if 'if [ -L ' in cmd or 'if [ -d ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='OK\n', stderr='')
            if 'mkdir -p' in cmd or 'cp ' in cmd or 'cat << ' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mock_exe_sha256\n123456\n", stderr='')
            if 'sha256sum' in cmd and 'stat -c %s' not in cmd:
                if 'mock_ref.so' in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout=f"{self.mock_ref_so_sha}  /root/mock_ref.so\n", stderr='')
                fname = Path(cmd.split()[-1].strip("'")).name
                if fname == 'Exp1_MinModelTemp.cpp':
                    patched_raw = instrument(self.mock_cpp_bytes, expected_sha=self.mock_cpp_sha)
                    h = hashlib.sha256(patched_raw).hexdigest()
                else:
                    h = self.file_hashes.get(fname, 'mock_hash')
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{h}  path\n", stderr='')
            if 'g++' in cmd and '-o' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='compiled ok', stderr='')
            if 'ldd ' in cmd:
                ldd_out = "\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1234)\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=ldd_out, stderr='')
            if '--validate-input' in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout='{"status":"input_valid","rows":501}\n', stderr='')
            if '--record' in cmd:
                if 'generated_e0_post_reference' in cmd:
                    lines = ['{"schema_version":1,"kind":"post_reference_start"}']
                    for k in range(501):
                        lines.append(json.dumps({
                            "schema_version": 1,
                            "kind": "post_reference_sample",
                            "k": k,
                            "call_number": k + 1,
                            "input_time_s": k * 0.001,
                            "engine_before_s": k * 0.001,
                            "engine_after_s": (k + 1) * 0.001,
                            "inPWMs": [0.0]*16,
                            "TerrainIn15d": [0.0]*15,
                            "post_step_api": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                            "step_status": "complete"
                        }))
                    lines.append('{"schema_version":1,"kind":"post_reference_end","status":"complete","attempted_calls":501,"returned_calls":501,"emitted_samples":501,"engine_end_s":0.501,"comparison_end_s":0.500}')
                    return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(lines) + "\n", stderr='')
                else:
                    lines = ['{"schema_version":1,"kind":"major_recorder_start"}']
                    for k in range(501):
                        lines.append(json.dumps({
                            "schema_version": 1,
                            "kind": "major_recorder_sample",
                            "k": k,
                            "call_number": k + 1,
                            "input_time_s": k * 0.001,
                            "engine_before_s": k * 0.001,
                            "engine_after_s": (k + 1) * 0.001,
                            "major_capture_count": 1,
                            "inPWMs": [0.0]*16,
                            "TerrainIn15d": [0.0]*15,
                            "major_root_outputs": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                            "post_step_api": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                            "step_status": "complete"
                        }))
                    lines.append('{"schema_version":1,"kind":"major_recorder_end","status":"complete","attempted_calls":501,"returned_calls":501,"emitted_samples":501,"engine_end_s":0.501,"comparison_end_s":0.500}')
                    return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(lines) + "\n", stderr='')
            if 'python3' in cmd and 'parity_checker.py' in cmd:
                parity_res = json.dumps({
                    'success': False,
                    'steps_checked': 501,
                    'dimensions_checked': 120,
                    'total_values_checked': 501 * 120,
                    'max_discrepancy': 0.0012,
                    'discrepancies_count': 1,
                    'sample_discrepancies': [{'k': 10, 'dim': 5, 'ref_val': 1.0, 'rec_val': 1.0012, 'abs_diff': 0.0012}],
                    'error': 'Found 1 discrepancies between major recorder post_step_api and reference library'
                })
                return subprocess.CompletedProcess(cmd, 1, stdout=parity_res + '\n', stderr='parity error')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        mock_runner.run_bash.side_effect = mock_bash

        build_id = 'test-major-parity-fail-01'
        with patch('tools.build_generated_e0_major.CPP_11_8_SHA256', self.mock_cpp_sha):
            summary = build_and_record(
                generation_evidence_dir=self.gen_evidence_dir,
                codegen_source_dir=self.gen_source_dir,
                matlab_include_dir=self.mock_include,
                recorder_source=self.mock_recorder_source,
                build_id=build_id,
                evidence_root=self.evidence_root,
                record_input=self.mock_csv,
                reference_lib='/root/mock_ref.so',
                reference_manifest=self.mock_ref_manifest,
                verify_parity=True,
                project_root=self.mock_root,
                runner=mock_runner,
            )

        self.assertEqual(summary['status'], 'parity_failed')
        self.assertFalse(summary['parity_verified'])
        self.assertEqual(summary['max_discrepancy'], 0.0012)
        self.assertIn('discrepancies', summary['error'])
        ev_dir = self.mock_validation / f'e0-major-recorder-{build_id}'
        self.assertTrue((ev_dir / 'parity-verification.json').is_file())

    def test_missing_prerequisites(self):
        """Test missing MathWorks headers or recorder source raises FileNotFoundError."""
        with patch('tools.build_generated_e0_major.CPP_11_8_SHA256', self.mock_cpp_sha):
            # Missing header
            (self.mock_include / 'rtw_continuous.h').unlink()
            with self.assertRaises(FileNotFoundError):
                build_and_record(
                    generation_evidence_dir=self.gen_evidence_dir,
                    codegen_source_dir=self.gen_source_dir,
                    matlab_include_dir=self.mock_include,
                    recorder_source=self.mock_recorder_source,
                    evidence_root=self.evidence_root,
                    project_root=self.mock_root,
                )

            # Restore header and unlink recorder source
            (self.mock_include / 'rtw_continuous.h').write_text('// header', encoding='utf-8')
            self.mock_recorder_source.unlink()
            with self.assertRaises(FileNotFoundError):
                build_and_record(
                    generation_evidence_dir=self.gen_evidence_dir,
                    codegen_source_dir=self.gen_source_dir,
                    matlab_include_dir=self.mock_include,
                    recorder_source=self.mock_recorder_source,
                    evidence_root=self.evidence_root,
                    project_root=self.mock_root,
                )

    # Targeted negative tests for Issue 4 (Staging directory exclusivity & non-destruction)
    def test_staging_dir_collision_rejected_and_non_destructive(self):
        """Test staging directory collision raises FileExistsError without deleting or overwriting."""
        collision_id = 'collision-probe-01'
        stage_dir = self.mock_work / f"e0-major-staging-{collision_id}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        canary = stage_dir / 'canary.txt'
        canary.write_text('CANARY_PRESERVED', encoding='utf-8')

        with self.assertRaises(FileExistsError):
            validate_and_create_staging_dir(self.mock_root, collision_id)

        # Assert existing directory contents were completely preserved (non-destructive)
        self.assertTrue(canary.is_file())
        self.assertEqual(canary.read_text(encoding='utf-8'), 'CANARY_PRESERVED')

    def test_staging_dir_traversal_rejected(self):
        """Test staging directory path traversal raises ValueError."""
        with self.assertRaises(ValueError):
            validate_and_create_staging_dir(self.mock_root, '../../escape')

    def test_staging_dir_preserved_after_build(self):
        """Test that private work/ staging directory is retained for post-mortem analysis."""
        build_id = 'test-preserve-01'
        created = validate_and_create_staging_dir(self.mock_root, build_id)
        self.assertTrue(created.is_dir())
        self.assertTrue(created.name.startswith('e0-major-staging-'))

    # Targeted negative tests for Issue 3 (Reference authentication & provenance)
    def test_reference_manifest_missing_rejected(self):
        """Test missing reference manifest raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            verify_reference_artifact(
                reference_lib='/root/mock.so',
                reference_manifest=self.mock_validation / 'nonexistent' / 'build-manifest.json',
            )

    def test_reference_manifest_unreviewed_cpp_sha_rejected(self):
        """Test reference manifest with wrong source CPP SHA256 raises ValueError."""
        bad_manifest = self.mock_validation / 'bad-manifest.json'
        write_json(bad_manifest, {
            'staged_sources': {'Exp1_MinModelTemp.cpp': {'sha256': 'unreviewed_sha'}},
            'output_library': {'filename': 'mock.so', 'sha256': 'some_sha'},
        })
        with self.assertRaises(ValueError) as ctx:
            verify_reference_artifact(
                reference_lib='/root/mock.so',
                reference_manifest=bad_manifest,
                expected_cpp_sha='expected_cpp_sha',
            )
        self.assertIn('Reference manifest source C++ SHA256 mismatch', str(ctx.exception))

    def test_reference_library_sha_mismatch_rejected(self):
        """Test WSL actual reference library SHA mismatch against manifest raises ValueError."""
        manifest = self.mock_validation / 'ref-manifest.json'
        write_json(manifest, {
            'staged_sources': {'Exp1_MinModelTemp.cpp': {'sha256': 'expected_cpp'}},
            'output_library': {'filename': 'mock.so', 'sha256': 'expected_so_sha'},
        })
        mock_runner = MagicMock(spec=WslRunner)
        mock_runner.run_bash.return_value = subprocess.CompletedProcess(
            [], 0, stdout="actual_different_sha  /root/mock.so\n", stderr=''
        )
        with self.assertRaises(ValueError) as ctx:
            verify_reference_artifact(
                reference_lib='/root/mock.so',
                reference_manifest=manifest,
                expected_cpp_sha='expected_cpp',
                runner=mock_runner,
            )
        self.assertIn('Reference library SHA256 in WSL mismatch', str(ctx.exception))

    # Targeted negative tests for Issue 1 & 2 (Parity checker strictness & 31-input contract)
    def _create_valid_records(self, modify_sample_fn=None):
        """Helper to create valid 503-line record.jsonl text."""
        lines = ['{"schema_version":1,"kind":"major_recorder_start"}']
        for k in range(501):
            sample = {
                "schema_version": 1,
                "kind": "major_recorder_sample",
                "k": k,
                "call_number": k + 1,
                "input_time_s": k * 0.001,
                "engine_before_s": k * 0.001,
                "engine_after_s": (k + 1) * 0.001,
                "major_capture_count": 1,
                "inPWMs": [0.0] * 16,
                "TerrainIn15d": [0.0] * 15,
                "major_root_outputs": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                "post_step_api": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                "step_status": "complete"
            }
            if modify_sample_fn:
                sample = modify_sample_fn(k, sample)
            lines.append(json.dumps(sample))
        lines.append(json.dumps({
            "schema_version": 1,
            "kind": "major_recorder_end",
            "status": "complete",
            "attempted_calls": 501,
            "returned_calls": 501,
            "emitted_samples": 501,
            "comparison_end_s": 0.5,
            "engine_end_s": 0.501
        }))
        return "\n".join(lines) + "\n"

    def test_parity_checker_corrupted_json_fails(self):
        """Test corrupt JSON line in record.jsonl fails parity check."""
        rec_path = self.mock_validation / 'corrupt_record.jsonl'
        valid_text = self._create_valid_records()
        corrupt_text = valid_text.replace('"k": 10,', '{"unclosed_json')
        rec_path.write_text(corrupt_text, encoding='utf-8')

        res = check_parity(str(rec_path), '/root/mock.so', str(self.mock_csv))
        self.assertFalse(res['success'])
        self.assertIn('JSON parse error', res['error'])

    def test_parity_checker_nan_output_fails(self):
        """Test non-finite (NaN) recorded value fails parity check explicitly."""
        rec_path = self.mock_validation / 'nan_record.jsonl'
        def inject_nan(k, sample):
            if k == 5:
                sample['post_step_api']['Vehicle60'][0] = float('nan')
            return sample
        rec_path.write_text(self._create_valid_records(inject_nan), encoding='utf-8')

        res = check_parity(str(rec_path), '/root/mock.so', str(self.mock_csv))
        self.assertFalse(res['success'])
        self.assertIn('Non-finite recorded value', res['error'])

    def test_parity_checker_missing_terminal_fails(self):
        """Test record.jsonl missing terminal major_recorder_end fails parity check."""
        rec_path = self.mock_validation / 'missing_terminal.jsonl'
        lines = self._create_valid_records().splitlines()[:-1]  # drop terminal line
        rec_path.write_text("\n".join(lines) + "\n", encoding='utf-8')

        res = check_parity(str(rec_path), '/root/mock.so', str(self.mock_csv))
        self.assertFalse(res['success'])
        self.assertTrue('records in record.jsonl' in res['error'] or 'terminal' in res['error'])

    def test_parity_checker_out_of_order_step_fails(self):
        """Test out-of-order step index k fails parity check."""
        rec_path = self.mock_validation / 'out_of_order.jsonl'
        def make_out_of_order(k, sample):
            if k == 3:
                sample['k'] = 99
            return sample
        rec_path.write_text(self._create_valid_records(make_out_of_order), encoding='utf-8')

        res = check_parity(str(rec_path), '/root/mock.so', str(self.mock_csv))
        self.assertFalse(res['success'])
        self.assertIn('Step index mismatch', res['error'])

    def test_parity_checker_nonzero_terrain_with_so_ref_fails(self):
        """Test input CSV with non-zero TerrainIn15d is rejected when reference is 16-PWM SO."""
        csv_path = self.mock_validation / 'nonzero_terrain.csv'
        header = "k,time_s" + "".join(f",inPWMs{i}" for i in range(16)) + "".join(f",TerrainIn15d{i}" for i in range(15)) + "\n"
        rows = [header]
        for k in range(501):
            t = k * 0.001
            terrain_val = "0.75" if k == 10 else "0"
            row_str = f"{k},{t:.3f}" + ",0"*16 + f",{terrain_val}" + ",0"*14 + "\n"
            rows.append(row_str)
        csv_path.write_text("".join(rows), encoding='ascii')

        rec_path = self.mock_validation / 'valid_record.jsonl'
        rec_path.write_text(self._create_valid_records(), encoding='utf-8')

        res = check_parity(str(rec_path), '/root/mock.so', str(csv_path))
        self.assertFalse(res['success'])
        self.assertIn('Non-zero TerrainIn15d detected in input CSV', res['error'])

    def _create_valid_post_reference_records(self, modify_sample_fn=None):
        """Helper to create valid 503-line post_reference.jsonl text."""
        lines = ['{"schema_version":1,"kind":"post_reference_start"}']
        for k in range(501):
            sample = {
                "schema_version": 1,
                "kind": "post_reference_sample",
                "k": k,
                "call_number": k + 1,
                "input_time_s": k * 0.001,
                "engine_before_s": k * 0.001,
                "engine_after_s": (k + 1) * 0.001,
                "inPWMs": [0.0] * 16,
                "TerrainIn15d": [0.0] * 15,
                "post_step_api": {"Vehicle60": [0.0]*60, "Sensor30": [0.0]*30, "GPS30": [0.0]*30},
                "step_status": "complete"
            }
            if modify_sample_fn:
                sample = modify_sample_fn(k, sample)
            lines.append(json.dumps(sample))
        lines.append(json.dumps({
            "schema_version": 1,
            "kind": "post_reference_end",
            "status": "complete",
            "attempted_calls": 501,
            "returned_calls": 501,
            "emitted_samples": 501,
            "comparison_end_s": 0.5,
            "engine_end_s": 0.501
        }))
        return "\n".join(lines) + "\n"

    def test_parity_checker_nonexistent_non_so_path_fails(self):
        """Test that a non-existent non-.so reference path fails parity check."""
        rec_path = self.mock_validation / 'valid_record.jsonl'
        rec_path.write_text(self._create_valid_records(), encoding='utf-8')
        non_existent = str(self.mock_validation / 'does_not_exist.jsonl')
        res = check_parity(str(rec_path), non_existent, str(self.mock_csv))
        self.assertFalse(res['success'])
        self.assertIn('Reference target path does not exist', res['error'])

    def test_parity_checker_tiny_discrepancy_1e13_fails(self):
        """Test that an exact discrepancy of 1e-13 causes parity check failure without tolerance slack."""
        rec_path = self.mock_validation / 'valid_record.jsonl'
        rec_path.write_text(self._create_valid_records(), encoding='utf-8')

        ref_path = self.mock_validation / 'discrepant_ref.jsonl'
        def inject_1e13(k, sample):
            if k == 42:
                sample['post_step_api']['Vehicle60'][5] = 1e-13
            return sample
        ref_path.write_text(self._create_valid_post_reference_records(inject_1e13), encoding='utf-8')

        res = check_parity(str(rec_path), str(ref_path), str(self.mock_csv))
        self.assertFalse(res['success'])
        self.assertEqual(res['discrepancies_count'], 1)
        self.assertEqual(res['max_discrepancy'], 1e-13)
        self.assertEqual(len(res['sample_discrepancies']), 1)
        self.assertEqual(res['sample_discrepancies'][0]['k'], 42)
        self.assertEqual(res['sample_discrepancies'][0]['dim'], 5)
        self.assertEqual(res['sample_discrepancies'][0]['abs_diff'], 1e-13)
        self.assertIn('Found 1 numeric discrepancies', res['error'])

    def test_parity_checker_many_discrepancies_counts_all_and_caps_samples(self):
        """Test that discrepancy count reflects true total while sample list is capped at 10."""
        rec_path = self.mock_validation / 'valid_record.jsonl'
        rec_path.write_text(self._create_valid_records(), encoding='utf-8')

        ref_path = self.mock_validation / 'many_discrepant_ref.jsonl'
        def inject_25_diffs(k, sample):
            if k < 25:
                sample['post_step_api']['Vehicle60'][0] = 0.05
            return sample
        ref_path.write_text(self._create_valid_post_reference_records(inject_25_diffs), encoding='utf-8')

        res = check_parity(str(rec_path), str(ref_path), str(self.mock_csv))
        self.assertFalse(res['success'])
        self.assertEqual(res['discrepancies_count'], 25)
        self.assertEqual(len(res['sample_discrepancies']), 10)
        self.assertEqual(res['max_discrepancy'], 0.05)

    def test_parity_checker_31_input_parity_success(self):
        """Test that matching 31-input major recorder and post reference pass with 0 discrepancies."""
        rec_path = self.mock_validation / 'valid_record.jsonl'
        rec_path.write_text(self._create_valid_records(), encoding='utf-8')

        ref_path = self.mock_validation / 'matching_ref.jsonl'
        ref_path.write_text(self._create_valid_post_reference_records(), encoding='utf-8')

        res = check_parity(str(rec_path), str(ref_path), str(self.mock_csv))
        self.assertTrue(res['success'])
        self.assertEqual(res['discrepancies_count'], 0)
        self.assertEqual(res['max_discrepancy'], 0.0)
        self.assertEqual(res['total_values_checked'], 501 * 120)
        self.assertEqual(res['input_binding']['bound_inputs'], ['inPWMs[16]', 'TerrainIn15d[15]'])

    def test_boolean_cannot_impersonate_zero_or_one_in_raw_records(self):
        reference=self.mock_validation/'bool-ref.jsonl'
        reference.write_text(self._create_valid_post_reference_records(),encoding='utf-8')
        for field in ('k','engine_before_s','major_capture_count','inPWMs'):
            lines=self._create_valid_records().splitlines();row=json.loads(lines[1])
            if field=='inPWMs':row[field][0]=False
            else:row[field]=True if field=='major_capture_count' else False
            lines[1]=json.dumps(row)
            record=self.mock_validation/'bool-record.jsonl'
            record.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            result=check_parity(str(record),str(reference),str(self.mock_csv))
            self.assertFalse(result['success'],field)


if __name__ == '__main__':
    unittest.main()
