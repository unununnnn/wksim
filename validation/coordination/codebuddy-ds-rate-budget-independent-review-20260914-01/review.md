# Independent review — codebuddy-ds-rate-budget-independent-review-20260914-01

- Reviewer: independent CodeBuddy evidence reviewer (did not author any scoped file)
- Date: 2026-09-14
- Reviewed HEAD: `9c581ad5b2e316904c9ef53e8543c5a6f413d6f9` ("Bind model closure context offline")
- Scope (3 candidate files, all untracked, none edited by this review):

| Path | SHA256 | Size |
| --- | --- | --- |
| `docs/coordination/ds-rate-budget-20260912.json` | `b6db16e282e670177eba0b9ce43d5b637ff0845279d8101a430a808d39681b37` | 32100 |
| `docs/coordination/ds-rate-budget-ingest-note-20260914.md` | `13e18676833ab21783953cb63f45135f3eb24e440e8401d99d6a254b4678dd1b` | 8751 |
| `validation/test_ds_rate_budget_context.py` | `4d9286f2606ee89373da885e9af860a0faefdd52d10e41611f049aed798969b3` | 18512 |

## Verified facts (all recomputed at the reviewed HEAD)

1. **Exact hashes/sizes.** The original JSON and ingest note hashes/sizes recomputed here match the note's section 1 binding and the test's pins exactly.
2. **Strict JSON.** `ds-rate-budget-20260912.json` strict-parses (duplicate keys, NaN/Infinity, and 1e400 overflow all rejected); schema `wksim.ds-rate-budget.v1`.
3. **Historical/current tool hashes.** At `f21fc3af` the analyzer blob is `c3ba9de8…` and the tail-test blob is `8b468bb7…` — exactly the JSON's pins. At `75353c06` and at HEAD both blobs are `1c43ac9c…` / `cf665b41…` (≠ pins), and the current worktree files match those superseding blobs — the pins are confirmed historical, superseded as the note section 2.2 records.
4. **Commit ancestry.** `7126d4d7`, `f333316e`, `f21fc3af`, and `75353c06` are all ancestors of HEAD (exit 0 each).
5. **Tracked supersession anchors.** `ds-7bdfxkb-diagnostic-analysis.json` (schema `wksim.ds-rate-diagnostic-analysis.v1`, run `joint-public-flight-7bdfxkb_`), `33-rate-measured-candidate-20260912.md` (contains `1w6dru32`, `CLOSED`, `#83 不重跑`, `7bdfxkb_`, `永不得充当 #83 通过证据`), and `33-rate-next-diagnostic-20260912.md` are all tracked at HEAD. These are cited as recorded history only.
6. **checks.json non-attestation semantics.** The tracked checks.json (schema `wksim.ds-g0-g5-frontier-checks.v1`) mentions the bound file only as the raw untracked-status listing `?? docs/coordination/ds-rate-budget-20260912.json` and contains no SHA256 of it — a status listing, not a byte attestation, exactly as note section 2.4 states.
7. **Note line-drift claims recomputed.** At `7126d4d7` the probe rejection sits at `joint_profile.py:219-220`; at HEAD it is at `274-276` with the marker tuple widened to include `perf_switch_capture` (commit `33c2b06e` verified); the P+V alternate-probe gate is at `run_joint_flight.py:1092-1099` at `7126d4d7`. The diagnostic-field boundary holds under the current, wider gate.
8. **Four identities.** Control candidates `0DQQz9` / `rWolCy` / `ZlTVa4` / `c2IXOr…`, their four control manifests, and the four epochs are all distinct; the identity-freeze "must never be mixed" rule is present.
9. **Timing / no-cross-run-subtraction boundaries.** The wall-clock rule is present; the four monotonic origins are distinct, and the recorded disorder (tpwl1k4p 271507270801 > 8fmacpgy 214814589137 with tpwl1k4p calendar-earlier) proves the runs do not share one boot origin. All four cumulative-increment identities close exactly (zzmg3k47 118903+99881013+92179=100092095; tpwl1k4p 116719+99877507+44659=100038885; nqyqcagl 115025+97921130+6224284=104260439; 8fmacpgy 114791+70719737+63993754=134828282). No root cause and no ns-level attribution beyond this exact arithmetic is asserted by the candidates or by this review; "overlap is not causation" and the no-exclusive-root-cause rule are present.
10. **Meaningful negatives.** The test's strict parser genuinely rejects duplicate keys, NaN/Infinity, and overflow, and five in-memory mutants (hash drift, sum-string drift, identity collapse, origin collapse, trace-identity detach) are each rejected. No repository file is modified.
11. **Descendant/staging safety.** The test resolves the repo root from `__file__`, reads "current" content from symbolic `HEAD` only, asserts ancestry rather than exact HEAD equality, never asserts the candidates stay untracked, and performs no file writes.

## Test results (both runs)

- Run 1 (normal worktree): `python -B -m unittest validation.test_ds_rate_budget_context -v` — **Ran 15 tests, OK, exit 0** (0.243 s).
- Run 2 (staged lifecycle): a temporary `GIT_INDEX_FILE` copied from the real index with exactly the 3 scope candidates staged (`git diff --cached` showed exactly those 3 paths); the same test under that index — **Ran 15 tests, OK, exit 0** (0.245 s). The temporary index was then deleted (no temp index files remain), and the real index was proven unchanged: `git ls-files -s | sha256sum` = `6a44e364f1aff11b33559aaf99e317281bfb4f37f8496c16c77538f68c90d3d4` with 10704 entries and 0 staged diffs, identical before and after.

## Findings

- **P3-1** (`validation/test_ds_rate_budget_context.py:215`): dead code in `test_strict_parser_rejects_duplicate_keys` — the `text` construction (lines 214-215) is never parsed; the line-214 mutation is a no-op (sets 24665 to 24665) and the construction adds an `owner` key, not a duplicate. Only the later `duplicated` variant exercises the guard. Harmless.
- **P3-2** (`docs/coordination/ds-rate-budget-20260912.json:101`): the 8fmacpgy `control_candidate` embeds an editorial parenthetical instead of a bare token; distinctness still holds.
- **P3-3** (`docs/coordination/ds-rate-budget-ingest-note-20260914.md:14`): until this batch is committed, the bound files' byte-identity pins exist only inside the (untracked) candidate files themselves; no tracked artifact attests them. Same accepted structural property as prior context batches.

**Counts: P1 = 0, P2 = 0, P3 = 3.**

## Verdict

**PASS** — zero P1 and zero P2 findings.

## Claims and boundaries

This review grants no approval, is not an acceptance record, and closes nothing. The `1w6dru32` / `#83 CLOSED` wording in the tracked measured-candidate anchor is cited as recorded history only; its current validity is not asserted here. All "current status / may close" judgments remain with the current authority (main agent / main session / human ruling). No candidate or existing file was edited; the real index was never staged; nothing was committed or pushed; the protected files `docs/Prometheus.gitmodules.reference` and `validation/coordination/short-cycle-dispatches.json` (pre-existing worktree modifications) were left untouched; no live GitHub state was queried; no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight execution was performed; #83 was not rerun. Outputs of this review are exactly the three untracked files in this directory: `review.md`, `review.json`, `SHA256SUMS`.
