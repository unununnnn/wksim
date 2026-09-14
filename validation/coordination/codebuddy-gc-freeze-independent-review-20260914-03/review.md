# Independent review 03: remediated GC-freeze candidate (P2-1 / P3-1)

Reviewer: independent session (read-only over the real repository; the only writes
are the three artifacts in this directory). Window: 2026-09-14, closed
`2026-09-14T22:04:22+09:00`; real-repo HEAD `ee6eb88819cefe255f22e788c39a77c0bbab490e`
("Bind native-wait context offline"), branch `main`, Python 3.13.11, git 2.53.0.windows.1.

Context read before review: `AGENTS.md`, `CONTEXT.md`, the two bound candidates, the
prior review `validation/coordination/codebuddy-gc-freeze-independent-review-20260914-02/`
(`review.md`, `review.json`, `SHA256SUMS`), and `validation/coordination/codebuddy-gc-freeze-independent-review-20260914-01/`.

## 0. Candidates (byte-verified before and after every run)

| Candidate | SHA256 | Bytes | Verified |
|---|---|---|---|
| `docs/coordination/codebuddy-gc-freeze-review-20260912.md` | `64d0e8766274df1ac8cd8d136ec9300b080bc755e0a1694a1272aae3ad406546` | 10594 | yes (pre-run and post-run recompute) |
| `docs/coordination/codebuddy-gc-freeze-ingest-note-20260914.md` | `f68c165fc44e07b22f40b82f3df956dca03f13bea1d4bdcb2d35e3c8808fa853` | 14664 | yes |
| `validation/test_codebuddy_gc_freeze_context.py` | `91dc7bf443a6ad1117cf59c7cec8a0529ab9d90a5d27cc42ea4a8859669d8b6e` | 38435 | yes |

All three match the dispatch-declared hashes/sizes exactly. The review doc and the note
are byte-identical to review-02's candidates; only the test file changed
(review-02 candidate `b0122691a7536bde74d5d0e1a29267fec7c9893914a3ee466fb9dccb7b5d135c`
/ 35278 → `91dc7bf4…` / 38435, +3157 bytes). No tracked or untracked file anywhere in
the repository pins either the old or the new test-file hash
(`git grep b0122691…` → exit 1; `git grep 91dc7bf4…` → exit 1), so the test-file revision
does not invalidate any byte binding, and the unchanged note byte-pin
(`f68c165f…` / 14664) remains authoritative under state A (pre-admission).
The note does not pin its companion test hash (note §9.2 binds only NOTE SHA256/size),
so no note rebinding is required.

## 1. Remediation verification

### 1.1 P2-1 — genuine valid-object non-ancestor exit 1 — **RESOLVED (verified)**

`TestArchitectureAncestor.test_genuine_non_ancestor_rejected`
(`validation/test_codebuddy_gc_freeze_context.py:591-648`) builds a repo-external
temporary git repo (no dependency on any local object), creates two unrelated root
commits with `mktree` + `commit-tree`, asserts the raw `merge-base --is-ancestor`
exits **1** (genuine non-ancestor, valid commit objects), asserts the fabricated
`OTHER_FAKE_SHA` still exits **128** (distinct failure mode preserved), then drives the
real `check_ancestor` over that repo (module-global `git` rebound for the duration,
restored in `finally`) with a self-ancestor control (must pass) and the genuine
non-ancestor (must raise `AssertionError`).

Independent fail-open probe (module loaded from its real path, `check_ancestor` swapped
for mutants, no repo file touched), command:
`python "$env:TEMP\gc-freeze-review-03-p2probe.py"`

```
control(real)        ran=2 failed=0 failed_tests=[]
mutant_exit128_only  ran=2 failed=1 failed_tests=['test_genuine_non_ancestor_rejected']
mutant_exit1_only    ran=2 failed=1 failed_tests=['test_non_ancestor_rejected']
```

`mutant_exit128_only` is exactly the fail-open regression P2-1 described (reject only
the invalid-object exit 128, treat exit 1 as pass): it is now **caught** by the new
negative and was not caught before. `mutant_exit1_only` shows the two negatives cover
distinct git exit codes and are non-redundant. The reviewer also re-confirmed the
review-02 fix hint at the current HEAD: `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce` is a
valid local commit (`cat-file -t` → `commit`) and `merge-base --is-ancestor 5dcd8cfa… HEAD`
exits 1 — available but no longer needed by the test.

### 1.2 P3-1 — temp-index candidate set exact equality — **RESOLVED (verified)**

`TestTemporaryIndex.test_candidates_staged_exactly` (lines 805-822) now asserts
`staged == set(CANDIDATE_PATHS)` (equality, not subset), keeps the stage-0 and
index-blob-equals-working-bytes checks per candidate, and the module docstring
(lines 50-54) matches the strengthened assertion.

Negative control (temp index deliberately holding a 4th file), command:
`GIT_INDEX_FILE=<tmp>/tempindex` + `git read-tree --empty` + `git add -f` the three
candidates + `git add -f AGENTS.md` + `WKSIM_GC_FREEZE_TEMP_INDEX=1` +
`python -m unittest validation.test_codebuddy_gc_freeze_context`

```
Ran 48 tests in 1.073s
FAILED (failures=1)
FAIL: test_candidates_staged_exactly … AssertionError: Items in the first set but not
the second: 'AGENTS.md' … got: ['AGENTS.md', …three candidates…]
```

Exactly one test fails — the strengthened assertion — and only that one. Under the old
subset assertion this 4-entry index would have passed. The positive exact-three case is
green in §3 (Mode B).

### 1.3 Regressions from the remediation — none found

The only behavioral changes are the added negative (§1.1) and the tightened equality
(§1.2). The invalid-object negative, byte bindings, pinned snapshots, lifecycle A/B/C
detectors, mutation negatives, nonclosure and #83 boundaries are unchanged and still
green in all three modes.

## 2. Protected files, ancestry, nonclosure, #83 no-rerun

- **Protected files (byte-pinned by the suite), unchanged from the audit baseline:**
  `docs/Prometheus.gitmodules.reference` = `5aa703020961433befcb2f74cd0432e14fbba139db1fd0616b34c6abf0223855`
  (492 bytes); `validation/coordination/short-cycle-dispatches.json` =
  `06e65cc1cd7d3aa467740f586e92d5e1de00cc973c07db49694c2c6a73862838` (1268 bytes).
  `TestNoElevation.test_protected_files_untouched` passed in A/B/C. The three further
  files the note §0 lists as untouched were also left alone by this review
  (`rolling-six-plan-20260912.md` `fbe93cbe…`, `claude-native-wait-next-probe.md`
  `443979e7…`, `validation/_probe_delivery_contract.py` `226b4c1d…` — hashes recorded
  observationally; no baseline exists for them).
- **Ancestry (fail-closed) at HEAD `ee6eb888`:** `merge-base --is-ancestor
  31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD` → exit 0;
  `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` → exit 0; note §9.1's revision-time HEAD
  `438ab764c0cf70f9e017cfbd82aeb04255282e3a` → exit 0. Re-verified exit 0 for both
  anchors inside the Mode-C clone (HEAD `2f47e116…`, descendant of `ee6eb888`). No
  exact-HEAD equality assertion remains anywhere in the suite.
- **Nonclosure:** `check_note_boundaries` passes; the six required negation phrases are
  present and none of the ten elevation phrases (`验收通过`, `已批准`, `已收口`,
  `performance_pass=true`, `#83 通过`, …) occurs — independently re-confirmed by an
  outside-the-suite case-insensitive scan of the note (no hits). The mutation negative
  (`test_note_detector_fails_on_elevation_mutation`) still fails on an elevation-mutated
  copy. Review doc §7 preserves the `未通过 / 未证` list.
- **#83 no-rerun:** plan text (`git show HEAD:docs/plan/33-rate-measured-candidate-20260912.md`)
  carries the current-conclusion block with `**#83 不重跑**` (public PV `1w6dru32` CLOSED;
  C1 remains a hypothesis; must not trigger/suggest/substitute a #83 rerun) and
  `C1 仍是假说`; the note carries `不是 #83 证据`; the suite's forbidden-phrase list
  rejects `#83 通过`, and the delivery boundary stays
  `candidate_source_delivery_not_flight` with `native_started=false`. The suite spawns
  only `git` (two `subprocess.run` sites: the module `git()` helper and the temporary-repo
  `tgit` in the new negative); it starts no native/ROS/DDS/SITL/PX4/MATLAB/Unreal stack
  and runs no #83 artifact.

## 3. Test execution (all offline; no git replace; no network; no native stack)

- **A — normal current worktree (real repo, lifecycle state A pre-admission):**
  `python -m unittest validation.test_codebuddy_gc_freeze_context -v` →
  **Ran 48 tests, OK (skipped=2)** (0 failures, 0 errors; skips = the `TestTemporaryIndex`
  class under its env guard). Real index fingerprint
  (`git ls-files -s | git hash-object --stdin`) `eed3f1811e3d9277f765d93bcfd07d40b7ccea62`
  before **and** after; HEAD `ee6eb888…` unchanged.
- **B — repo-external temp `GIT_INDEX_FILE`, exactly the three candidates:** temp index at
  `%TEMP%\wksim-gcfreeze-modeB-<id>\tempindex` built with `git read-tree --empty` then
  `git add -f` for exactly the three candidates (verified `git ls-files -s`: **3 entries,
  all stage 0**, blobs `f5f5eb43301867826c5b50156f3c1f5aeb41c2dd`,
  `a53592476680af7f99523b3102fc3d6b305eabd3`, `d1f305a9d7fbaa09b6f5cc1010595c2ae6a05aba`,
  each equal to `git hash-object` of the worktree file), `WKSIM_GC_FREEZE_TEMP_INDEX=1` →
  **Ran 48 tests, OK (skipped=0)**. Real index fingerprint re-verified unchanged after the
  run; temp index and directory deleted.
- **C — natural committed scratch clone, `core.autocrlf=false`:** repo-external clone
  `git -c core.longpaths=true -c core.autocrlf=false clone --no-hardlinks --single-branch
  --branch main <real repo> <tmp>/s`; clone config verified `core.autocrlf=false`,
  `core.longpaths=true`; checkout verified clean (`git status --porcelain` = 0 lines) and
  `HEAD:tools/compare_joint_gc_diagnostics.py` present; worktree runner hash
  `c8577093a62e4993c8048a69f4501984b3ee9045b8a73d26fb83aedc73acbb3b` / 79221 bytes as pinned.
  Copied in exactly the three candidates, the untracked evidence
  `validation/coordination/gc-diagnostic-comparator-20260912/self-check-7bdfxkb.json`, and
  the two tracked-dirty protected files (whose worktree bytes the suite byte-pins); then a
  natural `git add` (3 paths) + `git commit -m "Bind gc-freeze context offline"` →
  clone HEAD `2f47e116a822c824f35fbbf8bbd55194bb007779`, parent
  `ee6eb88819cefe255f22e788c39a77c0bbab490e`, `git show --name-only` = **exactly the three
  candidates**. Suite → **Ran 48 tests, OK (skipped=2)**; clone HEAD unchanged after the
  run; clone and temp root deleted. Real index fingerprint and HEAD re-verified unchanged.
- **Environment note (not a candidate defect):** the first Mode-C attempt failed during
  checkout of very deep paths (`validation/scheduler-kernel-bpf-…`: "Filename too long"),
  leaving the clone without an index; a naive `git add` + `commit` there produced a
  whole-tree-rewriting scratch commit. That clone was repo-external, was deleted, and the
  real repository was never touched (index fingerprint and HEAD identical before/after).
  Mode C must be run with `core.longpaths=true` on Windows; the §3-C results above are from
  the corrected run with a verified-clean checkout.
- No disjoint commit appeared in the real repository during the window (HEAD `ee6eb888` at
  start, between runs, and at close).

## 4. Operational attestations

- Real index never staged or mutated: fingerprint `eed3f181…` identical before Mode A,
  after Mode A, after Mode B (and its negative control), after Mode C, and at close.
- No real-repo commit / reset / clean / checkout / restore / push; no ref mutation (HEAD
  constant `ee6eb888…`); no network; no `git replace`; no native/MATLAB/ROS/DDS/SITL/
  flight/hardware/UE activity; #83 not touched or rerun; no sibling project touched.
- All temporary artifacts (temp indexes, temp clone, probe script) were created outside the
  repository and removed; no leftover `wksim-*` clone/index artifacts from this review
  remain.
- Candidates untouched: all three hashes/sizes recomputed identical at close.
- **Concurrent worktree drift observed (external actor, informational):** during the window
  the real worktree gained untracked paths not created by this review — a zero-byte file
  named `]` at the repo root (`2026-09-14T21:53:40`) and several G6/plan-59 files
  (`docs/plan/59-g6-*`, `tools/check_g6_time_field_forms.py`, `tools/map_g6_uncovered_states.py`,
  `validation/g6-*-20260914.json`, `validation/test_{check_g6_time_field_forms,codebuddy_g6_same_source_activation_readiness,e0_g6_owner_decision_request,map_g6_uncovered_states}.py`).
  None of these is an input to the reviewed suite, none is a candidate or protected file,
  and the real index/HEAD did not move. The worktree is therefore not quiescent; mode-A/C
  results bind the reviewed candidate bytes only.

## 5. Findings

- **P1 — none.**
- **P2 — none open.** P2-1 from review-02 is resolved and independently proven to catch the
  fail-open exit-1 regression (§1.1).
- **P3-1 — resolved.** Exact equality asserted and proven non-vacuous by a 4-entry negative
  control that fails only that assertion (§1.2).
- **P3-2 (informational, no action required):** the new negative rebinds the module-global
  `git` for its duration. It restores it in `finally` and is safe under sequential
  `unittest`/`pytest`, but it would be unsafe under intra-process parallel execution
  (for example a threaded `-n` runner). The suite has no such mode; if one is ever added,
  prefer an injectable helper or a context manager.
- **P3-3 (informational, environment):** `test_head_drift_boundary` still byte-pins the
  current runner (`c8577093…` / 79221); a future legitimate runner change will require a
  rebinding revision (accepted in review-02 and note §9.2).
- **P3-4 (informational, environment):** Mode C on Windows requires `core.longpaths=true`;
  without it the checkout of this repository is incomplete and any "postcommit" run there is
  meaningless (§3).

## 6. Verdict

**KEEP.**

Both dispatched remediation items are genuinely closed: the ancestry negative now exercises
a valid-object non-ancestor with `merge-base --is-ancestor` exit 1 and demonstrably catches
the fail-open regression that previously escaped; the temp-index assertion is exact set
equality and demonstrably rejects a superset. All 48 tests pass in Mode A (48, OK,
skipped=2), Mode B (48, OK, skipped=0, exact-three temp index) and Mode C (48, OK,
skipped=2, natural commit in a `core.autocrlf=false` clone), with protected bytes, ancestry,
nonclosure and the #83 no-rerun boundary intact and the real repository unmutated. No P1 or
P2 finding remains; the P3 items are informational and do not require rework.

## 7. Blockers

None.

— Independent review 03, 2026-09-14.
