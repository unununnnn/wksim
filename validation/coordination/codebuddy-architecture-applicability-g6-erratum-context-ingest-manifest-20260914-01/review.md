# CodeBuddy manifest — architecture-applicability G6 erratum context ingest batch (20260914-01)

Writer: CodeBuddy (manifest writer). Batch: admission manifest for the two candidate files
reviewed by `codebuddy-architecture-applicability-g6-erratum-independent-review-20260914-01`.
Offline, read-only over all inputs: no input file was edited; no commit, reset, clean,
restore, checkout, push, ref change, or real-index staging; no network; no native/
MATLAB/ROS/DDS/Unreal/SITL/flight/hardware runs; #83 was not rerun.

## Resume note (this file completes an interrupted batch)

This batch was interrupted after only `exact-paths.txt` had been written. At resume the
manifest directory contained exactly one file: `exact-paths.txt`, SHA256
`b09ca03ae4df67215b4458742c5fab10517dd263eb222d764d29467f3c994e45`, 968 bytes —
re-hashed and confirmed byte-identical to the dispatch pin before any write. Two records
coexist with that file: candidate identity, independent review outputs, and every review
verdict below are the **recorded results of the already-completed independent review**
(`...independent-review-20260914-01`), whose three output bytes are re-verified here, not
re-derived. The independent review has therefore not been redone.

This session created only the three files that were missing and nothing else:
`review.md`, `review.json`, `SHA256SUMS`. `exact-paths.txt` was neither edited nor
re-sorted; the candidates, the review triplet, the real index, siblings, and every
protected/pinned file were left byte-unchanged.

`exact-paths.txt` was verified before writing to hold exactly 9 unique, C-sorted paths
(2 candidates + 3 independent-review outputs + 4 manifest outputs, this set inclusive):
line count 9, `Sort-Object -Unique` count 9, and a case-sensitive sort of the file equals
the file itself.

## Scope: context-only

This batch is context-only. It binds the two candidates as admission context — the G6
erratum (`context-only` by its own §0) and its binding test suite — together with the
independent review that kept them, and registers the manifest quartet. It closes no
conclusion: no #84 closure, no G6 closure, no Full closure, no #83 rerun. No gate is
changed: the accepted gate values (1 ms physical tick, 4 ms common input barrier, strict
four-tick single step, 0.5×/1× tiers with 8 ms/4 ms group periods, no catch-up, >100 ms
`rate_unmet/resource_insufficient` latch, 10 s ±2% / 60 s ±1% / 100 ms phase acceptance)
are cited, never altered, and §2's correction is confined to one bibliographic anchor.

## Pins verified before writing

Every path in `exact-paths.txt` was re-hashed in this session with SHA256 plus byte size.
The eight already-existing paths matched their dispatch pins exactly; the three files this
session created are hashed in `SHA256SUMS` and reported after the staging proof, so the
reported bytes equal the staged bytes.

| Path | SHA256 | bytes | state |
| --- | --- | --- | --- |
| docs/coordination/codebuddy-architecture-applicability-g6-erratum-20260914.md | b2e1d34141a86080927e979df6cb048ebe667bace99bf422394f96c22fb52a20 | 7468 | candidate, untracked |
| validation/test_codebuddy_architecture_applicability_g6_erratum.py | a98b8fd339d02cbb7544dd33bc623a03b9ad0318769745d3aeb3715602799428 | 26527 | candidate, untracked |
| validation/coordination/codebuddy-architecture-applicability-g6-erratum-independent-review-20260914-01/review.md | 653d53d4204edf4c1a7ad8f2c052a1af09d1355df8dcbfaeddb3a184ead02799 | 7378 | review output, untracked |
| validation/coordination/codebuddy-architecture-applicability-g6-erratum-independent-review-20260914-01/review.json | e4993702fc58240ae8cf6b648c9b6abef418be20d833c426e163ce7797faa248 | 5857 | review output, untracked |
| validation/coordination/codebuddy-architecture-applicability-g6-erratum-independent-review-20260914-01/SHA256SUMS | f36236f487e57d4e6b25b0b01685a9828908cd7bee31cdc7880e4cddac10305c | 154 | review output, untracked |
| validation/coordination/codebuddy-architecture-applicability-g6-erratum-context-ingest-manifest-20260914-01/exact-paths.txt | b09ca03ae4df67215b4458742c5fab10517dd263eb222d764d29467f3c994e45 | 968 | manifest output, pre-existing, unedited |
| validation/coordination/codebuddy-architecture-applicability-g6-erratum-context-ingest-manifest-20260914-01/review.md | (see SHA256SUMS) | — | manifest output, created this session |
| validation/coordination/codebuddy-architecture-applicability-g6-erratum-context-ingest-manifest-20260914-01/review.json | (see SHA256SUMS) | — | manifest output, created this session |
| validation/coordination/codebuddy-architecture-applicability-g6-erratum-context-ingest-manifest-20260914-01/SHA256SUMS | (self; not self-hashing) | — | manifest output, created this session |

Git state: the two candidates and all six other paths are untracked and none is in the
HEAD tree (`git ls-tree HEAD` returns nothing for each of the 9). `validation/*/` is
gitignored (`.gitignore:53`), so the manifest and review outputs are status-invisible
without `git add -f`; force-add is used only under a repo-external temporary index. None of
the 9 paths has a tracked counterpart and none is a modification of committed bytes.

## HEAD relation

Ancestry checks only, no HEAD-equality assertion, per the batch contract:

- `git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD` → exit 0
- `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0

HEAD at manifest time: `ee6eb88819cefe255f22e788c39a77c0bbab490e` ("Bind native-wait
context offline"). HEAD is observation only; HEAD may advance with unrelated reviewed
commits without invalidating this registration, and no equality with any pinned commit is
claimed.

Zero overlap with the commits after `acf322860831cb2a7c83a45cb4e2586922444c57` (the HEAD
the independent review ran at): the three commits `e832fd2a`, `615c2f8c`, `ee6eb888`
touch 10/9/9 paths respectively, all under other batches (mixed-work-overrun,
perf-counter, native-wait). The union of their touched paths intersected with the 9 paths
of `exact-paths.txt` is **empty (0 paths)**.

## Independent review findings carried into this manifest

The independent review's recorded verdict is carried unchanged, not re-derived:

- Verdict: **KEEP** — both candidates, scope limited to
  `docs/coordination/codebuddy-architecture-applicability-g6-erratum-20260914.md` and
  `validation/test_codebuddy_architecture_applicability_g6_erratum.py`.
- Severity counts: **P1 = 0, P2 = 0, P3 = 3**. Blockers: none.
- P3-F1: erratum gate restatement omits accepted-record protocol details (per-tier ≥3
  independent epochs, 2 s stabilization marking); non-blocking because §4 rule 2 directs
  gate citations to `docs/*-accepted*.md`.
- P3-F2: sealed proposal copy `validation/joint-rate-contract-20260907/approved-proposal.md`
  is untracked; identity rests on disk hash plus the accepted record's own pin, and the
  erratum cites it by SHA256, so identity is unambiguous.
- P3-F3: ADR-0009/0014 consistent-guidance characterizations are judgmental but supported
  and correctly kept non-binding.

## Non-closure and #83 no-rerun (carried)

- No #83 rerun, none triggered and none suggested.
- No #84 closure, no G6 closure, no Full closure.
- No gate change, no architecture approval, no acceptance.
- Fixed gates preserved untouched: four-tick boundary, group structure, no-catch-up
  `previous_start+period_ns` anchoring, 100 ms `LATE_LIMIT_NS`, full-window capture,
  physics step invariants, `diagnostic_only` identity.

## Exclusions

Sibling batches and unrelated sibling artifacts are outside this batch and are neither
bound nor superseded: the `-01` manifest/review quartets and review triplets of the
mixed-work-overrun, perf-counter, and native-wait batches, the earlier
`omp-g6-first-step` context-ingest manifest `-02` and review `-03` trio, and the untracked
`docs/coordination/claude-native-wait-next-probe.md` /
`docs/plan/33-ac5-budget-row-proposal-20260914.md` working notes. `docs/Prometheus.gitmodules.reference`
and `validation/coordination/short-cycle-dispatches.json` show pre-existing modifications
from other sessions; they are not candidates, in no pin table, and were not touched here.

## Staging protocol (executed this session)

The 9 paths in `exact-paths.txt` are staged exactly once for proof, under a repo-external
temporary `GIT_INDEX_FILE` seeded from HEAD (`git read-tree HEAD`), with `git add -f`
(gitignore), leaving the real index untouched. Proven: staged delta vs HEAD is exactly
**9 A / 0 M / 0 D**, all 9 entries at **stage 0**, **9/9** index blobs byte-equal to the
working-tree files, and the scoped index-vs-worktree diff (including `git diff --cached
--check`) clean. The suite is then re-run under that same temp index in exact-9 mode.
Real-index fingerprints (`.git/index` SHA256 and `git ls-files -s | sha256sum`) are
byte-identical before and after; the temporary index is deleted after proof. No commit is
made; staging exists only in the temporary index. Actual blob SHA1s and fingerprints are
recorded in `review.json` and reported in the dispatch thread.

## Test execution

- Normal mode: `python -m unittest validation.test_codebuddy_architecture_applicability_g6_erratum -v`
  → **Ran 31 tests, OK**.
- Exact-9 mode (repo-external temp index seeded from HEAD with exactly the 9 paths forced
  in): `GIT_INDEX_FILE=<tmp>/index python -m unittest validation.test_codebuddy_architecture_applicability_g6_erratum -v`
  → **Ran 31 tests, OK**.

Both totals match the independent review's 31/31 in both of its modes. The suite's git
usage is limited to `rev-parse --verify`, `cat-file blob HEAD:…`, and
`merge-base --is-ancestor`; it inspects no index state, which is what makes the exact-9
temp-index run equal the normal run. Negative tests are in-memory only; the suite modifies
no file.

## Non-claims (explicit)

- This manifest is an admission record only; it is not acceptance, approval, or closure of
  #84, G6, or Full.
- #83 was not rerun and no rerun is triggered or suggested.
- Nothing here re-derives the independent review; its verdict is carried as a recorded
  input whose bytes are re-pinned.

## Outputs

`exact-paths.txt`, `review.md`, `review.json` are hashed in `SHA256SUMS` (the sums file
cannot contain its own hash). Hashes of all three created outputs are reported in the
dispatch thread after the temp-index proof so the reported bytes equal the staged bytes.
