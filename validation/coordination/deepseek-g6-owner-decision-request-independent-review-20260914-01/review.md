# Independent review: #59 G6 owner-decision request (2026-09-14)

- Review id: `deepseek-g6-owner-decision-request-independent-review-20260914-01`
- Reviewer: independent agent (`deepseek-v4-flash`, DSH harness), no authoring role in the candidate
- Date: 2026-09-14
- Verdict: **KEEP** — 0 × P1, 0 × P2, 5 × P3 (hardening only, none blocks acceptance of this request artifact)
- Checkout: `C:\Users\PC\Documents\odid编译\wksim`, branch `main`, HEAD `ee6eb88819cefe255f22e788c39a77c0bbab490e`
- Candidates were read only; no candidate byte was edited, staged in the real index, committed or pushed.

## 1. Subject identity (immutable, re-verified)

| file | SHA256 | size |
| --- | --- | --- |
| `docs/plan/59-g6-owner-decision-request-20260914.md` | `45dcec197c4e62376a2640de828ae8e14ad062d1ef6b232a0ca4b27a15ecedd7` | 5243 |
| `validation/e0-g6-owner-decision-request-20260914.json` | `42ad4572fbd8c21a9648593a37cae67dac4e13c173f88e0f33b31129a6c83274` | 15723 |
| `validation/test_e0_g6_owner_decision_request.py` | `a10abcfb37b1c9bc3ff123849ea4534f5f1eb020afbd803a8bd64f1fd109f0ba` | 47358 |

All three hashes/sizes match the values fixed by the review request exactly (recomputed with
`Get-FileHash -Algorithm SHA256` and `Get-Item ... Length` before and after every test run; unchanged).

## 2. Exact commands and observed results

1. Normal mode (read-only git plumbing; real index untouched):

   ```powershell
   python -B -m unittest -v validation.test_e0_g6_owner_decision_request
   ```

   Result: `Ran 29 tests in 0.654s` — `OK (skipped=2)` (the two `TemporaryIndexTests` are the skips).

2. Repo-external exact-three temp index (the suite's documented mode):

   ```powershell
   $tmp = Join-Path $env:TEMP ("wksim-59-odr-index-" + [guid]::NewGuid().ToString('N'))
   $env:GIT_INDEX_FILE = $tmp
   git add --force -- docs/plan/59-g6-owner-decision-request-20260914.md `
       validation/e0-g6-owner-decision-request-20260914.json `
       validation/test_e0_g6_owner_decision_request.py
   $env:WKSIM_59_ODR_TEMP_INDEX = "1"
   python -B -m unittest -v validation.test_e0_g6_owner_decision_request
   ```

   Result: `git ls-files` in the temp index listed exactly the three candidate paths; `git add` exit 0;
   `Ran 29 tests in 0.912s` — `OK` (no skips; both `TemporaryIndexTests` executed). The temp index lived at
   `C:\Users\PC\AppData\Local\Temp\wksim-59-odr-index-<guid>` (outside the repository) and was deleted afterwards.

3. Real-index integrity after the temp-index run (`GIT_INDEX_FILE` removed):

   ```powershell
   Remove-Item Env:\GIT_INDEX_FILE
   git ls-files | Where-Object { $_ -like '*59-g6-owner*' -or $_ -like '*test_e0_g6_owner*' }
   ```

   Result: no output — none of the three candidates is staged in the real index.

4. Ancestry gates (no exact-HEAD equality anywhere):

   ```powershell
   git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD   # exit 0
   git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD   # exit 0
   git merge-base --is-ancestor 0000000000000000000000000000000000000000 HEAD   # exit 128
   ```

   Both required ancestors exit 0; a non-existent commit exits 128, so the gate discriminates.

5. Independent pin verification (`git cat-file blob HEAD:<path>` → sha256/size, versus worktree bytes):
   all six pins `ALL_PINS_OK=True` (see §4).

6. Independent invariant probe (own script, not the candidate's suite): three groups, `not_made` states,
   all `chosen=false`, null decision fields, `owner_decisions_made=false`, 21 open ODs with zero overlap,
   `r1_status=numerical_failed`, `issues_closed=[]`, false acceptance/budget flags, blocked-by in {B1,B3,B4}
   — all pass.

7. Pinned-source cross-check: the OD-01/OD-02/OD-20 `question` strings and `slots` in the pinned
   `validation/e0-frame-datum-binding-20260914.json` match the request's DG-2/DG-3 verbatim
   (`Vehicle60[2]`, `Sensor30[0]`, `GPS30[0]`; `Vehicle60[20..23]`), the four slots carry
   `contract_semantic_status=inactive_channels_not_aircraft_coverage`, and all 24 binding ODs are
   `not_made` except none (all 24 stay `not_made` in the binding).

## 3. Required-property checklist

| # | Required property | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Exactly three decision groups | PASS | `decision_group_count=3`; `DG-1 solve_form_choice`, `DG-2 od01_od02_scheduling_time_semantics`, `DG-3 od20_active_vs_extra_motor_output_scope` |
| 2 | All groups `not_made`, no option chosen | PASS | 3 × `state=not_made`; 9 × `chosen=false`; `chosen_option`/`decided_by`/`decided_utc`/`decision_text` all `null`; `owner_decisions_made=false` |
| 3 | No numeric budget | PASS | zero forbidden numeric keys; the only numeric scalars in the document are `issue=59`, `parent_issue=10`, `decision_group_count=3`, `max_pins=6` and the six `size_bytes`; no `abs_budget`/`rel_budget`/`rms_budget`/`tolerance` field |
| 4 | Six tracked HEAD pins | PASS | all six paths resolve as HEAD blobs; HEAD-blob sha256/size = candidate values = worktree bytes (no drift) |
| 5 | Ancestry gates, no exact-HEAD assertion | PASS | both ancestors exit 0; `exact_head_equality_asserted=false`; `observed_head` documented as informational only |
| 6 | Case-insensitive `validation/coordination` rejection | PASS | `forbidden_evidence_path_prefix_casefold`; `normalize_path` casefolds/backslash- and slash-collapses; mutation test + 5 positive/3 negative variants pass |
| 7 | RD-01..RD-12 + closure/approval rejection | PASS | `forbidden_derivation_classes` = RD-01..RD-12 exactly; `derivation_class`/`derivation_ref` `null` in all groups; `issues_closed=[]`; `budget_approved`/`g6_acceptance`/`physical_accuracy` false in document and `open_items` |
| 8 | R1 `numerical_failed`, scopes open | PASS | `r1_status=numerical_failed`; `blockers_open=[B1,B3,B4]`; `owner_decisions_open` = OD-03..OD-24 except OD-20 (21 ids); `issues_open=[#84,G6,Full]` |
| 9 | 29 tests, normal mode | PASS | `Ran 29 tests ... OK (skipped=2)` |
| 10 | Repo-external exact-3 temp index | PASS | `Ran 29 tests ... OK`; exactly three stage-0 entries, blob bytes identical to worktree; real index stages none |
| 11 | Candidates unedited | PASS | SHA256/size identical before and after; files remain untracked; no real-index, commit or push action |
| 12 | No real staging/commit/push/#83/sibling edits | PASS | only `$env:TEMP` index written and removed; no `git add` without `GIT_INDEX_FILE`; no issue/network call; no sibling path touched |

## 4. Six tracked HEAD pins (independently recomputed)

| pin id | path | SHA256 | size | HEAD blob | worktree match |
| --- | --- | --- | --- | --- | --- |
| `g6_remediation_contract` | `docs/plan/10-g6-remediation-contract.md` | `48da61ad…cae5c0` | 9935 | `256455a4…` | yes |
| `dynamic_budget_source_map` | `docs/plan/59-e0-dynamic-budget-source-map.md` | `35a56084…13cd42` | 11215 | `97599ae5…` | yes |
| `frame_datum_binding` | `validation/e0-frame-datum-binding-20260914.json` | `5d589075…45b69f` | 105018 | `64acd9c8…` | yes |
| `solve_form_decision` | `validation/e0-g6-solve-form-decision-20260914.json` | `5086c3fb…34c293` | 11339 | `6f49f3a7…` | yes |
| `budget_approval_provenance` | `validation/e0-budget-approval-provenance-20260914.json` | `2962931a…544d3d` | 285820 | `4f2fdacf…` | yes |
| `r1_contract` | `Simulator/wksim_core/numerical-conformance-v1.json` | `23d72e26…2c08f0` | 29846 | `e5d5f339…` | yes |

Content spot-checks against the pins: the R1 contract holds `absolute_budget=0`/`relative_budget=0` for its
120 slots and `status=frozen`; the budget-provenance ledger reports `slots_with_numeric_budget=0`,
`slots_approved=0`, `external_derivation_records=[]`, `budget_approved=false` and an RD-01..RD-12
`forbidden_provenance_classes` list; the frame/datum binding reports `budget_approved=false`,
`g6_acceptance=false`, `physical_accuracy=false`, `r1_status=numerical_failed`. All pin-source claims in the
request are consistent with the pinned bytes.

## 5. Findings (all P3, non-blocking)

**P3-01 — numeric-budget gate is key-scoped, not value-scoped.**
`Verifier.scan` and `test_no_numeric_budget_anywhere` flag a forbidden *key* (any key containing `budget` or
`tolerance`, plus the frozen list). A budget written as a bare number under a neutral key, or as a numeric
element of an untyped list, would not be flagged. The candidate is clean: an independent walk finds exactly
10 numeric scalars (`issue`, `parent_issue`, `decision_group_count`, `max_pins`, six `size_bytes`), none of
which is a budget. Recommendation (future hardening only): add a value-level rule that any float under a
request-scoped container is a violation, and keep free-text budget statements in the markdown review checklist.

**P3-02 — several request strings are not type-validated.**
`check_group` does not assert the types of `title`, `question`, `evidence_question_ref` or the elements of
`not_covered_by_this_group`. All are well-formed strings in the candidate, so this is a latent gap in the
mutator space, not a defect in the artifact.

**P3-03 — `check_groups` assumes every group element is a dict.**
The ids comparison filters with `isinstance(group, dict)`, but the later
`declared.extend(group.get("owner_decision_ids") or [])` does not, so a non-dict element raises
`AttributeError` instead of recording a violation. Behaviour is still fail-closed (the run errors), but it is
an unclean rejection path and is not covered by any of the 18 mutation tests.

**P3-04 — `..` and non-repo absolute prefixes escape the coordination-path check.**
`normalize_path` casefolds, converts backslashes, collapses duplicate slashes and strips leading `./` and
`/`, but does not resolve `..` or absolute prefixes. `x/../validation/coordination/y.json` or
`C:/repo/validation/coordination/y.json` would not start with the forbidden prefix. For pins this is already
closed by the exact frozen-path equality; the scan is defense-in-depth for future path-bearing keys.

**P3-05 — case-insensitivity claim is stricter than the exercised vector set (informational).**
The suite exercises upper-case, backslash, double-slash, leading-`./` and whitespace variants — the variants a
Windows/POSIX path could realistically take. No concrete gap found; recorded so the claim is not read as a
proof over all Unicode case-folding.

## 6. Notes and non-actions

- The pin-id carve-out in `is_budget_key` is *necessary*: `dynamic_budget_source_map` and
  `budget_approval_provenance` contain the substring `budget`, so their `size_bytes` are the only
  "budget-like key" numbers in the document — correctly treated as sizes, not budgets.
- The request deliberately pins only six sources and pins none under `validation/coordination/`, while the
  pinned `solve_form_decision` packet itself cites `validation/coordination/...` traces. That is consistent:
  the rejection rule constrains this request's own evidence, and the request never dereferences the pinned
  packet's coordination paths as its own evidence.
- Checkout note: `git status` shows two pre-existing working-tree modifications
  (`docs/Prometheus.gitmodules.reference`, `validation/coordination/short-cycle-dispatches.json`) and a set of
  untracked files that pre-date this review. They were not touched, and neither were any sibling projects.
- No `python tools/run_e0_same_source_conformance.py`, no MATLAB/native/ROS/FC/UE/build invocation, no #83
  run, no GitHub mutation, no network call.

## 7. Verdict

**KEEP.** The request artifact satisfies every required property: three decision groups, all `not_made` with no
option chosen, no numeric budget, six tracked-HEAD pins that match at both HEAD and worktree, ancestry gates
without exact-HEAD equality, case-insensitive `validation/coordination` rejection, RD-01..RD-12 and
closure/approval rejection, R1 `numerical_failed` with B1/B3/B4, OD-03..OD-24 (except OD-20), #84/G6/Full open.
All 29 tests pass in both the normal and the repo-external exact-3 temp-index modes. The five findings are
P3 hardening observations on the verifier, not defects in the reviewed artifact; no rework of the candidate is
required.
