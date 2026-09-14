# Manifest — G6 same-source activation-readiness context ingest batch (20260914-01)

Writer: independent manifest writer (Claude Opus 4.8 (1M context), Claude Code harness),
owner of this manifest batch and of no other file in it. Batch: admission manifest for the
two immutable candidates reviewed by
`validation/coordination/deepseek-g6-same-source-activation-readiness-independent-review-20260914-01`.

Offline, read-only over all inputs: no input byte was edited; no real-index staging, no
commit, no push, no reset, clean, restore, checkout or ref change; no #83 run; no
MATLAB/native/ROS/DDS/SITL/FC/UE/model/build or flight execution; no network or GitHub
query/mutation; no sibling project or sibling batch directory touched.

## Scope: context-only

This batch is context-only and is **not** an acceptance action. It binds the two `#59` G6
same-source activation-readiness candidates plus their anchored independent review, and
registers them together with this manifest quartet. It closes nothing: no #59 closure, no
#84 closure, no G6 closure, no Full closure, no G6 acceptance, no budget approval, no
physical-accuracy claim, and no owner decision. `r1_status` remains `numerical_failed`;
0/120 budgets remain approved; #59/#84/G6 remain open and Full remains not-closed.

## Exact paths (9, byte-ordinal sorted)

Composition: **2 candidates + 3 anchored independent-review outputs + 4 manifest outputs =
9 unique paths**. The four manifest outputs include this file's own directory
(`SHA256SUMS`, `exact-paths.txt`, `review.json`, `review.md`), so all four are staged and
blob-equality-proven, not merely declared.

`exact-paths.txt` is written with LF endings only (9 LF bytes, 0 CR bytes, trailing LF),
9 unique entries, no duplicates, and its order equals the byte-ordinal (`LC_ALL=C`-equivalent)
sort of its own lines. Paths beginning `validation/coordination/` are gitignored
(`.gitignore:53`, `/validation/*/`), so staging requires `git add -f`; the two other
candidates are untracked but not gitignored.

## Pins verified before writing

All six immutable inputs were re-hashed in this session; every SHA256 and byte size matched
the dispatch pin exactly, before and after every test and proof run. All six are LF-only
(zero CR bytes).

| Path | SHA256 | bytes |
| --- | --- | --- |
| docs/plan/59-g6-same-source-activation-readiness-20260914.md | 9958b00feafb9bc6dc0098da123ab6f2a668e06bb03da551eaa56ac46dacb106 | 15498 |
| validation/test_codebuddy_g6_same_source_activation_readiness.py | 3cd1241a0f0e74bf96d0383bddc8a5ee1564fc7840cd9bd1a8b94696117e0fbc | 31570 |
| .../deepseek-g6-same-source-activation-readiness-independent-review-20260914-01/review.md | 2b4c9ccdf7aa92894697efa7f4f4435a5372102f7f001b47476262c71e5a515a | 14370 |
| .../deepseek-g6-same-source-activation-readiness-independent-review-20260914-01/review.json | f5a3b9c845b0e98b37166e1b58e215695e217e21166209b5e6109dbc8d06a73c | 22991 |
| .../deepseek-g6-same-source-activation-readiness-independent-review-20260914-01/SHA256SUMS | 7a4b3832c72cfffcff2cec65b6422757337c73b7a5f027e85df275b62052ad5b | 758 |

The anchored review's own `SHA256SUMS` was independently re-checked from the repository
root: all four of its entry lines match the files they name (the two candidates plus its own
`review.md`/`review.json`), and its declared self-check digest over the four entry lines
recomputes to `73cb551a8962963c6ce510406dd8dd8235142954f62348abc2da5e931e07e466` — verified.
Its `review.json` strict-parses as JSON.

## HEAD relation and ancestry

Ancestry only; no HEAD-equality assertion is made or implied. HEAD is recorded as an
observation, not a gate:

- `git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD` → exit 0
- `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0
- `git merge-base --is-ancestor 0000000000000000000000000000000000000000 HEAD` → exit 128
  (the gate discriminates; it is not a vacuous always-zero check)

HEAD observed at manifest time: `cca825b5bac5bd8b7837a9ac75c85e715b67deb6`. HEAD may advance
with unrelated reviewed commits without invalidating this registration; it has already
advanced past the `ee6eb888` recorded by the anchored review.

## Intervening commits: zero overlap

- Since `31e5b65f`: 7 commits (`ab165c3f`, `438ab764`, `acf32286`, `e832fd2a`, `615c2f8c`,
  `ee6eb888`, `cca825b5`), 77 distinct touched paths.
- Since `f333316e`: 78 commits, 1132 distinct touched paths.

Method: `git log --name-only --format='' <anchor>..HEAD`, de-duplicated with a case-sensitive
sort, intersected with the 9 batch paths. Intersection is **0** for both anchors — no commit
in either ancestry range added, modified or deleted any batch path. Consistently,
`git ls-tree -r HEAD -- <9 paths>` returns no entry (none is in the HEAD tree) and
`git ls-files -s -- <9 paths>` returns no entry (none is staged in the real index). All 9
batch paths are untracked working-tree files.

## Independent review findings carried (unweakened)

Verdict carried from the anchored review: **KEEP**, severity counts **P1 = 0, P2 = 0,
P3 = 5**, `rework_required = false`. The verdict is carried as a recorded result; this
manifest did not re-run the review, re-adjudicate it, or promote any finding.

- **P1:** none. **P2:** none. **Blockers:** none.
- **P3-01** — `applied-input.f64` wording is not what is implemented. §1 step 6 says the
  artifact is byte-identical with the input CSV, but the code compares against a fresh
  row-major little-endian binary64 re-encoding of the parsed CSV rows (entry lines 887–892,
  1007–1009; 501 × 33 × 8 = 132264 bytes), never against CSV text bytes (36822 bytes); the
  native-side statement in step 9 *is* literal byte equality (entry line 1030). No evidence
  claim is weakened — the enforced consistency is at least as strong — but a reader could
  look for an impossible text-vs-binary comparison. Recommend rewording in the next revision.
- **P3-02** — SLX/init identity SHA cross-check is an OR that can skip the SHA comparison.
  Entry lines 395–402 accept `identity.path == resolved staged path` *or* `staged sha ==
  identity sha`. With an absolute identity path string (the R1 identity convention), a wrong
  `identity.slx/init.sha256` passes `validate_execution`. Latent only: no same-source contract
  exists, the staged file's own declared sha256 is still verified against its bytes, identity
  shas do not propagate into evidence, and the BLOCKED readiness conclusion is unaffected.
  Recommend a conjunction when the entry is next revised.
- **P3-03** — some §2 claims are string-checked rather than re-derived. The R1 budget/rule
  summary, the 5+59=64 policy split and "all 24 owner decisions not_made" are verified as
  independently true, but the suite only checks literals/counts. Future hardening: re-derive
  them.
- **P3-04** — the normal-mode index guard is execution-order dependent (informational).
  `TestIndexModes` sorts before `TestPreflightOrder`/`TestSourcePins`/`TestWordingMutations`;
  an index-touching call added to a later class would escape the guard. No such call exists
  today.
- **P3-05** — the §5 reproducibility sentence is exact for blocked paths but reads as
  universal (informational). `_prepare_execution` uses `uuid4` for staging/epoch and refuses
  an existing evidence directory, so a repeat call with the same now-populated `evidence_dir`
  returns `blocked`. Readiness is currently and unconditionally blocked, so this is
  documentation precision only.

All five findings are P3 documentation-precision / future-hardening observations, not defects
that block acceptance of this readiness pair. None is applied, reworded, downgraded or
adjudicated away by this manifest, and none affects decision readiness. This manifest raises
**no finding of its own**. **Nonclosure and residual uncertainty are carried unchanged:**
the suite proves only the properties it encodes (it cannot prove the documented preflight
order is the only reachable order for every future execution identity; the launcher, WSL path
resolver and identity probe are injectable and no contract can currently reach the READY
path); the G0–G6 not-closed statement is consistent with the pinned ledgers but was not
re-derived from a separate closure ledger; and the six pins' own claims were hash-bound and
spot-checked, not exhaustively re-derived from the MATLAB model or the native build.

## Staging protocol and admission proof

The 9 paths of `exact-paths.txt` are staged exactly once for proof, under a
repository-external temporary `GIT_INDEX_FILE` seeded with `git read-tree HEAD`, using
`git add -f` (gitignore). The real `.git/index` is never written.

Proven in the post-write run over all 9 paths: staged delta versus HEAD is exactly
**9 A / 0 M / 0 D** (the temp index held 10851 entries = 10842 HEAD entries + the 9
additions); every entry is at **stage 0** with a regular file mode (`100644`); index blob
bytes are **byte-equal to the working-tree files** for all 9 paths; and the scoped
index-vs-worktree diff is **empty (0 rows)**, which is the byte-fidelity proof. The exact-2
candidate index run and the exact-9 admission index are separate repository-external objects,
and the temporary index is deleted after proof. Real-index fingerprints (`.git/index` SHA256,
`git ls-files -s` SHA256 and count) are byte-identical before and after. No commit is made;
staging exists only inside the temporary index.

`git diff --cached --check` is **clean for all 9 paths (0 rows)**: all nine batch paths are
LF-only with zero CR bytes (unlike some sibling batches, no pinned input here is CRLF), so
there are no trailing-whitespace notices. `review.json` and `SHA256SUMS` cannot contain their
own staged blob SHA1 or their own SHA256; those two self-referential values, together with the
final hashes of all four manifest outputs, are reported after the staging proof so the
reported bytes equal the staged bytes.

## Test execution

- **Normal mode** — `python -B -m unittest -v validation.test_codebuddy_g6_same_source_activation_readiness`:
  **Ran 24 tests, OK (skipped=1)**. The skip is the external-index-only guard; the
  normal-mode guard `test_normal_mode_makes_no_index_touching_git_call` executed and observed
  zero index-touching git calls.
- **Exact-2 candidate-index mode** — repo-external `GIT_INDEX_FILE` at a `%TEMP%` path absent
  before the run, `git add -- <2 candidates>` (exit 0), `git ls-files -s` listing exactly the
  2 candidates at stage 0 mode `100644` (blobs `46b773b7…` and `6618919e…`, recomputed from
  the worktree bytes), `WKSIM_G6_SSAR_TEST_MODE=external-index`: **Ran 24 tests, OK
  (skipped=1)** — the normal-mode-only guard skipped. The temp index was deleted afterwards.
  Each mode executes 23 tests and skips the other mode's guard, so the two modes together
  exercise all 24 test methods.
- **Exact-9 admission** is verified separately from the suite: the suite's exact-2 assertion
  requires that index to hold exactly two paths, so the 9-path batch admission is proven by
  its own temp-index run (9 A/0 M/0 D, stage 0, blob equality, scoped diff-check) rather than
  by the suite.

Both runs leave the two candidates byte-identical to their pinned identities.

## Exclusions

- The sibling batch quartets under `validation/coordination/` (including the anchored
  `deepseek-g6-same-source-activation-readiness-independent-review-20260914-01`, which is a
  batch input and was only read) were not created, modified or staged by this manifest.
- Pre-existing worktree modifications and concurrent-session untracked artifacts (other
  `validation/coordination/*` batches, `docs/coordination/*` working notes, `%TEMP%` probe
  artifacts) are outside this 9-path batch and were not touched.
- The five P3 findings above are registered, not fixed; no candidate or review byte was
  edited to address them.

## Non-claims (explicit)

- This manifest is an admission record only; it is not acceptance, approval, review authority
  or rerun permission for #59, #84, G6, Full or any other ticket.
- No owner decision is made, solicited on the owner's behalf, pre-filled or implied; all owner
  decisions remain `not_made`.
- No numeric budget, budget approval, acceptance flip, closure claim or physical-accuracy
  claim is introduced or implied; `r1_status` remains `numerical_failed` and 0/120 budgets
  remain approved.
- #83 was not rerun and no rerun is triggered or suggested.
- No same-source contract is created and no READY path is reached; readiness remains BLOCKED.
- No gate is changed; the R1 contract (`numerical_failed`, 32 observables / 120 indices, zero
  budgets, `finite_binary64_value_equal`) is preserved untouched and not appropriated.

## Outputs

`exact-paths.txt`, `review.md` and `review.json` are hashed in `SHA256SUMS`; the sums file
cannot contain its own hash. Hashes of all four outputs are reported after the temp-index
proof so the reported bytes equal the staged bytes.
