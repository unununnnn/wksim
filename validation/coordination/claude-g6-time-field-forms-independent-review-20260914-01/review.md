# Independent final review — G6 time-field-forms offline candidate (#59)

- **Reviewer**: Claude Opus 4.8 (1M context), acting as independent final reviewer
- **Date**: 2026-09-14
- **Subject**: completed G6 time-field-forms offline candidate in the shared `wksim` repository
- **Verdict**: **GO**

All evidence below was re-derived independently in this session (read-only git, in-memory
regeneration, self-built sandbox repositories, and an independent AST/import scan). The shipped
test suite was executed but its assertions were **not** trusted in place of inspection.

## Environment observed

| Item | Value |
| --- | --- |
| Repository | `C:/Users/PC/Documents/odid编译/wksim` |
| Branch | `main` |
| Observed HEAD | `0b10f786e808eebe7698e9a277766bf2f68a4d35` |
| Evidence anchor | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` |

## Candidate files (immutable; re-hashed, unchanged)

| Path | SHA-256 (recomputed) | Size (bytes) | Matches expected |
| --- | --- | --- | --- |
| `tools/check_g6_time_field_forms.py` | `23ad9e9263632d2d070726c113573ee0ced6a373712a2e48a12977304d8d1607` | 99822 | yes |
| `validation/g6-time-field-forms-20260914.json` | `bf87ef7e2c0b6f2ea69b51ab18c92089741858ac32be50c26a09b437cb13b37d` | 117396 | yes |
| `validation/test_check_g6_time_field_forms.py` | `d5bd68b69e1d15d45cc6e36c90413f24004d39ffb72f739e0cb8b8481236b40c` | 71982 | yes |
| `docs/plan/59-g6-time-field-forms-20260914.md` | `780b01713e7f029445f4d2176b900d5bc71aff4f2236d5470ab869b7ae62ef01` | 9248 | yes |

## Per-check results

### 1. Anchor is an ancestor of observed HEAD — PASS
`git merge-base --is-ancestor f333316… 0b10f78…` → exit `0`. `git cat-file -t` confirms the
anchor is a `commit`. The anchor is a genuine ancestor of the observed current HEAD.

### 2. Six pinned evidence paths unchanged anchor→HEAD; no exact-HEAD requirement — PASS
`git diff <anchor>..<HEAD> -- <path>` is **empty** for every one of the six pinned paths:
`record.jsonl`, `numerical-conformance-v1.json`, `verification.json`,
`initial-assumption-rejected.json`, `verify_times.py`, `2026-09-13-major-time-conventions.md`.
The observed HEAD literal `0b10f786…` appears in **none** of the four candidate files. The only
40-hex commit literal in the generator is the legitimate stable anchor `f333316…`; every other
40-hex string is a SHA-256 evidence/reference pin. There is no exact-HEAD equality requirement
anywhere: `head_commit()` is read at runtime only to feed `merge-base`/`diff`, and the document
records `observed_head_recording: "deliberately_not_recorded"`.

### 3. Fail-closed under unavailable probe / non-ancestor / pinned-path overlap — PASS
18 independent negative probes (own sandboxes, direct inspection of returned structures) all pass:
- **Non-ancestor** (real object DB, `f333316…~1`): classified `not_ancestor`; emits
  `base_ancestor_not_ancestor`; `anchor_is_ancestor_of_observed_head=False`.
- **Unavailable probe** (sandbox lacking the anchor object): classified `unavailable`; emits
  `base_ancestor_check_unavailable` and `evidence_diff_unavailable`.
- **observed HEAD = None**: emits `observed_head_unavailable`.
- **Missing raw reference arrays**: `status="blocked"`, three `missing_untracked_input::*`
  blocks, no invented `value`/`assumed_value` in any blocker.
- **Missing tracked evidence** (empty dir): `status="blocked"`, `missing_tracked_evidence` blocks.
- **Pinned-path overlap** (two-commit sandbox, one pinned path changed): head still descends from
  base, yet `pinned_path_overlap` fires with `changed_pinned_paths=[rel]`. Clean controls
  (unchanged path; identical endpoints) produce **no** overlap block.

### 4. Offline hygiene — PASS
Independent AST/import/subprocess scan of the generator: imports are stdlib-only
(`argparse, hashlib, json, pathlib, struct, subprocess, sys, __future__`); the sole
`subprocess.run` program is `git`; the only subcommands across all `_git(...)` call sites are
`ls-tree`, `rev-parse`, `merge-base`, `diff` — all read-only and index-independent. No
MATLAB/Simulink/ROS/DDS/SITL/flight/UE/PX4/ArduCopter surface, no network library, no
index/state-mutating git verb (`add`/`ls-files`/`update-index`/`checkout-index`/`write-tree`/
`commit`/`push`/`status`). The earlier `status` grep hit is a JSON key, not a git invocation.

### 5. Regenerated JSON validates; no G6-physical / budget / closure claims — PASS
In-memory `build_document()` regenerates bytes **byte-identical** to the committed file
(`bf87ef7e…` both) and `validate(..., repo_root)` returns `ok=true, codes=[]`. CLI `--validate`
also returns `ok=true` (exit 0). Decision surface is clean: `g6_acceptance=false`,
`physical_accuracy=false`, `budget_approved=false`, `issues_closed=false`, `effective=false`,
`authority="none"`, `pending_approvals=[]`, `r1_status="numerical_failed"`,
`open_items = issue_84/g6/full all "open"`, `evidence_class_split.evaluated_here=false`, and no
forbidden budget/acceptance/closure key is present.

### 6. Normal unittest run — PASS
`python -B -m unittest validation.test_check_g6_time_field_forms` → **68 tests, OK (skipped=2)**,
exit 0. The two skips are the exact4 temp-index tests (meaningful only under a temp index).

### 7. Repo-external `GIT_INDEX_FILE` exact4 run; real index preserved — PASS
Staged **exactly** the four immutable candidates into a repo-external temp index
(`…/Temp/g6exact4_…/exact4-index`, confirmed outside the repo) and ran the same suite:
- **count** = 4 staged entries exactly; **paths** == the four candidate paths;
- **status** = every entry stage `0`, mode `100644` (clean, no conflict);
- **blob** equality = each staged blob's git id **and** SHA-256 equals the working-tree bytes.
- Suite: **68 tests, OK** — both `TestExact4TempIndex` tests now run and pass (not skipped).

Real-index preservation (index and HEAD identical before/after):

| | Real index SHA-256 | HEAD |
| --- | --- | --- |
| Before | `cf249890d18567a9f62173ff1e8ac717362fe531ecea02a545a72ee185319a32` | `0b10f786e808eebe7698e9a277766bf2f68a4d35` |
| After | `cf249890d18567a9f62173ff1e8ac717362fe531ecea02a545a72ee185319a32` | `0b10f786e808eebe7698e9a277766bf2f68a4d35` |

### 8. Candidate hash recompute — PASS
Recomputed SHA-256 and byte sizes after all operations: all four match the expected implementation
hashes (table above). No candidate hash changed. Real index and HEAD still `cf249890…` / `0b10f78…`.

## Scope and non-actions
This review is read-only. It did not stage, commit, push, build, or modify any path; it did not run
any model, MATLAB, ROS, flight-controller, UE, or native/full-profile work. Untracked files owned by
other agents were ignored. All scratch repositories and the temp index were created under the system
temp directory and removed; the real `.git/index` and HEAD were never written.
