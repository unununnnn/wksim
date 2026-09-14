# Independent re-review — remediated DS Full historical-context candidate (2026-09-14, round 02)

Reviewer: CodeBuddy (independent). Reviewed HEAD: `cc42c19f1b06538cf5bfd326d7dcd11f7b1ed6a5` (verified via `git rev-parse HEAD`). Prior review: `validation/coordination/codebuddy-ds-full-frontier-independent-review-20260914-01/` (verdict FAIL, F-01 P1 / F-02 P2 / F-03 P3 / F-04 P3).

## Scope (exact files reviewed, hashes and sizes independently recomputed)

| File | SHA256 | Size (bytes) |
|---|---|---|
| `docs/coordination/ds-full-frontier-20260912.json` | `3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4` | 36161 |
| `docs/coordination/ds-full-frontier-ingest-note-20260914.md` | `7701eee11c91615c069fab26b309512830315c5f5d6cb62cb6ce87a41c8d9a61` | 12050 |
| `validation/test_ds_full_frontier_context.py` | `5a23b662813ae41a9c4ed619cd32143df635a6196afa1afebd8d4119957c3478` | 16923 |

The original snapshot hash and size are byte-identical to round 01, confirming note §7's claim that only the note and the test were remediated. The note hash (`7701eee1…`) matches the test's `NOTE_SHA256` pin exactly (test docstring line 10 and constant line 57); the test file's own hash necessarily changed with the remediation.

## Test execution (only test command run)

Command: `python -B -m unittest validation.test_ds_full_frontier_context -v`

1. **Unstaged** (working tree as-is): **OK — 15 ran, 15 passed, 0 failed, 0 errors, 0 skipped** (0.233s).
2. **Staged simulation** (temporary `GIT_INDEX_FILE` copied from the real index, with exactly the three candidates `git add`-ed into the temporary index only): **OK — 15 ran, 15 passed, 0 failed, 0 errors, 0 skipped** (0.257s). Under the temporary index, the scoped `git grep` still returned exactly the four ds-g0-g5 allowlisted files.

Lifecycle safety: the temporary index was then deleted; the real index was proven unchanged by identical `git ls-files -s | sha256sum` before (`795ee281d77fa6081106c90fc248477eed631d9eebc0737d4394cc754d90ed8b`) and after; the candidates remain untracked (`??`) in the real index. Nothing was staged in the real index, committed, or pushed.

## Prior-finding verification

- **F-01 (P1) — FIXED.** `test_git_grep_exact_four_tracked_files` is now pathspec-scoped to `validation/coordination/ds-g0-g5-frontier-20260913-01` (`validation/test_ds_full_frontier_context.py:293`) and asserts exactly the four allowlisted files within that scope (`GIT_GREP_EXPECTED`, lines 63–68). Empirically proven staging-stable: with the three candidates staged in the temporary index, the scoped grep still returned exactly the four files and the suite passed 15/15. The scope contains none of the candidate paths, so staging them cannot alter the result.
- **F-02 (P2) — FIXED.** Note §3 boundaries 2 and 4 now name concrete tracked anchors. Independently verified: boundary 2 — `docs/plan/59-g6-solve-form-decision-20260914.md` (5797 bytes, tracked, header "# #59 G6/B5 求解形式决策包（PROPOSED，未裁决）"), `validation/e0-g6-solve-form-decision-20260914.json` (11339 bytes, tracked, `"schema": "wksim.59-g6-solve-form-decision.v1"`, `"authority": "proposal_only"`, `"effective": false`), `docs/plan/g6-c3g-stage2-boundary.md` (3260 bytes, tracked, fail-closed C3G stage-2 operand boundary, dated 2026-09-14); boundary 4 — `tools/audit_26_closure_readiness.py` and `validation/test_audit_26_closure_readiness.py` (both tracked; commit `521b5124` "Harden #26 closure evidence portability" modified exactly these two files) and `validation/test_audit_26_current_source_plan.py` (tracked; added by commit `1884ea64`). All eight anchor paths exist and are tracked. The note preserves each anchor's own authority layering verbatim ("does not assert their approval, effectiveness", "it does not record #26 closure or approval"), and the test now pins all of them (`G6_RECORD_PATHS`, `AUDIT26_PATHS`, `NOTE_ANCHOR_PHRASES`, plus a negative test removing boundary-2/boundary-4 anchors).
- **F-04 (P3) — FIXED.** The HEAD-equality pin is gone. `test_binding_baseline_is_ancestor_of_running_head` (`validation/test_ds_full_frontier_context.py:325-330`) requires `cc42c19f…` (BASELINE_FULL) and `e8defc1d8317892e022ee24de086b026c1317e5a` (ANCESTOR_FULL, full hash independently verified) to be ancestors of the running HEAD via `git merge-base --is-ancestor`. Independently verified: `cc42c19f`, `2b436c12658ecae6f847579bd5e83fd17cd53a12` (the note's binding HEAD), and `e8defc1d` are all ancestors of the current HEAD; `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` is an ancestor of the `cc42c19f` baseline (hence transitively of any HEAD passing the test). See N-01 for a wording nuance.
- **F-03 (P3, prior)** — unchanged and still correctly handled by the dict-record walk (`bind_attestation`); the `"?? docs/…"` status-list string at `checks.json:28` is correctly ignored.

## Checklist results

- Strict JSON: PASS. `strict_loads` rejects duplicate keys, NaN/Infinity constants, and `1e999` overflow; original parses with `schema == "wksim.ds-full-frontier.v1"`, no trailing data. Negative coverage for all four rejection classes present.
- Unique attestation binding: PASS. `checks.json` lines 257–262 contain the entry quoted in note §2 verbatim (path / `exists: true` / `size_bytes: 36161` / sha256 `3fcf2003…`); exactly one dict record in `checks.json` binds the original path; hash and size both re-verified against the recomputed file identity. Duplicate and drifted records are rejected by dedicated negatives.
- Scoped exact historical grep allowlist: PASS. Scoped `git grep -l -F` returns exactly `audit.json`, `audit.md`, `checks/checks.json`, `verify_frontier.py` under the pinned evidence directory — identical unstaged and under the staged simulation.
- Supersession anchors and authority boundaries: PASS. Anchors 1 (`docs/plan/full-acceptance-report.md`, 31086 bytes, tracked) and 3 (`docs/plan/9-vendor-abi-defer-boundary.json`, 31146 bytes, tracked) match the note's stated sizes; boundaries 2/4 anchors as under F-02; boundary 5 (`e8defc1d` + `2b436c12` binding #83 offline evidence) ancestry-verified. The note consistently disclaims authority/approval/acceptance for every anchor.
- Baseline/architecture ancestry: PASS (see N-01). `f333316e` (architecture-continuation baseline required by AGENTS.md) is an ancestor of the `cc42c19f` binding baseline and therefore of any HEAD passing the suite.
- Context-only / non-current / non-approval / no-closure wording: PASS. All `NOTE_BOUNDARY_PHRASES` verified present in the note ("context only, non-authoritative", "historical context only", the four denials including "not the current Full-acceptance or G0–G6 state", "were not re-verified against GitHub"). The note contains no approval, acceptance, or closure claim; live GitHub snapshot states are explicitly disclaimed as not current facts.
- R1 `numerical_failed`: PASS. Note §4.2 quotes `numerical_failed (保持原状，不改判)` verbatim; figures match the original JSON `r1_state` exactly (contract SHA256 `23d72e26…`, 180360 comparisons, 5684 failed values, 49 failed case-axes, C0=2 / C2G=1943 / C3G=3739); snapshot-forbidden-claims guidance preserved.
- #83 boundary: PASS. Note §3.5 states the `e8defc1d`/`2b436c12` binding "does **not** constitute Full/G6 acceptance". No #83 work was rerun.
- Meaningful negative mutations: PASS with N-02. Hash drift, malformed JSON (three classes), duplicate attestation, drifted attestation, stripped boundary phrase, stripped boundary-2/boundary-4 anchors, and reversed ancestry direction each exercise a distinct real failure path of the binding helpers.

## Findings (this round)

### N-01 — P3 — `f333316e` ancestry is enforced only transitively

The module docstring (line 28) says the suite asserts `e8defc1d`/`f333316e` are ancestors of the running HEAD, but the test directly checks only `BASELINE_FULL` (`cc42c19f…`) and `ANCESTOR_FULL` (`e8defc1d…`). The invariant still holds because `f333316e` is an ancestor of `cc42c19f` (independently verified, exit 0), so any HEAD passing the baseline check necessarily contains `f333316e`. Documentation-vs-implementation nuance only; a direct constant would be defense-in-depth.

### N-02 — P3 — `test_grep_allowlist_mutation_rejected` mutation portion is tautological

After the real scoped-grep exact-match assertion, the two `assertRaises(AssertionError)` blocks (`validation/test_ds_full_frontier_context.py:398-401`) assert that `assertEqual` raises for deliberately unequal lists — guaranteed by Python semantics, independent of any git/grep behavior. Real allowlist coverage exists (the positive exact-match assertion plus the staging-stability proof), so this is cosmetic; the mutation blocks do not add evidence.

## Verdict

**PASS** — zero P1/P2. Both prior blocking findings (F-01, F-02) and F-04 are verifiably fixed; the suite passes 15/15 both unstaged and under a staged-candidates temporary index, and the scoped grep is proven staging-stable. The two P3 observations above are non-blocking.

## Scope and nonclaims

Performed: independent hash/size recomputation of the three candidates; read-only inspection of the three candidates, prior review artifacts, `checks.json:250-270`, and the eight anchor files; read-only git queries (`rev-parse`, `merge-base --is-ancestor`, `ls-files`, scoped `grep -l -F`, `log`/`show --stat` for `521b5124`/`1884ea64`); the single mandated unittest unstaged and under a temporary `GIT_INDEX_FILE` staged with only the three candidates; deletion of that temporary index; real-index invariance proof.

Not performed / nonclaims: no candidate, prior-review, or protected file (`docs/Prometheus.gitmodules.reference`, `validation/coordination/short-cycle-dispatches.json`) was edited; nothing was staged in the real index, committed, or pushed; no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight work was run; #83 was not rerun; no GitHub re-verification of snapshot issue states. This review does not confer authority, approval, acceptance, or closure on the 2026-09-12 snapshot, the ingest note, the test, or any G6/Full state; it evaluates binding, wording, and after-staging validity only. Findings bind the exact candidate hashes above.
