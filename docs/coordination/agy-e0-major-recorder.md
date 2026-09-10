# Coordination: 11.8 Major Model Recorder Driver & Parity Hardening (#59 Precondition)

## 1. Context & Scope

This deliverable provides the hardened standalone Linux compilation and major sampling recorder driver for the 11.8 generated Simulink model (`Exp1_MinModelTemp`), serving as the verified major-step observation entrypoint for #59 homologous numerical comparison.

- **Issue Status & Precedence**:
  - Issues #70, #71, and #72 are fully completed and committed on `main`.
  - Issue #59 ("Homologous numerical comparison between Simulink and native model") and milestone G6 remain open.
  - Historical evidence in `validation/e0-major-recorder-short-cycle-01/` is preserved as executed and not overwritten.
- **Governing Principles**:
  1. **Strict Immutability**: Original codegen and build tools (`tools/generate_model_e0.py`, `tools/build_generated_e0.py`) remain completely frozen and unmodified.
  2. **Non-Interference Guarantee**: The observer instruments a *private build copy* of `Exp1_MinModelTemp.cpp` in WSL with a read-only capture callback (`wk_capture_major`), without modifying equations, continuous states, solver steps, or production interfaces.
  3. **Homologous Parity**: Post-step outputs (`post_step_api`) from the instrumented recorder executable match the unmodified 11.8 model library (`libwksim_e0.so` or `tools/generated_e0_post_reference.cpp`) to exact numerical equality with **STRICT ZERO TOLERANCE** (`diff > 0.0` fails; `max_discrepancy = 0.0` and `discrepancies_count = 0` across all 501 samples and 120 output dimensions = 60,120 values). Floating-point tolerance ($1\times 10^{-12}\text{ s}$) is permitted solely for timestamp grid multiples ($k \times 0.001\text{ s}$).
  4. **Boundary**: This driver establishes the verified observation, provenance, and data collection contract. It does NOT claim G6 acceptance (the per-quantity physical tolerance budget is pending) and does NOT close #59.

---

## 2. 11.8 Line 7919 Instrumentation Recipe

### 2.1 Distinction Between 11.0 and 11.8
In earlier 11.0 generation, root output assembly completed around line 7877 before `// If: '<S12>/If1'`. In the verified 11.8 codegen:
- Root major outputs (`VehileInfo60d[60]`, `HILSensor30d[30]`, `HILGPS30d[30]`) complete at **line 7919**, immediately following the `Constant_Value_ea` memcpy for `VehileInfo60d[33..59]`.
- The downstream block is `// If: '<S13>/If1'`.
- ODE4 continuous state integration (`rt_ertODEUpdateContinuousStates`) occurs further downstream at line 8305.

Any driver attempting to apply the 11.0 line number or context string will fail validation immediately.

### 2.2 Patch Invariant and Hashes
- **Original Source**: `work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp`
  - SHA256: `2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274`
  - Size: 327,598 bytes, 9,457 lines (CRLF line endings).
- **Callback Declaration** (inserted after system `#include` block, line 23):
  ```cpp
  extern void wk_capture_major(const ExtY_Exp1_MinModelTemp_T&) noexcept;
  ```
- **Observer Hook** (inserted at line 7919):
  ```cpp
    if (rtmIsMajorTimeStep((&Exp1_MinModelTemp_M))) {
      wk_capture_major(Exp1_MinModelTemp_Y);
    }
  ```
- **Patched Source**:
  - SHA256: `993f33ea3cfcd282418599c94ce6ef4d6265add76f7d9763039965f6c6c1dc9d`
- **Reversion Invariant**: Stripping the declaration and hook lines restores the byte-identical original file (`reversion_verified: true`, `equations_modified: false`).

---

## 3. 501-Sample Recording Contract & Hardened Verification

The driver (`tools/build_generated_e0_major.py`) and recorder executable (`tools/major_model_recorder.cpp`) enforce the strict #23 numerical comparison sampling contract:
1. **Input Grid**: 501 rows corresponding to $k = 0, \dots, 500$, with timestamps strictly on the 1 ms grid ($t_k = k \times 0.001\text{ s}$, from $0.000\text{ s}$ to $0.500\text{ s}$).
2. **Root Inputs**: Bound to `inPWMs[16]` and `TerrainIn15d[15]` (rejecting invalid names such as `FaultInParams`).
3. **Capture Invariant**: Exactly 1 major capture callback per step (`major_capture_count == 1`). If zero or multiple callbacks fire, execution aborts.
4. **Time Bounds**: Pre-step engine time is $k \times 0.001\text{ s}$; post-step engine time is $(k+1) \times 0.001\text{ s}$. Final engine time after 501 steps is $0.501\text{ s}$.
5. **No Padding / No Shift**: Exactly 501 samples emitted, zero extrapolation, zero alignment offsets.

### 3.1 Hardened Parity Checker Contract & Zero Tolerance
The verification script (`parity_checker.py` / `check_parity`):
- **Parse Safety**: Intercepts JSON decode errors on start, sample, and end lines without swallowing exceptions.
- **Finite Value Enforcement**: Validates every recorded and reference floating-point value (`math.isfinite`); explicitly rejects `NaN` and `Inf` without allowing `NaN == NaN` passes.
- **Strict Structural Sequence**:
  - Line 1: `major_recorder_start` (schema version 1).
  - Lines 2..502: Strictly ordered `major_recorder_sample` with $k = 0..500$, `call_number == k+1`, input time $k \times 0.001\text{ s}$, pre-step engine time $k \times 0.001\text{ s}$, post-step engine time $(k+1) \times 0.001\text{ s}$, and `major_capture_count == 1`.
  - Line 503: `major_recorder_end` verifying status `"complete"`, `emitted_samples == 501`, and final engine time $0.501\text{ s}$.
- **Strict Zero-Tolerance Comparison**:
  - For all 501 steps and 120 output dimensions ($501 \times 120 = 60,120$ float values), checks `abs(ref_val - rec_val) > 0.0`.
  - Any non-zero difference triggers discrepancy failure. No tolerance slack is granted to model outputs.
- **Accurate Discrepancy Accounting**:
  - `discrepancies_count`: Evaluates every single float and reports the true total count of discrepancies across all 60,120 values.
  - `sample_discrepancies`: Capped at 10 diagnostic samples with step index $k$, output dimension index, reference value, recorded value, and absolute difference.
- **Precision Terminology**: Characterizes equivalence as exact numerical zero-discrepancy equality ("数值严格相等"), with zero tolerance.

---

## 4. 31-Input Full Reference Driver & Terrain Semantics

### 4.1 Physical Semantics of `TerrainIn15d`
Inspection of the model source (`Exp1_MinModelTemp.cpp` lines 4544–4554) confirms:
```cpp
terrainZ = TerrainIn(1);
z = Xe(3) - terrainZ;
Exp1_MinModelTemp_U.TerrainIn15d[0];
```
In the North-East-Down (NED) frame used by the physics engine:
- $X_e(3)$ is the vertical position coordinate $z_{NED}$ in meters (positive downwards).
- `TerrainIn15d[0]` corresponds to $z_{NED,\text{terrain}}$ in meters.
- Test input `validation/e0-major-recorder-terrain-01/inputs/C0_terrain_step.csv` specifies $z_{NED,\text{terrain}} = -0.5\text{ m}$ (ground elevation 0.5 m above reference datum) with `TerrainIn15d[1..14] = 0.0`, reflecting physically valid NED coordinates without unit guesswork.

### 4.2 Standalone 31-Input Reference Driver (`tools/generated_e0_post_reference.cpp`)
To eliminate dependency on the frozen 16-PWM adapter in `Simulator/wksim_core/model.cpp`:
- Implements `MulticopterModelClass` wrapper reading all 31 inputs (`inPWMs[16]` and `TerrainIn15d[15]`).
- Evaluates the unmodified 11.8 model step-by-step and outputs reference `post_step_api` records without callbacks or pseudo-major steps.
- The parity checker validates the input CSV: if evaluated against the 16-PWM shared library (`libwksim_e0.so`), it explicitly rejects CSVs containing non-zero `TerrainIn15d` inputs with:
  `"Non-zero TerrainIn15d detected in input CSV, but reference shared library ABI only accepts 16 PWM inputs; full 31-input reference driver required"`.

### 4.3 Reference Provenance Authentication
When verifying against `--reference-lib`:
- Requires `--reference-manifest` (`build-manifest.json`).
- Verifies that the reference manifest specifies the reviewed source CPP SHA (`2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274`).
- Verifies the actual WSL binary SHA256 of `--reference-lib` matches `output_library.sha256` in the manifest.
- Records the complete `reference_identity` metadata block into `summary.json`, `build-manifest.json`, and `parity-verification.json`.

---

## 5. Live WSL Ubuntu 22.04 Execution Evidence

Exclusive native execution runs were conducted in WSL Ubuntu-22.04 using GCC 11.4.0 (`g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0`) with compiler flags `-std=c++17 -O2 -fno-fast-math -Wl,--no-undefined`.

### 5.1 Run 1: C0 Baseline (31 Inputs, Zero Terrain)
- **Command**:
  ```bash
  python tools/build_generated_e0_major.py --build-id short-cycle-c0-31in --record-input validation/numerical-contract-20260909/inputs/C0.csv
  ```
- **Artifacts**:
  - Evidence Directory: `validation/e0-major-recorder-short-cycle-c0-31in`
  - Recorder Binary: `major_model_recorder` (SHA256: `649ca709b09944f114af8e64b9cf85cdba6af05c6b064090afe34b0df9fc13bb`, size: 126,920 bytes)
  - Reference Binary: `generated_e0_post_reference` (SHA256: `91ee385483d2c23718b40901cfeeb6af436a8940c7b4be10d7322a028cd39203`, size: 122,312 bytes)
  - Runtime Dependencies (`ldd` audit): Clean (only `linux-vdso`, `libstdc++`, `libm`, `libgcc_s`, `libc`, `ld-linux-x86-64`; zero MATLAB/Simulink dependencies).
- **Parity Result**:
  - `status`: `"verified"`
  - `steps_checked`: 501
  - `dimensions_checked`: 120
  - `total_values_checked`: 60,120
  - `max_discrepancy`: `0.0`
  - `discrepancies_count`: `0`
  - `terrain_all_zeros_verified`: `true`

### 5.2 Run 2: Non-Zero Terrain Step (31 Inputs, $z_{NED,\text{terrain}} = -0.5\text{ m}$)
- **Command**:
  ```bash
  python tools/build_generated_e0_major.py --build-id short-cycle-terrain-31in --record-input validation/e0-major-recorder-terrain-01/inputs/C0_terrain_step.csv --evidence-root validation/e0-major-recorder-terrain-01
  ```
- **Artifacts**:
  - Evidence Directory: `validation/e0-major-recorder-terrain-01/e0-major-recorder-short-cycle-terrain-31in`
  - Recorder Binary: `major_model_recorder` (SHA256: `649ca709b09944f114af8e64b9cf85cdba6af05c6b064090afe34b0df9fc13bb`)
  - Reference Binary: `generated_e0_post_reference` (SHA256: `91ee385483d2c23718b40901cfeeb6af436a8940c7b4be10d7322a028cd39203`)
- **Parity Result**:
  - `status`: `"verified"`
  - `total_values_checked`: 60,120
  - `max_discrepancy`: `0.0`
  - `discrepancies_count`: `0`
  - `terrain_all_zeros_verified`: `false` (non-zero terrain inputs verified ingested and simulated)

### 5.3 Triggered Negative Verification
- Evaluating `C0_terrain_step.csv` against the 16-PWM shared library (`libwksim_e0.so`) triggers rejection:
  ```json
  {
    "success": false,
    "error": "Non-zero TerrainIn15d detected in input CSV, but reference shared library ABI only accepts 16 PWM inputs; full 31-input reference driver required"
  }
  ```

---

## 6. Staging Directory Exclusivity & Safety

- **Private Workspace Isolation**: `validate_and_create_staging_dir` ensures staging directories (`work/e0-major-staging-<build_id>`) are created strictly within `work/`.
- **Exclusivity & Non-Destruction**: Uses `exist_ok=False`. If the staging directory exists, it raises `FileExistsError` without deleting, overwriting, or clobbering existing files.
- **Path Traversal Prevention**: Enforces strict regex validation on `build_id` (`^[a-zA-Z0-9_-]+$`) and verifies `stage_dir.parent == work_dir`.
- **Preservation for Forensic Analysis**: Staging directories are preserved for post-build verification and diagnostic inspection.

---

## 7. Unit Test Suite

The test suite `validation/test_generated_e0_major.py` includes 25 comprehensive test cases covering:
1. Exact Line 7919 instrumentation, round-trip reversion invariant, and equation immutability.
2. Rejection of unreviewed source SHA, shifted line boundaries, and existing callbacks.
3. Strict WSL directory format and traversal rejection (`validate_wsl_major_dir`).
4. End-to-end build, record, and parity orchestration with mocked toolchain.
5. Preserving logs and status on compilation errors.
6. Clean parity failure handling without tolerance inflation.
7. **Hardened Parity Negative Tests**: Corrupt JSON, NaN/non-finite values, missing terminal records, out-of-order steps $k$, non-zero terrain input with 16-PWM SO reference, non-existent reference path rejection, tiny $1\times 10^{-13}$ numerical discrepancy rejection, and full-count accounting across 60,120 floats with sample capping.
8. **Provenance Negative Tests**: Missing reference manifest, unreviewed CPP SHA, and SO binary SHA mismatch.
9. **Staging Directory Negative Tests**: Collision detection with non-destructive canary preservation, path traversal rejection, and staging directory retention.

All 25 unit tests pass cleanly:
```bash
python -m unittest validation/test_generated_e0_major.py
# Ran 25 tests in 0.872s: OK
```

