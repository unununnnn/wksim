"""WSL-based compilation and execution driver for generated e0 Simulink model.

Builds libwksim_e0.so in WSL Ubuntu 22.04 from verified Embedded Coder C++ artifacts
and Simulator/wksim_core/model.cpp wrapper, with zero runtime MATLAB dependency.
Optionally probes the compiled library with a 1ms fixed-step finite output evaluation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.generate_model_e0 import REQUIRED_LICENSES, REQUIRED_STAGES
DEFAULT_GENERATION_DIR = ROOT / 'validation/codegen-e0/short-cycle-codegen-01'
DEFAULT_EVIDENCE_ROOT = ROOT / 'validation'
DEFAULT_MATLAB_INCLUDE = Path('D:/matlab/install date/simulink/include')
DEFAULT_WRAPPER_SOURCE = ROOT / 'Simulator/wksim_core/model.cpp'
DEFAULT_WSL_DISTRO = 'Ubuntu-22.04'
DEFAULT_WSL_USER = 'root'

REQUIRED_EVIDENCE_FILES = [
    'summary.json',
    'command.json',
    'generated-sources-manifest.json',
    'post-source-verification.json',
    'post-staged-verification.json',
    'codegen-report.json',
]

REQUIRED_GENERATED_SOURCES = {
    'Exp1_MinModelTemp.cpp',
    'Exp1_MinModelTemp.h',
    'rtwtypes.h',
    'ert_main.cpp',
}

REQUIRED_BUILD_SOURCES = {
    'Exp1_MinModelTemp.cpp',
    'Exp1_MinModelTemp.h',
    'rtwtypes.h',
    'model.cpp',
    'rtw_continuous.h',
    'rtw_solver.h',
}

EXCLUDED_BUILD_SOURCES = {
    'ert_main.cpp',
}

DISALLOWED_DEP_SUBSTRINGS = [
    'matlab',
    'simulink',
    'libmw',
    'mcr',
    'slprj',
    'rflysim',
]

COMPILER_FLAGS = [
    '-std=c++17',
    '-O2',
    '-fno-fast-math',
    '-fPIC',
    '-shared',
    '-Wl,--no-undefined',
]


def digest(path: Path) -> str:
    """Compute sha256 hex digest of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    """Write JSON data with consistent UTF-8 formatting."""
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def validate_build_id(build_id: str) -> None:
    """Ensure build_id contains only alphanumeric, hyphen, underscore, and no path separators."""
    if not isinstance(build_id, str) or not re.match(r'^[a-zA-Z0-9_-]+$', build_id):
        raise ValueError(f"Invalid build_id: '{build_id}'. Must match ^[a-zA-Z0-9_-]+$ with no path separators.")


def validate_wsl_build_dir(wsl_build_dir: str) -> None:
    """Ensure wsl_build_dir is strictly a direct child of /root matching ^/root/wksim-codegen-e0-build-[a-zA-Z0-9_-]+$."""
    if not isinstance(wsl_build_dir, str):
        raise ValueError("wsl_build_dir must be a string")
    if '\n' in wsl_build_dir or '\r' in wsl_build_dir or "'" in wsl_build_dir or '"' in wsl_build_dir:
        raise ValueError(f"Invalid WSL build directory '{wsl_build_dir}': contains forbidden characters")
    if not re.match(r'^/root/wksim-codegen-e0-build-[a-zA-Z0-9_-]+$', wsl_build_dir):
        raise ValueError(
            f"Invalid WSL build directory '{wsl_build_dir}'. "
            f"Must be a direct subdirectory of /root matching ^/root/wksim-codegen-e0-build-[a-zA-Z0-9_-]+$ with no traversal."
        )


def is_within(child: Path, parent: Path) -> bool:
    """Check if child resolves strictly within parent directory."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_evidence_containment(evidence_dir: Path, project_root: Path = ROOT) -> None:
    """Validate that evidence_dir is strictly inside project_root/validation and not non-empty."""
    evidence_base = (project_root / 'validation').resolve()
    evidence_res = Path(evidence_dir).resolve()

    if evidence_res == evidence_base:
        raise ValueError(f"evidence_dir cannot be the validation root itself: '{evidence_dir}'")
    if not is_within(evidence_res, evidence_base):
        raise ValueError(f"evidence_dir '{evidence_dir}' must be strictly located within '{evidence_base}'")
    if evidence_res.exists() and any(evidence_res.iterdir()):
        raise ValueError(f"Refusing to reuse non-empty evidence directory: '{evidence_dir}'")


def to_wsl_path(path: Path) -> str:
    """Convert a Windows path (or absolute path) to WSL /mnt/... format."""
    path_str = str(Path(path).resolve())
    m = re.match(r'^([a-zA-Z]):[\\/](.*)', path_str)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace('\\', '/')
        return f"/mnt/{drive}/{rest}"
    return path_str.replace('\\', '/')


def verify_generation_evidence(
    generation_evidence_dir: Path,
    codegen_source_dir: Optional[Path] = None,
    project_root: Path = ROOT,
) -> Dict[str, Any]:
    """Verify integrity of generation evidence artifacts and check generated source hashes.

    Strict verification gates:
    - All REQUIRED_EVIDENCE_FILES must exist (summary.json, command.json, generated-sources-manifest.json,
      post-source-verification.json, post-staged-verification.json, codegen-report.json).
    - command.json has return_code == 0, timed_out == False, cleanup_unverified == False.
    - Staged codegen_config.json exists in command.json['cwd'], and codegen_folder binds.
    - summary.json has status == 'generated', matlab_return_code == 0, stages_ok == True,
      licenses_ok == True, has_valid_artifacts == True, source_tampered == False, staged_tampered == False,
      timed_out == False, cleanup_unverified == False.
    - post-source-verification.json and post-staged-verification.json are non-empty and show unchanged: True.
    - codegen-report.json has status == 'generated', all REQUIRED_STAGES present and 'ok' (non-empty stages),
      and all 5 REQUIRED_LICENSES test=1 and checkout=1.
    - generated-sources-manifest.json contains required generated files without traversal, leading slashes,
      or duplicate basenames, strictly bound within codegen_folder.
    - actual source files in codegen_source_dir exist and match manifest hashes.
    """
    evidence_dir = Path(generation_evidence_dir).resolve()
    if not evidence_dir.is_dir():
        raise FileNotFoundError(f"Generation evidence directory not found: '{evidence_dir}'")

    # 1. Mandatory evidence files existence check
    for fname in REQUIRED_EVIDENCE_FILES:
        fpath = evidence_dir / fname
        if not fpath.is_file():
            raise FileNotFoundError(f"Required generation evidence file missing in '{evidence_dir}': '{fname}'")

    # 2. Check command.json and resolve staged codegen_config
    cmd_data = json.loads((evidence_dir / 'command.json').read_text(encoding='utf-8'))
    if cmd_data.get('return_code') != 0:
        raise ValueError(f"Generation command return_code is {cmd_data.get('return_code')}, expected 0")
    if cmd_data.get('timed_out', False):
        raise ValueError("Generation command indicates timed_out is True")
    if cmd_data.get('cleanup_unverified', False):
        raise ValueError("Generation command indicates cleanup_unverified is True")

    staged_cwd = cmd_data.get('cwd')
    if not staged_cwd or not Path(staged_cwd).is_dir():
        raise FileNotFoundError(f"Staged model directory from command.json does not exist: '{staged_cwd}'")
    staged_dir = Path(staged_cwd).resolve()

    codegen_cfg_file = staged_dir / 'codegen_config.json'
    if not codegen_cfg_file.is_file():
        raise FileNotFoundError(f"staged codegen_config.json missing in '{staged_dir}'")
    codegen_cfg = json.loads(codegen_cfg_file.read_text(encoding='utf-8'))

    cfg_codegen_folder = codegen_cfg.get('codegen_folder')
    if not cfg_codegen_folder or not Path(cfg_codegen_folder).is_dir():
        raise FileNotFoundError(f"codegen_folder '{cfg_codegen_folder}' specified in codegen_config.json does not exist")
    codegen_folder = Path(cfg_codegen_folder).resolve()

    bound_model_codegen_dir = (codegen_folder / 'Exp1_MinModelTemp_ert_rtw').resolve()

    if codegen_source_dir is not None:
        user_codegen = Path(codegen_source_dir).resolve()
        if user_codegen != bound_model_codegen_dir:
            raise ValueError(
                f"Provided codegen_source_dir '{user_codegen}' does not match bound staged codegen_config folder '{bound_model_codegen_dir}'"
            )
    codegen_source_dir = bound_model_codegen_dir
    if not codegen_source_dir.is_dir():
        raise FileNotFoundError(f"Bound codegen source directory does not exist: '{codegen_source_dir}'")

    # 3. Check summary.json
    summary = json.loads((evidence_dir / 'summary.json').read_text(encoding='utf-8'))
    if summary.get('status') != 'generated':
        raise ValueError(f"Generation summary status is '{summary.get('status')}', expected 'generated'")
    if summary.get('matlab_return_code') != 0:
        raise ValueError(f"Generation summary matlab_return_code is {summary.get('matlab_return_code')}, expected 0")
    if not summary.get('stages_ok', False):
        raise ValueError("Generation summary indicates stages_ok is not True")
    if not summary.get('licenses_ok', False):
        raise ValueError("Generation summary indicates licenses_ok is not True")
    if not summary.get('has_valid_artifacts', False):
        raise ValueError("Generation summary indicates has_valid_artifacts is not True")
    if summary.get('source_tampered', True):
        raise ValueError("Generation summary indicates source_tampered is True")
    if summary.get('staged_tampered', True):
        raise ValueError("Generation summary indicates staged_tampered is True")
    if summary.get('timed_out', False):
        raise ValueError("Generation summary indicates timed_out is True")
    if summary.get('cleanup_unverified', False):
        raise ValueError("Generation summary indicates cleanup_unverified is True")

    # 4. Check post-source and post-staged verification
    post_source = json.loads((evidence_dir / 'post-source-verification.json').read_text(encoding='utf-8'))
    if not isinstance(post_source, list) or len(post_source) == 0:
        raise ValueError("post-source-verification.json must contain a non-empty list")
    for item in post_source:
        if not item.get('unchanged', False) or item.get('actual_sha256') != item.get('expected_sha256'):
            raise ValueError(f"Post-source verification failed for '{item.get('filename')}'")

    post_staged = json.loads((evidence_dir / 'post-staged-verification.json').read_text(encoding='utf-8'))
    if not isinstance(post_staged, list) or len(post_staged) == 0:
        raise ValueError("post-staged-verification.json must contain a non-empty list")
    for item in post_staged:
        if not item.get('unchanged', False) or item.get('actual_sha256') != item.get('expected_sha256'):
            raise ValueError(f"Post-staged verification failed for '{item.get('filename')}'")

    # 5. Check codegen-report.json
    report = json.loads((evidence_dir / 'codegen-report.json').read_text(encoding='utf-8'))
    if report.get('status') != 'generated':
        raise ValueError(f"codegen-report status is '{report.get('status')}', expected 'generated'")

    raw_stages = report.get('stages', [])
    if not isinstance(raw_stages, list) or len(raw_stages) == 0:
        raise ValueError("codegen-report stages must be a non-empty list")
    stages_dict = {s.get('name'): s.get('status') for s in raw_stages if isinstance(s, dict)}
    for req_stage in REQUIRED_STAGES:
        st_val = stages_dict.get(req_stage)
        if st_val != 'ok':
            raise ValueError(f"Required stage '{req_stage}' status is '{st_val}', expected 'ok'")

    lic_test = report.get('licenses', {}).get('test', {})
    lic_checkout = report.get('licenses', {}).get('checkout', {})
    for lic in REQUIRED_LICENSES:
        vname = lic.replace('-', '_')
        t_val = lic_test.get(vname)
        c_val = lic_checkout.get(vname)
        if t_val != 1 or c_val != 1:
            raise ValueError(f"License verification failed for '{lic}': test={t_val}, checkout={c_val}")

    # 6. Check generated-sources-manifest.json
    gen_manifest = json.loads((evidence_dir / 'generated-sources-manifest.json').read_text(encoding='utf-8'))
    sources_list = gen_manifest.get('sources', [])
    if not isinstance(sources_list, list) or len(sources_list) == 0:
        raise ValueError("generated-sources-manifest.json sources must be a non-empty list")

    expected_sources = {}
    seen_basenames = set()
    expected_hashes = {}

    for entry in sources_list:
        rel_path = entry.get('relative_path', '')
        if not rel_path or not isinstance(rel_path, str):
            raise ValueError("Empty or invalid relative_path in generated sources manifest")
        norm_rel = rel_path.replace('\\', '/')
        if norm_rel.startswith('/'):
            raise ValueError(f"Absolute or leading-slash path forbidden in manifest: '{rel_path}'")
        parts = norm_rel.split('/')
        if '..' in parts:
            raise ValueError(f"Path traversal '..' forbidden in manifest: '{rel_path}'")

        base_name = Path(norm_rel).name
        if base_name in seen_basenames:
            raise ValueError(f"Duplicate basename in generated sources manifest: '{base_name}'")
        seen_basenames.add(base_name)

        resolved_file = (codegen_folder / norm_rel).resolve()
        if not is_within(resolved_file, codegen_folder):
            raise ValueError(f"Source file '{rel_path}' resolves outside codegen_folder '{codegen_folder}'")

        exp_sha = entry.get('sha256')
        if not exp_sha:
            raise ValueError(f"Missing sha256 in manifest for '{rel_path}'")

        expected_sources[base_name] = {
            'relative_path': rel_path,
            'sha256': exp_sha,
            'size_bytes': entry.get('size_bytes'),
            'resolved_path': resolved_file,
        }
        expected_hashes[base_name] = exp_sha

    for req in REQUIRED_GENERATED_SOURCES:
        if req not in expected_sources:
            raise ValueError(f"Required generated source '{req}' missing from manifest")

    verified_sources = {}
    for req in REQUIRED_GENERATED_SOURCES:
        src_path = expected_sources[req]['resolved_path']
        if not src_path.is_file():
            raise FileNotFoundError(f"Required generated source file not found on disk: '{src_path}'")
        actual_hash = digest(src_path)
        expected_hash = expected_hashes[req]
        if actual_hash != expected_hash:
            raise ValueError(
                f"Generated source SHA mismatch for '{req}': expected '{expected_hash}', got '{actual_hash}'"
            )
        verified_sources[req] = {
            'path': str(src_path),
            'sha256': actual_hash,
            'size_bytes': src_path.stat().st_size,
        }

    return {
        'evidence_dir': str(evidence_dir),
        'generation_run_id': evidence_dir.name,
        'codegen_source_dir': str(codegen_source_dir),
        'codegen_folder': str(codegen_folder),
        'verified_sources': verified_sources,
        'expected_hashes': expected_hashes,
        'summary': summary,
    }


def verify_external_prerequisites(
    matlab_include_dir: Path,
    wrapper_source: Path,
) -> Dict[str, Dict[str, Any]]:
    """Verify presence and validity of MathWorks include headers and model wrapper."""
    inc_dir = Path(matlab_include_dir).resolve()
    if not inc_dir.is_dir():
        raise FileNotFoundError(f"MathWorks include directory not found: '{inc_dir}'")

    headers = ['rtw_continuous.h', 'rtw_solver.h']
    result = {}
    for hdr in headers:
        hdr_path = inc_dir / hdr
        if not hdr_path.is_file():
            raise FileNotFoundError(f"Required MathWorks header not found: '{hdr_path}'")
        size = hdr_path.stat().st_size
        if size == 0:
            raise ValueError(f"MathWorks header is empty: '{hdr_path}'")
        result[hdr] = {
            'path': str(hdr_path),
            'sha256': digest(hdr_path),
            'size_bytes': size,
        }

    wrap_path = Path(wrapper_source).resolve()
    if not wrap_path.is_file():
        raise FileNotFoundError(f"Model wrapper source not found: '{wrap_path}'")
    wrap_size = wrap_path.stat().st_size
    if wrap_size == 0:
        raise ValueError(f"Model wrapper source is empty: '{wrap_path}'")
    result['model.cpp'] = {
        'path': str(wrap_path),
        'sha256': digest(wrap_path),
        'size_bytes': wrap_size,
    }

    return result


class WslRunner:
    """Execute commands in WSL Ubuntu environment."""

    def __init__(self, distro: str = DEFAULT_WSL_DISTRO, user: str = DEFAULT_WSL_USER):
        self.distro = distro
        self.user = user

    def run_bash(self, bash_cmd: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
        """Execute a bash command string in the configured WSL distribution with console window hidden."""
        cmd = ['wsl', '-d', self.distro, '-u', self.user, 'bash', '-c', bash_cmd]
        creationflags = 0x08000000 if sys.platform == 'win32' else 0
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=creationflags)

    def check_dir_empty_or_new(self, wsl_dir: str) -> None:
        """Verify that a WSL directory does not exist or is completely empty and not a symlink."""
        quoted_dir = shlex.quote(wsl_dir)
        check_cmd = (
            f"if [ -L {quoted_dir} ]; then echo 'SYMLINK'; "
            f"elif [ -d {quoted_dir} ] && [ \"$(ls -A {quoted_dir} 2>/dev/null)\" ]; then echo 'NON_EMPTY'; "
            f"else echo 'OK'; fi"
        )
        res = self.run_bash(check_cmd, timeout=10.0)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to inspect WSL directory '{wsl_dir}': {res.stderr}")
        status = res.stdout.strip()
        if status == 'SYMLINK':
            raise ValueError(f"Refusing to use symlink as WSL build directory: '{wsl_dir}'")
        if status == 'NON_EMPTY':
            raise ValueError(f"Refusing to reuse non-empty WSL build directory: '{wsl_dir}'")

    def get_toolchain_version(self) -> str:
        """Retrieve g++ version string from WSL."""
        res = self.run_bash('g++ --version', timeout=10.0)
        if res.returncode != 0:
            raise RuntimeError(f"g++ is not available in WSL: {res.stderr}")
        return res.stdout.splitlines()[0].strip() if res.stdout else 'unknown'


def audit_ldd_output(ldd_text: str) -> Tuple[bool, List[str], List[str]]:
    """Audit ldd output for dynamic dependencies.

    Returns:
    - is_clean: bool (True if no disallowed dependencies or missing dependencies found)
    - dependencies: List[str] (all resolved library basenames)
    - violations: List[str] (any matching disallowed substrings or 'not found')
    """
    dependencies = []
    violations = []
    for line in ldd_text.splitlines():
        line = line.strip()
        if not line:
            continue

        lower_line = line.lower()
        if 'not found' in lower_line:
            violations.append(f"Missing dynamic dependency in ldd output: '{line}'")

        parts = line.split('=>')
        lib_token = parts[0].strip().split()[0]
        dependencies.append(lib_token)

        for disallowed in DISALLOWED_DEP_SUBSTRINGS:
            if disallowed in lower_line:
                violations.append(f"{lib_token} matches '{disallowed}'")

    is_clean = len(violations) == 0
    return is_clean, dependencies, violations


PROBE_PYTHON_SNIPPET = r"""
import json
import math
import os
from pathlib import Path
import sys

def run_probe(so_path_str, steps, project_root_str=None):
    lib_path = Path(so_path_str).resolve()
    if not lib_path.is_file():
        return {"success": False, "error": f"Library file not found: {lib_path}"}

    model_cls = None
    if project_root_str:
        p_root = Path(project_root_str).resolve()
        if p_root.is_dir():
            sys.path.insert(0, str(p_root))
            try:
                from Simulator.wksim_core.model import Model
                model_cls = Model
            except Exception:
                model_cls = None

    if model_cls is not None:
        try:
            with model_cls(str(lib_path)) as model:
                last_output = []
                for s in range(steps):
                    out = model.step([0.5] * 16, steps=1)
                    if not all(math.isfinite(x) for x in out):
                        return {
                            "success": False,
                            "error": f"Non-finite output at step {s}",
                            "step": s,
                        }
                    last_output = out

                dt = 0.001
                return {
                    "success": True,
                    "steps_evaluated": model.ticks,
                    "step_size_seconds": dt,
                    "sim_time_seconds": round(model.ticks * dt, 6),
                    "all_outputs_finite": True,
                    "non_finite_step": None,
                    "output_dimension": 120,
                    "copter_id": last_output[0] if last_output else None,
                    "vehicle_type": last_output[1] if len(last_output) > 1 else None,
                    "sample_head": last_output[:8] if last_output else [],
                    "sample_tail": last_output[-8:] if last_output else [],
                }
        except Exception as ex:
            return {"success": False, "error": f"Model class execution failed: {ex}"}
    else:
        import ctypes
        lib = ctypes.CDLL(str(lib_path))
        lib.wk_model_create.argtypes = []
        lib.wk_model_create.restype = ctypes.c_void_p
        lib.wk_model_destroy.argtypes = [ctypes.c_void_p]
        lib.wk_model_destroy.restype = None
        lib.wk_model_step.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
        ]
        lib.wk_model_step.restype = ctypes.c_int

        handle = lib.wk_model_create()
        if not handle:
            return {"success": False, "error": "wk_model_create() returned NULL handle"}

        in_vals = [0.5] * 16
        in_arr = (ctypes.c_double * 16)(*in_vals)
        out_arr = (ctypes.c_double * 120)()

        dt = 0.001
        ticks = 0
        all_finite = True
        non_finite_step = None
        last_output = []

        try:
            for s in range(steps):
                rc = lib.wk_model_step(handle, in_arr, 16, 1, out_arr, 120)
                if rc != 0:
                    return {
                        "success": False,
                        "error": f"wk_model_step returned status {rc} at step {s}",
                        "step": s,
                    }
                ticks += 1
                vals = list(out_arr)
                if not all(math.isfinite(x) for x in vals):
                    all_finite = False
                    non_finite_step = s
                    last_output = vals
                    break

                sim_time = vals[2]
                expected_time = ticks * dt
                if abs(sim_time - expected_time) > 1e-8:
                    return {
                        "success": False,
                        "error": f"Clock desync at step {s}: sim_time={sim_time}, expected={expected_time}",
                        "step": s,
                    }
                last_output = vals

            return {
                "success": all_finite,
                "steps_evaluated": ticks,
                "step_size_seconds": dt,
                "sim_time_seconds": round(ticks * dt, 6),
                "all_outputs_finite": all_finite,
                "non_finite_step": non_finite_step,
                "output_dimension": 120,
                "copter_id": last_output[0] if last_output else None,
                "vehicle_type": last_output[1] if len(last_output) > 1 else None,
                "sample_head": last_output[:8] if last_output else [],
                "sample_tail": last_output[-8:] if last_output else [],
            }
        finally:
            lib.wk_model_destroy(handle)

if __name__ == "__main__":
    so_arg = sys.argv[1]
    steps_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    root_arg = sys.argv[3] if len(sys.argv) > 3 else None
    res = run_probe(so_arg, steps_arg, root_arg)
    print(json.dumps(res))
    if not res.get("success", False):
        sys.exit(1)
"""


def build_and_evaluate(
    generation_evidence_dir: Path = DEFAULT_GENERATION_DIR,
    codegen_source_dir: Optional[Path] = None,
    matlab_include_dir: Path = DEFAULT_MATLAB_INCLUDE,
    wrapper_source: Path = DEFAULT_WRAPPER_SOURCE,
    build_id: str = 'short-cycle-01',
    evidence_dir: Optional[Path] = None,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    wsl_user: str = DEFAULT_WSL_USER,
    wsl_build_dir: Optional[str] = None,
    run_test: bool = False,
    test_steps: int = 100,
    timeout: float = 120.0,
    project_root: Path = ROOT,
    runner: Optional[WslRunner] = None,
) -> Dict[str, Any]:
    """Execute the full standalone Linux build and evaluation workflow."""
    start_time = time.time()
    started_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time))
    validate_build_id(build_id)

    folder_name = build_id if build_id.startswith('codegen-e0-build-') else f"codegen-e0-build-{build_id}"
    if evidence_dir is None:
        evidence_dir = (evidence_root / folder_name).resolve()
    else:
        evidence_dir = Path(evidence_dir).resolve()
    validate_evidence_containment(evidence_dir, project_root=project_root)

    if wsl_build_dir is None:
        wsl_build_dir = f"/root/wksim-{folder_name}"
    validate_wsl_build_dir(wsl_build_dir)

    if runner is None:
        runner = WslRunner(distro=wsl_distro, user=wsl_user)

    runner.check_dir_empty_or_new(wsl_build_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    gen_evidence = verify_generation_evidence(
        generation_evidence_dir=generation_evidence_dir,
        codegen_source_dir=codegen_source_dir,
        project_root=project_root,
    )
    codegen_dir = Path(gen_evidence['codegen_source_dir'])

    ext_prereqs = verify_external_prerequisites(
        matlab_include_dir=matlab_include_dir,
        wrapper_source=wrapper_source,
    )

    initial_expected_hashes = {}
    initial_expected_hashes.update(gen_evidence['expected_hashes'])
    for fname, p_info in ext_prereqs.items():
        initial_expected_hashes[fname] = p_info['sha256']

    toolchain_version = runner.get_toolchain_version()

    mkdir_res = runner.run_bash(f"mkdir -p {shlex.quote(wsl_build_dir)}", timeout=15.0)
    if mkdir_res.returncode != 0:
        raise RuntimeError(f"Failed to create WSL build directory '{wsl_build_dir}': {mkdir_res.stderr}")

    staged_manifest = {}
    files_to_copy = {
        'Exp1_MinModelTemp.cpp': codegen_dir / 'Exp1_MinModelTemp.cpp',
        'Exp1_MinModelTemp.h': codegen_dir / 'Exp1_MinModelTemp.h',
        'rtwtypes.h': codegen_dir / 'rtwtypes.h',
        'model.cpp': Path(wrapper_source).resolve(),
        'rtw_continuous.h': Path(matlab_include_dir).resolve() / 'rtw_continuous.h',
        'rtw_solver.h': Path(matlab_include_dir).resolve() / 'rtw_solver.h',
    }

    for name in EXCLUDED_BUILD_SOURCES:
        if name in files_to_copy:
            del files_to_copy[name]

    for fname, local_path in files_to_copy.items():
        wsl_src = to_wsl_path(local_path)
        wsl_dst = f"{wsl_build_dir}/{fname}"
        cp_cmd = f"cp {shlex.quote(wsl_src)} {shlex.quote(wsl_dst)}"
        cp_res = runner.run_bash(cp_cmd, timeout=15.0)
        if cp_res.returncode != 0:
            raise RuntimeError(f"Failed to copy '{fname}' to WSL: {cp_res.stderr}")

        sha_cmd = f"sha256sum {shlex.quote(wsl_dst)}"
        sha_res = runner.run_bash(sha_cmd, timeout=10.0)
        if sha_res.returncode != 0:
            raise RuntimeError(f"Failed to checksum staged file '{wsl_dst}': {sha_res.stderr}")
        staged_hash = sha_res.stdout.split()[0].strip()

        expected_initial_hash = initial_expected_hashes[fname]
        if staged_hash != expected_initial_hash:
            raise RuntimeError(
                f"Staged file checksum mismatch for '{fname}': expected {expected_initial_hash}, got {staged_hash}"
            )

        staged_manifest[fname] = {
            'source_path': str(local_path),
            'wsl_staged_path': wsl_dst,
            'sha256': staged_hash,
            'size_bytes': local_path.stat().st_size,
        }

    # Pre-compilation integrity re-verification in WSL against initial expected SHA
    for fname in files_to_copy:
        wsl_dst = f"{wsl_build_dir}/{fname}"
        sha_check_res = runner.run_bash(f"sha256sum {shlex.quote(wsl_dst)}", timeout=10.0)
        if sha_check_res.returncode != 0:
            raise RuntimeError(f"Failed to verify staged file before compilation: {wsl_dst}")
        current_staged_hash = sha_check_res.stdout.split()[0].strip()
        if current_staged_hash != initial_expected_hashes[fname]:
            raise RuntimeError(
                f"Pre-compilation integrity verification failed for '{fname}': expected {initial_expected_hashes[fname]}, got {current_staged_hash}"
            )

    library_name = 'libwksim_e0.so'
    compile_cmd = (
        f"cd {shlex.quote(wsl_build_dir)} && "
        f"g++ {' '.join(COMPILER_FLAGS)} -I. Exp1_MinModelTemp.cpp model.cpp -o {shlex.quote(library_name)}"
    )
    compile_res = runner.run_bash(compile_cmd, timeout=timeout)

    (evidence_dir / 'build.stdout.log').write_text(compile_res.stdout, encoding='utf-8')
    (evidence_dir / 'build.stderr.log').write_text(compile_res.stderr, encoding='utf-8')

    finished_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time()))

    if compile_res.returncode != 0:
        summary_failed = {
            'status': 'failed',
            'scope': 'Simulink e0 standalone Linux compilation and execution probe; zero runtime MATLAB dependency; no flight or G6 equivalence claim',
            'build_id': build_id,
            'generation_run_id': gen_evidence['generation_run_id'],
            'generation_evidence_dir': str(Path(generation_evidence_dir).resolve()),
            'compiler_return_code': compile_res.returncode,
            'compiler': toolchain_version,
            'wsl_build_dir': wsl_build_dir,
            'error': compile_res.stderr,
            'evidence_directory': str(evidence_dir),
        }
        write_json(evidence_dir / 'summary.json', summary_failed)
        command_failed = {
            'argv': compile_cmd,
            'compiler': toolchain_version,
            'wsl_distro': wsl_distro,
            'wsl_user': wsl_user,
            'wsl_build_dir': wsl_build_dir,
            'timeout_seconds': timeout,
            'started_utc': started_iso,
            'finished_utc': finished_iso,
            'return_code': compile_res.returncode,
            'library_sha256': None,
        }
        write_json(evidence_dir / 'command.json', command_failed)
        return summary_failed

    stat_cmd = f"sha256sum {shlex.quote(wsl_build_dir + '/' + library_name)} && stat -c %s {shlex.quote(wsl_build_dir + '/' + library_name)}"
    stat_res = runner.run_bash(stat_cmd, timeout=10.0)
    if stat_res.returncode != 0:
        raise RuntimeError(f"Failed to stat compiled library: {stat_res.stderr}")
    lines = stat_res.stdout.strip().splitlines()
    library_sha256 = lines[0].split()[0].strip()
    library_size = int(lines[1].strip()) if len(lines) > 1 else 0

    ldd_cmd = f"ldd {shlex.quote(wsl_build_dir + '/' + library_name)}"
    ldd_res = runner.run_bash(ldd_cmd, timeout=10.0)
    ldd_text = ldd_res.stdout
    (evidence_dir / 'ldd.txt').write_text(ldd_text, encoding='utf-8')

    is_clean, deps, violations = audit_ldd_output(ldd_text)
    if not is_clean:
        summary_failed = {
            'status': 'failed',
            'scope': 'Simulink e0 standalone Linux compilation and execution probe; zero runtime MATLAB dependency; no flight or G6 equivalence claim',
            'build_id': build_id,
            'generation_run_id': gen_evidence['generation_run_id'],
            'generation_evidence_dir': str(Path(generation_evidence_dir).resolve()),
            'compiler_return_code': 0,
            'compiler': toolchain_version,
            'wsl_build_dir': wsl_build_dir,
            'clean_runtime_deps': False,
            'violations': violations,
            'error': f"Dynamic dependency audit failed: {violations}",
            'evidence_directory': str(evidence_dir),
        }
        write_json(evidence_dir / 'summary.json', summary_failed)
        command_failed = {
            'argv': compile_cmd,
            'compiler': toolchain_version,
            'wsl_distro': wsl_distro,
            'wsl_user': wsl_user,
            'wsl_build_dir': wsl_build_dir,
            'timeout_seconds': timeout,
            'started_utc': started_iso,
            'finished_utc': finished_iso,
            'return_code': 1,
            'library_sha256': library_sha256,
        }
        write_json(evidence_dir / 'command.json', command_failed)
        return summary_failed

    test_result = None
    final_status = 'built'
    if run_test:
        probe_py_wsl = f"{wsl_build_dir}/probe_runner.py"
        quoted_probe_file = shlex.quote(probe_py_wsl)
        write_probe_cmd = f"cat << 'EOF' > {quoted_probe_file}\n{PROBE_PYTHON_SNIPPET.strip()}\nEOF"
        wr_res = runner.run_bash(write_probe_cmd, timeout=10.0)
        if wr_res.returncode != 0:
            raise RuntimeError(f"Failed to deploy probe runner in WSL: {wr_res.stderr}")

        quoted_so = shlex.quote(f"{wsl_build_dir}/{library_name}")
        quoted_root = shlex.quote(to_wsl_path(project_root))
        exec_probe_cmd = f"python3 {quoted_probe_file} {quoted_so} {test_steps} {quoted_root}"
        probe_res = runner.run_bash(exec_probe_cmd, timeout=60.0)
        if probe_res.stdout:
            try:
                test_result = json.loads(probe_res.stdout.strip().splitlines()[-1])
            except json.JSONDecodeError:
                test_result = {'success': False, 'raw_output': probe_res.stdout, 'raw_error': probe_res.stderr}
        else:
            test_result = {'success': False, 'raw_error': probe_res.stderr}

        write_json(evidence_dir / 'test-probe.json', test_result)

        if probe_res.returncode == 0 and test_result.get('success', False):
            final_status = 'tested'
        else:
            final_status = 'test_failed'

    elapsed = round(time.time() - start_time, 3)

    summary = {
        'status': final_status,
        'scope': 'Simulink e0 standalone Linux compilation and execution probe; zero runtime MATLAB dependency; no flight or G6 equivalence claim',
        'build_id': build_id,
        'generation_run_id': gen_evidence['generation_run_id'],
        'generation_evidence_dir': str(Path(generation_evidence_dir).resolve()),
        'wsl_build_dir': wsl_build_dir,
        'wsl_distro': wsl_distro,
        'compiler': toolchain_version,
        'compiler_flags': COMPILER_FLAGS,
        'library_name': library_name,
        'library_sha256': library_sha256,
        'library_size_bytes': library_size,
        'clean_runtime_deps': is_clean,
        'ldd_dependencies': deps,
        'excluded_files': list(EXCLUDED_BUILD_SOURCES),
        'run_test': run_test,
        'test_passed': test_result.get('success', False) if test_result else None,
        'steps_evaluated': test_result.get('steps_evaluated') if test_result else None,
        'all_outputs_finite': test_result.get('all_outputs_finite') if test_result else None,
        'elapsed_seconds': elapsed,
        'evidence_directory': str(evidence_dir),
    }
    if final_status == 'test_failed':
        summary['error'] = test_result.get('error', 'Execution probe test failed')
    write_json(evidence_dir / 'summary.json', summary)

    manifest = {
        'build_id': build_id,
        'generation_run_id': gen_evidence['generation_run_id'],
        'staged_sources': staged_manifest,
        'excluded_files': list(EXCLUDED_BUILD_SOURCES),
        'toolchain': {
            'compiler': toolchain_version,
            'flags': COMPILER_FLAGS,
            'compile_command': compile_cmd,
        },
        'output_library': {
            'filename': library_name,
            'sha256': library_sha256,
            'size_bytes': library_size,
        },
        'ldd_audit': {
            'clean': is_clean,
            'dependencies': deps,
            'violations': violations,
        },
        'test_probe': test_result,
    }
    write_json(evidence_dir / 'build-manifest.json', manifest)

    finished_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time()))
    command_info = {
        'argv': compile_cmd,
        'compiler': toolchain_version,
        'wsl_distro': wsl_distro,
        'wsl_user': wsl_user,
        'wsl_build_dir': wsl_build_dir,
        'timeout_seconds': timeout,
        'started_utc': started_iso,
        'finished_utc': finished_iso,
        'return_code': 0 if final_status in ('built', 'tested') else 1,
        'library_sha256': library_sha256,
    }
    write_json(evidence_dir / 'command.json', command_info)

    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--generation-dir',
        type=Path,
        default=DEFAULT_GENERATION_DIR,
        help=f"Path to generation evidence dir (default: {DEFAULT_GENERATION_DIR})",
    )
    parser.add_argument(
        '--codegen-source-dir',
        type=Path,
        default=None,
        help="Optional override for codegen source folder containing Exp1_MinModelTemp.cpp",
    )
    parser.add_argument(
        '--matlab-include-dir',
        type=Path,
        default=DEFAULT_MATLAB_INCLUDE,
        help=f"Path to MathWorks simulink include dir (default: {DEFAULT_MATLAB_INCLUDE})",
    )
    parser.add_argument(
        '--wrapper-source',
        type=Path,
        default=DEFAULT_WRAPPER_SOURCE,
        help=f"Path to model.cpp wrapper (default: {DEFAULT_WRAPPER_SOURCE})",
    )
    parser.add_argument(
        '--build-id',
        type=str,
        default='short-cycle-01',
        help="Identifier for this build run (^[a-zA-Z0-9_-]+$)",
    )
    parser.add_argument(
        '--evidence-dir',
        type=Path,
        default=None,
        help="Explicit destination directory for evidence artifacts",
    )
    parser.add_argument(
        '--evidence-root',
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help=f"Root directory for build evidence (default: {DEFAULT_EVIDENCE_ROOT})",
    )
    parser.add_argument(
        '--wsl-distro',
        type=str,
        default=DEFAULT_WSL_DISTRO,
        help=f"WSL distribution name (default: {DEFAULT_WSL_DISTRO})",
    )
    parser.add_argument(
        '--wsl-user',
        type=str,
        default=DEFAULT_WSL_USER,
        help=f"WSL username (default: {DEFAULT_WSL_USER})",
    )
    parser.add_argument(
        '--wsl-build-dir',
        type=str,
        default=None,
        help="Explicit WSL build directory (default: /root/wksim-codegen-e0-build-<build_id>)",
    )
    parser.add_argument(
        '--run-test',
        action='store_true',
        help="Execute 1ms fixed-step finite output probe after compilation",
    )
    parser.add_argument(
        '--test-steps',
        type=int,
        default=100,
        help="Number of steps for the probe test (default: 100)",
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=120.0,
        help="Compilation timeout in seconds (default: 120.0)",
    )

    args = parser.parse_args()

    try:
        summary = build_and_evaluate(
            generation_evidence_dir=args.generation_dir,
            codegen_source_dir=args.codegen_source_dir,
            matlab_include_dir=args.matlab_include_dir,
            wrapper_source=args.wrapper_source,
            build_id=args.build_id,
            evidence_dir=args.evidence_dir,
            evidence_root=args.evidence_root,
            wsl_distro=args.wsl_distro,
            wsl_user=args.wsl_user,
            wsl_build_dir=args.wsl_build_dir,
            run_test=args.run_test,
            test_steps=args.test_steps,
            timeout=args.timeout,
        )
        if summary.get('status') in ('failed', 'test_failed'):
            print(f"Build {summary['status']}: {summary.get('error', 'unknown error')}", file=sys.stderr)
            sys.exit(summary.get('compiler_return_code') or 1)

        print(f"Build complete. Status: {summary['status']}")
        print(f"Library: {summary['library_name']} (SHA256: {summary['library_sha256']})")
        print(f"Evidence: {summary['evidence_directory']}")
        sys.exit(0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
