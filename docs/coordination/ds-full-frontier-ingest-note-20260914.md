# ds-full-frontier-20260912.json ingest note (2026-09-14)

Note binding: written at authoritative HEAD `2b436c12658ecae6f847579bd5e83fd17cd53a12`
(required ancestor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` confirmed present via
`git merge-base --is-ancestor`, exit 0).

## 1. Binding scope of the original snapshot — context only, non-authoritative

- Path: `docs/coordination/ds-full-frontier-20260912.json`
- SHA256: `3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4`
- Size: `36161` bytes (verified locally at this HEAD by `sha256sum` and `wc -c`)

This file is bound **as a 2026-09-12 prior-slot snapshot and historical context only**.
It is **NOT** any of the following at the time of this note:

- not the current Full-acceptance or G0–G6 state;
- not authority over any current plan, verdict, or frontier decision;
- not approval of anything;
- not acceptance of anything.

Any statement inside that snapshot about issue states, frontiers, or verdicts is
pinned as-of 2026-09-12 and must not be repeated as a current live fact. Live
GitHub states (OPEN/CLOSED labels, triage labels, `updatedAt` fields) recorded in
the snapshot were not re-verified against GitHub by this note and are reported
here solely as snapshot contents.

## 2. Exact tracked attestation of the original snapshot

The original snapshot's tracked attestation lives in
`validation/coordination/ds-g0-g5-frontier-20260913-01/checks/checks.json`,
which contains the entry (lines 257–262 in the checked-out file):

```json
{
  "path": "docs/coordination/ds-full-frontier-20260912.json",
  "exists": true,
  "size_bytes": 36161,
  "sha256": "3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4"
}
```

This attestation pins the file's identity in a tracked path; it does not confer
authority, approval, or acceptance on the snapshot's contents.

## 3. Supersession boundaries (all verified to exist at this HEAD)

The 2026-09-12 snapshot is superseded/advanced along every one of the following
boundaries. Every boundary names concrete tracked paths; each named path was
verified read-only at this HEAD by `ls` (existence) and `git ls-files`
(tracked in the index):

1. `docs/plan/full-acceptance-report.md` now exists (31086 bytes checked out).
   The Full-acceptance picture is carried by that report, not by the 2026-09-12
   snapshot.
2. Later G6 records exist beyond the snapshot's 2026-09-12 G6 budget state
   (its `g6_budget_state` reported 56 slots, 0 budget values, schema admitting
   no approved state). Concrete tracked later records, all dated after the
   snapshot:
   - `docs/plan/59-g6-solve-form-decision-20260914.md` (a 2026-09-14 G6/B5
     solve-form decision packet, itself marked PROPOSED / 未裁决) with its
     machine-readable record `validation/e0-g6-solve-form-decision-20260914.json`
     (schema `wksim.59-g6-solve-form-decision.v1`, `authority: proposal_only`,
     `effective: false`);
   - `docs/plan/g6-c3g-stage2-boundary.md` (a 2026-09-14 fail-closed C3G
     stage-2 operand-boundary record).
   These later records — not the snapshot — carry the current G6
   frontier/budget/datum position. Naming them here does not assert their
   approval, effectiveness, or any G6/Full acceptance.
3. `docs/plan/9-vendor-abi-defer-boundary.json` now exists (31146 bytes checked
   out). The vendor-ABI question, which the snapshot recorded as owner decision
   #9 blocking #26/#27/#28 closure, has since been given an explicit defer
   boundary record.
4. #26 audit work has advanced beyond the snapshot's 2026-09-12 record of
   sub-tickets 70/71/72 closed with parent OPEN. Concrete tracked later #26
   audit evidence:
   - `tools/audit_26_closure_readiness.py` and
     `validation/test_audit_26_closure_readiness.py`, hardened on 2026-09-14
     (commit `521b5124` "Harden #26 closure evidence portability");
   - `validation/test_audit_26_current_source_plan.py`, added 2026-09-14
     (commit `1884ea64`) for the #26 current-wrapper cold-recheck plan.
   This evidences later #26 audit work only; it does not record #26 closure or
   approval, and the closure rule (§4.1) remains governing: sub-ticket closure
   does not close the parent.
5. HEAD `e8defc1d` plus its descendant `2b436c12658ecae6f847579bd5e83fd17cd53a12`
   (ancestry of `e8defc1d` to current HEAD verified via
   `git merge-base --is-ancestor`, exit 0) bind #83 offline evidence/interface
   context. That binding does **not** constitute Full/G6 acceptance.

## 4. Still-useful context preserved from the snapshot

The following snapshot content remains useful as reference context and is
preserved verbatim in meaning; it is quoted from the snapshot, not asserted as
current state.

### 4.1 Closure rule

From snapshot `closure_rule_in_force`:

> 父票只有在原 AC 与原 Blocked-by 同时满足时才可关闭；子票关闭不等于父票关闭。

Snapshot consequence: #26 sub-tickets 70/71/72 all closed but parent OPEN;
#46 sub-tickets 113/114/115 all closed but parent OPEN with dependency on #20
unsatisfied. This closure rule remains the governing principle referenced by
later work; the specific issue states around it are snapshot-as-of facts only.

### 4.2 R1 `numerical_failed` state

From snapshot issue #59 `r1_state` (status quoted verbatim):

> numerical_failed (保持原状，不改判)

Snapshot figures: contract
`Simulator/wksim_core/numerical-conformance-v1.json` SHA256
`23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0`;
180360 comparisons; 5684 failed values; 49 failed case-axes; per-case unequal as recorded in the snapshot:
C0=2, C2G=1943, C3G=3739. R1 originals and the 5684 failed values were
identity-rechecked and unchanged per the snapshot. Snapshot-forbidden claims
remain operative guidance: no back-derivation of acceptance budgets from
candidate deltas; no equating lifecycle byte-repeatability with G6 numerical
pass; no rewriting or relaxing R1 budgets; no reclassifying original failures
as pass; no treating SLX 11.0 and 11.8 as same-version pairs. Later G6
records (see §3.2) supersede the snapshot's G6 position; the R1
`numerical_failed` identity itself is preserved context.

## 5. Offline-test seam

A later offline test may pin and enforce the following. All checks are
file-system/git only; no network, no build, no runtime.

```yaml
# offline-test-seam: v1 (machine-checkable expectations)
original:
  path: docs/coordination/ds-full-frontier-20260912.json
  sha256: 3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4
  size_bytes: 36161
note:
  path: docs/coordination/ds-full-frontier-ingest-note-20260914.md
  sha256: <pin-at-first-read; recorded in session report, see §6>
attestation:
  path: validation/coordination/ds-g0-g5-frontier-20260913-01/checks/checks.json
  expect: unique entry with path == original.path,
          sha256 == original.sha256, size_bytes == 36161
original_json:
  expect: strict JSON parse succeeds (rfc-equivalent); no trailing data
supersession_paths:
  - docs/plan/full-acceptance-report.md          # must exist and be tracked
  - docs/plan/9-vendor-abi-defer-boundary.json   # must exist and be tracked
g6_later_records:                                # boundary 2 anchors
  - docs/plan/59-g6-solve-form-decision-20260914.md        # must exist and be tracked
  - validation/e0-g6-solve-form-decision-20260914.json     # must exist and be tracked
  - docs/plan/g6-c3g-stage2-boundary.md                    # must exist and be tracked
audit26_later_evidence:                          # boundary 4 anchors
  - tools/audit_26_closure_readiness.py                    # must exist and be tracked
  - validation/test_audit_26_closure_readiness.py          # must exist and be tracked
  - validation/test_audit_26_current_source_plan.py        # must exist and be tracked
historical_grep:
  # pathspec-scoped to the pinned evidence directory: staging-stable by
  # construction; staging the candidates cannot change the hit set
  pathspec_scope: validation/coordination/ds-g0-g5-frontier-20260913-01
  expect_exact_files:
    - audit.json
    - audit.md
    - checks/checks.json
    - verify_frontier.py
ancestry:
  # binding-baseline semantics: each entry must be an ANCESTOR of whatever
  # HEAD the suite runs at; cc42c19f is the binding baseline, NOT required to
  # equal future HEAD
  must_contain_ancestor_of_HEAD:
    - e8defc1d
    - f333316e6efa6b299b4288a9d91fb2bccedfb9d6
    - cc42c19f
wording:
  fail_closed_non_authority:
    - note must contain the phrase "context only" bound to the original path
    - note must deny: authority, approval, acceptance, current Full/G0-G6 state
    - note must state live GitHub states in the snapshot are not current facts
  note_binding:
    - note must name HEAD 2b436c12658ecae6f847579bd5e83fd17cd53a12
```

Suggested checks: (a) re-hash original and attestation entry match; (b) strict
JSON parse of original; (c) attestation entry is unique within `checks.json`;
(d) all supersession/boundary-2/boundary-4 paths exist and are tracked; (e)
ancestry via `git merge-base --is-ancestor` against the running HEAD (never
HEAD equality against a pinned commit); (f) wording assertions above pass
(fail-closed: any missing phrase fails the test); (g) the historical grep is
run pathspec-scoped to the pinned ds-g0-g5 evidence directory with the exact
four-file allowlist above, so staging new candidates cannot change its result.

## 6. Verification performed by this note (read-only only)

- HEAD: `2b436c12658ecae6f847579bd5e83fd17cd53a12` (verified `git rev-parse`).
- `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD`
  → exit 0.
- `git merge-base --is-ancestor e8defc1d HEAD` → exit 0.
- `sha256sum docs/coordination/ds-full-frontier-20260912.json`
  → `3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4`; size
  36161 bytes. Matches the attestation entry.
- Existence checks for the three supersession/attestation paths in §2/§3.

No files were staged, committed, or pushed; no protected files were touched; no
native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight/#83 work was run. The
note's own SHA256 and line count are reported in the session output (the note
cannot contain its own hash; the seam in §5 pins it externally).

## 7. Remediation 2026-09-14 (at HEAD `cc42c19f1b06538cf5bfd326d7dcd11f7b1ed6a5`)

Remediation of independent review
`validation/coordination/codebuddy-ds-full-frontier-independent-review-20260914-01/review.json`
(verdict FAIL). Only this note and
`validation/test_ds_full_frontier_context.py` were edited; the original
snapshot `docs/coordination/ds-full-frontier-20260912.json` and all review
artifacts are untouched.

- F-01 (P1): the historical grep in the test is now pathspec-scoped to the
  pinned evidence directory `validation/coordination/ds-g0-g5-frontier-20260913-01`
  and asserts the exact four-file allowlist within it (§5 `historical_grep`).
  Staging the candidates therefore cannot change the grep result; exact
  historical allowlist validation is retained inside that scope.
- F-02 (P2): boundaries 2 and 4 in §3 now name concrete tracked anchors
  (boundary 2: the #59 G6/B5 solve-form decision packet pair and the C3G
  stage-2 boundary record; boundary 4: the 2026-09-14 #26 closure-readiness
  hardening and current-wrapper plan contract test), each verified for
  existence and index-tracking by read-only `ls` and `git ls-files`. This is
  repository evidence of later work only; no closure, approval, or acceptance
  is claimed, and the packet's own PROPOSED/`effective: false` layering is
  preserved verbatim.
- F-04 (P3): the test no longer requires HEAD to equal `cc42c19f`; it requires
  `cc42c19f` (the binding baseline), `e8defc1d`, and `f333316e` to be
  ancestors of whatever HEAD the suite runs at (§5 `ancestry`). The suite is
  valid at future commits whose history contains the baseline.

Recomputed after these edits: this note's SHA256 is pinned by the test
(`NOTE_SHA256`); the test file's own hash is reported in the session output.
