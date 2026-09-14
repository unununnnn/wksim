# CodeBuddy ingest manifest — #26 current-source offline contract

- Date: 2026-09-14
- Role: CodeBuddy ingest-manifest owner (offline ingestion of the independent review slice)
- Repo: `C:/Users/PC/Documents/odid编译/wksim`, branch `main`
- HEAD verified: `5370b2324672c9036d41239cb93e21fc5eb42897`
- Ancestor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` verified present at HEAD (`git merge-base --is-ancestor`, exit 0)
- Source review slice: `validation/coordination/codebuddy-audit26-current-source-independent-review-20260914-01/`

## Candidate paths (exactly four, see exact-paths.txt)

1. `validation/test_audit_26_current_source_plan.py` — the plan-test candidate (untracked in git)
2. `validation/coordination/codebuddy-audit26-current-source-independent-review-20260914-01/review.md`
3. `validation/coordination/codebuddy-audit26-current-source-independent-review-20260914-01/review.json`
4. `validation/coordination/codebuddy-audit26-current-source-independent-review-20260914-01/SHA256SUMS`

## Ingested artifacts and current hashes (SHA-256, bytes observed at this HEAD)

| Ingested file | SHA-256 | Size |
|---|---|---|
| validation/test_audit_26_current_source_plan.py | `6ef7be9bc9b6d2b31e960c6e4859602615bcbfa07ec2385b40aa2e8633963fc3` | 33871 |
| .../independent-review-20260914-01/review.md | `d52822b9c5af549eb2fa719ac6c9b4971fb6e7e899ebec0a5c677e96a6efd09c` | 8086 |
| .../independent-review-20260914-01/review.json | `5d059f4a91f8e730b532bc11f57a4175b9bbac0b8c38551b9f4764c1de631a69` | 5395 |
| .../independent-review-20260914-01/SHA256SUMS | `a0442f15cf3edc669aaa7b5bf56efdffc66f2a962fdc47cda963d216f46f4c44` | 154 |

Cross-validation performed independently during ingest:

- All six hashes recorded inside the review's `review.json` (candidate + three imported
  source seams + two referenced plan/data files) were recomputed from the current worktree
  and match exactly, including recorded byte sizes.
- The review slice's own `SHA256SUMS` verifies `2/2 OK` (`review.md`, `review.json`) with
  `sha256sum -c` at this HEAD.

## Strict parse of the review's review.json

- Duplicate keys: rejected — mechanism proven on crafted inputs (`{"a":1,"a":2}` and a
  nested-object case both raise `duplicate JSON key` via `object_pairs_hook`); the
  artifact itself parses clean with zero duplicate keys.
- `NaN` / `Infinity` / `-Infinity`: rejected via `parse_constant`.
- `1e999` overflow parses as `inf` (JSON number path, `parse_constant` not invoked);
  downstream finite guards reject it, matching the review's probe 3.
- Full strict parse of the artifact: OK. Verdict `PASS`; recorded counts 49/48/1.

## Test execution (proven behavior during ingest)

Command: `python -B -m unittest validation.test_audit_26_current_source_plan` (repo root,
pure CPython, exit 0).

- Tests run: 49; passed: 48; skipped: 1; failures: 0; errors: 0.
- Exact platform skip: `test_checker_maps_windows_provenance_to_mnt_on_posix_hosts`
  (CheckerBindingTests) — `skipped 'POSIX-specific mapping rule'`; correct behavior on
  this Windows host, by-design POSIX-only mapping rule.

## Findings (carried from the independent review; none added by ingest)

### P1 — none.

### P2 — none.

### P3 (five, carried)

1. `validation/test_audit_26_current_source_plan.py:128-139` — second assertion in
   `test_driver_stages_exactly_the_six_sources_the_checker_pins` re-compares the driver
   constant to the same literal instead of the checker's six-source literal
   (`tools/audit_26_closure_readiness.py:1373`); misleading claim only, covered by tracked
   sibling `test_audit_26_closure_readiness.py`.
2. `validation/test_audit_26_current_source_plan.py:167-175,178-186` — two host-bound
   tests error rather than skip on hosts lacking the private `work/` codegen tree or the
   external MATLAB include dir; fail-loud by design, portability limit.
3. `validation/test_audit_26_current_source_plan.py:19` — docstring overstates: claims an
   in-process WSL recorder that does not exist; WSL is simply never invoked.
4. `tools/audit_26_closure_readiness.py:1579-1581` (source seam, not the candidate) —
   `_wsl_precheck_found` docstring misattributes `1e999` rejection to the strict decoder;
   the decoder yields `inf`, downstream finite guards reject. Fail-closed outcome correct.
5. Coverage note — the checker's duplicate-key/NaN rejection helpers are never directly
   asserted by the candidate; reviewer TEMP probes confirmed both rejections work.

## Limitations

- Ingest is offline and read-only toward all candidates and existing files: no edits to
  the candidate, the review slice, or any other existing file; no Git commit/push; no
  GitHub changes.
- Only `python -B -m unittest validation.test_audit_26_current_source_plan` was executed
  (plus pure temp-dir JSON parse probes). No native, WSL, ROS, DDS, SITL, FC, UE, MATLAB,
  model, build, or flight actions; no user-process actions.
- This manifest ingests and binds the independent review's claims; it adds no new
  validation beyond the strict parse, hash cross-checks, and the single unittest run.
- The suite's own recorded limits bind: 100-step constant-input probe window,
  `full_or_g6_acceptance: false`, no reset/cold-cycle or terrain coverage; the suite is
  intentionally single-revision (staleness tripwire).

## Acceptance status

#26, #84, Full, and G6 remain unaccepted, and the Goal remains unaccepted. This manifest
claims none of them; the review verdict PASS covers only the candidate test file's
correctness, fail-closed behavior, and non-duplication within its stated offline scope.
Recommended commit path stays exactly `validation/test_audit_26_current_source_plan.py`.
