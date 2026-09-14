# Independent Review: perf-counter historical-context batch (2026-09-14-01)

Reviewer: independent CodeBuddy review agent. No owner approval, acceptance,
closure, or promotion is claimed or implied by this document.

## Scope

Exactly four candidate files (dispatch pins, all independently re-hashed from
working bytes at review time):

| path | SHA256 (expected = observed) | bytes |
| --- | --- | --- |
| `docs/coordination/omp-perf-counter-integration-review-20260913.md` | `9e4a857bb52fc740e25085cb955879f96942f29663a360c802b45e07dab50b2c` | 5601 |
| `docs/coordination/omp-perf-lost-counter-review-20260913.md` | `e35ba529ae1eb18eb04c591f8bec2aea7f10c1a96ee02c1db56cf696dfcfef39` | 4890 |
| `docs/coordination/codebuddy-perf-counter-context-ingest-note-20260914.md` | `0c72d5e33b7efb444e7c9d4cba478991cf691cf0ec51d753b56f950a3780e4ca` | 10600 |
| `validation/test_codebuddy_perf_counter_context.py` | `0c5e1590a945cb41515004c3b06c4ec158f82e16dec48bfab85568a9659c948a` | 32082 |

All four match. The two reviews are tracked (index blob == HEAD blob ==
worktree bytes); the ingest note and the test are untracked, i.e. lifecycle
state **pre-admission**, one of the three states the suite accepts.

## Baseline

- HEAD observed `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` (matches dispatch
  ancestry baseline). Treated as ancestor baseline only; no equality assertion.
- Ancestor-of-HEAD checks, all exit 0: `31e5b65f…`, `f333316e…` (architecture),
  `9e8ba03e…` (review-recorded checkout), `1b3dfdcc…` (main-verdict
  `source_head`).
- `merge-base(9e8ba03e…, 1b3dfdcc…) = 9e8ba03e…` — the P3 ordering claimed by
  the note (§6) holds.

## Receipt arithmetic (independently re-read from raw JSON)

`validation/coordination/perf-lost-counter-20260913-01/receipt.json`
(SHA256 `9bb5a22c…` / 7177 B): kernel `6.6.87.2-microsoft-standard-WSL2`,
`read_format=16`, boot `b3fa43aa…`.

- normal: `kernel_lost=0`, `read_bytes=16`, `ring_head=128` (= 4×32),
  `ring_tail=0`, 0 queued LOST — no false positive on the lossless case.
- overflow_disabled_without_drain: `kernel_lost=385`, `ring_head=4064`,
  `ring_tail=0`, `queued_records=127`, 0 published LOST records.
- **127 + 385 = 512** — arithmetic closes against the expected 512-record
  production.

Other receipts:

- `final-consumer-check.json` (SHA256 `f7caf584…` / 881 B): consumer pin
  `dee9a3b5…`; normal exit 0; loss exit 3 with `kernel_loss_counter_nonzero`
  and detail `26471` in stderr.
- `main-verdict.json` (SHA256 `4fcd7a6a…` / 3174 B): `source_head=1b3dfdcc…`,
  `classification=diagnostic_only`, `architecture_acceptance=false`,
  `full_acceptance=false`; pending loss 16383 records, all SWITCH / 0 LOST,
  counter 26471; normal `kernel_lost_count=0`.
- `consumer-receipt.json` in integration `-01` (SHA256 `dc547651…` / 6290 B)
  and `-02` (SHA256 `6e246ec9…` / 6290 B): each `cases=17`, `failures=0`,
  `inspect_legacy` exit 0, `required_legacy` exit 3.
- integration `receipt.json` (SHA256 `66a29ed9…` / 8396 B): `source_head=9e8ba03e…`,
  recorder pin `aa807f3b…`, header pin `ef1eabf2…`.

Every figure quoted in ingest-note §3 reproduces from the raw receipt bytes.

## Snapshot / source pins (17 files, all match)

Byte-identical groups across tracked evidence dirs, each also verified
against the HEAD tree (`git ls-tree HEAD` blob == `git hash-object` of working
bytes; spot-checked on 8 files incl. both reviews, recorder, consumer,
main-verdict, overflow raw, fixtures `.gitattributes`):

- recorder `wksim_perf_stream.c` `aa807f3b…` (55245 B) —
  `ds-perf-stream-recorder-20260913-01/` and
  `perf-counter-integration-20260913-01/sources/`
- header `wksim_perf_stream.h` `ef1eabf2…` (7318 B) — same two dirs
- consumer `perf_stream_consumer.py` `dee9a3b5…` (29362 B) —
  `ds-perf-stream-consumer-20260913-01/` and integration `sources/`
- probe `lost_counter_probe.c` `93a95a4a…` (4579 B) — lost-counter dir top and
  `sources/`
- superseded `superseded-sentinel-source.c` `49303dab…` (57916 B)
- receipts and raw captures: the six JSON receipts above plus
  `capture/normal.raw` (`c46d039b…`, 128 B) and
  `capture/overflow_disabled_without_drain.raw` (`e096de88…`, 4064 B)

## Historical checkout discrepancy (P3, confirmed)

Reviews record `main @ 9e8ba03e…`; `main-verdict.json` records
`source_head=1b3dfdcc…`; integration `receipt.json` records `9e8ba03e…`.
Both commits exist, both are ancestors of the current HEAD, and `9e8ba03e…`
is an ancestor of `1b3dfdcc…`. The discrepancy does not touch the source
bindings: every source identity in this batch is pinned by tracked snapshot
bytes, independent of any checkout line. Matches ingest-note §6 exactly;
historical, left unrewritten.

## Per-evidence-dir .gitattributes claims

All six evidence dirs (`perf-lost-counter-20260913-01`,
`perf-counter-integration-20260913-01/-02`, `ds-perf-stream-recorder-20260913-01`,
`ds-perf-stream-consumer-20260913-01`, `ds-perf-stream-fixtures-20260913-01`)
each track a `.gitattributes` whose content is exactly `* -text`.
The repo-root `.gitattributes` contains no global text rule.
`git check-attr text`: evidence-dir paths report `text: unset` (from the
dir-level rule; strictly no conversion); a docs/coordination review path
reports `unspecified`. The note's §7 parenthetical says “= unspecified”
without scoping — see finding P3-01. The byte-identity premise itself holds.

## No promotion / no closure

- `main-verdict.json` flags verified in raw JSON: `diagnostic_only`,
  `architecture_acceptance=false`, `full_acceptance=false`. Not upgraded.
- Ingest-note §8 disclaims closure of MIXED/G6/Full conclusions, #84 closure,
  and #83 rerun; forbidden elevation phrases (验收通过 / 已批准 / 已收口 /
  `full_acceptance=true` / #83-rerun claims) are absent from the note.
- `docs/coordination/perf-stream-contract-20260913.md` remains tracked and
  outside the batch (live pointer, referenced only).

## Mutation negatives

All in-suite negatives pass (repository untouched; temp copies / pure
detectors):

- hash detector rejects mutated bytes (`inherit = 0` → `inherit = 1`) and
  mutated size (55245 → 55246);
- receipt arithmetic rejects `kernel_lost` 385→386, `queued_records` 127→128,
  and a normal-case false positive 0→1;
- note boundary detector rejects removal of “不重跑 #83” and injection of
  “验收通过”;
- lifecycle detector rejects mixed presence, nonzero stage, and blob mismatch.

## Test results

Normal run (pre-admission state):

```
python -m unittest validation.test_codebuddy_perf_counter_context -v
Ran 31 tests — OK (skipped=2: TestTemporaryIndex, by design)
```

Private temp-index exact-4 run: temp index created at a never-pre-created
`mktemp -u` path, exactly the four batch paths staged (plain `git add` under
`GIT_INDEX_FILE`; none of the four is gitignored, so no `-f` needed), all at
stage 0 with blobs byte-identical to `git hash-object` of working bytes
(`e67aba71…`, `f92fd811…`, `1d2532ae…`, `08a1875b…`);
`git diff --name-only` (index vs worktree) empty. With
`WKSIM_PERF_COUNTER_TEMP_INDEX=1`:

```
Ran 31 tests — OK (skipped=0)
```

Temp index file deleted after the run.

## Real index integrity

- `.git/index` SHA256 before any work:
  `a7fd6154535cbcde789c99d6ee5f38097d914323453dde5d5ad97b1da09e9253`
- `.git/index` SHA256 after all runs and artifact writes: identical.
- `git ls-files -s | sha256sum` before / after staging:
  `5e08ccabec2775053b28f34e44eedd55db1a8b37ef8b4d895023d651f4b835ef` both.
- No stage, commit, reset, clean, push at any point; no external/native
  toolchain invoked; no network; #83 not rerun.

## Findings

### P3-01 — ingest-note §7 check-attr wording (docs/coordination/codebuddy-perf-counter-context-ingest-note-20260914.md:58)

The parenthetical “git check-attr text = unspecified” is imprecise for the six
evidence-dir paths: with a tracked dir-level `* -text`, check-attr reports
`text: unset` (verified on `receipt.json` and `sources/wksim_perf_stream.c`).
`unspecified` is correct only for paths outside those dirs (e.g. the review
docs). Impact: none — both values mean no newline conversion, so the
byte-identity conclusion stands. Wording-only; the bound historical note is
not rewritten in this batch.

### P3-02 — suite index parser whitespace assumption (validation/test_codebuddy_perf_counter_context.py:311)

`read_index_entries` keys `git ls-files -s` rows on `parts[3]`, so index paths
containing spaces would be mis-keyed. Every path this suite looks up (the two
candidates and the tracked anchors) contains no spaces, so no assertion in
this batch can produce a wrong result. Latent robustness limitation only.

No P1 or P2 findings.

## Verdict

- **P1 = 0, P2 = 0, P3 = 2.**
- **KEEP.** The batch binds the two perf-counter reviews as superseded
  historical context exactly as claimed: byte bindings, receipt arithmetic,
  pins, discrepancy registration, .gitattributes premise, and no-promotion
  boundaries all verify independently; both suite runs pass; the real index is
  byte-identical.

Proven behavior is limited to the offline checks and runs listed above. This
review is not #84 closure, not a #83 rerun, and grants no architecture or full
acceptance.
