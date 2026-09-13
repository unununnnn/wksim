"""Standalone Linux build and major recorder execution driver for generated e0 Simulink model.

Builds major_model_recorder in WSL Ubuntu 22.04 from verified Embedded Coder C++ artifacts
and tools/major_model_recorder.cpp, with zero runtime MATLAB dependency.
Instruments a private copy of Exp1_MinModelTemp.cpp with wk_capture_major read-only callback
at the exact point where root major outputs are assembled before ODE4 continuous state update.
Validates parity against the unmodified 11.8 model library (libwksim_e0.so).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_generated_e0 import (
    DEFAULT_GENERATION_DIR,
    DEFAULT_MATLAB_INCLUDE,
    DEFAULT_WSL_DISTRO,
    DEFAULT_WSL_USER,
    WslRunner,
    audit_ldd_output,
    digest,
    to_wsl_path,
    validate_build_id,
    validate_evidence_containment,
    verify_generation_evidence,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDER_SOURCE = ROOT / 'tools/major_model_recorder.cpp'
DEFAULT_POST_REFERENCE_SOURCE = ROOT / 'tools/generated_e0_post_reference.cpp'
DEFAULT_INPUT_CSV = ROOT / 'validation/numerical-contract-20260909/inputs/C0.csv'
DEFAULT_EVIDENCE_ROOT = ROOT / 'validation'
DEFAULT_REFERENCE_LIB = None
DEFAULT_REFERENCE_MANIFEST = ROOT / 'validation/codegen-e0-build-short-cycle-01/build-manifest.json'
REFERENCE_SO_11_8_SHA256 = '7da6853201b89238c273f2e1360ad21fe479e267d0ed08cf3500f98bf535505e'

CPP_11_8_SHA256 = '2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274'
PATCHED_CPP_11_8_SHA256 = '993f33ea3cfcd282418599c94ce6ef4d6265add76f7d9763039965f6c6c1dc9d'
EXPECTED_INSERTION_LINE = 7919

INCLUDE = b'#include "Exp1_MinModelTemp.h"\r\n'
DECLARATION = b'extern void wk_capture_major(const ExtY_Exp1_MinModelTemp_T&) noexcept;\r\n'
OUTPUT_END = (
    b'  std::memcpy(&Exp1_MinModelTemp_Y.VehileInfo60d[33],\r\n'
    b'              &Exp1_MinModelTemp_P.Constant_Value_ea[0], 27U * sizeof(real_T));\r\n'
)
NEXT_CONTEXT = (
    b'  if (rtmIsMajorTimeStep((&Exp1_MinModelTemp_M))) {\r\n'
    b"    // If: '<S13>/If1' incorporates:\r\n"
)
HOOK = (
    b'  if (rtmIsMajorTimeStep((&Exp1_MinModelTemp_M))) {\r\n'
    b'    wk_capture_major(Exp1_MinModelTemp_Y);\r\n'
    b'  }\r\n'
)

COMPILER_FLAGS = [
    '-std=c++17',
    '-O2',
    '-fno-fast-math',
    '-Wl,--no-undefined',
]

PARITY_CHECK_PYTHON_SNIPPET = r"""
import ctypes
import json
import math
import os
from pathlib import Path
import subprocess
import sys

def strict_numeric_fields(value):
    for key in ('schema_version','k','call_number','major_capture_count','attempted_calls','returned_calls','emitted_samples'):
        if key in value and type(value[key]) is not int:
            raise ValueError(f'{key} must be an integer, not a boolean')
    for key in ('input_time_s','engine_before_s','engine_after_s','engine_end_s','comparison_end_s'):
        if key in value and (type(value[key]) not in (int,float) or not math.isfinite(value[key])):
            raise ValueError(f'{key} must be a finite numeric time')
    for key in ('inPWMs','TerrainIn15d','Vehicle60','Sensor30','GPS30'):
        if key in value and (not isinstance(value[key],list) or any(type(x) not in (int,float)
                or not math.isfinite(x) for x in value[key])):
            raise ValueError(f'Non-finite recorded value, nonnumeric value or boolean in {key}')
    return value

def check_parity(record_jsonl_path, ref_target, csv_input_path):
    # 1. Parse and validate input CSV
    csv_p = Path(csv_input_path)
    if not csv_p.exists():
        return {"success": False, "error": f"Input CSV file does not exist: '{csv_input_path}'"}
    try:
        csv_raw = csv_p.read_text(encoding='ascii')
    except Exception as err:
        return {"success": False, "error": f"Failed to read input CSV as ASCII: {err}"}

    csv_lines = [l.strip() for l in csv_raw.splitlines() if l.strip()]
    if not csv_lines:
        return {"success": False, "error": "Empty input CSV"}
    header = csv_lines[0]
    expected_header = "k,time_s" + "".join(f",inPWMs{i}" for i in range(16)) + "".join(f",TerrainIn15d{i}" for i in range(15))
    if header != expected_header:
        return {"success": False, "error": f"Invalid CSV header: expected '{expected_header}', got '{header}'"}

    rows = []
    has_nonzero_terrain = False
    for idx, line in enumerate(csv_lines[1:]):
        cells = line.split(',')
        if len(cells) != 33:
            return {"success": False, "error": f"Row {idx} has {len(cells)} cells, expected 33"}
        try:
            k_val = int(cells[0])
            t_val = float(cells[1])
            pwms = [float(x) for x in cells[2:18]]
            terrains = [float(x) for x in cells[18:33]]
        except ValueError as err:
            return {"success": False, "error": f"Non-numeric cell at CSV row {idx}: {err}"}

        if k_val != idx:
            return {"success": False, "error": f"CSV row index mismatch at row {idx}: k={k_val}"}
        if not math.isfinite(t_val) or abs(t_val - idx * 0.001) > 1e-12:
            return {"success": False, "error": f"CSV time mismatch at row {idx}: time={t_val}, expected {idx*0.001}"}
        for pwm_idx, p in enumerate(pwms):
            if not math.isfinite(p) or p < 0.0 or p > 1.0:
                return {"success": False, "error": f"Invalid PWM{pwm_idx} at row {idx}: {p}"}
        for terr_idx, tr in enumerate(terrains):
            if not math.isfinite(tr):
                return {"success": False, "error": f"Non-finite Terrain{terr_idx} at row {idx}: {tr}"}
            if tr != 0.0:
                has_nonzero_terrain = True
        rows.append({"k": k_val, "time": t_val, "pwms": pwms, "terrains": terrains})

    if len(rows) != 501:
        return {"success": False, "error": f"Expected exactly 501 CSV rows, got {len(rows)}"}

    # Reference mode detection: shared library (.so) vs 31-input post reference
    is_ref_so = str(ref_target).endswith('.so')
    if is_ref_so and has_nonzero_terrain:
        return {
            "success": False,
            "error": "Non-zero TerrainIn15d detected in input CSV, but reference shared library ABI only accepts 16 PWM inputs; full 31-input reference driver required"
        }

    # 2. Parse and validate record.jsonl strictly
    rec_p = Path(record_jsonl_path)
    if not rec_p.exists():
        return {"success": False, "error": f"Major record file does not exist: '{record_jsonl_path}'"}
    try:
        record_text = rec_p.read_text(encoding='utf-8')
    except Exception as err:
        return {"success": False, "error": f"Failed to read record.jsonl: {err}"}

    record_lines = [l.strip() for l in record_text.splitlines() if l.strip()]
    if len(record_lines) != 503:
        return {
            "success": False,
            "error": f"Expected exactly 503 records in record.jsonl (1 start, 501 samples, 1 end), got {len(record_lines)}"
        }

    # Check start record (line 0)
    try:
        start_obj = json.loads(record_lines[0],object_hook=strict_numeric_fields)
    except Exception as err:
        return {"success": False, "error": f"JSON parse error in start record (line 1): {err}"}
    if start_obj.get("kind") != "major_recorder_start":
        return {"success": False, "error": f"Expected major_recorder_start in line 1, got '{start_obj.get('kind')}'"}
    if start_obj.get("schema_version") != 1:
        return {"success": False, "error": f"Expected schema_version 1 in start record, got {start_obj.get('schema_version')}"}

    # Check terminal end record (line 502)
    try:
        end_obj = json.loads(record_lines[502],object_hook=strict_numeric_fields)
    except Exception as err:
        return {"success": False, "error": f"JSON parse error in terminal record (line 503): {err}"}
    if end_obj.get("kind") != "major_recorder_end":
        return {"success": False, "error": f"Missing terminal record: line 503 kind is '{end_obj.get('kind')}'"}
    if end_obj.get("status") != "complete":
        return {"success": False, "error": f"Terminal record status is '{end_obj.get('status')}', expected 'complete'"}
    if end_obj.get("attempted_calls") != 501 or end_obj.get("returned_calls") != 501 or end_obj.get("emitted_samples") != 501:
        return {"success": False, "error": "Terminal record call count mismatch"}
    end_engine = end_obj.get("engine_end_s", float('nan'))
    if not (math.isfinite(end_engine) and abs(end_engine - 0.501) <= 1e-12):
        return {"success": False, "error": f"Terminal engine end time mismatch: expected 0.501, got {end_engine}"}
    end_comp = end_obj.get("comparison_end_s", float('nan'))
    if not (math.isfinite(end_comp) and abs(end_comp - 0.500) <= 1e-12):
        return {"success": False, "error": f"Terminal comparison end time mismatch: expected 0.500, got {end_comp}"}

    # Check 501 sample records (lines 1..501)
    rec_samples = []
    for k in range(501):
        line_idx = k + 1
        try:
            obj = json.loads(record_lines[line_idx],object_hook=strict_numeric_fields)
        except Exception as err:
            return {"success": False, "error": f"JSON parse error in sample at line {line_idx+1} (step k={k}): {err}"}

        if obj.get("kind") != "major_recorder_sample":
            return {"success": False, "error": f"Record at line {line_idx+1} has kind '{obj.get('kind')}', expected 'major_recorder_sample'"}
        if obj.get("schema_version") != 1:
            return {"success": False, "error": f"Expected schema_version 1 at sample line {line_idx+1}"}
        if obj.get("k") != k:
            return {"success": False, "error": f"Step index mismatch at line {line_idx+1}: expected k={k}, got {obj.get('k')}"}
        if obj.get("call_number") != k + 1:
            return {"success": False, "error": f"Call number mismatch at step k={k}: expected {k+1}, got {obj.get('call_number')}"}
        in_t = obj.get("input_time_s", float('nan'))
        if not (math.isfinite(in_t) and abs(in_t - k * 0.001) <= 1e-12):
            return {"success": False, "error": f"Input time mismatch at step k={k}: expected {k*0.001}, got {in_t}"}
        eng_bef = obj.get("engine_before_s", float('nan'))
        if not (math.isfinite(eng_bef) and abs(eng_bef - k * 0.001) <= 1e-12):
            return {"success": False, "error": f"Engine before time mismatch at step k={k}: expected {k*0.001}, got {eng_bef}"}
        eng_aft = obj.get("engine_after_s", float('nan'))
        if not (math.isfinite(eng_aft) and abs(eng_aft - (k + 1) * 0.001) <= 1e-12):
            return {"success": False, "error": f"Engine after time mismatch at step k={k}: expected {(k+1)*0.001}, got {eng_aft}"}
        if obj.get("major_capture_count") != 1:
            return {"success": False, "error": f"major_capture_count at step k={k} is {obj.get('major_capture_count')}, expected 1"}
        if obj.get("step_status") != "complete":
            return {"success": False, "error": f"step_status at step k={k} is '{obj.get('step_status')}', expected 'complete'"}

        # Validate input signals match CSV
        rec_pwms = obj.get("inPWMs")
        if not isinstance(rec_pwms, list) or len(rec_pwms) != 16 or rec_pwms != rows[k]["pwms"]:
            return {"success": False, "error": f"inPWMs mismatch at step k={k}"}
        rec_terrains = obj.get("TerrainIn15d")
        if not isinstance(rec_terrains, list) or len(rec_terrains) != 15 or rec_terrains != rows[k]["terrains"]:
            return {"success": False, "error": f"TerrainIn15d mismatch at step k={k}"}

        # Validate recorded outputs structure and finite values
        rec_post = obj.get("post_step_api")
        if not isinstance(rec_post, dict):
            return {"success": False, "error": f"Missing or invalid post_step_api at step k={k}"}
        rec_vals = []
        for grp, exp_len in [("Vehicle60", 60), ("Sensor30", 30), ("GPS30", 30)]:
            vals = rec_post.get(grp)
            if not isinstance(vals, list) or len(vals) != exp_len:
                return {"success": False, "error": f"post_step_api['{grp}'] at step k={k} must have length {exp_len}"}
            for d_idx, val in enumerate(vals):
                if not (isinstance(val, (int, float)) and math.isfinite(val)):
                    return {"success": False, "error": f"Non-finite recorded value in post_step_api['{grp}'][{d_idx}] at step k={k}: {val}"}
            rec_vals.extend(vals)

        rec_maj = obj.get("major_root_outputs")
        if not isinstance(rec_maj, dict):
            return {"success": False, "error": f"Missing or invalid major_root_outputs at step k={k}"}
        for grp, exp_len in [("Vehicle60", 60), ("Sensor30", 30), ("GPS30", 30)]:
            vals = rec_maj.get(grp)
            if not isinstance(vals, list) or len(vals) != exp_len:
                return {"success": False, "error": f"major_root_outputs['{grp}'] at step k={k} must have length {exp_len}"}
            for d_idx, val in enumerate(vals):
                if not (isinstance(val, (int, float)) and math.isfinite(val)):
                    return {"success": False, "error": f"Non-finite recorded value in major_root_outputs['{grp}'][{d_idx}] at step k={k}: {val}"}

        rec_samples.append(rec_vals)

    # 3. Resolve reference source: .so vs .jsonl vs executable
    ref_p = Path(ref_target)
    if not ref_p.exists():
        return {"success": False, "error": f"Reference target path does not exist: '{ref_target}'"}

    is_ref_so = str(ref_target).endswith('.so')
    ref_samples = []

    if is_ref_so:
        if has_nonzero_terrain:
            return {
                "success": False,
                "error": "Non-zero TerrainIn15d detected in input CSV, but reference shared library ABI only accepts 16 PWM inputs; full 31-input reference driver required"
            }
        try:
            lib = ctypes.CDLL(str(ref_target))
        except Exception as err:
            return {"success": False, "error": f"Failed to load reference shared library '{ref_target}': {err}"}

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
            return {"success": False, "error": "wk_model_create returned NULL handle"}

        out_arr = (ctypes.c_double * 120)()
        try:
            for k in range(501):
                in_pwms = rows[k]["pwms"]
                in_arr = (ctypes.c_double * 16)(*in_pwms)
                rc = lib.wk_model_step(handle, in_arr, 16, 1, out_arr, 120)
                if rc != 0:
                    return {"success": False, "error": f"Ref model step returned status {rc} at step {k}"}
                ref_vals = list(out_arr)
                for dim, val in enumerate(ref_vals):
                    if not math.isfinite(val):
                        return {"success": False, "error": f"Non-finite reference output at step k={k}, dim={dim}: {val}"}
                ref_samples.append(ref_vals)
        finally:
            lib.wk_model_destroy(handle)

    else:
        # Non-.so reference: either a JSONL file or an executable
        if ref_p.is_file() and str(ref_target).endswith('.jsonl'):
            try:
                ref_text = ref_p.read_text(encoding='utf-8')
            except Exception as err:
                return {"success": False, "error": f"Failed to read reference JSONL file '{ref_target}': {err}"}
        elif ref_p.is_file() and os.access(str(ref_p), os.X_OK):
            # Run executable to get reference JSONL
            proc = subprocess.run([str(ref_p), "--record", str(csv_input_path)], capture_output=True, text=True)
            if proc.returncode != 0:
                return {"success": False, "error": f"Reference executable exited with {proc.returncode}: {proc.stderr}"}
            ref_text = proc.stdout
        else:
            return {"success": False, "error": f"Unsupported or unknown reference target format: '{ref_target}'"}

        ref_lines = [l.strip() for l in ref_text.splitlines() if l.strip()]
        if len(ref_lines) != 503:
            return {
                "success": False,
                "error": f"Expected exactly 503 records in reference output (1 start, 501 samples, 1 end), got {len(ref_lines)}"
            }

        # Validate reference start record (line 0)
        try:
            ref_start = json.loads(ref_lines[0],object_hook=strict_numeric_fields)
        except Exception as err:
            return {"success": False, "error": f"JSON parse error in reference start record (line 1): {err}"}
        if ref_start.get("kind") != "post_reference_start" or ref_start.get("schema_version") != 1:
            return {"success": False, "error": f"Expected post_reference_start (schema_version 1) in reference line 1, got '{ref_start.get('kind')}'"}

        # Validate reference end record (line 502)
        try:
            ref_end = json.loads(ref_lines[502],object_hook=strict_numeric_fields)
        except Exception as err:
            return {"success": False, "error": f"JSON parse error in reference terminal record (line 503): {err}"}
        if ref_end.get("kind") != "post_reference_end" or ref_end.get("status") != "complete":
            return {"success": False, "error": f"Reference terminal record missing or incomplete"}
        if ref_end.get("attempted_calls") != 501 or ref_end.get("returned_calls") != 501 or ref_end.get("emitted_samples") != 501:
            return {"success": False, "error": "Reference terminal record call count mismatch"}
        r_end_eng = ref_end.get("engine_end_s", float('nan'))
        if not (math.isfinite(r_end_eng) and abs(r_end_eng - 0.501) <= 1e-12):
            return {"success": False, "error": f"Reference terminal engine end time mismatch: expected 0.501, got {r_end_eng}"}
        r_end_comp = ref_end.get("comparison_end_s", float('nan'))
        if not (math.isfinite(r_end_comp) and abs(r_end_comp - 0.500) <= 1e-12):
            return {"success": False, "error": f"Reference terminal comparison end time mismatch: expected 0.500, got {r_end_comp}"}

        # Validate reference 501 samples (lines 1..501)
        for k in range(501):
            line_idx = k + 1
            try:
                ref_obj = json.loads(ref_lines[line_idx],object_hook=strict_numeric_fields)
            except Exception as err:
                return {"success": False, "error": f"JSON parse error in reference sample at line {line_idx+1} (step k={k}): {err}"}

            if ref_obj.get("kind") != "post_reference_sample" or ref_obj.get("schema_version") != 1:
                return {"success": False, "error": f"Expected post_reference_sample at reference line {line_idx+1}"}
            if ref_obj.get("k") != k or ref_obj.get("call_number") != k + 1:
                return {"success": False, "error": f"Reference step k or call_number mismatch at step k={k}"}

            r_in_t = ref_obj.get("input_time_s", float('nan'))
            if not (math.isfinite(r_in_t) and abs(r_in_t - k * 0.001) <= 1e-12):
                return {"success": False, "error": f"Reference input time mismatch at step k={k}: expected {k*0.001}, got {r_in_t}"}
            r_eng_bef = ref_obj.get("engine_before_s", float('nan'))
            if not (math.isfinite(r_eng_bef) and abs(r_eng_bef - k * 0.001) <= 1e-12):
                return {"success": False, "error": f"Reference engine before time mismatch at step k={k}: expected {k*0.001}, got {r_eng_bef}"}
            r_eng_aft = ref_obj.get("engine_after_s", float('nan'))
            if not (math.isfinite(r_eng_aft) and abs(r_eng_aft - (k + 1) * 0.001) <= 1e-12):
                return {"success": False, "error": f"Reference engine after time mismatch at step k={k}: expected {(k+1)*0.001}, got {r_eng_aft}"}
            if ref_obj.get("step_status") != "complete":
                return {"success": False, "error": f"Reference step_status at step k={k} is '{ref_obj.get('step_status')}', expected 'complete'"}

            # Validate input fields match CSV and major recorder line-by-line
            ref_pwms = ref_obj.get("inPWMs")
            if not isinstance(ref_pwms, list) or len(ref_pwms) != 16 or ref_pwms != rows[k]["pwms"]:
                return {"success": False, "error": f"Reference inPWMs mismatch with CSV at step k={k}"}
            ref_terrains = ref_obj.get("TerrainIn15d")
            if not isinstance(ref_terrains, list) or len(ref_terrains) != 15 or ref_terrains != rows[k]["terrains"]:
                return {"success": False, "error": f"Reference TerrainIn15d mismatch with CSV at step k={k}"}

            ref_post = ref_obj.get("post_step_api")
            if not isinstance(ref_post, dict):
                return {"success": False, "error": f"Missing or invalid post_step_api in reference at step k={k}"}
            ref_vals = []
            for grp, exp_len in [("Vehicle60", 60), ("Sensor30", 30), ("GPS30", 30)]:
                vals = ref_post.get(grp)
                if not isinstance(vals, list) or len(vals) != exp_len:
                    return {"success": False, "error": f"Reference post_step_api['{grp}'] at step k={k} must have length {exp_len}"}
                for d_idx, val in enumerate(vals):
                    if not (isinstance(val, (int, float)) and math.isfinite(val)):
                        return {"success": False, "error": f"Non-finite reference output in post_step_api['{grp}'][{d_idx}] at step k={k}: {val}"}
                ref_vals.extend(vals)
            ref_samples.append(ref_vals)

    # 4. Strict exact numerical output comparison (zero tolerance)
    if len(ref_samples) != 501 or len(rec_samples) != 501:
        return {"success": False, "error": f"Sample count mismatch: ref={len(ref_samples)}, rec={len(rec_samples)}"}

    sample_discrepancies = []
    total_discrepancies = 0
    max_abs_diff = 0.0

    for k in range(501):
        ref_v_list = ref_samples[k]
        rec_v_list = rec_samples[k]
        for dim in range(120):
            ref_v = ref_v_list[dim]
            rec_v = rec_v_list[dim]
            diff = abs(ref_v - rec_v)
            if diff > 0.0:  # STRICT ZERO TOLERANCE: any diff > 0 is a discrepancy
                total_discrepancies += 1
                if diff > max_abs_diff:
                    max_abs_diff = diff
                if len(sample_discrepancies) < 10:
                    sample_discrepancies.append({
                        "k": k,
                        "dim": dim,
                        "ref_val": ref_v,
                        "rec_val": rec_v,
                        "abs_diff": diff
                    })

    success = (total_discrepancies == 0) and (max_abs_diff == 0.0)
    return {
        "success": success,
        "steps_checked": 501,
        "dimensions_checked": 120,
        "total_values_checked": 501 * 120,
        "max_discrepancy": max_abs_diff,
        "discrepancies_count": total_discrepancies,
        "sample_discrepancies": sample_discrepancies,
        "input_binding": {
            "bound_inputs": ["inPWMs[16]"] if is_ref_so else ["inPWMs[16]", "TerrainIn15d[15]"],
            "unsupported_inputs": ["TerrainIn15d[15]"] if is_ref_so else [],
            "terrain_all_zeros_verified": not has_nonzero_terrain,
        },
        "error": None if success else f"Found {total_discrepancies} numeric discrepancies between major recorder post_step_api and reference"
    }

if __name__ == "__main__":
    res = check_parity(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(res))
    if not res.get("success", False):
        sys.exit(1)
"""

# Re-export check_parity for python runtime inspection and unit tests
_exec_globals = {}
exec(PARITY_CHECK_PYTHON_SNIPPET, _exec_globals)
check_parity = _exec_globals['check_parity']


def validate_wsl_major_dir(wsl_build_dir: str) -> None:
    """Ensure wsl_build_dir matches ^/root/wksim-e0-major-[a-zA-Z0-9_-]+$ with no traversal or shell chars."""
    if not isinstance(wsl_build_dir, str):
        raise ValueError("wsl_build_dir must be a string")
    if any(c in wsl_build_dir for c in ('\n', '\r', "'", '"', ' ', ';', '&')):
        raise ValueError(f"Invalid WSL major directory '{wsl_build_dir}': contains forbidden characters")
    if not re.match(r'^/root/wksim-e0-major-[a-zA-Z0-9_-]+$', wsl_build_dir):
        raise ValueError(
            f"Invalid WSL major directory '{wsl_build_dir}'. "
            f"Must be a direct subdirectory of /root matching ^/root/wksim-e0-major-[a-zA-Z0-9_-]+$ with no traversal."
        )


def validate_and_create_staging_dir(project_root: Path, build_id: str) -> Path:
    """Pre-check and exclusively create private staging dir strictly within work/ with zero overwriting."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', build_id):
        raise ValueError(
            f"Invalid build_id '{build_id}'. Must match ^[a-zA-Z0-9_-]+$ with no directory traversal."
        )
    work_dir = (project_root / 'work').resolve()
    if not work_dir.is_dir():
        raise FileNotFoundError(f"Project work directory does not exist: '{work_dir}'")
    stage_dir = (work_dir / f"e0-major-staging-{build_id}").resolve()

    try:
        stage_dir.relative_to(work_dir)
    except ValueError:
        raise ValueError(f"Staging directory '{stage_dir}' resolves outside work directory '{work_dir}'")

    if stage_dir.parent != work_dir:
        raise ValueError(f"Staging directory '{stage_dir}' must be a direct child of '{work_dir}'")

    if stage_dir.is_symlink():
        raise ValueError(f"Staging directory cannot be a symlink: '{stage_dir}'")

    if stage_dir.exists():
        raise FileExistsError(
            f"Staging directory already exists: '{stage_dir}'. Refusing to reuse or overwrite."
        )

    stage_dir.mkdir(parents=False, exist_ok=False)
    return stage_dir


def verify_reference_artifact(
    reference_lib: str,
    reference_manifest: Optional[Path] = None,
    expected_cpp_sha: str = CPP_11_8_SHA256,
    runner: Optional[WslRunner] = None,
) -> Dict[str, Any]:
    """Verify that reference shared library is authenticated by a valid build manifest and matches expected SHA256."""
    if reference_manifest is None:
        reference_manifest = DEFAULT_REFERENCE_MANIFEST
    ref_mf_path = Path(reference_manifest).resolve()
    if not ref_mf_path.is_file():
        raise FileNotFoundError(f"Reference build manifest not found: '{ref_mf_path}'")

    try:
        manifest = json.loads(ref_mf_path.read_text(encoding='utf-8'))
    except Exception as err:
        raise ValueError(f"Failed to parse reference build manifest '{ref_mf_path}': {err}")

    # Verify manifest source provenance
    staged_sources = manifest.get('staged_sources', {})
    cpp_info = staged_sources.get('Exp1_MinModelTemp.cpp', {})
    src_cpp_sha = cpp_info.get('sha256')
    if src_cpp_sha != expected_cpp_sha:
        raise ValueError(
            f"Reference manifest source C++ SHA256 mismatch: expected {expected_cpp_sha}, got {src_cpp_sha}"
        )

    out_lib_info = manifest.get('output_library', {})
    exp_lib_sha = out_lib_info.get('sha256')
    if not exp_lib_sha:
        raise ValueError("Reference manifest missing output_library.sha256")

    actual_lib_sha = None
    if runner is not None:
        sha_res = runner.run_bash(f"sha256sum {shlex.quote(reference_lib)}", timeout=10.0)
        if sha_res.returncode != 0:
            raise RuntimeError(f"Failed to inspect reference library in WSL '{reference_lib}': {sha_res.stderr}")
        actual_lib_sha = sha_res.stdout.split()[0].strip()
        if actual_lib_sha != exp_lib_sha:
            raise ValueError(
                f"Reference library SHA256 in WSL mismatch: manifest expects {exp_lib_sha}, actual is {actual_lib_sha}"
            )

    return {
        'type': 'shared_library',
        'wsl_path': reference_lib,
        'sha256': actual_lib_sha or exp_lib_sha,
        'manifest_path': str(ref_mf_path),
        'generation_run_id': manifest.get('generation_run_id'),
        'source_cpp_sha256': src_cpp_sha,
        'bound_inputs': ['inPWMs[16]'],
        'unsupported_inputs': ['TerrainIn15d[15]'],
        'terrain_handling': 'rejected_if_nonzero',
    }


def instrument(raw: bytes, expected_sha: str = CPP_11_8_SHA256) -> bytes:
    """Instrument Exp1_MinModelTemp.cpp with wk_capture_major read-only callback.

    Strict integrity invariants:
    - Exact match of raw SHA256 against expected_sha.
    - Exactly one occurrence of #include "Exp1_MinModelTemp.h"\\r\\n.
    - Exactly one occurrence of OUTPUT_END + NEXT_CONTEXT.
    - 'wk_capture_major' not already present.
    - Insertion line strictly at 7919.
    - Reversion test: removing DECLARATION and HOOK yields exact raw bytes.
    """
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(f"Unreviewed generated CPP SHA256: expected {expected_sha}, got {actual_sha}")

    if raw.count(INCLUDE) != 1:
        raise ValueError("Include directive context is not unique")
    if b'wk_capture_major' in raw:
        raise ValueError("Source file already contains wk_capture_major")

    context = OUTPUT_END + NEXT_CONTEXT
    if raw.count(context) != 1:
        raise ValueError("Output boundary context is not unique")

    before = raw[:raw.index(context) + len(OUTPUT_END)]
    line_no = before.replace(b'\r\r\n', b'\n').replace(b'\r\n', b'\n').count(b'\n')
    if line_no != EXPECTED_INSERTION_LINE:
        raise ValueError(f"Reviewed root output boundary moved: expected line {EXPECTED_INSERTION_LINE}, got {line_no}")

    patched = raw.replace(INCLUDE, INCLUDE + DECLARATION, 1)
    patched = patched.replace(context, OUTPUT_END + HOOK + NEXT_CONTEXT, 1)

    if patched.replace(DECLARATION, b'', 1).replace(HOOK, b'', 1) != raw:
        raise ValueError("Instrumentation changed original source bytes or equations")

    return patched


def build_and_record(
    generation_evidence_dir: Path = DEFAULT_GENERATION_DIR,
    codegen_source_dir: Optional[Path] = None,
    matlab_include_dir: Path = DEFAULT_MATLAB_INCLUDE,
    recorder_source: Path = DEFAULT_RECORDER_SOURCE,
    post_reference_source: Path = DEFAULT_POST_REFERENCE_SOURCE,
    build_id: str = 'e0-major-01',
    evidence_dir: Optional[Path] = None,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    wsl_user: str = DEFAULT_WSL_USER,
    wsl_build_dir: Optional[str] = None,
    record_input: Optional[Path] = None,
    reference_lib: Optional[str] = DEFAULT_REFERENCE_LIB,
    reference_manifest: Optional[Path] = None,
    verify_parity: bool = True,
    timeout: float = 120.0,
    project_root: Path = ROOT,
    runner: Optional[WslRunner] = None,
) -> Dict[str, Any]:
    """Build the major model recorder in WSL, optionally record CSV telemetry, and verify parity."""
    start_time = time.time()
    started_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time))
    validate_build_id(build_id)

    folder_name = build_id if build_id.startswith('e0-major-recorder-') else f"e0-major-recorder-{build_id}"
    if evidence_dir is None:
        evidence_dir = (evidence_root / folder_name).resolve()
    else:
        evidence_dir = Path(evidence_dir).resolve()
    validate_evidence_containment(evidence_dir, project_root=project_root)

    if wsl_build_dir is None:
        wsl_build_dir = f"/root/wksim-e0-major-{build_id}"
    validate_wsl_major_dir(wsl_build_dir)

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

    inc_dir = Path(matlab_include_dir).resolve()
    hdr_continuous = inc_dir / 'rtw_continuous.h'
    hdr_solver = inc_dir / 'rtw_solver.h'
    for hdr in (hdr_continuous, hdr_solver):
        if not hdr.is_file() or hdr.stat().st_size == 0:
            raise FileNotFoundError(f"Required MathWorks header missing or empty: '{hdr}'")

    rec_src_path = Path(recorder_source).resolve()
    if not rec_src_path.is_file() or rec_src_path.stat().st_size == 0:
        raise FileNotFoundError(f"Recorder source missing or empty: '{rec_src_path}'")
    rec_src_raw = rec_src_path.read_bytes()

    original_cpp_path = codegen_dir / 'Exp1_MinModelTemp.cpp'
    original_cpp_raw = original_cpp_path.read_bytes()
    patched_cpp_raw = instrument(original_cpp_raw, expected_sha=CPP_11_8_SHA256)
    patched_cpp_sha = hashlib.sha256(patched_cpp_raw).hexdigest()

    toolchain_version = runner.get_toolchain_version()

    mkdir_res = runner.run_bash(f"mkdir -p {shlex.quote(wsl_build_dir)}", timeout=15.0)
    if mkdir_res.returncode != 0:
        raise RuntimeError(f"Failed to create WSL major directory '{wsl_build_dir}': {mkdir_res.stderr}")

    source_identity = {
        'builder': 'tools/build_generated_e0_major.py',
        'builder_sha256': digest(Path(__file__)),
        'generation_run_id': gen_evidence['generation_run_id'],
        'original_cpp_sha256': CPP_11_8_SHA256,
        'patched_cpp_sha256': patched_cpp_sha,
        'header_sha256': digest(codegen_dir / 'Exp1_MinModelTemp.h'),
        'rtwtypes_sha256': digest(codegen_dir / 'rtwtypes.h'),
        'rtw_continuous_sha256': digest(hdr_continuous),
        'rtw_solver_sha256': digest(hdr_solver),
        'driver_sha256': hashlib.sha256(rec_src_raw).hexdigest(),
        'phase': 'major root outputs complete; before subsequent explicit Update/ODE',
        'output_order': ['Vehicle60', 'Sensor30', 'GPS30'],
        'root_inputs': ['inPWMs[16]', 'TerrainIn15d[15]'],
        'insertion_line': EXPECTED_INSERTION_LINE,
    }
    identity_json = json.dumps(source_identity, sort_keys=True, separators=(',', ':'))

    patch_recipe = {
        'target_file': 'Exp1_MinModelTemp.cpp',
        'original_sha256': CPP_11_8_SHA256,
        'patched_sha256': patched_cpp_sha,
        'insertion_line': EXPECTED_INSERTION_LINE,
        'declaration': DECLARATION.decode('ascii'),
        'hook': HOOK.decode('ascii'),
        'reversion_verified': True,
        'equations_modified': False,
    }
    write_json(evidence_dir / 'patch-recipe.json', patch_recipe)

    # Staging files into WSL via private work/ staging directory
    stage_dir = validate_and_create_staging_dir(project_root=project_root, build_id=build_id)
    patched_cpp_file = stage_dir / 'Exp1_MinModelTemp.cpp'
    patched_cpp_file.write_bytes(patched_cpp_raw)

    orig_cpp_file = stage_dir / 'Exp1_MinModelTemp.original.cpp'
    orig_cpp_file.write_bytes(original_cpp_raw)

    source_h_file = stage_dir / 'major_recorder_source.h'
    source_h_content = f'static constexpr const char* WK_SOURCE_JSON = R"wksim({identity_json})wksim";\n'
    source_h_file.write_text(source_h_content, encoding='utf-8')

    headers_to_copy = {
        'Exp1_MinModelTemp.cpp': patched_cpp_file,
        'Exp1_MinModelTemp.original.cpp': orig_cpp_file,
        'Exp1_MinModelTemp.h': codegen_dir / 'Exp1_MinModelTemp.h',
        'rtwtypes.h': codegen_dir / 'rtwtypes.h',
        'rtw_continuous.h': hdr_continuous,
        'rtw_solver.h': hdr_solver,
        'major_model_recorder.cpp': rec_src_path,
        'major_recorder_source.h': source_h_file,
    }
    post_ref_path = Path(post_reference_source).resolve()
    if post_ref_path.is_file():
        headers_to_copy['generated_e0_post_reference.cpp'] = post_ref_path

    for fname, lpath in headers_to_copy.items():
        cp_cmd = f"cp {shlex.quote(to_wsl_path(lpath))} {shlex.quote(wsl_build_dir + '/' + fname)}"
        cp_res = runner.run_bash(cp_cmd, timeout=15.0)
        if cp_res.returncode != 0:
            raise RuntimeError(f"Failed to copy '{fname}' to WSL: {cp_res.stderr}")
    # Note: stage_dir is intentionally preserved for failure inspection and post-mortem review.

    # Pre-compilation checksum verification in WSL
    expected_staged_hashes = {
        'Exp1_MinModelTemp.cpp': patched_cpp_sha,
        'Exp1_MinModelTemp.original.cpp': CPP_11_8_SHA256,
        'Exp1_MinModelTemp.h': source_identity['header_sha256'],
        'rtwtypes.h': source_identity['rtwtypes_sha256'],
        'rtw_continuous.h': source_identity['rtw_continuous_sha256'],
        'rtw_solver.h': source_identity['rtw_solver_sha256'],
        'major_model_recorder.cpp': source_identity['driver_sha256'],
    }
    if post_ref_path.is_file():
        expected_staged_hashes['generated_e0_post_reference.cpp'] = digest(post_ref_path)
    for fname, exp_h in expected_staged_hashes.items():
        dst_f = f"{wsl_build_dir}/{fname}"
        sha_res = runner.run_bash(f"sha256sum {shlex.quote(dst_f)}", timeout=10.0)
        if sha_res.returncode != 0:
            raise RuntimeError(f"Failed to checksum staged file '{dst_f}': {sha_res.stderr}")
        act_h = sha_res.stdout.split()[0].strip()
        if act_h != exp_h:
            raise RuntimeError(f"Pre-compilation integrity verification failed for '{fname}': expected {exp_h}, got {act_h}")

    executable_name = 'major_model_recorder'
    compile_cmd = (
        f"cd {shlex.quote(wsl_build_dir)} && "
        f"g++ {' '.join(COMPILER_FLAGS)} -I. Exp1_MinModelTemp.cpp major_model_recorder.cpp -o {shlex.quote(executable_name)}"
    )
    compile_res = runner.run_bash(compile_cmd, timeout=timeout)
    (evidence_dir / 'build.stdout.log').write_text(compile_res.stdout, encoding='utf-8')
    (evidence_dir / 'build.stderr.log').write_text(compile_res.stderr, encoding='utf-8')

    finished_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time()))

    if compile_res.returncode != 0:
        summary_failed = {
            'status': 'failed',
            'scope': 'Simulink e0 major observer compilation and sampling recorder; zero runtime MATLAB dependency; #59 source-consistent entrypoint; no G6 claim',
            'build_id': build_id,
            'generation_run_id': gen_evidence['generation_run_id'],
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
            'executable_sha256': None,
        }
        write_json(evidence_dir / 'command.json', command_failed)
        return summary_failed

    stat_cmd = f"sha256sum {shlex.quote(wsl_build_dir + '/' + executable_name)} && stat -c %s {shlex.quote(wsl_build_dir + '/' + executable_name)}"
    stat_res = runner.run_bash(stat_cmd, timeout=10.0)
    if stat_res.returncode != 0:
        raise RuntimeError(f"Failed to stat compiled executable: {stat_res.stderr}")
    lines = stat_res.stdout.strip().splitlines()
    exe_sha256 = lines[0].split()[0].strip()
    exe_size = int(lines[1].strip()) if len(lines) > 1 else 0

    ldd_cmd = f"ldd {shlex.quote(wsl_build_dir + '/' + executable_name)}"
    ldd_res = runner.run_bash(ldd_cmd, timeout=10.0)
    (evidence_dir / 'ldd.txt').write_text(ldd_res.stdout, encoding='utf-8')
    is_clean, deps, violations = audit_ldd_output(ldd_res.stdout)
    if not is_clean:
        summary_failed = {
            'status': 'failed',
            'scope': 'Simulink e0 major observer compilation and sampling recorder; zero runtime MATLAB dependency; #59 source-consistent entrypoint; no G6 claim',
            'build_id': build_id,
            'generation_run_id': gen_evidence['generation_run_id'],
            'compiler_return_code': 0,
            'clean_runtime_deps': False,
            'violations': violations,
            'error': f"Dynamic dependency audit failed: {violations}",
            'evidence_directory': str(evidence_dir),
        }
        write_json(evidence_dir / 'summary.json', summary_failed)
        return summary_failed

    # Compile 31-input reference executable
    ref_executable_name = 'generated_e0_post_reference'
    ref_compile_cmd = (
        f"cd {shlex.quote(wsl_build_dir)} && "
        f"g++ {' '.join(COMPILER_FLAGS)} -I. Exp1_MinModelTemp.original.cpp generated_e0_post_reference.cpp -o {shlex.quote(ref_executable_name)}"
    )
    ref_compile_res = runner.run_bash(ref_compile_cmd, timeout=timeout)
    (evidence_dir / 'ref_build.stdout.log').write_text(ref_compile_res.stdout, encoding='utf-8')
    (evidence_dir / 'ref_build.stderr.log').write_text(ref_compile_res.stderr, encoding='utf-8')

    if ref_compile_res.returncode != 0:
        summary_failed = {
            'status': 'failed',
            'scope': 'Simulink e0 major observer compilation and sampling recorder; zero runtime MATLAB dependency; #59 source-consistent entrypoint; no G6 claim',
            'build_id': build_id,
            'generation_run_id': gen_evidence['generation_run_id'],
            'compiler_return_code': ref_compile_res.returncode,
            'compiler': toolchain_version,
            'wsl_build_dir': wsl_build_dir,
            'error': f"Reference executable compilation failed: {ref_compile_res.stderr}",
            'evidence_directory': str(evidence_dir),
        }
        write_json(evidence_dir / 'summary.json', summary_failed)
        return summary_failed

    ref_stat_cmd = f"sha256sum {shlex.quote(wsl_build_dir + '/' + ref_executable_name)} && stat -c %s {shlex.quote(wsl_build_dir + '/' + ref_executable_name)}"
    ref_stat_res = runner.run_bash(ref_stat_cmd, timeout=10.0)
    if ref_stat_res.returncode != 0:
        raise RuntimeError(f"Failed to stat compiled reference executable: {ref_stat_res.stderr}")
    ref_lines = ref_stat_res.stdout.strip().splitlines()
    ref_exe_sha256 = ref_lines[0].split()[0].strip()
    ref_exe_size = int(ref_lines[1].strip()) if len(ref_lines) > 1 else 0

    ref_ldd_cmd = f"ldd {shlex.quote(wsl_build_dir + '/' + ref_executable_name)}"
    ref_ldd_res = runner.run_bash(ref_ldd_cmd, timeout=10.0)
    (evidence_dir / 'ref_ldd.txt').write_text(ref_ldd_res.stdout, encoding='utf-8')
    ref_is_clean, ref_deps, ref_violations = audit_ldd_output(ref_ldd_res.stdout)
    if not ref_is_clean:
        summary_failed = {
            'status': 'failed',
            'scope': 'Simulink e0 major observer compilation and sampling recorder; zero runtime MATLAB dependency; #59 source-consistent entrypoint; no G6 claim',
            'build_id': build_id,
            'generation_run_id': gen_evidence['generation_run_id'],
            'compiler_return_code': 0,
            'clean_runtime_deps': False,
            'violations': ref_violations,
            'error': f"Reference executable dynamic dependency audit failed: {ref_violations}",
            'evidence_directory': str(evidence_dir),
        }
        write_json(evidence_dir / 'summary.json', summary_failed)
        return summary_failed

    record_summary: Dict[str, Any] = {}
    final_status = 'built'
    parity_result: Optional[Dict[str, Any]] = None

    if record_input is not None:
        input_csv_path = Path(record_input).resolve()
        if not input_csv_path.is_file():
            raise FileNotFoundError(f"Input CSV not found: '{input_csv_path}'")
        input_csv_sha = digest(input_csv_path)

        wsl_input_csv = f"{wsl_build_dir}/input.csv"
        cp_in_cmd = f"cp {shlex.quote(to_wsl_path(input_csv_path))} {shlex.quote(wsl_input_csv)}"
        runner.run_bash(cp_in_cmd, timeout=15.0)

        # Validate input for major recorder
        val_cmd = f"{shlex.quote(wsl_build_dir + '/' + executable_name)} --validate-input {shlex.quote(wsl_input_csv)}"
        val_res = runner.run_bash(val_cmd, timeout=15.0)

        # Validate input for reference executable
        ref_val_cmd = f"{shlex.quote(wsl_build_dir + '/' + ref_executable_name)} --validate-input {shlex.quote(wsl_input_csv)}"
        ref_val_res = runner.run_bash(ref_val_cmd, timeout=15.0)

        if val_res.returncode != 0:
            final_status = 'input_invalid'
            record_summary['input_validation_error'] = val_res.stderr or val_res.stdout
        elif ref_val_res.returncode != 0:
            final_status = 'input_invalid'
            record_summary['input_validation_error'] = f"Reference validation error: {ref_val_res.stderr or ref_val_res.stdout}"
        else:
            # Run recording for major recorder
            rec_cmd = f"{shlex.quote(wsl_build_dir + '/' + executable_name)} --record {shlex.quote(wsl_input_csv)}"
            rec_res = runner.run_bash(rec_cmd, timeout=timeout)
            (evidence_dir / 'record.jsonl').write_text(rec_res.stdout, encoding='utf-8')

            # Run recording for 31-input reference executable
            ref_rec_cmd = f"{shlex.quote(wsl_build_dir + '/' + ref_executable_name)} --record {shlex.quote(wsl_input_csv)}"
            ref_rec_res = runner.run_bash(ref_rec_cmd, timeout=timeout)
            (evidence_dir / 'post_reference.jsonl').write_text(ref_rec_res.stdout, encoding='utf-8')

            if rec_res.returncode != 0:
                final_status = 'record_failed'
                record_summary['record_error'] = rec_res.stderr
            elif ref_rec_res.returncode != 0:
                final_status = 'record_failed'
                record_summary['record_error'] = f"Reference execution error: {ref_rec_res.stderr}"
            else:
                final_status = 'recorded'
                record_summary['input_csv'] = str(input_csv_path)
                record_summary['input_csv_sha256'] = input_csv_sha
                record_summary['samples_recorded'] = 501
                record_summary['major_grid_start_s'] = 0.0
                record_summary['major_grid_end_s'] = 0.500
                record_summary['engine_end_s'] = 0.501

                # Parity verification
                if verify_parity:
                    is_so_mode = bool(reference_lib and reference_lib.endswith('.so'))
                    ref_identity: Optional[Dict[str, Any]] = None
                    wsl_ref_target = ""

                    if is_so_mode:
                        wsl_ref_target = reference_lib
                        try:
                            ref_identity = verify_reference_artifact(
                                reference_lib=reference_lib,
                                reference_manifest=reference_manifest,
                                expected_cpp_sha=CPP_11_8_SHA256,
                                runner=runner,
                            )
                        except Exception as err:
                            final_status = 'parity_failed'
                            parity_result = {
                                'success': False,
                                'error': f"Reference verification failed: {err}",
                            }
                            write_json(evidence_dir / 'parity-verification.json', parity_result)
                    else:
                        wsl_ref_target = f"{wsl_build_dir}/post_reference.jsonl"
                        ref_identity = {
                            'mode': 'post_reference_31_input',
                            'executable_name': ref_executable_name,
                            'executable_sha256': ref_exe_sha256,
                            'executable_size_bytes': ref_exe_size,
                            'source_cpp': 'Exp1_MinModelTemp.original.cpp',
                            'source_cpp_sha256': CPP_11_8_SHA256,
                            'reference_driver_source': 'generated_e0_post_reference.cpp',
                            'reference_driver_sha256': digest(post_ref_path),
                            'bound_inputs': ['inPWMs[16]', 'TerrainIn15d[15]'],
                            'unsupported_inputs': [],
                            'clean_runtime_deps': ref_is_clean,
                            'ldd_dependencies': ref_deps,
                        }

                    if final_status != 'parity_failed':
                        wsl_rec_jsonl = f"{wsl_build_dir}/record.jsonl"
                        cp_rec_cmd = f"cp {shlex.quote(to_wsl_path(evidence_dir / 'record.jsonl'))} {shlex.quote(wsl_rec_jsonl)}"
                        runner.run_bash(cp_rec_cmd, timeout=15.0)

                        if not is_so_mode:
                            cp_ref_cmd = f"cp {shlex.quote(to_wsl_path(evidence_dir / 'post_reference.jsonl'))} {shlex.quote(wsl_ref_target)}"
                            runner.run_bash(cp_ref_cmd, timeout=15.0)

                        checker_local = evidence_dir / 'parity_checker.py'
                        checker_local.write_text(PARITY_CHECK_PYTHON_SNIPPET, encoding='utf-8')
                        wsl_checker_py = f"{wsl_build_dir}/parity_checker.py"
                        cp_chk_cmd = f"cp {shlex.quote(to_wsl_path(checker_local))} {shlex.quote(wsl_checker_py)}"
                        runner.run_bash(cp_chk_cmd, timeout=15.0)

                        chk_cmd = f"python3 {shlex.quote(wsl_checker_py)} {shlex.quote(wsl_rec_jsonl)} {shlex.quote(wsl_ref_target)} {shlex.quote(wsl_input_csv)}"
                        chk_res = runner.run_bash(chk_cmd, timeout=60.0)

                        if chk_res.stdout:
                            try:
                                parity_result = json.loads(chk_res.stdout.strip().splitlines()[-1])
                            except json.JSONDecodeError:
                                parity_result = {'success': False, 'raw_output': chk_res.stdout, 'raw_error': chk_res.stderr}
                        else:
                            parity_result = {'success': False, 'raw_error': chk_res.stderr}

                        if ref_identity is not None and isinstance(parity_result, dict):
                            parity_result['reference_identity'] = ref_identity

                        write_json(evidence_dir / 'parity-verification.json', parity_result)

                        if chk_res.returncode == 0 and parity_result.get('success', False):
                            final_status = 'verified'
                        else:
                            final_status = 'parity_failed'

    elapsed = round(time.time() - start_time, 3)

    summary = {
        'status': final_status,
        'scope': 'Simulink e0 major observer compilation and sampling recorder; zero runtime MATLAB dependency; #59 source-consistent entrypoint; no G6 claim',
        'build_id': build_id,
        'generation_run_id': gen_evidence['generation_run_id'],
        'wsl_build_dir': wsl_build_dir,
        'wsl_distro': wsl_distro,
        'compiler': toolchain_version,
        'compiler_flags': COMPILER_FLAGS,
        'executable_name': executable_name,
        'executable_sha256': exe_sha256,
        'executable_size_bytes': exe_size,
        'clean_runtime_deps': is_clean,
        'ldd_dependencies': deps,
        'reference_executable': {
            'executable_name': ref_executable_name,
            'executable_sha256': ref_exe_sha256,
            'executable_size_bytes': ref_exe_size,
            'clean_runtime_deps': ref_is_clean,
            'ldd_dependencies': ref_deps,
        },
        'patch_recipe': patch_recipe,
        'record_input': str(record_input) if record_input else None,
        'record_summary': record_summary,
        'reference_identity': parity_result.get('reference_identity') if parity_result else None,
        'parity_verified': parity_result.get('success', False) if parity_result else None,
        'max_discrepancy': parity_result.get('max_discrepancy') if parity_result else None,
        'elapsed_seconds': elapsed,
        'evidence_directory': str(evidence_dir),
    }
    if final_status in ('failed', 'input_invalid', 'record_failed', 'parity_failed'):
        summary['error'] = (
            parity_result.get('error')
            if parity_result and 'error' in parity_result
            else record_summary.get('record_error', 'Execution or parity failure')
        )

    write_json(evidence_dir / 'summary.json', summary)

    manifest = {
        'build_id': build_id,
        'generation_run_id': gen_evidence['generation_run_id'],
        'source_identity': source_identity,
        'patch_recipe': patch_recipe,
        'executable': {
            'filename': executable_name,
            'sha256': exe_sha256,
            'size_bytes': exe_size,
        },
        'ldd_audit': {
            'clean': is_clean,
            'dependencies': deps,
            'violations': violations,
        },
        'reference_executable': {
            'filename': ref_executable_name,
            'sha256': ref_exe_sha256,
            'size_bytes': ref_exe_size,
        },
        'reference_ldd_audit': {
            'clean': ref_is_clean,
            'dependencies': ref_deps,
            'violations': ref_violations,
        },
        'record_summary': record_summary,
        'reference_identity': parity_result.get('reference_identity') if parity_result else None,
        'parity_verification': parity_result,
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
        'return_code': 0 if final_status in ('built', 'recorded', 'verified') else 1,
        'executable_sha256': exe_sha256,
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
        '--recorder-source',
        type=Path,
        default=DEFAULT_RECORDER_SOURCE,
        help=f"Path to major_model_recorder.cpp (default: {DEFAULT_RECORDER_SOURCE})",
    )
    parser.add_argument(
        '--post-reference-source',
        type=Path,
        default=DEFAULT_POST_REFERENCE_SOURCE,
        help=f"Path to generated_e0_post_reference.cpp (default: {DEFAULT_POST_REFERENCE_SOURCE})",
    )
    parser.add_argument(
        '--build-id',
        type=str,
        default='e0-major-01',
        help="Identifier for this build run (^[a-zA-Z0-9_-]+$)",
    )
    parser.add_argument(
        '--evidence-dir',
        type=Path,
        default=None,
        help="Explicit destination directory for evidence artifacts in validation/",
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
        help="Explicit WSL build directory (default: /root/wksim-e0-major-<build_id>)",
    )
    parser.add_argument(
        '--record-input',
        type=Path,
        default=None,
        help="Path to 501-row input CSV (e.g. validation/numerical-contract-20260909/inputs/C0.csv)",
    )
    parser.add_argument(
        '--reference-lib',
        type=str,
        default=DEFAULT_REFERENCE_LIB,
        help="Path in WSL to reference (.so shared library or .jsonl). If omitted, uses built-in 31-input reference executable",
    )
    parser.add_argument(
        '--reference-manifest',
        type=Path,
        default=DEFAULT_REFERENCE_MANIFEST,
        help=f"Path to reference build-manifest.json for source and SHA verification (default: {DEFAULT_REFERENCE_MANIFEST})",
    )
    parser.add_argument(
        '--no-verify-parity',
        action='store_true',
        help="Skip post-step parity verification against reference library",
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=120.0,
        help="Compilation and execution timeout in seconds (default: 120.0)",
    )

    args = parser.parse_args()

    try:
        summary = build_and_record(
            generation_evidence_dir=args.generation_dir,
            codegen_source_dir=args.codegen_source_dir,
            matlab_include_dir=args.matlab_include_dir,
            recorder_source=args.recorder_source,
            post_reference_source=args.post_reference_source,
            build_id=args.build_id,
            evidence_dir=args.evidence_dir,
            evidence_root=args.evidence_root,
            wsl_distro=args.wsl_distro,
            wsl_user=args.wsl_user,
            wsl_build_dir=args.wsl_build_dir,
            record_input=args.record_input,
            reference_lib=args.reference_lib,
            reference_manifest=args.reference_manifest,
            verify_parity=not args.no_verify_parity,
            timeout=args.timeout,
        )
        if summary.get('status') in ('failed', 'input_invalid', 'record_failed', 'parity_failed'):
            print(f"Major build/record {summary['status']}: {summary.get('error', 'unknown error')}", file=sys.stderr)
            sys.exit(summary.get('compiler_return_code') or 1)

        print(f"Major build complete. Status: {summary['status']}")
        print(f"Executable: {summary['executable_name']} (SHA256: {summary['executable_sha256']})")
        print(f"Evidence: {summary['evidence_directory']}")
        sys.exit(0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
