# CodeBuddy manifest: perf-counter historical-context ingest manifest (2026-09-14-01)

Writer: CodeBuddy manifest writer agent, 2026-09-14. This batch is a manifest
binding over the independently reviewed perf-counter historical-context
ingest. No owner approval, acceptance, closure, or promotion is claimed or
implied by this document.

## Scope — exact-paths.txt (11 entries, LC_ALL=C sorted, LF-only)

Composition: 4 candidates + 3 review outputs (of
`codebuddy-perf-counter-independent-review-20260914-01`) + 4 manifest outputs
(this directory). Exactly 11 unique paths, verified `LC_ALL=C sort -c` clean,
11/11 unique, no CR bytes.

| # | path | role | sha256 (observed = expected) |
| --- | --- | --- | --- |
| 1 | `docs/coordination/codebuddy-perf-counter-context-ingest-note-20260914.md` | candidate (untracked, pre-admission) | `0c72d5e33b7efb444e7c9d4cba478991cf691cf0ec51d753b56f950a3780e4ca` (10600 B) |
| 2 | `docs/coordination/omp-perf-counter-integration-review-20260913.md` | candidate (tracked, HEAD blob `e67aba71…` == worktree hash-object) | `9e4a857bb52fc740e25085cb955879f96942f29663a360c802b45e07dab50b2c` (5601 B) |
| 3 | `docs/coordination/omp-perf-lost-counter-review-20260913.md` | candidate (tracked, HEAD blob `f92fd811…` == worktree hash-object) | `e35ba529ae1eb18eb04c591f8bec2aea7f10c1a96ee02c1db56cf696dfcfef39` (4890 B) |
| 4 | `validation/test_codebuddy_perf_counter_context.py` | candidate (untracked, pre-admission) | `0c5e1590a945cb41515004c3b06c4ec158f82e16dec48bfab85568a9659c948a` (32082 B) |
| 5 | `validation/coordination/codebuddy-perf-counter-independent-review-20260914-01/SHA256SUMS` | prior review output | `d247b2f57bf2d7628f38e255d29ad97385dd64f4aa4cd89d40690f1bc379bfcb` |
| 6 | `validation/coordination/codebuddy-perf-counter-independent-review-20260914-01/review.json` | prior review output | `ec898acef35997ea5eb6ca5a5716d91e97cea34aaf431eddda8355864958d4a0` |
| 7 | `validation/coordination/codebuddy-perf-counter-independent-review-20260914-01/review.md` | prior review output | `b4c13ef3f49ccb016e6ddc55dcf403261d9e96e18b9bf9fdf59a9a913009b5fc` |
| 8–11 | this directory: `SHA256SUMS`, `exact-paths.txt`, `review.json`, `review.md` | manifest outputs | cross-pinned: SHA256SUMS covers the other three; review.json pins review.md + exact-paths.txt hashes |

All seven pre-existing files re-hashed from working bytes at manifest-writing
time; every hash equals its dispatch pin. Prior SHA256SUMS self-check passes:
recomputed entries `b4c13ef3…` (review.md) and `ec898ace…` (review.json) match
its two recorded lines byte-for-byte.

## Inherited review verdict

`codebuddy-perf-counter-independent-review-20260914-01` (review.md sha256
`b4c13ef3…`, review.json sha256 `ec898ace…`): **KEEP, P1=0 / P2=0 / P3=2** —
P3-01 (ingest-note §7 check-attr wording, note line 58) and P3-02 (suite index
parser whitespace keying, test line 311). Both are wording/robustness items
with zero impact on binding claims. They are carried here as registered; this
manifest does not fix or rewrite them.

## Baseline and ancestry

- HEAD observed `438ab764c0cf70f9e017cfbd82aeb04255282e3a`.
- `git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD`
  → exit 0 (dispatch baseline).
- `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD`
  → exit 0 (architecture anchor).
- Ancestor checks only; no HEAD-equality assertion, so later HEAD movement
  does not invalidate this manifest. The bound ingest note records writing-time
  HEAD `31e5b65f…`; the current HEAD's descent from it is exactly the relation
  the note's §0 requires.

## Receipt arithmetic (re-verified at manifest-writing time)

All six receipt files re-hashed; hashes and sizes match ingest-note §3:

| receipt | sha256 | bytes |
| --- | --- | --- |
| `perf-lost-counter-20260913-01/receipt.json` | `9bb5a22c8327b4de518d5283d466d89fc05fb5036bfb0273dfbd0dda0b255f4f` | 7177 |
| `perf-counter-integration-20260913-01/main-verdict.json` | `4fcd7a6a217fb8e57e598a1b50bebf94e2c1181ab9e8c2f6d0c41bb7f15ebb96` | 3174 |
| `perf-counter-integration-20260913-01/final-consumer-check.json` | `f7caf584ccf013503dcd011540634306345b909fb8d6b8790f586e9282cb2ebc` | 881 |
| `perf-counter-integration-20260913-01/consumer-receipt.json` | `dc5476513cadb23e2fefb82c62d4e672c00160335c64b184dd136f621407518e` | 6290 |
| `perf-counter-integration-20260913-02/consumer-receipt.json` | `6e246ec94eda958de44f348120fc547cc44385aaad635cbb19aa108cedc6e351` | 6290 |
| `perf-counter-integration-20260913-01/receipt.json` | `66a29ed985491b1884c190f53adbc2ca5676f874fbc064758ad4843f46fc9769` | 8396 |

Key closure carried unchanged: overflow case `kernel_lost=385` +
`queued_records=127` = 512 = expected production, 0 LOST; normal case
`kernel_lost=0` (no false positive); counter 26471; consumer receipts 17
cases / 0 failures each; `main-verdict.json` flags `diagnostic_only`,
`architecture_acceptance=false`, `full_acceptance=false` preserved as-is.

## P3 carried items (re-confirmed, not fixed)

- **P3-01 — per-dir .gitattributes wording.** `git check-attr text` re-run:
  evidence-dir paths (`perf-lost-counter-20260913-01/receipt.json`,
  `perf-counter-integration-20260913-01/sources/wksim_perf_stream.c`) report
  `text: unset` (from the tracked dir-level `* -text`); a docs/coordination
  review path reports `unspecified`. The ingest note's §7 parenthetical
  "= unspecified" is imprecise for the evidence-dir paths. Both values mean no
  newline conversion, so the byte-identity premise of note §§1–3 holds.
  Wording-only; the bound historical note is not rewritten.
- **P3-02 — suite index parser whitespace assumption.**
  `validation/test_codebuddy_perf_counter_context.py` `read_index_entries`
  keys `git ls-files -s` rows on `parts[3]`; paths containing spaces would be
  mis-keyed. Every path the suite looks up contains no spaces; latent
  robustness limitation only.

## Historical checkout discrepancy (registered, re-verified)

Reviews record `main @ 9e8ba03e43627918d5fab28aa59765a02fb068d1`;
`main-verdict.json` records `source_head=1b3dfdcc106be18bcff8ff0e69269f6c7eab755d`;
integration `receipt.json` records `9e8ba03e…`. Re-verified at manifest time:
both commits are ancestors of current HEAD (exit 0) and
`merge-base(9e8ba03e…, 1b3dfdcc…) = 9e8ba03e…`. Historical, does not touch
source bindings (all identity pinned by tracked snapshot bytes), left
unrewritten.

## Boundaries — strict context-only

- This manifest binds historical context only; it promotes nothing to current
  execution, acceptance, approval, or closure.
- No G6-Full conclusion is touched or closed; the `diagnostic_only` /
  `architecture_acceptance=false` / `full_acceptance=false` flags remain in
  force and unupgraded.
- Not #84 closure; #83 is not rerun and no rerun is triggered, suggested, or
  substituted.
- Tracked live contract `docs/coordination/perf-stream-contract-20260913.md`
  stays outside the batch; referenced only, not bound, not superseded.
- Forbidden elevation phrases (验收通过 / 已批准 / 已收口 /
  `full_acceptance=true` / #83-rerun claims) are absent from all four
  manifest outputs.

## Verification results

- **Normal suite:** `python -m unittest validation.test_codebuddy_perf_counter_context -v`
  → `Ran 31 tests — OK (skipped=2)` (TestTemporaryIndex, by design). 31/31.
- **Round-A temp-index stage (recorded, 8 then-existing paths):** repo-external
  temp index (`mktemp -u`, `C:\Users\PC\AppData\Local\Temp`, never
  pre-created, not under the repo), seeded `git read-tree HEAD`, then
  `git add -f` of the 4 candidates + 3 prior review outputs +
  `exact-paths.txt` (all staged with `-f` because `validation/coordination/`
  is gitignored via `.gitignore` line 53 `/validation/*/`; the two tracked
  candidates re-stage byte-identically). `git diff-index --cached
  --name-status HEAD` → exactly **6 A / 0 M / 0 D**. Temp index file removed.
- **Closing exact-11 stage (post-finalization):** after all four manifest
  outputs were final, the same procedure is run with all 11 exact paths
  staged (`git add -f`), and must show: staged set == the 11 paths of
  `exact-paths.txt`; `diff-index --cached HEAD` → exactly **9 A / 0 M / 0 D**
  (9 new-in-HEAD paths; the two tracked candidate reviews add no delta); all
  11 entries at stage 0 with blobs equal to `git hash-object` of working
  bytes; `git diff --name-only` scoped to the 11 paths empty; temp index
  removed; real `.git/index` and `git ls-files -s` hashes byte-identical to
  before. Observed results are reported in the dispatch thread; any
  deviation is a failure of this manifest.
- **Real index integrity:** `.git/index` sha256 before any work
  `327b22366c0ba7cb1e3fbddc8cd41023541b92f3cea745af754aba1b41862976`;
  `git ls-files -s | sha256sum` before
  `5de63e159c44d37a72acfecee8c178ab154b80b00d36cb9130588e9042f5a8ef`.
  No stage/commit/reset/clean/push at any point; the real index is only ever
  read, never written.

## Verdict

- **Manifest complete.** 11 exact paths verified against dispatch pins;
  inherited verdict KEEP (P1=0/P2=0/P3=2) recorded with both P3 items carried,
  not fixed; receipt arithmetic, discrepancy registration, and
  .gitattributes premise re-confirmed from raw bytes; suite 31/31; round-A
  staging 6 A / 0 M / 0 D clean.
- No new findings. Proven behavior is limited to the offline checks and runs
  listed above. This manifest is not #84 closure, not a #83 rerun, grants no
  architecture or full acceptance, and closes no G6-Full conclusion.
