# Independent review: owned-scheduling historical-context candidates — 2026-09-14

Independent CodeBuddy review, non-implementing. Read-only over the worktree; the only writes are
the three artifacts in this directory. No Git mutation of the real index/refs, no network, no
native/model/MATLAB/ROS/DDS/SITL/FC/UE/build runs. #83 (CLOSED/PASS) not touched; #84/G6/Full not
touched. All unrelated and in-progress files excluded and untouched.

## 1. Authority and identities (recomputed by this reviewer)

- Authoritative HEAD: `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` — matches `git rev-parse HEAD`
  at review start (expected baseline confirmed).
- Architecture baseline `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` is an ancestor of HEAD
  (`git merge-base --is-ancestor` exit 0, independently re-run).
- Candidates (SHA256 + bytes recomputed by this reviewer, both match the dispatch exactly):

| Candidate | SHA256 | Bytes |
|---|---|---|
| docs/coordination/codebuddy-owned-scheduling-ingest-note-20260914.md | `a8559e33f75d4475a4756787ab724b3c3338db4df8832a8fed6037c7d0da75a7` | 10688 |
| validation/test_owned_scheduling_context.py | `07d5f11be9d6e83198a51828bc503e83a1f2c5ea3697120753cf0ed4a2f2a884` | 23376 |

## 2. Independent verification of ingest-note claims (all re-derived, not restated)

Every claim below was recomputed by this reviewer against the tracked tree at HEAD
`31e5b65f…`; tracked files were additionally checked byte-identical to their HEAD blobs
(`git cat-file` SHA256 of blob content == worktree SHA256).

1. **Five source docs** — SHA256/sizes match note §1 exactly:
   review `e7641f65…`/5598, comparison-review `2bc26aaf…`/4878, snapshot `b4f1f532…`/7470,
   comparison `0dfd79ad…`/6365, e2e `fc7a74d7…`/6709. All tracked, worktree == HEAD blob.
2. **Six tracked anchors** — SHA256/sizes match note §2 exactly:
   capture `a3f3badd…`/20901, test_owned `a0e747d3…`/22401, compare (current)
   `13a61a7f…`/21412, test_compare (current) `a8eb584d…`/21061, source-compare-v1
   `033d8af8…`/21218, source-run-e2e-v1 `b2e691cd…`/8226. All tracked, worktree == HEAD blob.
3. **Semantic anchors at claimed lines** — verified by direct source reads:
   capture `:458` `performance_verdict="not_evaluated"`, `:462` `open("x", …)` exclusive
   output, `:327` `read_bytes()` raw-byte hashing, `kernel_prio` rename `:105,222-225`,
   `sched_schedstats_disabled/unreadable` `:203,205`, `thread_identity_changed` `:276-277`,
   `_identity_problem` `:380,405,415`; compare `:140` `_as_int`, `:160`
   `invalid_counter_value`, `:121` `host_sched_schedstats_not_enabled(`, `:126`
   `runqueue_counters_valid") is True`. Test def counts: 18 in
   `validation/test_owned_scheduling.py`, 23 in `validation/test_compare_owned_scheduling.py`
   — consistent with the historically reported 31/40 collected (parametrize expansion).
4. **Current vs historical comparator** — current tracked comparator is `13a61a7f…` (21412B),
   recorded by the 主会话收口补记 in owned-scheduling-comparison-20260913.md; it supersedes the
   comparison-review pin `033d8af8…` (21218B), whose exact bytes are preserved as
   `validation/coordination/owned-scheduling-e2e-20260913/source-compare-v1.py` (byte-exact,
   verified). Old evidence pins are not rewritten.
5. **Historical test pin limitation is real** — the comparison-review pin
   `20cc459052c2cf8d860e2c1583334e583abd3b95c3d022a8a0795580ab8642fe` (19740B) has **no** byte
   copy anywhere in the tracked tree at the anchor: this reviewer hashed all 8719 unique blobs
   of `git ls-tree -r 31e5b65f…` via `git cat-file --batch`; zero matches. The note's framing
   (documented limitation; must not be presented as current fact) is accurate.
6. **e2e result pins** — `owned-scheduling-e2e-20260913/result.json`: `verdict="pass"`,
   `source_sha256` == {capture `a3f3badd…`, compare `033d8af8…`, run_e2e `b2e691cd…`} exactly
   as pinned in the note and the candidate test.
7. **Flight snapshots (both runs, both phases)** — verified per-file:
   - schema `wksim.owned-scheduling-snapshot.v1`; `sampler_sha256` == capture tool
     `a3f3badd…`; 11 roles (manager, px4-{agent,control,fc,model,task},
     arducopter-{agent,control,fc,model,task}) all `captured` in before and after;
   - `host.sched_schedstats == "0"` (string), `CLK_TCK == 100`,
     `performance_verdict == "not_evaluated"`;
   - `children.sha256`, `boot_id`, run_id match pins exactly; byte sizes match note §3
     (228813/331637 and 228656/331602); before/after raw-byte SHA256 match both the pinned
     values and the `result.json.owned_scheduling` recorded values (chain intact);
   - `result.json`: `classification="diagnostic_only"`, `full_acceptance=false`,
     `initialized=true`, `flight_completed=false`,
     `error=RateUnmet('rate_unmet/resource_insufficient')` for both runs;
   - monotonic_ns pins match and strictly increase (91625358121 → 270719650116;
     97474541343 → 316507734204).
8. **Supersession framing** — the five docs are 2026-09-13 historical context (then-HEAD
   `820f5323` exists in history; current HEAD `31e5b65f`); the note claims no acceptance
   status for the current HEAD from them. Correct.
9. **Forbidden-promotion language** — note §4.4 contains the exact prohibitions; the note
   contains no acceptance/G6/Full PASS claims, no `flight_completed=true`, no
   `full_acceptance=true`. e2e is framed as ordinary-Python verifier/spinner smoke, not
   SITL/model/native evidence; sched_schedstats=0 nulls are not read as "no runqueue wait";
   `kernel_prio` is not RT priority. All boundary language verified against the source docs.
10. **Preserved frozen gates** — note §3 restates (without re-verification claims) the 1ms
    tick / native barrier / 4-tick group / no catch-up / 100ms late limit / full sliding
    window / physics and identity gates. Restatement only; no promotion attempted.
11. **Drift / rerun policy** — implemented in the candidate test as described: anchor-pinned
    content reads (`git show ANCHOR:path`), HEAD-mismatch skip, unreachable-anchor skip
    (fail-safe), byte/hash mismatch FAIL, candidates absent at anchor (verified: both paths
    untracked, absent from the anchor commit), staged-index mode asserts candidates staged in
    the external index with blob == worktree bytes and absent from the real index.
12. **Exclusions respected** — `docs/Prometheus.gitmodules.reference`,
    `validation/coordination/short-cycle-dispatches.json`,
    `docs/coordination/rolling-six-plan-20260912.md`,
    `docs/coordination/claude-native-wait-next-probe.md`,
    `validation/_probe_delivery_contract.py`, `%TEMP%audit26-report.json`, failed review dirs,
    and all other in-flight untracked files: untouched; `git status --porcelain` identical
    before/after review actions.

## 3. Tests executed (proven behavior)

1. **Normal mode** (no `GIT_INDEX_FILE`):
   `python -m unittest validation.test_owned_scheduling_context -v`
   → **Ran 25 tests, OK (skipped=1)** — the only skip is
   `TestStagedIndexMode.test_staged_index_contract`, which by design is inactive without
   `GIT_INDEX_FILE`. 0 failures, 0 errors.
2. **Staged-index mode** (single repo-external temporary `GIT_INDEX_FILE`, copied from the
   real index, staging exactly the 2 candidates + 3 review artifacts = 5 new paths):
   `GIT_INDEX_FILE=<repo-external tmp> python -m unittest validation.test_owned_scheduling_context`
   → **Ran 25 tests, OK** (staged-index contract executed: both candidates staged in the
   external index with blob hashes equal to worktree bytes; real index does not contain
   them). 0 failures, 0 errors, 0 skips.

Staged-index proofs (all with the single external temp index):
- `git diff --cached --name-status HEAD` → exactly 5 lines, all `A` (added): the 2 candidates
  + 3 review artifacts. No `M`, no `D` — no existing-path changes or removals.
- `git diff --cached --check HEAD` → no output, exit 0 (batch diff-check clean).
- Real `.git/index` SHA256 recorded before and after the entire staged phase: unchanged.
- `git status --porcelain` before/after: identical.

## 4. Findings

- **P1: none.**
- **P2: none.**
- **P3 (observations, no action required):**
  1. Ingest note §8 is an explicit placeholder (占位) delegating final SHA/counters to the
     batch report; the note's §1/§2 tables are themselves complete and verified, so no gap
     remains, but consumers should treat the batch report as the delivery receipt.
  2. The candidate test pins `NOTE_SHA256`/`NOTE_SIZE` of the ingest note; any future edit of
     the note requires re-pinning both constants. This coupling is documented in the note (§8)
     and in the test's failure message — by design, listed for awareness.
  3. The 31/40 collected-test counts cited in the note derive from the 2026-09-13 review docs
     (pytest parametrize expansion) and were not re-executed in this review (old suites are
     out of scope); the 18/23 def counts were verified directly and are consistent.

## 5. Boundaries and limitations

- This review proves only the offline historical-context ingest batch: identities, tracked
  evidence anchors, snapshot chains, boundary/supersession language, and the candidate test's
  offline assertions. It is **not** acceptance for #84/G6/Full, not a performance result, and
  not native/SITL evidence. `diagnostic_only` / `full_acceptance=false` /
  `performance_verdict=not_evaluated` / `attribution=not_evaluated` /
  `flight_completed=false` (RateUnmet) remain exactly as recorded; no promotion is authorized
  by this review.
- The historical test pin `20cc4590…`/19740B cannot be anchored to tracked bytes (exhaustive
  blob search, zero matches) — a documented limitation of the historical comparison review,
  correctly disclosed in the note; it must not be cited as current fact.
- Historical tail values (e.g., 57419470ns/54569053ns) belong to the 2026-09-13 sessions and
  were not transferred to the current HEAD.

## 6. Independence

Reviewer is non-implementing: the two candidates were authored by a prior batch, not by this
review session. All identities recomputed; all claims re-derived from tracked bytes and live
`git` plumbing reads; the candidate test was executed twice (normal + staged) by this
reviewer. No candidate file, tracked file, excluded file, or the real index was modified. No
manifest created. Reviewer output limited to the three files in this directory.

## 7. Verdict

**PASS / ADOPT** — P1 = 0 and P2 = 0; both candidates verified against tracked evidence and
both test modes green (25/25 executed assertions passing in each mode; the single normal-mode
skip is the by-design inactive staged-index contract).

Artifact SHA256 values are recorded in `SHA256SUMS` (covers `review.md` and `review.json`
only).
