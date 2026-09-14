# CodeBuddy manifest — native-wait contract context ingest batch (20260914-01)

Writer: CodeBuddy (manifest writer). Batch: admission manifest for the four candidate
files reviewed by `codebuddy-native-wait-contract-independent-review-20260914-01`.
Offline, read-only over all inputs: no input file was edited; no commit, reset, clean,
restore, checkout, push, ref change, or real-index staging; no network; no native/
MATLAB/ROS/DDS/Unreal/SITL/flight/hardware runs; #83 was not rerun.

## Scope: context-only

This batch is context-only. It binds the two already-tracked native-wait documents as
historical context (KEEP per the independent review, P1=0, P2=0, P3=2) and registers
them with the companion ingest note and offline test suite. It closes no conclusion:
no #84 closure, no G6 closure, no Full closure, no #83 rerun. The fixed gates (four-tick
boundary, group structure, no-catch-up `previous_start+period_ns` anchoring, 100ms
`LATE_LIMIT_NS`, full-window capture, physics step invariants, `diagnostic_only`
identity) are preserved untouched.

## Pins verified before writing

All seven inputs re-hashed in this session; every SHA256 and byte size matched the
dispatch exactly.

| Path | SHA256 | bytes |
| --- | --- | --- |
| docs/coordination/native-wait-integration-contract-20260913.md | 947e759873513ce8d1f11363cb6df9c8c5fc7dc1c868037fbff3b24e90a7b823 | 6132 |
| docs/coordination/claude-native-input-timing.md | f15cd0e28396722c23e005f38b2738ca2dfa889975f5f38ae345b7cbacaf0735 | 8714 |
| docs/coordination/codebuddy-native-wait-contract-ingest-note-20260914.md | 9a34cb0aea15dd1469699d70facd8b3d6d93f9f3a3394b75e9fa986564de21a6 | 7740 |
| validation/test_codebuddy_native_wait_contract_context.py | bebfec48087395f1ec9b5fdbf1082c4c5851a7503b943271f16487d852559906 | 26483 |
| validation/coordination/codebuddy-native-wait-contract-independent-review-20260914-01/review.md | 2443fc8c6d62a6d9e948c8e0ec52dcbe0ecd01bea719900ea370aeb821da49ce | 9428 |
| validation/coordination/codebuddy-native-wait-contract-independent-review-20260914-01/review.json | 82dc0b15055b24b45cef4352bfb4e15845c395bb8a1a76c8928eb44764dfc9d5 | 7735 |
| validation/coordination/codebuddy-native-wait-contract-independent-review-20260914-01/SHA256SUMS | e1a07a1ac120026968419e5946c3966e28fda09e3372ce1539a3c72a1732b984 | 154 |

Git state: candidates 1–2 are tracked and worktree-clean for their paths (scoped
`git status --porcelain` empty); candidates 3–4 and the review triplet are untracked
(`validation/*/` is gitignored, .gitignore:53, so the review outputs are status-invisible
without `git add -f`).

## HEAD relation

Ancestry checks only, no HEAD-equality assertion, per the batch contract:

- `git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD` → exit 0
- `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0

HEAD at manifest time: `438ab764c0cf70f9e017cfbd82aeb04255282e3a` (same commit the
independent review ran at). HEAD may advance with unrelated reviewed commits without
invalidating this registration.

## Historical contract section-5 drift

The independent review and the ingest note §3 both record: contract §5's claims that
"joint_profile.py:328-331 required set does not contain the two pacer files" and that
enablement is negatively bound via the single marker `rate_timing_probe` are
historical. Current bytes place the required set at joint_profile.py:330-334 including
both pacer files (333: joint_rate.py, 334: joint_rate_probe.py) and the marker tuple at
line 274 includes `perf_switch_capture`. The pinned contract bytes are not rewritten;
the drift is registered side by side with current-byte anchors. Related P3-1: contract
§5 cites the sealing loop as "334-339"; current bytes place it at 337-339 — inside
pinned bytes, no edit permitted or needed.

## Independent review findings carried into this manifest

- P1: none. P2: none.
- P3-1: contract-internal line drift (334-339 vs current 337-339), covered by
  byte-binding; no action.
- P3-2: concurrent sibling sessions modified other tracked files and dropped unrelated
  untracked files during the review window; out of batch scope, candidates' scoped
  status unaffected; no action. Per established practice, real-index proofs use
  byte-stable `.git/index` + `ls-files -s` fingerprints, not full-tree status hashes;
  identical full status is not required or claimed here.

## Exclusions

- `docs/coordination/perf-stream-contract-20260913.md`: tracked live pointer, outside
  the batch; its bytes are not bound or superseded by this manifest.
- `docs/coordination/claude-native-wait-next-probe.md`: untracked at review time; not a
  candidate, in no pin table, not bound or endorsed.

## Staging protocol (executed this session)

The 11 paths in `exact-paths.txt` are staged exactly once for proof, under a
repo-external temporary `GIT_INDEX_FILE` seeded from HEAD (`git read-tree HEAD`), with
`git add -f` (gitignore), leaving the real index untouched. Proven: staged delta vs
HEAD is exactly 9 A / 0 M / 0 D (the first two source docs are already tracked
unchanged), all 11 entries at stage 0, 11/11 index blobs byte-equal to working-tree
files, scoped index-vs-worktree diff clean, suite passes under
`WKSIM_NATIVE_WAIT_TEMP_INDEX=1` in exact-11 temp-index mode, and real-index
fingerprints (`.git/index` sha256, `git ls-files -s | sha256sum`) unchanged before/after.
Actual fingerprints and totals are reported in the dispatch thread and recorded in
review.json. No commit is made; staging exists only in the temporary index, which is
deleted after proof.

## Test execution

Normal mode: `python -m unittest validation.test_codebuddy_native_wait_contract_context`
→ Ran 30, OK (skipped=2; the two temp-index-only tests), matching the independent
review's normal-mode totals.

## Non-claims (explicit)

- This manifest is an admission record only; it is not acceptance, approval, or closure
  of #84, G6, or Full.
- #83 was not rerun and no rerun is triggered or suggested.
- The external `/root/wksim-scheduler-probe-35728b1-03` evidence remains non-reproducible
  here and no conclusion depends on it.

## Outputs

`exact-paths.txt`, `review.md`, `review.json` are hashed in `SHA256SUMS` (the sums file
cannot contain its own hash). Hashes of all four outputs are reported in the dispatch
thread after the temp-index proof so the reported bytes equal the staged bytes.
