"""Drive isolated MATLAB R2022b to generate standalone C++ code from e0 SLX 11.8.

Default execution only prepares isolated staging and manifests (dry prepare).
Explicit --run is required to launch commercial MATLAB for code generation.

Build-time requires commercial MATLAB R2022b with Simulink and Embedded Coder.
Runtime in WSL/SITL without MATLAB is a subsequent goal to be verified post-build.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path('E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp')
DEFAULT_MATLAB = Path('D:/matlab/install date/bin/matlab.exe')

EXPECTED_SOURCES = {
    'MulticopterModel.zip': 'd528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed',
    'Exp1_MinModelTemp.slx': 'c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392',
    'Exp1_MinModelTemp_init.m': '9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991',
}

REQUIRED_LICENSES = [
    'SIMULINK',
    'Real-Time_Workshop',
    'RTW_Embedded_Coder',
    'Aerospace_Blockset',
    'Aerospace_Toolbox',
]

REQUIRED_STAGES = [
    'license_verification',
    'fileGenControl',
    'load_system',
    'verify_solver',
    'configure_target',
    'initialization',
    'slbuild',
    'artifact_verification',
    'close_model',
]


def digest(path: Path) -> str:
    """Compute sha256 hex digest of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, data) -> None:
    """Write JSON data with consistent UTF-8 formatting."""
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def validate_run_id(run_id: str) -> None:
    """Ensure run_id contains only alphanumeric, hyphen, underscore, and no path separators."""
    if not isinstance(run_id, str) or not re.match(r'^[a-zA-Z0-9_-]+$', run_id):
        raise ValueError(f"Invalid run_id: '{run_id}'. Must match ^[a-zA-Z0-9_-]+$ with no path separators.")


def is_within(child: Path, parent: Path) -> bool:
    """Check if child resolves strictly within parent directory."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_directory_containment(work_dir: Path, evidence_dir: Path, project_root: Path = ROOT):
    """Validate that work_dir is strictly inside project_root/work and evidence_dir is inside project_root/validation.

    Ensures:
    - work_dir is strictly inside project_root / 'work' (not equal to work root)
    - evidence_dir is strictly inside project_root / 'validation' (not equal to validation root)
    - work_dir and evidence_dir do not equal each other and do not overlap
    - No alias or traversal escape
    """
    work_base = (project_root / 'work').resolve()
    evidence_base = (project_root / 'validation').resolve()

    work_res = Path(work_dir).resolve()
    evidence_res = Path(evidence_dir).resolve()

    if work_res == work_base:
        raise ValueError(f"work_dir cannot be the work root itself: '{work_dir}'")
    if evidence_res == evidence_base:
        raise ValueError(f"evidence_dir cannot be the validation root itself: '{evidence_dir}'")

    if not is_within(work_res, work_base):
        raise ValueError(f"work_dir '{work_dir}' must be strictly located within '{work_base}'")
    if not is_within(evidence_res, evidence_base):
        raise ValueError(f"evidence_dir '{evidence_dir}' must be strictly located within '{evidence_base}'")

    if work_res == evidence_res:
        raise ValueError(f"work_dir and evidence_dir cannot be the same path: '{work_dir}'")

    if is_within(work_res, evidence_res) or is_within(evidence_res, work_res):
        raise ValueError(f"work_dir '{work_dir}' and evidence_dir '{evidence_dir}' cannot overlap")


class ProcessTracker:
    """Track spawned MATLAB process and verified child tree by identity and creation time."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.pid = proc.pid
        self.psutil_proc = None
        self.create_time = None
        if psutil is not None:
            try:
                self.psutil_proc = psutil.Process(self.pid)
                self.create_time = self.psutil_proc.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.psutil_proc = None

    def terminate(self, timeout: float = 15.0) -> bool:
        """Terminate the root process and all verified child processes.

        Returns True only if all child processes and parent are proven terminated.
        Returns False (cleanup_unverified) if psutil is unavailable or identity check fails.
        """
        if psutil is None or self.psutil_proc is None or self.create_time is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=min(timeout, 3.0))
            except Exception:
                pass
            return False

        try:
            if not self.psutil_proc.is_running() or self.psutil_proc.create_time() != self.create_time:
                return False

            children = self.psutil_proc.children(recursive=True)
            procs = children + [self.psutil_proc]
            for p in procs:
                try:
                    p.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            gone, alive = psutil.wait_procs(procs, timeout=timeout)
            if alive:
                for p in alive:
                    try:
                        p.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                _, alive_after = psutil.wait_procs(alive, timeout=5.0)
                return len(alive_after) == 0

            return True
        except Exception:
            return False


def prepare_run(
    source_dir: Path,
    work_dir: Path,
    evidence_dir: Path,
    expected_hashes=EXPECTED_SOURCES,
    project_root: Path = ROOT,
):
    """Prepare isolated directories, stage input model files and generate staging manifest.

    Strict path containment and non-reuse checks are enforced before any directory creation.
    """
    validate_directory_containment(work_dir, evidence_dir, project_root=project_root)

    for d, label in [(work_dir, 'work directory'), (evidence_dir, 'evidence directory')]:
        if d.exists() and any(d.iterdir()):
            raise ValueError(f"Refusing to reuse non-empty {label}: '{d}'")

    staged_dir = work_dir / 'staged-model'
    temp_dir = work_dir / 'temp'
    pref_dir = work_dir / 'pref'
    cache_dir = work_dir / 'cache'
    codegen_dir = work_dir / 'codegen'

    for sub in (staged_dir, temp_dir, pref_dir, cache_dir, codegen_dir):
        sub.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for filename, expected_hash in expected_hashes.items():
        src = source_dir / filename
        if not src.is_file():
            raise FileNotFoundError(f"Required model input not found: '{src}'")
        actual_hash = digest(src)
        if actual_hash != expected_hash:
            raise ValueError(f"Source SHA mismatch for '{src}': expected '{expected_hash}', got '{actual_hash}'")
        dst = staged_dir / filename
        shutil.copyfile(src, dst)
        staged_hash = digest(dst)
        if staged_hash != actual_hash:
            raise RuntimeError(f"Copy verification failed for '{dst}'")
        manifest.append({
            'filename': filename,
            'source_path': str(src.resolve()),
            'staged_path': str(dst.resolve()),
            'sha256': actual_hash,
            'size_bytes': src.stat().st_size,
        })

    m_driver_src = ROOT / 'tools/generate_model_e0.m'
    if not m_driver_src.is_file():
        raise FileNotFoundError(f"Companion MATLAB driver not found: '{m_driver_src}'")
    m_driver_dst = staged_dir / 'generate_model_e0.m'
    shutil.copyfile(m_driver_src, m_driver_dst)

    m_config = {
        'model_name': 'Exp1_MinModelTemp',
        'cache_folder': str(cache_dir.resolve()),
        'codegen_folder': str(codegen_dir.resolve()),
        'report_output': str((evidence_dir / 'codegen-report.json').resolve()),
        'system_target_file': 'ert.tlc',
        'target_lang': 'C++',
        'gen_code_only': 'on',
        'package_artifacts': 'off',
        'required_licenses': REQUIRED_LICENSES,
    }
    write_json(staged_dir / 'codegen_config.json', m_config)
    write_json(evidence_dir / 'source-manifest.json', manifest)

    return {
        'status': 'prepared',
        'work_dir': str(work_dir.resolve()),
        'staged_dir': str(staged_dir.resolve()),
        'evidence_dir': str(evidence_dir.resolve()),
        'manifest': manifest,
        'config': m_config,
    }


def execute_codegen(
    matlab_bin: Path,
    staged_dir: Path,
    work_dir: Path,
    evidence_dir: Path,
    timeout_seconds: float = 600.0,
):
    """Execute real MATLAB in headless mode with hidden window and process tree tracking."""
    if not matlab_bin.is_file():
        raise FileNotFoundError(f"MATLAB binary not found: '{matlab_bin}'")

    temp_dir = work_dir / 'temp'
    pref_dir = work_dir / 'pref'
    log_file = evidence_dir / 'matlab-console.log'

    env = os.environ.copy()
    env.update({
        'TEMP': str(temp_dir.resolve()),
        'TMP': str(temp_dir.resolve()),
        'MATLAB_PREFDIR': str(pref_dir.resolve()),
    })
    env.pop('MATLABPATH', None)

    argv = [
        str(matlab_bin.resolve()),
        '-wait',
        '-sd', str(staged_dir.resolve()),
        '-batch', 'generate_model_e0',
    ]

    command_meta = {
        'argv': argv,
        'cwd': str(staged_dir.resolve()),
        'environment_overrides': {
            'TEMP': str(temp_dir.resolve()),
            'TMP': str(temp_dir.resolve()),
            'MATLAB_PREFDIR': str(pref_dir.resolve()),
        },
        'timeout_seconds': timeout_seconds,
        'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    write_json(evidence_dir / 'command.json', command_meta)

    proc = None
    tracker = None
    timed_out = False
    cleanup_unverified = False
    return_code = None
    exec_error = None

    creationflags = 0x08000000 if sys.platform == 'win32' else 0

    with log_file.open('w', encoding='utf-8') as log_stream:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=staged_dir,
                env=env,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            tracker = ProcessTracker(proc)
            return_code = proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if tracker is not None:
                clean = tracker.terminate(timeout=15.0)
                if not clean:
                    cleanup_unverified = True
            return_code = -1
        except Exception as err:
            exec_error = str(err)
            if tracker is not None:
                clean = tracker.terminate(timeout=10.0)
                if not clean:
                    cleanup_unverified = True
            return_code = -1

    command_meta['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    command_meta['return_code'] = return_code
    command_meta['timed_out'] = timed_out
    command_meta['cleanup_unverified'] = cleanup_unverified
    if exec_error is not None:
        command_meta['exec_error'] = exec_error
    write_json(evidence_dir / 'command.json', command_meta)

    return {
        'return_code': return_code,
        'timed_out': timed_out,
        'cleanup_unverified': cleanup_unverified,
        'exec_error': exec_error,
    }


def audit_and_finalize(
    source_dir: Path,
    staged_dir: Path,
    codegen_dir: Path,
    evidence_dir: Path,
    exec_result,
    expected_hashes=EXPECTED_SOURCES,
):
    """Audit post-execution artifacts, licenses, stage progression, and input immutability."""
    report_file = evidence_dir / 'codegen-report.json'
    m_report = {}
    if report_file.is_file():
        try:
            m_report = json.loads(report_file.read_text(encoding='utf-8'))
        except Exception as e:
            m_report = {'error': f'Failed to parse codegen-report.json: {e}'}

    # 1. Verify original source immutability
    source_verification = []
    source_tampered = False
    for filename, expected_hash in expected_hashes.items():
        src = source_dir / filename
        current_hash = digest(src) if src.is_file() else None
        unchanged = (current_hash == expected_hash)
        if not unchanged:
            source_tampered = True
        source_verification.append({
            'filename': filename,
            'source_path': str(src.resolve()),
            'expected_sha256': expected_hash,
            'actual_sha256': current_hash,
            'unchanged': unchanged,
        })
    write_json(evidence_dir / 'post-source-verification.json', source_verification)

    # 2. Verify staged input immutability
    staged_verification = []
    staged_tampered = False
    for filename, expected_hash in expected_hashes.items():
        staged_file = staged_dir / filename
        current_hash = digest(staged_file) if staged_file.is_file() else None
        unchanged = (current_hash == expected_hash)
        if not unchanged:
            staged_tampered = True
        staged_verification.append({
            'filename': filename,
            'staged_path': str(staged_file.resolve()),
            'expected_sha256': expected_hash,
            'actual_sha256': current_hash,
            'unchanged': unchanged,
        })
    write_json(evidence_dir / 'post-staged-verification.json', staged_verification)

    # 3. Check license results and MATLAB environment recording
    has_license_report = report_file.is_file() and ('licenses' in m_report)
    licenses_ok = True
    if has_license_report:
        license_details = m_report.get('licenses', {})
        test_results = license_details.get('test', {})
        checkout_results = license_details.get('checkout', {})
        for feat in REQUIRED_LICENSES:
            valid_name = feat.replace('-', '_')
            t_val = test_results.get(valid_name)
            c_val = checkout_results.get(valid_name)
            if t_val != 1 or c_val != 1:
                licenses_ok = False
                break
    else:
        licenses_ok = False

    # 4. Check all required stages passed ok
    stages_dict = {s.get('name'): s.get('status') for s in m_report.get('stages', [])}
    stages_ok = all(stages_dict.get(st) == 'ok' for st in REQUIRED_STAGES)
    slbuild_ok = (stages_dict.get('slbuild') == 'ok')

    # 5. Enumerate generated C++ and header files
    generated_sources = []
    cpp_count = 0
    header_count = 0
    if codegen_dir.is_dir():
        for item in codegen_dir.rglob('*'):
            if item.is_file():
                suffix = item.suffix.lower()
                if suffix in ('.cpp', '.cxx', '.cc', '.h', '.hpp'):
                    size = item.stat().st_size
                    if suffix in ('.cpp', '.cxx', '.cc'):
                        cpp_count += 1
                    elif suffix in ('.h', '.hpp'):
                        header_count += 1
                    rel_path = str(item.relative_to(codegen_dir))
                    generated_sources.append({
                        'relative_path': rel_path,
                        'sha256': digest(item),
                        'size_bytes': size,
                        'is_empty': (size == 0),
                    })

    write_json(evidence_dir / 'generated-sources-manifest.json', {
        'total_files': len(generated_sources),
        'cpp_count': cpp_count,
        'header_count': header_count,
        'sources': generated_sources,
    })

    has_empty_file = any(s['is_empty'] for s in generated_sources)
    has_artifacts = (cpp_count > 0 and header_count > 0 and not has_empty_file)
    matlab_clean = (exec_result.get('return_code') == 0 and not exec_result.get('timed_out'))
    m_status_ok = (m_report.get('status') == 'generated')

    if exec_result.get('cleanup_unverified'):
        final_status = 'cleanup_unverified'
    elif source_tampered or staged_tampered:
        final_status = 'rejected_input_tampered'
    elif has_license_report and (not licenses_ok or m_report.get('status') == 'license_failed'):
        final_status = 'rejected_license_failure'
    elif not matlab_clean:
        final_status = 'failed'
    elif not has_license_report or not licenses_ok:
        final_status = 'rejected_license_failure'
    elif not slbuild_ok or not stages_ok or not m_status_ok:
        final_status = 'failed'
    elif not has_artifacts:
        final_status = 'rejected_missing_artifacts'
    else:
        final_status = 'generated'

    final_summary = {
        'status': final_status,
        'scope': 'Simulink e0 SLX 11.8 C++ headless code generation via Embedded Coder ert.tlc; no simulation or G6 claim',
        'matlab_return_code': exec_result.get('return_code'),
        'timed_out': exec_result.get('timed_out', False),
        'cleanup_unverified': exec_result.get('cleanup_unverified', False),
        'source_tampered': source_tampered,
        'staged_tampered': staged_tampered,
        'licenses_ok': licenses_ok,
        'stages_ok': stages_ok,
        'slbuild_ok': slbuild_ok,
        'has_valid_artifacts': has_artifacts,
        'cpp_count': cpp_count,
        'header_count': header_count,
        'generated_files_count': len(generated_sources),
        'evidence_directory': str(evidence_dir.resolve()),
    }
    write_json(evidence_dir / 'summary.json', final_summary)
    return final_summary


def run(
    run_flag: bool,
    source_dir: Path = DEFAULT_SOURCE,
    matlab_bin: Path = DEFAULT_MATLAB,
    work_root=None,
    evidence_root=None,
    run_id=None,
    timeout_seconds: float = 600.0,
    project_root: Path = ROOT,
):
    """Execute either dry preparation (default) or real MATLAB generation."""
    if work_root is None:
        work_root = project_root / 'work/codegen-e0'
    if evidence_root is None:
        evidence_root = project_root / 'validation/codegen-e0'

    if run_id is None:
        run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    validate_run_id(run_id)

    work_dir = work_root / run_id
    evidence_dir = evidence_root / run_id

    prep = prepare_run(source_dir, work_dir, evidence_dir, project_root=project_root)
    staged_dir = Path(prep['staged_dir'])
    codegen_dir = work_dir / 'codegen'

    if not run_flag:
        summary = {
            'status': 'prepared',
            'scope': 'Dry preparation of model staging and manifests; MATLAB was NOT executed.',
            'run_id': run_id,
            'work_directory': str(work_dir.resolve()),
            'evidence_directory': str(evidence_dir.resolve()),
            'staged_inputs': len(prep['manifest']),
        }
        write_json(evidence_dir / 'summary.json', summary)
        return summary

    exec_res = execute_codegen(matlab_bin, staged_dir, work_dir, evidence_dir, timeout_seconds)
    summary = audit_and_finalize(source_dir, staged_dir, codegen_dir, evidence_dir, exec_res)
    summary['run_id'] = run_id
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Explicitly execute commercial MATLAB for code generation')
    parser.add_argument('--source-dir', type=Path, default=DEFAULT_SOURCE, help='Path to e0 model source directory')
    parser.add_argument('--matlab', type=Path, default=DEFAULT_MATLAB, help='Path to matlab.exe')
    parser.add_argument('--work-root', type=Path, default=None, help='Root directory for isolated work outputs')
    parser.add_argument('--evidence-root', type=Path, default=None, help='Root directory for validation evidence')
    parser.add_argument('--run-id', type=str, default=None, help='Unique run identifier')
    parser.add_argument('--timeout', type=float, default=600.0, help='Max execution seconds for MATLAB')
    parser.add_argument('--project-root', type=Path, default=ROOT, help='Project root directory')
    args = parser.parse_args()

    try:
        result = run(
            run_flag=args.run,
            source_dir=args.source_dir,
            matlab_bin=args.matlab,
            work_root=args.work_root,
            evidence_root=args.evidence_root,
            run_id=args.run_id,
            timeout_seconds=args.timeout,
            project_root=args.project_root,
        )
        print(json.dumps({
            'status': result.get('status'),
            'run_id': result.get('run_id'),
            'evidence_directory': result.get('evidence_directory', result.get('evidence_dir')),
            'matlab_return_code': result.get('matlab_return_code'),
        }, indent=2))
        if result.get('status') not in ('prepared', 'generated'):
            sys.exit(1)
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
