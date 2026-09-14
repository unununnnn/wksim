# CodeBuddy independent review — audit26 current-source plan test candidate

- Date: 2026-09-14
- Reviewer: CodeBuddy (independent offline slice)
- Repo: `C:/Users/PC/Documents/odid编译/wksim`, branch `main`
- HEAD verified: `5370b2324672c9036d41239cb93e21fc5eb42897`
- Ancestor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` verified present at HEAD (`git merge-base --is-ancestor`, exit 0)

## Scoped file list

Candidate (untracked, the only recommended commit path):

- `validation/test_audit_26_current_source_plan.py` (33871 bytes)

Imported source seams actually exercised (read-only):

- `tools/audit_26_closure_readiness.py` (imported as `checker`)
- `tools/build_generated_e0.py` (imported as `driver`)
- `tools/generate_model_e0.py` (imported transitively by the driver for `REQUIRED_LICENSES` / `REQUIRED_STAGES`)

Data surfaces read by the suite (all git-tracked; verified with `git ls-files`):

- `Simulator/wksim_core/model.cpp`, `docs/plan/26-current-wrapper-recheck-plan.md`,
  `docs/plan/26-closure-readiness-manifest.json`,
  `validation/codegen-e0-build-short-cycle-01/`, `validation/codegen-e0-build-current-wrapper-01/`,
  `validation/codegen-e0-lifecycle-01/`, `validation/codegen-e0-lifecycle-current-wrapper-01/`,
  `validation/codegen-e0/short-cycle-codegen-01/`, `validation/coordination/native-inputs-20260912/`.

## Hashes (SHA-256, bytes observed on this worktree at HEAD)

| File | SHA-256 | Size |
|---|---|---|
| validation/test_audit_26_current_source_plan.py | `6ef7be9bc9b6d2b31e960c6e4859602615bcbfa07ec2385b40aa2e8633963fc3` | 33871 |
| tools/audit_26_closure_readiness.py | `7aad2227a56d42bcaacb5246a9026c8343c5b4aa5787d8dc93843d66ed9e028e` | 80768 |
| tools/build_generated_e0.py | `0f6c7a8caa6b6b885115e76986bceb0ecc07f06050ea78c316d8aa14747c1c68` | 41243 |
| tools/generate_model_e0.py | `a2d388a4daf1841a080c1666e196fec17a83126f2b25ef1f59350db17cfa0d44` | 21480 |
| docs/plan/26-current-wrapper-recheck-plan.md | `5f3b7f4178bff503fc79a58e85ae2c40465997c3d635eeb804be4196e05b0728` | 18349 |
| docs/plan/26-closure-readiness-manifest.json | `229eb94c8bc4cec71693719b32ad86f716b8a92ac4a2e19b541fc701bc72a1d7` | 7530 |

Cross-checks performed independently:

- Wrapper identity `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290`, size 4070 — recomputed, matches the candidate's frozen premise and the plan.
- Driver source hash `0f6c7a8c…` equals the freeze-record pin asserted at `validation/test_audit_26_current_source_plan.py:525`.

## Execution (proven behavior)

Command: `python validation/test_audit_26_current_source_plan.py -v` (pure CPython, no environment changes).

- Tests run: 49; passed: 48; skipped: 1; failures: 0; errors: 0; wall time 0.071 s.
- The single skip is `test_checker_maps_windows_provenance_to_mnt_on_posix_hosts` — platform-conditional by design (POSIX-only mapping rule), correct behavior on Windows.

TEMP-only pure probes (reviewer-added, wrote only to the system temp directory):

1. Duplicate JSON key (`{"a":1,"a":2}`) through `checker._load_json` → rejected (`duplicate JSON key`). Proven.
2. `NaN` literal through `checker._load_json` → rejected (`non-finite JSON number`). Proven.
3. Overflow literal `1e999` through `checker._load_json` → loader returns `inf` (not decoder-rejected); `checker._strict_number` rejects it. Proven.
4. Overflow `1e999` as `checked_unix` in a WSL receipt through `checker._wsl_precheck_found` → classified `_MISSING` (rejected). Proven.

No repo file was written by the suite or the probes; `git status` after execution shows only pre-existing modifications/untracked entries.

## Findings

### P1 — none found.

No correctness, fail-closed, or truthfulness defect was proven in the candidate. Fail-closed tripwires behave as claimed: any wrapper change fails `WrapperIdentityTests`; tampered generated sources, vacuous `unchanged` lists, foreign codegen folders, reused non-empty evidence dirs, and WSL-path traversal are all rejected by the driver gates, each demonstrated by a passing negative test with a passing untampered control.

### P2 — none found.

### P3

1. `validation/test_audit_26_current_source_plan.py:128-139` — in `test_driver_stages_exactly_the_six_sources_the_checker_pins`, the second assertion is commented "The checker expects the same set in the build manifest" but re-compares the driver constant against the same inline literal; the checker's actual six-source literal (`tools/audit_26_closure_readiness.py:1373`) is never compared here. Coverage of that checker rule exists in the tracked sibling `validation/test_audit_26_closure_readiness.py` (build-manifest fixture paths), so this is a misleading in-file claim, not a coverage hole.
2. `validation/test_audit_26_current_source_plan.py:167-175,178-186` — `test_reference_generation_evidence_satisfies_every_gate` needs the untracked private `work/codegen-e0/short-cycle-codegen-01/codegen` tree (via the `command.json` `cwd`/`codegen_folder` binding) and `test_mathworks_include_prerequisites_resolve` needs the external MATLAB include directory; both error (not skip) on hosts lacking them, inconsistent with the skip guard in `ExecutedEvidenceTests.setUp` (:451-453). Still fail-loud, matching the module's stated philosophy; noted as portability limits.
3. `validation/test_audit_26_current_source_plan.py:19` — docstring says "the WSL runner is replaced by an in-process recorder"; no recorder exists in the file — WSL is simply never invoked. Wording overstatement only; the substantive no-WSL claim is true.
4. Seam (source, not the candidate): `tools/audit_26_closure_readiness.py:1579-1581` — `_wsl_precheck_found` docstring attributes `1e999` rejection to the strict decoder; the probe proves the decoder accepts it as `inf` and rejection comes from the downstream finite guards. Fail-closed outcome verified correct; mechanism description inaccurate.
5. Coverage note: the candidate never directly asserts the checker's duplicate-key/NaN rejection helpers (`_strict_object_pairs`/`_reject_constant`, `tools/audit_26_closure_readiness.py:127-137`); they are only exercised on the happy path via `test_report_carries_the_three_semantics_without_new_field_names`. Reviewer probes confirmed both rejections work.

## Non-duplicate assessment

A grep of every `validation/test_*.py` shows the facts locked by this candidate — `current-wrapper-01` evidence ids, wrapper hash `150ddf3b…`, library hash `528db324…`, freeze record `native-inputs-20260912/current-wrapper-01.json`, and the plan-document markers — appear in no other test file. The tracked siblings `test_audit_26_closure_readiness.py` (62 tests) and `test_build_generated_e0.py` (26 tests) cover the checker and driver generally; the candidate adds the plan-precondition and executed-evidence layer on top. It is a useful, non-duplicate commit candidate.

## Scope limits

- Only the named pure unittest module plus TEMP-only pure fixtures were run. No compiler, no `.so` load, no MATLAB/Embedded Coder, no native, ROS, DDS, SITL, flight-controller, UE, model, or build actions; no WSL commands; no operating user processes.
- Nothing outside the review directory was created or modified; the candidate and all existing files are untouched.
- This is an offline independent review only. It does not claim #26 closure, #84, Full, G6, or any official acceptance, and does not validate any parent-ticket acceptance criteria. The suite's own recorded limits (100-step constant-input probe window, `full_or_g6_acceptance: false`, no reset/cold-cycle or terrain coverage) remain the binding statements of scope.
- The suite is intentionally single-revision: its frozen wrapper premise makes it fail loudly on the next legitimate wrapper change; that is the designed staleness tripwire, not a defect.

## Verdict

PASS — `validation/test_audit_26_current_source_plan.py` is correct, fail-closed, truthful within its stated scope, and a recommended non-duplicate commit candidate. Recommended commit path: exactly `validation/test_audit_26_current_source_plan.py` (no other file).
