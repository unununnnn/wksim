# CodeBuddy independent review — mixed-work-overrun historical-context batch (2026-09-14-01)

Reviewer: CodeBuddy (independent session). Workspace `C:/Users/PC/Documents/odid编译/wksim`.
Review window opened 2026-09-14 (~20:30+09:00), artifacts written 2026-09-14T20:48+09:00.

## Scope and identity verification

Reviewed exactly the three dispatched files; nothing else inspected except anchors they cite.

| File | SHA256 (recomputed) | Bytes | Match dispatch |
| --- | --- | --- | --- |
| `docs/coordination/mixed-work-overrun-20260913-v2.md` | `b432e2c3bca0ffbcd7b77dd91304d6a5d064e9d6dabd20a8fba1ec99e8836352` | 5410 | yes |
| `docs/coordination/codebuddy-mixed-work-overrun-ingest-note-20260914.md` | `1648f3d486e3e9bfe42632c39efaf4976237385be3703dc0903a4885bec6c575` | 9531 | yes |
| `validation/test_codebuddy_mixed_work_overrun_context.py` | `a510bd6aac8fd96f779e234b5be4b2974e66909a75ad7dde3bc150f86882450b` | 25557 | yes |

- HEAD verified: `git rev-parse HEAD` = `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` — exact match to the dispatch baseline (not merely ancestry).
- Architecture ancestor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`: `git merge-base --is-ancestor … HEAD` exit 0.
- The ingest note self-declares HEAD `31e5b65f…` at writing time — consistent.

## Independent verification results

All checks below were recomputed by this reviewer with direct commands; suite constants were not trusted.

### 1. Tracked anchors (HEAD-tree bytes) — PASS

| Anchor | Recomputed (sha256 / bytes) | Note claim | Verdict |
| --- | --- | --- | --- |
| `validation/coordination/mixed-work-overrun-20260913/analyze_mixed_work_overrun.py` | `1162d9fb…e691972` / 28503 | same | match |
| `validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun-v2.json` | `e10619cc…68c408` / 12062 | same | match |
| `validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun.json` (v1) | `d0a214e3…18272` / 9843 | sha claim only | match |
| `validation/coordination/mixed-work-overrun-20260913/main-rate-crosscheck.json` | `461f6bd3…9febe` / 926 | sha claim only | match |
| `docs/coordination/mixed-work-overrun-20260913.md` (v1) | `a0bd3df0…cd3ec` / 4082 | same | match |
| `docs/coordination/mixed-work-overrun-20260913-v2.md` at HEAD tree | `24ad1572…4893a` / 2863 (pre-remediation) | same | match |
| `validation/33-formal-promotion/current-mixed-oxv29042/rate.jsonl.gz` | `8058ecff…c99da` / 2138673 | same | match |
| `…/source__tools__run_joint_flight.py.txt` (frozen snapshot) | `65c7a867…d8161` / 82953 | sha claim only | match |
| `tools/run_joint_flight.py` (live) | `c8577093…acbb3b` / 79221 | same | match |
| `Simulator/wksim_core/joint.py` | `f5433c2e…241d50` (worktree byte-identical to HEAD tree) | same | match |
| `validation/coordination/ds-g0-g5-frontier-20260913-01/audit.json` | `7206d768…d94f` / 64330 | same | match |

Additional anchor checks:

- `Simulator/wksim_core/joint.py:54` is exactly `self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'` (HEAD tree and worktree).
- Frozen snapshot `record()` is at lines 829–831 (`def record(kind, **data):` at 829).
- v1 doc line 15 contains the obsolete SHA citation `e5a0db2b…d81595fe` as claimed.
- Analyzer path history: `git log --all -- <analyzer path>` completes with exactly one commit, `596cb5e6`, whose content hashes to `1162d9fb…` — the single-committed-version claim holds for completable history (see caveat F-1).
- Runner drift: GNU diff `^[<>]` count snapshot vs live = **377**, exactly matching the note's §5.3 approximation claim.
- Gates phrase `1 ms tick, 4-tick group, no catch-up, <=100 ms lateness, complete windows, source_unchanged` present in the tracked ds-g0-g5 audit.json (grep count 1).
- Protected dirty files match the test's baseline worktree hashes (`docs/Prometheus.gitmodules.reference` = `5aa70302…`, `validation/coordination/short-cycle-dispatches.json` = `06e65cc1…`); both differ from their HEAD-tree blobs, consistent with note §5.4 disclosure. Not touched.

### 2. launch.sh line 4 unset semantics — PASS

`validation/33-formal-promotion/current-mixed-oxv29042/launch.sh:4`, verified verbatim in HEAD tree and worktree:

```
unset CMAKE_PREFIX_PATH AMENT_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH ROS_PACKAGE_PATH ROS_DISTRO PKG_CONFIG_PATH WKSIM_JOINT_CPU_TIMING WKSIM_JOINT_RATE_TIMING_PROBE
```

Contains both env names, starts with `unset `, no `=` assignment — an unset control, not a set. Same directory `launch.json` and `children-start.json`: `git grep WKSIM_JOINT_CPU_TIMING` at HEAD = zero matches (exit 1). `pre-run-identity.json:28` = `"WKSIM_JOINT_CPU_TIMING": null,`. The v2 doc's correction of the earlier "均不含" phrasing is accurate and material.

### 3. raw-wire / go.json / admission absence limitations — PASS

- `go.json`, `experimental-admission.json`, `joint-wire.jsonl`: absent from the oxv29042 field directory in the HEAD tree (`git ls-tree -r` grep exit 1) and on disk (`ls` grep exit 1).
- Raw wire (SHA `20d0634e…`, 495,410 rows) is correctly declared locally non-recomputable; conclusions rest on the tracked v2 JSON fixature. Reviewer independently parsed the tracked v2 JSON: `observed_counts` = all three diagnostic kinds 0, `observed_total` 0, `rows_in_overrun_windows` `[]`, `extractable_stages` null, `expected_min_step_cpu_records_if_enabled` 527 (arithmetic check: floor(131760/250) = 527 ✓), `window_ticks_examined` = 7 groups × 17 = 119 ticks with starts `1992, 5496, 47732, 57448, 87636, 119276, 127936` ✓, `wire_kind_census` = {actuator, sensor, step, barrier, gps, connected} ✓, `tick_alignment_control.true_P+1..P+4=true` and `wrong_alignments_rejected=true` ✓.
- No PASS in the suite depends on an untracked-only external artifact — confirmed by reading the test: every checked anchor is HEAD-tree bytes or one of the two candidates.

### 4. v1 historical vs v2 authoritative — PASS

v1 doc preserved byte-identical (`a0bd3df0…`); v2 §"可复核性与当前限度" explicitly declares v1 historical and v2 the current authoritative statement; HEAD tree still holds the pre-remediation v2 (`24ad1572…` / 2863), so the remediation is uncommitted worktree state — exactly as the note discloses (§1, §5.1). No overclaim.

### 5. No promotion / no closure — PASS

v2 JSON independently parsed: `full_run_acceptance=false`, `performance_pass=false`, `native_executed=false`, `run_id=joint-public-flight-oxv29042`, `epoch=18c96a7e0af9477092aa87e18239c23c`. Note §0/§4 disclaims acceptance, approval, closure, and promotion; the note-boundary detector enforces required boundary phrases and forbids elevation phrases, and its mutation negatives fail closed.

### 6. Gate language — PASS

Diagnostic gate vocabulary preserved in both docs (1ms tick, native barrier, 4-tick grouping / `true_P+1..P+4`, no catch-up, ≤100ms, full-window, physics, identity gates), with the tracked anchor sentence verified in `ds-g0-g5-frontier-20260913-01/audit.json`.

### 7. Mutation negatives — PASS (verified by execution)

All six mutation-negative tests pass in the normal run: hash detector fails on mutated source bytes and on size mutation; zero-count detector fails on nonzero count; unset-semantics detector fails on `export …=1` and `set …` mutations; never-committed detector fails on a fake `e5a0db2b…` version and on any second version; note-boundary detector fails on removal of a required boundary phrase and on elevation insert. Detectors fail closed; suite never mutates Git state (all git invocations read-only; `hash-object` without `-w`).

## Test results (executed)

- **Normal run** (`python -m unittest validation.test_codebuddy_mixed_work_overrun_context -v`, Python 3.13.11): **Ran 29 tests — OK (skipped=1)**; skip is the temp-index-only test by design; exit 0. Works with candidates untracked, as documented.
- **Private temp-index exact-3 candidate run**: fresh non-existent temp index path (`/tmp/wksim_tempidx_cWII`, git-created), `git add` of exactly the three batch files; `git ls-files -s` under the temp index shows **exactly 3 entries, all stage 0, mode 100644**; suite with `WKSIM_MIXED_OVERRUN_TEMP_INDEX=1`: **Ran 29 tests — OK (0 skipped)**, including `TestTemporaryIndex` asserting both candidates staged blob-identical to working-tree bytes. Temp index file removed afterwards.
- **Real index untouched**: `.git/index` SHA256 `a7fd6154535cbcde789c99d6ee5f38097d914323453dde5d5ad97b1da09e9253` before session start and after all runs — byte-identical. No staging into the real index, no commit, no reset, no clean, no push.

## Findings

### F-1 (P3, environmental, pre-existing) — shallow clone + foreign checkpoint refs bound full-history pickaxe

The repository is shallow (`git rev-parse --is-shallow-repository` = true) and carries many `refs/codex/turn-diffs/checkpoints/*` refs pointing at objects beyond the shallow boundary. `git log --all -S"e5a0db2b"` aborts with `fatal: unable to read d12de5b5c7b91b9acf06e790113d6b1a1bdd4ef5` mid-traversal. Consequently the "e5a0db2b… never committed" conclusion is proven within completable path-scoped history (exactly one commit `596cb5e6`, content `1162d9fb…`) — the same method the suite uses, which exits 0 — and cannot be strengthened to an unrestricted whole-repo pickaxe in this checkout. Not introduced by this batch; does not invalidate any batch claim; no action required here. Recorded so future full-history audits do not mistake the abort for a batch defect.

No P1 or P2 findings. No defect found in any of the three reviewed files; every independently recomputable claim matched.

## Verdict

**KEEP.** Findings: P1=0, P2=0, P3=1 (F-1, environmental caveat only).

The batch is internally consistent, its limitation boundaries are honest (external artifacts declared unverifiable rather than asserted), the promotion/closure prohibitions hold in both prose and machine-checkable form, and the test suite is fail-closed with a passing normal run and a passing private temp-index exact-3 run. Proven behavior above covers the offline slice only; per the batch's own boundary it is not field acceptance and does not close G6/Full/#84 or trigger #83.
