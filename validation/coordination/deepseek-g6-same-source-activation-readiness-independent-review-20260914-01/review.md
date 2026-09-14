# Independent review: #59 G6 same-source activation-readiness pair (2026-09-14)

- Review id: `deepseek-g6-same-source-activation-readiness-independent-review-20260914-01`
- Reviewer: independent agent (`deepseek-v4-flash`, DSH harness), no authoring role in either candidate
- Date: 2026-09-14
- Verdict: **KEEP** — 0 × P1, 0 × P2, 5 × P3 (documentation precision and future hardening only; nothing blocks acceptance of this readiness pair)
- Checkout: `C:\Users\PC\Documents\odid编译\wksim`, branch `main`, HEAD `ee6eb88819cefe255f22e788c39a77c0bbab490e` (informational only; the candidates deliberately pin no exact HEAD value)
- Candidates were read only; not one byte was edited, staged in the real index, committed or pushed.

## 1. Subject identity (immutable, re-verified)

| file | SHA256 | size |
| --- | --- | --- |
| `docs/plan/59-g6-same-source-activation-readiness-20260914.md` | `9958b00feafb9bc6dc0098da123ab6f2a668e06bb03da551eaa56ac46dacb106` | 15498 |
| `validation/test_codebuddy_g6_same_source_activation_readiness.py` | `3cd1241a0f0e74bf96d0383bddc8a5ee1564fc7840cd9bd1a8b94696117e0fbc` | 31570 |

Both hashes and sizes match the fixed review identities exactly and were re-verified unchanged after
every run; the document is LF-normalized and newline-terminated. Both candidates are untracked worktree
files, which is consistent with the pair's own statement that it is an offline slice. AGENTS.md was read;
the checkout satisfies the architecture-continuity ancestry gates (§2.3).

## 2. Exact commands and observed results

### 2.1 24 tests, normal mode

```powershell
python -B -m unittest validation.test_codebuddy_g6_same_source_activation_readiness -v
```

Result: `Ran 24 tests in 0.648s` — `OK (skipped=1)`, exit 0. The skip is the external-index-only guard.
The normal-mode guard `test_normal_mode_makes_no_index_touching_git_call` executed and observed zero
index-touching git calls, so the worktree run never read or wrote the shared real index.

### 2.2 24 tests, repo-external exact-2 temp index

```powershell
$TMPIDX = Join-Path $env:TEMP 'wksim-tmpidx-g6ssar'
$env:GIT_INDEX_FILE = $TMPIDX
git add -- docs/plan/59-g6-same-source-activation-readiness-20260914.md `
           validation/test_codebuddy_g6_same_source_activation_readiness.py
git ls-files -s
$env:WKSIM_G6_SSAR_TEST_MODE = 'external-index'
python -B -m unittest validation.test_codebuddy_g6_same_source_activation_readiness -v
Remove-Item $TMPIDX
```

Result: the index lived at `C:\Users\PC\AppData\Local\Temp\wksim-tmpidx-g6ssar` (outside the repository,
confirmed by prefix check), `git add` exited 0 and `git ls-files -s` listed **exactly two** stage-0 entries,
mode `100644`:

```text
100644 46b773b79992459f00512f8578f231a9e4d134f9 0	docs/plan/59-g6-same-source-activation-readiness-20260914.md
100644 6618919eb191dbc3b4f86070d310b52027731bc4 0	validation/test_codebuddy_g6_same_source_activation_readiness.py
```

Both blob SHA-1s were independently recomputed from the worktree bytes (`sha1("blob <n>\0" + bytes)`) and
match. The run gave `Ran 24 tests in 0.889s` — `OK (skipped=1)` (the normal-mode-only guard), exit 0. The
temp index was deleted afterwards. Each mode executes 23 tests and skips the other mode's guard, so the two
modes together exercise all 24 test methods.

### 2.3 Real-index integrity, ancestry gates

```powershell
Remove-Item Env:\GIT_INDEX_FILE
git ls-files | Where-Object { $_ -like '*59-g6-same-source*' -or $_ -like '*test_codebuddy_g6_same_source*' }
git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD   # exit 0
git merge-base --is-ancestor 6eafdf9c0b734db07a9fe790c86b409d3468c10b HEAD   # exit 0
git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD   # exit 0
git merge-base --is-ancestor 0000000000000000000000000000000000000000 HEAD   # exit 128
```

Result: `staged_candidate_count=0` — the shared `.git/index` stages neither candidate and both remain
`??`. All three required ancestors exit 0; an invalid object name exits 128, so the gate discriminates.
Neither candidate pins the current HEAD (the suite asserts this and it re-verified here).

### 2.4 Six pinned tracked sources, independently re-derived

`git ls-tree -r HEAD -- <six paths>` lists all six; for each, `git cat-file blob HEAD:<path>` hashed and
sized gives exactly the documented values, and equals the worktree bytes (no drift):

| path | bytes | sha256 | HEAD blob sha1 |
| --- | --- | --- | --- |
| `tools/run_e0_same_source_conformance.py` | 64513 | `8398100b7fb6b839e279afd6e8f8708e57e415450dbb6621acdc9ea9ecc46517` | `e275762475eebbc7e84c0e6822f0c3f596066a93` |
| `docs/plan/59-e0-same-source-command.md` | 10221 | `345caff0fd354717a64ed1dfac2c3ad33f87c72713cf3362483c395fb66b197e` | `b417a1291a5890045f8595a112724f879cda2297` |
| `docs/plan/10-g6-remediation-contract.md` | 9935 | `48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0` | `256455a46220014c970b556b0bca066391c5e9e1` |
| `validation/e0-budget-approval-provenance-20260914.json` | 285820 | `2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d` | `4f2fdacfd556b12dada630dd5af7983062558676` |
| `validation/e0-frame-datum-binding-20260914.json` | 105018 | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | `64acd9c8e51e9418e05866f15631e1b8e1e2be80` |
| `Simulator/wksim_core/numerical-conformance-v1.json` | 29846 | `23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0` | `e5d5f33911ff80fc861952612cceac9bf647702d` |

No seventh source is pinned. The tracked `docs/2026-09-09-reference-sampling-contract.md` is neither cited
by nor a dependency of the pair (§3.8).

### 2.5 Independent probes (not the candidate's suite)

1. **Preflight order by line number.** Extracting the first textual occurrence of each documented call site
   inside `run()` gives `validate_contract:1083`, `validate_execution:1090`, preflight probe `:1093`,
   `_prepare_execution:1095`, normal launch `:1166`, `_validate_reference_outputs:1172`, prelaunch probe
   `:1174`, native launch `:1180`, `_validate_native_inputs:1189`, `parse_native_record:1191`, `align:1193`,
   `compare_aligned:1194`, `_execution_result:1195` — strictly increasing and identical to documented
   steps 1–13. No launch or probe call exists earlier in `run()`.
2. **Blocker counts.** Re-derived from the pinned ledgers: ledger counts exact (`slots_total=120`,
   `slots_dynamic_candidate=56`, `slots_policy=64`, `slots_with_numeric_budget=0`,
   `slots_with_approval_identity=0`, `slots_approved=0`, `slots_blocked=56`,
   `slots_pending_owner_policy=64`, `external_owner_records=0`, `external_derivation_records=0`, dynamic
   frame/datum commitments 0); frame counts exact (`frame_bound=25`, `frame_unresolved=31`,
   `datum_bound=10`, `datum_unresolved=46`, `owner_decision_count=24`, `slot_count=56`) with all 24
   `owner_decisions` at `status=not_made`; policy split `5 + 59 = 64`; `r1_status=numerical_failed` in both.
3. **R1 non-appropriation.** The R1 contract carries its frozen id, 32 observables covering exactly 120
   indices, distinct `absolute_budget={0}` and `relative_budget={0}`, a single `rule=finite_binary64_value_equal`,
   and sha256 starting `23d72e26`; the entry refuses it by resolved-path equality, and the suite's real run
   returned `blocked` with a `frozen R1 contract` reason and no evidence directory.
4. **Sampling-document exclusion.** The suite's sampling-path regex finds nothing in the document, no
   `*same-source*`/`*same_source*` contract JSON exists, and every path-bearing statement resolves to the six
   tracked pins plus the two candidates.
5. **Identity cross-check probe (finding P3-02).** A throwaway synthetic contract built outside the repository
   was passed directly to `entry.validate_execution`: with `identity.slx/init.path` equal to the exact
   resolved staged path string plus a deliberately wrong identity sha256 (`a`×64) the call **passed**; with a
   plain relative identity path plus the same wrong sha256 it raised `Reject: normal slx does not match
   contract identity`.
6. **applied-input probe (finding P3-01).** `entry._expected_input_f64(parsed rows)` is 132264 bytes
   (501 × 33 × 8) versus 36822 raw CSV bytes; they are unequal, and `tools/export_model_reference.m` line 80
   writes the artifact as `fwrite(a','double')`, so the document's literal byte-equality wording is
   unachievable by construction.

Both probe artifacts were created under `%TEMP%` and removed; nothing was written inside the repository
except the three files of this review directory.

## 3. Required-property checklist

| # | property | result | evidence |
| --- | --- | --- | --- |
| 1 | immutable pair identity (sha256 + size) | PASS | §1; re-verified unchanged after all runs |
| 2 | exactly six tracked source pins, HEAD-blob bound | PASS | §2.4; all six match documented hash/size and worktree bytes |
| 3 | documented preflight order == implemented order | PASS | §2.5.1; 13/13 steps in increasing line order |
| 4 | documented blocker counts re-derived | PASS | §2.5.2; all ledger/frame counts incl. 24 not_made owner decisions |
| 5 | R1 not appropriable (path + id + zero budgets + equal rule) | PASS | §2.5.3 |
| 6 | future authorized command shape | PASS | CLI `contract/--output/--evidence-dir`; normal `[matlab, -wait, -sd <stage>, -batch export_model_reference]`; native `[wsl.exe, -d <distro>, --exec, timeout, --signal=TERM, --kill-after=5s, <timeout>s, <wsl_executable>, --record, <wsl-input.csv>]`; fresh evidence dir required; private `TEMP/TMP/MATLAB_PREFDIR` |
| 7 | expected output/evidence fields | PASS | all 14 named evidence artifacts plus `normal/` internals and private `temp/pref/cache/codegen`; all 20 execution-path, 8 blocked-path and 13 per-scalar result fields exist in code |
| 8 | no untracked reference-sampling dependency | PASS | §2.5.4 |
| 9 | six forbidden budget-derivation sources prohibited | PASS | observed differences, ULP/epsilon, noise, RK4 O(h⁴)/grid convergence, SITL/flight gates, control-seam rows each appear only under an explicit prohibition; mutation tests confirm each prohibition is load-bearing; no budget value is invented |
| 10 | non-closure preserved | PASS | R1 `numerical_failed` retained; both ledgers `issues_closed/budget_approved/g6_acceptance/physical_accuracy=false`; #59/#84/G6 open, Full not-closed, 0/120 approved |
| 11 | fail-closed, no launch, no evidence before launch | PASS | missing / R1 / partial-budget contracts all `blocked`, all launch flags false, no evidence directory; `_result()` hardcodes the false flags |
| 12 | 24 tests normal | PASS | §2.1 |
| 13 | 24 tests, repo-external exact-2 temp index | PASS | §2.2 |
| 14 | no simulator, #83, real staging/commit/push, sibling edits | PASS | §5 |

## 4. Findings (all P3)

- **P3-01 — `applied-input.f64` wording is not what is implemented.** §1 step 6 says the artifact is
  byte-identical with the input CSV. The code compares against a fresh row-major little-endian binary64
  re-encoding of the parsed CSV rows (entry lines 887–892, 1007–1009), never against CSV text bytes; the
  native-side statement in step 9 *is* literal byte equality (entry line 1030). No evidence claim is
  weakened — the enforced consistency is at least as strong — but a reader could look for an impossible
  text-vs-binary comparison. Recommend rewording in the next revision.
- **P3-02 — SLX/init identity SHA cross-check is an OR that can skip the SHA comparison.** Entry lines
  395–402 accept `identity.path == resolved staged path` *or* `staged sha == identity sha`. With an
  absolute identity path string (the R1 identity convention), a wrong `identity.slx/init.sha256` passes
  `validate_execution` (probe in §2.5.5). Latent only: no same-source contract exists, the staged file's own
  declared sha256 is still verified against its bytes, identity shas do not propagate into evidence, and the
  BLOCKED readiness conclusion is unaffected. Recommend a conjunction when the entry is next revised.
- **P3-03 — some §2 claims are string-checked rather than re-derived.** The R1 budget/rule summary, the
  5+59=64 policy split and "all 24 owner decisions not_made" are verified here as independently true, but the
  suite only checks literals/counts. Future hardening: re-derive them.
- **P3-04 — the normal-mode index guard is execution-order dependent (informational).** `TestIndexModes`
  sorts before `TestPreflightOrder`/`TestSourcePins`/`TestWordingMutations`; an index-touching call added to
  a later class would escape the guard. No such call exists today.
- **P3-05 — the §5 reproducibility sentence is exact for blocked paths but reads as universal
  (informational).** `_prepare_execution` uses `uuid4` for staging/epoch and refuses an existing evidence
  directory, so a repeat call with the same now-populated `evidence_dir` returns `blocked`. Readiness is
  currently and unconditionally blocked, so this is documentation precision only.

## 5. Non-actions

No candidate edited; no real-index staging, commit or push; no `#83` rerun; no GitHub mutation; no network;
no MATLAB/native/ROS/DDS/SITL/Unreal/build/flight execution; no sibling project touched. Only these three
files were written:

- `validation/coordination/deepseek-g6-same-source-activation-readiness-independent-review-20260914-01/review.md`
- `validation/coordination/deepseek-g6-same-source-activation-readiness-independent-review-20260914-01/review.json`
- `validation/coordination/deepseek-g6-same-source-activation-readiness-independent-review-20260914-01/SHA256SUMS`

## 6. Residual uncertainty

- The suite proves the properties it encodes; it cannot prove that the documented preflight order is the
  only reachable order for every future execution identity — the launcher, WSL path resolver and identity
  probe are injectable and no contract can currently reach the READY path.
- The §8 statement that G0–G6 are all not-closed is consistent with the pinned ledgers
  (`issues_closed=false`, non-claims text) but was not re-derived from a separate closure ledger; only R1
  `numerical_failed` and the openness of #59/#84/G6/Full were spot-checked.
- The six pins' own claims were hash-bound and spot-checked on their key fields, not exhaustively re-derived
  from the MATLAB model or the native build.
