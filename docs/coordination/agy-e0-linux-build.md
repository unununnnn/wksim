# Technical Coordination: Standalone Linux Model Build & Step Execution Probe (#70/#71)

## 1. Executive Summary

This deliverable establishes the standalone Linux compilation driver and execution verification for the Simulink e0 quadrotor model (`Exp1_MinModelTemp`), migrating from Embedded Coder generated C++ artifacts to a zero-MATLAB-runtime shared library `libwksim_e0.so` in WSL Ubuntu 22.04.

- **Primary Driver**: `tools/build_generated_e0.py`
- **Unit Test Suite**: `validation/test_build_generated_e0.py` (25 offline test cases, 100% pass)
- **Source Generation Evidence**: `validation/codegen-e0/short-cycle-codegen-01` (R2022b Embedded Coder headless generation, ODE4, 1ms fixed step)
- **Compilation Output**: `libwksim_e0.so` (87,312 bytes, SHA256: `7da6853201b89238c273f2e1360ad21fe479e267d0ed08cf3500f98bf535505e`)
- **Evidence Run ID**: `short-cycle-01`
- **Evidence Directory**: `validation/codegen-e0-build-short-cycle-01`
- **WSL Private Build Directory**: `/root/wksim-codegen-e0-build-short-cycle-01`
- **Final Status**: `tested` (compilation succeeded, ldd audit clean, 100-step 1ms finite output verified)

---

## 2. Strict Evidence & Integrity Verification Gates

Before initiating compilation, `tools/build_generated_e0.py` enforces strict multi-layer integrity gates:

1. **Mandatory Generation Evidence Bundle**:
   - All 6 evidence files must be present: `summary.json`, `command.json`, `generated-sources-manifest.json`, `post-source-verification.json`, `post-staged-verification.json`, `codegen-report.json`. Missing any raises `FileNotFoundError`.
2. **Generation Command Gate**:
   - `command.json` must record `return_code == 0`, `timed_out == false`, and `cleanup_unverified == false`.
   - `cwd` must point to the staged model directory containing `codegen_config.json`.
   - `codegen_config.json` must specify `codegen_folder` on disk; any external or mismatched `--codegen-source-dir` is strictly rejected.
3. **Generation Summary Gate**:
   - `summary.json` must record `status == "generated"`.
   - `matlab_return_code == 0`, `stages_ok == true`, `licenses_ok == true`, `has_valid_artifacts == true`.
   - `source_tampered == false`, `staged_tampered == false`, `timed_out == false`, and `cleanup_unverified == false`.
4. **Post-Verification Parity**:
   - `post-source-verification.json` and `post-staged-verification.json` must be non-empty lists where every item confirms `unchanged == true` and `actual_sha256 == expected_sha256`.
5. **Codegen Report Gate (Stages & Licenses)**:
   - `codegen-report.json` must record `status == "generated"`.
   - `stages` must be a non-empty list containing all `REQUIRED_STAGES` (`license_verification`, `fileGenControl`, `load_system`, `verify_solver`, `configure_target`, `initialization`, `slbuild`, `artifact_verification`, `close_model`) each with `status: "ok"`.
   - All 5 `REQUIRED_LICENSES` (`SIMULINK`, `Real-Time_Workshop`, `RTW_Embedded_Coder`, `Aerospace_Blockset`, `Aerospace_Toolbox`) must show both `test == 1` and `checkout == 1`.
6. **Artifact Manifest & Path Security**:
   - `generated-sources-manifest.json` entries must contain relative paths strictly within `codegen_folder`.
   - Rejects any relative path with directory traversal (`..`), leading slashes (`/`), or duplicate file basenames.
   - All required generated sources (`Exp1_MinModelTemp.cpp`, `Exp1_MinModelTemp.h`, `rtwtypes.h`, `ert_main.cpp`) must exist on disk and match manifest hashes.
7. **External Prerequisites Verification**:
   - MathWorks continuous solver headers from `simulink/include`:
     - `rtw_continuous.h` (SHA256 verified, non-empty)
     - `rtw_solver.h` (SHA256 verified, non-empty)
   - Repository C wrapper:
     - `Simulator/wksim_core/model.cpp` (SHA256 verified, non-empty)
8. **WSL Security & Emptiness Gate**:
   - Private WSL build directory must match regex `^/root/wksim-codegen-e0-build-[a-zA-Z0-9_-]+$`.
   - Injections, quotes, newlines, spaces, and path traversals are rejected before any shell execution.
   - Symlinks and pre-existing non-empty directories are actively rejected before running `mkdir` or copying files.
   - All paths are escaped using `shlex.quote`.
9. **Two-Stage Staged SHA Binding & Pre-Compilation Verification**:
   - Staged files copied into WSL are immediately verified against `initial_expected_hashes` recorded from the manifest and prerequisites.
   - Immediately prior to `g++` invocation, staged files in WSL are re-verified via `sha256sum` against `initial_expected_hashes` to guarantee no pre-compilation tampering.
10. **Error Retention & Structured Diagnostics**:
    - Build failures (compilation return code != 0, missing ldd dependencies, probe failure) write `build.stdout.log`, `build.stderr.log`, `summary.json` (with `status: 'failed'` or `'test_failed'`), and `command.json` (with non-zero exit code). State is preserved rather than dropped by unhandled exceptions.

---

## 3. Toolchain & Compilation Specification

The model is compiled in WSL Ubuntu 22.04 with standard GNU C++ toolchain:

- **Compiler**: `g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0`
- **Flags**: `-std=c++17 -O2 -fno-fast-math -fPIC -shared -Wl,--no-undefined`
- **Entrypoint Exclusion**: `ert_main.cpp` is explicitly excluded from compilation to eliminate standalone `main()` symbols and prevent binary bloat.
- **Compilation Command**:
  ```bash
  cd '/root/wksim-codegen-e0-build-short-cycle-01' && \
  g++ -std=c++17 -O2 -fno-fast-math -fPIC -shared -Wl,--no-undefined \
      -I. Exp1_MinModelTemp.cpp model.cpp -o 'libwksim_e0.so'
  ```
- **Compilation Result**:
  - Exit code: `0`
  - Output file: `libwksim_e0.so` (87,312 bytes)
  - Compiler stdout/stderr: logged to `build.stdout.log` (0 bytes) and `build.stderr.log` (0 bytes)

---

## 4. Dynamic Dependency (ldd) Audit

Dynamic dependency analysis via `ldd libwksim_e0.so` confirmed complete independence from MATLAB runtime libraries:

```text
linux-vdso.so.1 (0x00007ffd9bdec000)
libstdc++.so.6 => /lib/x86_64-linux-gnu/libstdc++.so.6 (0x0000704c18a00000)
libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x0000704c18919000)
libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x0000704c18600000)
/lib64/ld-linux-x86-64.so.2 (0x0000704c18cd4000)
libgcc_s.so.1 => /lib/x86_64-linux-gnu/libgcc_s.so.1 (0x0000704c18c82000)
```

- **Clean Runtime Verified**: `clean_runtime_deps: true`
- **Prohibited Tokens**: Zero matches for `matlab`, `simulink`, `libmw`, `mcr`, `slprj`, or `rflysim`.
- **Runtime Portability**: Directly runnable on any standard Linux x86_64 system without MATLAB licenses, MCR, or vendor installations.

---

## 5. Execution Probe Results

When `--run-test` was invoked, an isolated Python 3 process in WSL loaded `libwksim_e0.so` and executed a 100-step probe:

- **Actuator Input**: 16 normalized PWM channels at `0.5` (quadrotor baseline hover input)
- **Step Integration**: 1ms (`dt = 0.001s`), evaluated 100 consecutive steps
- **ABI Functions Verified**:
  - `wk_model_create()`: returned non-null handle
  - `wk_model_step(handle, in_arr, 16, 1, out_arr, 120)`: returned exit code `0` on all 100 steps
  - `wk_model_destroy(handle)`: freed model instance cleanly without segmentation fault or leak
- **Output Validation**:
  - `steps_evaluated`: 100
  - `sim_time_seconds`: `0.1s` (precisely matches `ticks * 0.001`, verified via `out_arr[2]`)
  - `all_outputs_finite`: `true` (all 120 dimensions checked for `isfinite()` at every step)
  - `copter_id`: `1.0` (`out_arr[0]`)
  - `vehicle_type`: `3.0` (`out_arr[1]`)
  - `sample_head`: `[1.0, 3.0, 0.1, 2.58138994201342e-18, 1.218553033219928e-18, 0.016527135654665414, 4.897896590435587e-20, 2.356513974321344e-20]`
  - `sample_tail`: `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]`

---

## 6. Offline Verification Suite (`validation/test_build_generated_e0.py`)

A comprehensive 25-case test suite was authored and executed with `python -B -m unittest validation.test_build_generated_e0 -v` (100% pass):

| Test Name | Verification Focus | Result |
| :--- | :--- | :--- |
| `test_validate_build_id_valid_and_invalid` | Accepts alphanumeric/hyphen/underscore; rejects traversal and illegal characters | PASS |
| `test_validate_evidence_containment` | Enforces validation directory containment and non-empty directory reuse rejection | PASS |
| `test_to_wsl_path` | Validates Windows drive letter to `/mnt/<drive>/` path conversion | PASS |
| `test_audit_ldd_output` | Detects standard system libraries as clean; flags prohibited vendor/MATLAB substrings | PASS |
| `test_verify_generation_evidence_success` | Validates full generation evidence bundle when all hashes and statuses match | PASS |
| `test_verify_generation_evidence_status_not_generated` | Rejects generation bundles with status != `generated` | PASS |
| `test_verify_generation_evidence_source_tampered` | Rejects generation bundles flagged with `source_tampered: true` | PASS |
| `test_verify_generation_evidence_source_sha_mismatch` | Rejects modified source files with explicit SHA mismatch diagnostic | PASS |
| `test_verify_external_prerequisites_missing_headers` | Rejects build when MathWorks include headers are absent | PASS |
| `test_verify_external_prerequisites_missing_wrapper` | Rejects build when `Simulator/wksim_core/model.cpp` is absent | PASS |
| `test_mock_wsl_build_and_evaluate_success_with_test` | Verifies end-to-end orchestration, manifest writing, and probe recording | PASS |
| `test_mock_wsl_compilation_failure_handling` | Ensures compiler errors are captured into stdout/stderr logs and summary | PASS |
| `test_missing_evidence_files_rejected` | Asserts `FileNotFoundError` when any of the 6 required evidence files is missing | PASS |
| `test_command_json_failure_conditions` | Rejects `return_code != 0`, `timed_out == true`, or `cleanup_unverified == true` | PASS |
| `test_staged_codegen_config_binding` | Validates staged `codegen_config.json` binding and rejects mismatched `codegen_source_dir` | PASS |
| `test_summary_flags_rejected` | Rejects summary failure flags (`matlab_return_code != 0`, `stages_ok == false`, etc.) | PASS |
| `test_post_verification_failures` | Rejects empty post-verification lists, `unchanged == false`, or SHA mismatches | PASS |
| `test_codegen_report_stages_and_licenses` | Rejects empty stages, missing stages, failed stages, or unverified tool licenses | PASS |
| `test_manifest_path_traversal_and_duplicates` | Rejects manifest path traversal (`..`), leading slashes, and duplicate basenames | PASS |
| `test_wsl_build_dir_security` | Enforces `/root/wksim-codegen-e0-build-` pattern and blocks quotes/newlines/traversals | PASS |
| `test_wsl_check_dir_symlink_and_non_empty` | Rejects symlinks and pre-existing non-empty WSL build directories | PASS |
| `test_ldd_audit_missing_dependency` | Flags `not found` dynamic dependencies in dynamic linker audit | PASS |
| `test_pre_compilation_staged_integrity_failure` | Detects staged file tampering immediately prior to compilation | PASS |
| `test_ldd_violations_abort_compilation_run` | Aborts build gracefully and preserves diagnostics if dynamic dependency audit fails | PASS |
| `test_probe_failure_preserves_summary` | Preserves failure telemetry, `test-probe.json`, and summary on probe failure | PASS |

---

## 7. Artifact Manifest Summary

Evidence directory `validation/codegen-e0-build-short-cycle-01` contains:

- `summary.json`: High-level build and probe outcome (`status: "tested"`, clean runtime dependencies, elapsed 8.48s)
- `build-manifest.json`: Full source file hashes, compiler flags, staged paths, output library SHA256, LDD audit, and probe metrics
- `command.json`: Invocation metadata, compiler version, start/finish UTC timestamps, exit code
- `build.stdout.log` & `build.stderr.log`: Raw compiler logs
- `ldd.txt`: Complete dynamic link dependency audit log
- `test-probe.json`: Complete 100-step numerical evaluation telemetry

---

## 8. Migration Boundaries & Handoff for #72

- **Claim Boundary**: This milestone delivers a standalone Linux C++ compilation and execution probe for the generated e0 model with zero runtime MATLAB dependencies. It establishes ABI conformance and basic numerical finiteness under constant actuator inputs. It does **not** claim full flight dynamics equivalence, closed-loop stability, or G6 benchmark compliance.
- **Handoff for #72**:
  - The compiled library `libwksim_e0.so` can be loaded via `Simulator/wksim_core/model.py` (`Model` class).
  - Ready for cold-restart testing, longer-duration flight simulation, and integration with the ROS2/PX4 SITL bridge.
