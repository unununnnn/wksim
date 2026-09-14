# CodeBuddy independent review — remediated OMP G6 first-step evidence batch (-03)

2026-09-14; read-only independent review. Baseline verified at review time:
HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`;
`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD`
exit 0. Prior `-02` review and `-01` ingest manifest are superseded; their byte
identities were not trusted and are not included.

## 1. Candidates (byte-pinned)

| Path | SHA256 | Size |
| --- | --- | --- |
| docs/coordination/omp-reference-first-step-review-20260913.md | `7973f0220c05861547283fbc47f3cfb8e5875a6101023e64593ad7b2664bc17a` | 2979 B |
| docs/coordination/omp-first-step-comparison-review-20260913.md | `728bce90e0e2da893746e9113954694b6fb7147537db18f564e186dfa5769c14` | 3985 B |
| docs/coordination/omp-g6-first-step-ingest-note-20260914.md | `c7f034535096047e321ab654fac418d7de5775854ac0e5ff06d97db2369308bc` | 14459 B |
| validation/test_omp_g6_first_step_context.py | `ef7e613b0781902a76f5b88ac383510eaa200599a7fb8a4ec7e4c9885eea25cf` | 54340 B |

Both dispatch-pinned values (ingest note `c7f03453…`/14459 B, test
`ef7e613b…`/54340 B) match. Candidates re-hashed after all operations:
byte-identical. No candidate or any other existing file was modified.

## 2. Material claims — independent verification results

1. **Frozen R1 driver identity** — `7f3bc0c88263a6e1c94a3f42658fe43db2a0b75abca7a5fb59fcfaafdba99cde`
   re-hashed in all three pinned locations
   (`validation/numerical-conformance-u56ce17a/C0/run_numerical_conformance.py`,
   `validation/numerical-conformance-gxxh6xhr/C2G/…`, `…/C3G/…`): three
   byte-identical copies ✓.
2. **Repo-current driver** — `tools/run_numerical_conformance.py`
   sha256 `4221246303642b26290b63c118ced5209a6e928a6101140cc00dc4cd12278040`
   ✓; HEAD blob `1cedff93bd8fd48d7e867541ed83423edaa03089` ✓ and blob bytes
   hash to the same sha256 (byte identity) ✓; file absent at parent
   `bf3c224e` of `3f40ba031f670dfd09fd341f4dfdb6fa2b702d51` ("Execute frozen
   model comparisons and retain every strict mismatch"), present at
   `3f40ba03` with the same blob — introducing-commit claim ✓.
3. **Exact frozen-vs-current difference** — two lines only: L137 type gate
   (`type(x) in (int, float)` added to the `require(...)` predicate) and L148
   `float(...)` cast (`x = float(sample['major_root_outputs'][name][index])`);
   no other differing lines ✓ (matches the claim "恰差一个类型门与一次 float
   强转").
4. **execution-03 invoked neither driver** — tracked
   `g6-reference-probe-20260913/execution-03/invocation.json` records
   `unused_changed_driver` with expected `7f3bc0c8…` vs actual `42212463…`
   (`matches:false`) plus scope "New diagnostic uses frozen C3G model/init/
   input/dependencies, not the old R1 orchestration driver",
   `all_used_frozen_identities_match:true`, 38 verified frozen dependencies;
   tracked `execution-03/input-checks.json` carries the same False entry.
   `unused_changed_driver` as a non-defect is sound ✓.
5. **Owner ruling encoding** — note §5/§8 record: frozen copies immutable,
   neither frozen-copy update nor repo backfill authorized, ruling supersedes
   the former live two-option wording (test forbids the six superseded /
   destructive phrasings), launch-time SHA recomputation + executed-bytes
   snapshot for every future driver execution ✓. Closure scope correctly
   bounded: only the owner-ruling subissue; not G6/Full; 23 states,
   `ode4_stage_mapping`, native/full-window remain; issue 83 never rerun ✓
   (live check: #83 CLOSED, #84 OPEN via `gh`, repo `unununnnn/wksim`).
6. **Artifact identities** — independently re-hashed:
   `run-03/reference-first-step.json` = `99fc1ec8…85` ✓; top-level
   `g6-target-first-step-20260913/first-step-trace.jsonl` = `34350997…86` ✓;
   with-major variant = `d55542d7…60` ✓ (distinct identity, not to be mixed);
   `comparison-v2.json` = `2a6b8fe9…c9`, 3477 B, tracked at HEAD as blob
   `f129a1e1…` and byte-equal to disk (test verifies blob equality) ✓. v2
   embeds `reference_sha256`/`target_trace_sha256` matching the two artifacts ✓.
7. **ULP facts recomputed independently** from comparison-v2.json: stage
   differences p,q/r s2 derivatives[1]=1; q s3 derivatives[2]=1; q s3
   derivatives[3]=**64**; p,q/r s3 cont_states[1]=1; ub,vb,wb s3
   derivatives[0]=1; final q index3=**44**, ub,vb,wb index0=1 — no
   "all-later-1-ULP" regularity; xyz block zero differences; −4.95e-18 is the
   earliest differing double's value magnitude (1-ULP delta ~−7.7e-34); all
   difference doubles normal (3.46e-47 included) ✓ — matches the 2026-09-14
   precision-corrected wording in both review documents and the note.
8. **Scope/boundaries** — 13/36 mapped rigid states, 23 uncovered, no
   full-model or G6-pass claim ✓; stage order
   stage0(0)→stage1(.0005)→stage2(.0005)→stage3(.001)→ode4_update(.001),
   v2 final state = last 0.001 (update) ✓; 72 = 20+20+16+16, dropped=0,
   PostDerivatives 0×4/.0005×8/.001×4 ✓; 240 major f64, zero-bit mismatch
   vs frozen C3G, `parse_int=Decimal` −0 preservation ✓; timing anchors
   (`docs/2026-09-07_joint-rate-contract-proposal.md:58`: no catch-up,
   >100ms late freeze-with-restore, 1ms major) and
   `omp-mixed-failure-review-20260913.md:59` ("mixed 能力证明行仍 MISSING")
   verified at cited lines ✓.
9. **Git-side facts** — note-writing HEAD `e2ecd62e…` ("Bind scene frontier
   context offline") and review HEAD `01181887…` are ancestors of current
   HEAD ✓; `e2ecd62e^..e2ecd62e` delta touches only scene-frontier topics
   (disjoint from the bound documents, driver, and both g6 evidence dirs) ✓;
   both g6 evidence dirs have exactly 101 tracked files at HEAD, all 101
   byte-match disk, 0 tracked files missing ✓; `ds-g6-major-time-binding-
   20260913-01/` has 0 files in the HEAD tree and is gitignored on disk
   (cannot serve as tracked anchor) ✓; `.gitignore:53` = `/validation/*/` ✓.
10. **Supersession registration** — note §1/§8 registers old B bytes
    `8b222e1d…` (3182 B) and the pre-remediation note/test identities
    (`e9f74bfc…`/11165 B, `f1db73fc…`/45920 B) as superseded; the `-02`/
    `-01` directories are excluded, not trusted ✓.

## 3. Test execution

- Normal run: `python -m unittest validation.test_omp_g6_first_step_context -v`
  → **32/32 OK** (3.5 s).
- Repo-external private temp index (`/tmp/wksim-omp-g6-idx03-…` via
  `mktemp`, `GIT_INDEX_FILE` exported; never the real index):
  `git read-tree HEAD`, then staged exactly the four candidates
  (three docs via `git add`; the gitignored test via `git add -f`);
  temp-index entry count 10770 (= HEAD tree 10766 + 4);
  `git diff --cached --name-only HEAD -- <4 paths>` = exactly the four
  candidates → **32/32 OK** (3.2 s). Temp index deleted afterwards.

## 4. Real-index immutability proof

`git ls-files -s | sha256sum` before all operations:
`5e08ccabec2775053b28f34e44eedd55db1a8b37ef8b4d895023d651f4b835ef`;
after all operations (including both test runs): **identical**. No
`git add/reset/clean/commit/push` was run against the real index at any
point. Worktree status: the two known pre-existing modified files plus
`docs/coordination/mixed-work-overrun-20260913-v2.md` (external parallel-batch
drift, mtime 2026-09-14 20:16, appeared mid-review, not caused by and not
related to this batch — investigated, left untouched). Protected and
unrelated files preserved.

## 5. Findings

- **P1: none.**
- **P2: none.**
- **P3-1 (wording precision, non-blocking):** note §5 says the two evidence
  directories' "现有文件…已被显式提交跟踪（101 个跟踪文件，无未跟踪残留）".
  All 101 tracked files byte-match disk and there is no untracked-and-unignored
  residue (the test asserts exactly this), but 125 additional on-disk files —
  Simulink build caches under `run-01/cache/` (`slprj/`, `.slxc`) — exist,
  gitignored, untracked. Under git semantics "ignored ≠ untracked" the
  statement is defensible, yet a reader can misread it as "on-disk contents ==
  101 files". No byte change requested; interpretation is already protected by
  the test's `unignored == []` check.
- Environment observations (not defects of the batch): stray untracked
  `%TEMP%audit26-report.json` at repo root (literal `%TEMP%` expansion failure
  from a parallel batch); the `mixed-work-overrun-20260913-v2.md` drift above.

## 6. Verdict

**PASS — ADOPT.** P1 = 0, P2 = 0, P3 = 1 (non-blocking). The remediated
ingest note and its context test are byte-bound, all material claims verified
independently, both test runs pass, the real index is proven unchanged, and
the batch closes only the owner-ruling subissue with all scope boundaries
intact (no G6/Full acceptance, no #83 rerun, 23 states / stage mapping /
native / full-window remain).
