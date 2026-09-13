
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
