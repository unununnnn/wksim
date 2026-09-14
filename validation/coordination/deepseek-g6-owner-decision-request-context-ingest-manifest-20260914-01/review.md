# Manifest — G6 owner-decision request context ingest batch (20260914-01)

Writer: independent manifest writer (`deepseek-v4-flash`, DSH harness), owner of this
manifest batch and of no other file in it. Batch: admission manifest for the three
immutable candidates reviewed by
`validation/coordination/deepseek-g6-owner-decision-request-independent-review-20260914-01`.

Offline, read-only over all inputs: no input byte was edited; no real-index staging, no
commit, no push, no reset, clean, restore, checkout or ref change; no #83 run; no
MATLAB/native/ROS/DDS/SITL/FC/UE/model/build or flight execution; no network or GitHub
query/mutation; no sibling project or sibling batch directory touched.

## Scope: context-only

This batch is context-only and is **not** an acceptance action. It binds the three
`#59` G6 owner-decision-request candidates plus their anchored independent review, and
registers them together with this manifest quartet. It closes nothing: no #59 closure,
no #84 closure, no G6 closure, no Full closure, no G6 acceptance, no budget approval,
no physical-accuracy claim, and no owner decision. `r1_status` remains
`numerical_failed`; B1/B3/B4, OD-03..OD-24 (except OD-20), OD-01/OD-02, and
#84/G6/Full all remain open.

## Exact paths (10, byte-ordinal sorted)

Composition: **3 candidates + 3 anchored independent-review outputs + 4 manifest
outputs = 10 unique paths**. The four manifest outputs include this file's own directory
(`SHA256SUMS`, `exact-paths.txt`, `review.json`, `review.md`), so all four are staged
and blob-equality-proven, not merely declared.

`exact-paths.txt` is written with LF endings only (10 LF bytes, 0 CR bytes, trailing
LF), 10 unique entries, no duplicates, and its order equals the byte-ordinal
(`LC_ALL=C`-equivalent) sort of its own lines. Paths beginning `validation/coordination/`
are gitignored (`.gitignore:53`, `/validation/*/`), so staging requires `git add -f`;
the two other candidates are untracked but not gitignored.

## Pins verified before writing

All six immutable inputs were re-hashed in this session; every SHA256 and byte size
matched the dispatch pin exactly, before and after every test and proof run.

| Path | SHA256 | bytes |
| --- | --- | --- |
| docs/plan/59-g6-owner-decision-request-20260914.md | 45dcec197c4e62376a2640de828ae8e14ad062d1ef6b232a0ca4b27a15ecedd7 | 5243 |
| validation/e0-g6-owner-decision-request-20260914.json | 42ad4572fbd8c21a9648593a37cae67dac4e13c173f88e0f33b31129a6c83274 | 15723 |
| validation/test_e0_g6_owner_decision_request.py | a10abcfb37b1c9bc3ff123849ea4534f5f1eb020afbd803a8bd64f1fd109f0ba | 47358 |
| .../deepseek-g6-owner-decision-request-independent-review-20260914-01/review.md | c77474d14c6284acf3d195be87c68116bf506cd2d087cbc672c68b40032d7cd6 | 12171 |
| .../deepseek-g6-owner-decision-request-independent-review-20260914-01/review.json | ddc265498515963a4a7df9a38d78d106a2337220b201b6a1cadd5ee93994865b | 14068 |
| .../deepseek-g6-owner-decision-request-independent-review-20260914-01/SHA256SUMS | a2897c9ea52304cfa312eaf6166f3a200e54544ca28c57ae07a29d6ed70159bb | 831 |

The anchored review's own `SHA256SUMS` was independently re-checked from the repository
root: all five of its entry lines match the files they name (the three candidates plus
its own `review.md`/`review.json`), and its declared self-check digest over the five
entry lines recomputes to
`8a70cc49c484fbba33ffd6d47a9233f22286b2e1fc5e02e7fdd6fd5a8fcf9633` — verified.

## HEAD relation and ancestry

Ancestry only; no HEAD-equality assertion is made or implied. HEAD is recorded as an
observation, not a gate:

- `git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD` → exit 0
- `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0
- `git merge-base --is-ancestor 0000000000000000000000000000000000000000 HEAD` → exit 128
  (the gate discriminates; it is not a vacuous always-zero check)

HEAD observed at manifest time: `ee6eb88819cefe255f22e788c39a77c0bbab490e`. HEAD may
advance with unrelated reviewed commits without invalidating this registration.

## Intervening commits: zero overlap

- Since `31e5b65f`: 6 commits (`ab165c3f`, `438ab764`, `acf32286`, `e832fd2a`,
  `615c2f8c`, `ee6eb888`), 68 distinct touched paths.
- Since `f333316e`: 77 commits, 1123 distinct touched paths.

Method: `git log --name-only --format='' <anchor>..HEAD`, de-duplicated with a
case-sensitive sort, intersected with the 10 batch paths. Intersection is **0** for both
anchors — no commit in either ancestry range added, modified or deleted any batch path.
Consistently, `git ls-tree -r HEAD -- <10 paths>` returns no entry (none is in the HEAD
tree) and `git ls-files -s -- <10 paths>` returns no entry (none is staged in the real
index). All 10 batch paths are untracked working-tree files.

## Independent review findings carried (unweakened)

Verdict carried from the anchored review: **KEEP**, severity counts **P1 = 0, P2 = 0,
P3 = 5**, `rework_required = false`. The verdict is carried as a recorded result; this
manifest did not re-run the review, re-adjudicate it, or promote any finding.

- **P1:** none. **P2:** none. **Blockers:** none.
- **P3-01** — the numeric-budget gate is key-scoped, not value-scoped: a budget written
  as a bare number under a neutral key, or as a numeric element of an untyped list,
  would not be flagged. Candidate is clean (exactly 10 numeric scalars: `issue`,
  `parent_issue`, `decision_group_count`, `max_pins`, six `size_bytes`; none is a
  budget). Latent verifier gap only.
- **P3-02** — `title`, `question`, `evidence_question_ref` and the elements of
  `not_covered_by_this_group` are not type-validated in `check_group`; all present
  values are well-formed strings. Mutation-space coverage gap only.
- **P3-03** — `check_groups` assumes every group element is a dict: the id comparison
  filters with `isinstance(group, dict)` but the later
  `group.get("owner_decision_ids")` accumulation does not, so a non-dict element raises
  `AttributeError` instead of recording a violation. Still fail-closed (the run errors),
  but an unclean rejection path not covered by the 18 mutation tests.
- **P3-04** — `..` and non-repo absolute prefixes escape the coordination-path check:
  `normalize_path` handles case, backslashes, duplicate/leading slashes, `./` and
  whitespace, but does not resolve `..` or absolute prefixes, so
  `x/../validation/coordination/y.json` or `C:/repo/validation/coordination/y.json`
  would not be rejected. Pins remain closed by exact frozen-path equality; the scan is
  defense-in-depth for future path-bearing keys.
- **P3-05** — the case-insensitivity claim is stricter than the exercised vector set
  (upper-case, backslash, double-slash, leading-`./`, whitespace). Informational only;
  it is not a proof over all Unicode case folding.

All five findings are P3 hardening observations on the verifier, not defects in the
reviewed artifact. None is applied, reworded, downgraded or adjudicated away by this
manifest, and none affects decision readiness. This manifest raises **no finding of its
own**; its single batch-level observation — the CRLF encoding of the pinned
`validation/test_e0_g6_owner_decision_request.py` — is recorded in the staging section
and is not a defect, not a review finding, and not a rework trigger. **Nonclosure and residual uncertainty
are carried unchanged:** the verifier proves only the structural and byte-identity
properties it encodes (it does not prove the three questions are the semantically right
questions for the owner); the pinned sources' own claims were spot-checked, not
exhaustively re-derived from the MATLAB model; and case-insensitive rejection is
verified over realistic path variants only.

## Staging protocol and admission proof

The 10 paths of `exact-paths.txt` are staged exactly once for proof, under a
repository-external temporary `GIT_INDEX_FILE` seeded with `git read-tree HEAD`, using
`git add -f` (gitignore). The real `.git/index` is never written.

Proven in the post-write run over all 10 paths: staged delta versus HEAD is exactly
**10 A / 0 M / 0 D** (the temp index held 10843 entries = 10833 HEAD entries + the 10
additions); every entry is at **stage 0** with a regular file mode; index blob bytes are
**byte-equal to the working-tree files** for all 10 paths; and the scoped
index-vs-worktree diff is **empty (0 rows)**, which is the byte-fidelity proof. The
exact-3 candidate index run and the exact-10 admission index are separate
repository-external objects, and the temporary index is deleted after proof. Real-index
fingerprints (`.git/index` SHA256, `git ls-files -s` SHA256 and count) are byte-identical
before and after. No commit is made; staging exists only inside the temporary index.

`git diff --cached --check` is **clean for 9 of the 10 paths** (0 rows). For
`validation/test_e0_g6_owner_decision_request.py` it emits **1082 "trailing whitespace"
notices**, because that pinned immutable candidate carries CRLF line endings (1082 CR
bytes and 1082 LF bytes; every other batch path is LF-only with 0 CR bytes, including
all four manifest outputs). This is a property of the pinned input bytes — whose SHA256
matches the dispatched identity exactly — and not a staging defect; this manifest does
not edit, re-encode or normalize it, and the byte-equality proof above is unaffected.

`review.json` and `SHA256SUMS` cannot contain their own staged blob SHA1 or their own
SHA256; those two self-referential values, together with the final hashes of all four
manifest outputs, are reported after the staging proof so the reported bytes equal the
staged bytes.

## Test execution

- **Normal mode** — `python -B -m unittest -v validation.test_e0_g6_owner_decision_request`:
  **Ran 29 tests, OK (skipped=2)**. The two skips are the `TemporaryIndexTests` that are
  meaningful only in the repo-external temporary-index run.
- **Exact-3 candidate-index mode** — repo-external `GIT_INDEX_FILE` at a
  `%TEMP%` path absent before the run, `git add --force -- <3 candidates>` (exit 0),
  `git ls-files` listing exactly the 3 candidates, `WKSIM_59_ODR_TEMP_INDEX=1`:
  **Ran 29 tests, OK (no skips)** — both `TemporaryIndexTests` executed, including the
  assertions that the external index holds exactly the three candidates at stage 0 with
  blob bytes identical to the working tree and that the real index still stages none of
  them. The temp index was deleted afterwards.
- **Exact-10 admission** is verified separately from the suite: the suite's exact-3
  assertion (`set(git ls-files) == set(CANDIDATE_PATHS)`) requires that index to hold
  exactly three paths, so the 10-path batch admission is proven by its own temp-index
  run (10 A/0 M/0 D, stage 0, blob equality, scoped diff-check) rather than by the
  suite.

Both runs leave the three candidates byte-identical to their pinned identities.

## Exclusions

- The sibling batch quartets under `validation/coordination/` (including the anchored
  `deepseek-g6-owner-decision-request-independent-review-20260914-01`, which is a batch
  input and was only read) were not created, modified or staged by this manifest.
- Pre-existing worktree modifications (`docs/Prometheus.gitmodules.reference`,
  `validation/coordination/short-cycle-dispatches.json`) and concurrent-session
  untracked artifacts (e.g. `%TEMP%audit26-report.json`, `docs/coordination/*` working
  notes, other `validation/coordination/*` batches) are outside this 10-path batch and
  were not touched.
- The five P3 findings above are registered, not fixed; no candidate or review byte was
  edited to address them.

## Non-claims (explicit)

- This manifest is an admission record only; it is not acceptance, approval, review
  authority or rerun permission for #59, #84, G6, Full or any other ticket.
- No owner decision is made, solicited on the owner's behalf, pre-filled or implied; the
  three decision groups remain `not_made` with no option chosen.
- No numeric budget, approval flag, closure claim or acceptance flip is introduced.
- #83 was not rerun and no rerun is triggered or suggested.
- No gate is changed: the fixed gates (1 ms physical tick, four-tick group boundary,
  no-catch-up `previous_start + period_ns`, 100 ms `LATE_LIMIT_NS`, full-window capture,
  physics invariants, `diagnostic_only` identity) are preserved untouched.

## Outputs

`exact-paths.txt`, `review.md` and `review.json` are hashed in `SHA256SUMS`; the sums
file cannot contain its own hash. Hashes of all four outputs are reported after the
temp-index proof so the reported bytes equal the staged bytes.
