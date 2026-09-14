# Independent admission review — native-wait offline context batch (2026-09-14-01)

Reviewer: CodeBuddy (independent). Scope: read-only admission review of exactly four
candidate files; offline; no native/ROS/DDS/UE/SITL/MATLAB/build/flight runs; no
staging/commit/ref changes to the real index or refs.

## Batch candidates and drift check

| # | Path | Expected SHA256 | Actual SHA256 | Expected/Actual bytes |
| --- | --- | --- | --- | --- |
| 1 | docs/coordination/native-wait-integration-contract-20260913.md | 947e759873513ce8d1f11363cb6df9c8c5fc7dc1c868037fbff3b24e90a7b823 | same | 6132 / 6132 |
| 2 | docs/coordination/claude-native-input-timing.md | f15cd0e28396722c23e005f38b2738ca2dfa889975f5f38ae345b7cbacaf0735 | same | 8714 / 8714 |
| 3 | docs/coordination/codebuddy-native-wait-contract-ingest-note-20260914.md | 9a34cb0aea15dd1469699d70facd8b3d6d93f9f3a3394b75e9fa986564de21a6 | same | 7740 / 7740 |
| 4 | validation/test_codebuddy_native_wait_contract_context.py | bebfec48087395f1ec9b5fdbf1082c4c5851a7503b943271f16487d852559906 | same | 26483 / 26483 |

All four byte-match the dispatch exactly. No candidate bytes changed during review;
reviewed content is the expected content.

## Repository state at review

- HEAD: `438ab764c0cf70f9e017cfbd82aeb04255282e3a` ("Bind G6 first-step context offline").
- Ancestry (exit 0 for both): `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → 0;
  baseline `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` is a direct ancestor (3 commits back in `git log`).
  No HEAD-equality was asserted anywhere, per dispatch.
- Candidates 1–2 are tracked (`git ls-files`) and status-clean for those paths; candidates 3–4 are untracked (`??`).
  Lifecycle at review time = pre-admission, which the test suite accepts.

## Evidence-binding verification (note + test vs current bytes)

Independently recomputed (sha256sum / wc -c), all match the note §1/§2 and the test pins:

- `Simulator/wksim_runtime/joint_rate.py` 0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4, 7271 bytes
- `Simulator/wksim_runtime/joint_rate_probe.py` a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653, 7826 bytes
- `Simulator/wksim_runtime/joint_profile.py` 90cc868b8050b41e54ef0c38cf20104c58aefb97f07d1448dfd0be1f8633320a, 31113 bytes
- `Simulator/wksim_core/joint.py` f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50, 15808 bytes
- `validation/33-formal-promotion/current-mixed-oxv29042/result.json` 68114715ac4057337fe8174cd708f03ae8343e205335ab61a63ca4ad47e73dbd, 130322 bytes

Line anchors read directly from current bytes and confirmed:
- joint_rate.py: `LATE_LIMIT_NS=100_000_000` (6); no-catch-up `earliest=max(ideal,…,previous_start+self.period_ns)` (93);
  first final-1ms branch 99–103 with spin 100–101; second branch 114–118 with spin 115–116;
  window-invariant comment 120–123; sleep 124; `actual_start_ns=now`/`previous_start=now` 126–127;
  `rate_group_start` record 128–130.
- joint_rate_probe.py: `def timing_probe_enabled` 23, env contract "must be unset, 0 or 1" 30;
  `def timing_probe_identity` 33 with `classification="diagnostic_only"` 36; terminal/actual/ideal group reads 221–224.
- joint_profile.py: marker rejection loop 274–275, tuple `('rate_timing_probe','group_work_timing','perf_switch_capture')` at 274;
  `required = {` 330 with both pacer files at 333 (`'Simulator/wksim_runtime/joint_rate.py',`) and 334
  (`'Simulator/wksim_runtime/joint_rate_probe.py'}`); `if not required <= sources.keys():` 335;
  byte-sealing check `'source__'+name.replace('/','__')+'.txt'` 338.
- joint.py: opt-in gate `self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'` at 54 (comment 53).
- result.json (parsed, not just hashed): `status="failed"`, `source_unchanged=True`,
  `source_sha256` contains both pacer files with values byte-equal to the current worktree
  (`0b53a16a…`, `a8bac9ac…`), 37 sources total.

Contract §5 historical-drift registration (note §3) is accurate: the contract's
"required set at joint_profile.py:328-331 does not contain the two pacer files" and its
single-marker (`rate_timing_probe`) negative-only binding are **historical**; current bytes
place the required set at 330–334 *including* both pacer files, and the marker list at 274
*includes* `perf_switch_capture`. The note records the drift explicitly without rewriting
the pinned contract bytes. The test asserts both facts side by side
(TestHistoricalDrift) and I confirmed both against source.

## Exclusions / protected paths

- `docs/coordination/claude-native-wait-next-probe.md`: `git ls-files --error-unmatch` exit 1
  (untracked). It appears in no pin table and is excluded from `CANDIDATE_PATHS`
  (test lines 450–452); the note §5 refuses to bind or endorse it. Confirmed.
- `docs/coordination/perf-stream-contract-20260913.md`: tracked, treated as a live pointer
  outside the batch (note §5; test lines 433–440). Confirmed.
- No other protected path is a candidate; the batch is exactly the four files above.

## Test execution (offline; exact commands)

1. Normal mode: `python -m unittest validation.test_codebuddy_native_wait_contract_context -v`
   → **Ran 30 tests … OK (skipped=2)** (the 2 skips are the temp-index-only class).
   Meaningful normal run: 28 assertions-bearing tests pass, including byte/HEAD-tree pins,
   line anchors, drift coexistence, ancestry, exclusions, lifecycle, and 7 mutation negatives.
2. Temp-index mode (repo-external, real index untouched):
   - `TI=$(mktemp -u)` → `/tmp/tmp.x68vWcdFyT` (outside the repo, non-existent path; git created it).
   - `GIT_INDEX_FILE=$TI git add <4 candidate paths>` → `git ls-files -s` under that index
     shows **exactly 4 entries, all stage 0**:
     `6f74e3f7 claude-native-input-timing.md`, `2b5c5a90 codebuddy-native-wait-contract-ingest-note-20260914.md`,
     `cf16f7fd native-wait-integration-contract-20260913.md`, `27401ba0 test_codebuddy_native_wait_contract_context.py`.
   - `git diff --name-only` (index vs worktree) → empty ⇒ staged blobs byte-identical to working bytes.
   - HEAD blob comparison: `6f74e3f7` and `cf16f7fd` equal the HEAD blobs of the two tracked docs
     ⇒ staged delta vs HEAD is **A (new)** for candidates 3–4 only; no M, no D.
   - `WKSIM_NATIVE_WAIT_TEMP_INDEX=1 python -m unittest …` → **Ran 30 tests … OK** (0 skipped),
     including `test_candidates_staged_stage0_blob_identical` and
     `test_tracked_anchors_present_in_real_index`.
   - Real-index fingerprints byte-identical before/after both runs:
     `.git/index` sha256 `327b22366c0ba7cb1e3fbddc8cd41023541b92f3cea745af754aba1b41862976`;
     `git ls-files -s | sha256sum` `5de63e159c44d37a72acfecee8c178ab154b80b00d36cb9130588e9042f5a8ef`.
   - Temp index deleted afterwards; no scratch artifacts written inside the repo.
3. Ancestry: `git merge-base --is-ancestor 31e5b65f… HEAD` and `f333316e… HEAD` both exit 0.
   No exact-HEAD-equality is used by the suite (BASELINE_HEAD appears only in an is-ancestor call
   and as a text anchor in the note).

## Findings

### P1 (blocking) — none

### P2 (should fix before or at admission) — none

### P3 (observations, no action required)

1. **P3 — contract-internal line drift already covered by byte-binding.**
   Contract §5 cites "joint_profile.py:334-339" for the sealing loop; in current bytes that
   loop is at 337–339. This is inside the pinned contract bytes and the note's §2/§3
   explicitly bind line anchors only "对当前 tracked 字节", so no edit is needed or permitted
   here; recorded so future readers do not treat contract §5 line refs as current.
2. **P3 — concurrent sibling activity inside the review window.**
   `git status` during the session shows modifications to
   `docs/Prometheus.gitmodules.reference`, `docs/coordination/mixed-work-overrun-20260913-v2.md`,
   `validation/coordination/short-cycle-dispatches.json`, plus sibling untracked files —
   none attributable to this review (candidates' scoped status is `??` for note/test only,
   clean for the two bound docs). Per established practice the "real index untouched" proof
   uses byte-stable `.git/index` + `ls-files -s` hashes rather than a full-tree status hash;
   a full-tree status hash would not have been meaningful here.

## Limitations

- The external `/root/wksim-scheduler-probe-35728b1-03` capture (tick5504/tick2000 timings in
  candidate 2) is not reproducible in this checkout; this review, like the note and the test,
  treats it purely as a byte-level text anchor and depends on it for nothing.
- The claude doc's own historical test-run claims (8/14/16/9-item runs) are context-only
  bindings, not re-executed here (offline boundary); the files it references all exist in
  this checkout (joint.py, both validation test modules, all three tools).
- Proven behavior vs acceptance: a passing offline slice here is **not** #84 acceptance and
  does not rerun or retire #83; the note and test make the same explicit non-claims.

## Verdict

**KEEP** — all four candidates bind current repository evidence accurately; the test suite is
fail-closed, ancestry-only, lifecycle-safe, and its temp-index mode stages exactly the four
candidates repo-externally without touching the real index. P1=0, P2=0, P3=2.

SHA256 of this file and review.json are recorded in `SHA256SUMS` (self-checked below).
