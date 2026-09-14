# Ingest manifest — omp-delivery-diagnostic-context-ingest-manifest-20260914-01

- Manifested at: 2026-09-14, HEAD `e2ecd62e914e075d0d9e40eef8ea9c034b958d2f` ("Bind scene frontier context offline")
- Independent review: `codebuddy-omp-delivery-diagnostic-independent-review-20260914-01`, `reviewed_head` `1c5656ed924020b3e626e68739caeeaef9f41a9e` — verified ancestor of the manifested HEAD (immediate parent; `git merge-base --is-ancestor` exit 0)
- Architecture ancestor: `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` verified as ancestor of the manifested HEAD
- Intervening disjoint delta: exactly one commit (`e2ecd62e`), changing exactly 10 scene-frontier files; no OMP delivery/diagnostic path touched, no byte of this batch changed across the window
- Scope: **context-only**; acceptance: **non-acceptance**

## Exact staging list (11 paths, lexically sorted, all existing)

1. `docs/coordination/omp-delivery-diagnostic-ingest-note-20260914.md`
2. `docs/coordination/omp-delivery-gates-20260912.md`
3. `docs/coordination/omp-diagnostic-entry-20260912.md`
4. `validation/coordination/codebuddy-omp-delivery-diagnostic-independent-review-20260914-01/SHA256SUMS`
5. `validation/coordination/codebuddy-omp-delivery-diagnostic-independent-review-20260914-01/review.json`
6. `validation/coordination/codebuddy-omp-delivery-diagnostic-independent-review-20260914-01/review.md`
7. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/SHA256SUMS`
8. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/exact-paths.txt`
9. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/review.json`
10. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/review.md`
11. `validation/test_omp_delivery_diagnostic_context.py`

No protected files (`docs/Prometheus.gitmodules.reference`, `validation/coordination/short-cycle-dispatches.json`) and no unrelated paths are on the list.

## Verified inputs (recomputed at the manifested HEAD)

| Path | SHA256 | Size |
| --- | --- | --- |
| `docs/coordination/omp-delivery-gates-20260912.md` | `df438b44ad94940990d84a6e39504df8327e24b8e0c0a914710417c61104ac21` | 4010 |
| `docs/coordination/omp-diagnostic-entry-20260912.md` | `73bbc35f0db45ee1b3d9925f7ea5bbfff05c5513ce002e078ea10446b065fe0b` | 7530 |
| `docs/coordination/omp-delivery-diagnostic-ingest-note-20260914.md` | `ba21365683e7b5c3661fc448247a075780b2d64f26461a372b21497105ffa653` | 13251 |
| `validation/test_omp_delivery_diagnostic_context.py` | `67d3e642e26f8df046133d490e5c121210ed304520e9272bbf44fc7d882f646f` | 19991 |
| `…/codebuddy-…-review-20260914-01/review.md` | `8ab6cb365bb1c816312ac3862a6a55e41b5d527c6a943e01c874963766e165d9` | 8263 |
| `…/codebuddy-…-review-20260914-01/review.json` | `9cdbec740ffacbba98492af3eb1d397809ddff48ea5730cfd2ad01b99c3738e7` | 13197 |
| `…/codebuddy-…-review-20260914-01/SHA256SUMS` | `044f72e6c37ee33e31c1f1256b5e6983c11fd157699fe5e8214b5334a4cd860c` | 154 |

The review directory's `SHA256SUMS` self-verifies from inside its own directory at this HEAD (exit 0). All hashes/sizes equal the values recorded by the independent review and this manifest's task statement; no candidate or review byte changed across the commit window.

## Review facts (carried from the independent review)

- Verdict **PASS**; findings **P1 = 0, P2 = 0, P3 = 3**, carried verbatim in `review.json`: (P3-1) vacuous self-guard at `test…py:203`; (P3-2) current-byte pins on three tracked files as a maintenance seam (`test…py:235`); (P3-3) the P2 provenance demotion ("9 项 Windows/WSL" claim) must travel with every future citation (`note:54`).
- The note's five stale-fact registrations, the P2 provenance caveat (tracked 20→21 history `d5954380`→`982336cd`, no 2026-09-12 revision), and the external/WSL/PX4 boundaries were all independently verified by the review.
- Historical-only boundaries: the review asserts no acceptance, approval, closure, review, or rerun permission for #83 (or #9/#26/#29/#62/#102 or any ticket); all "current status" judgments remain with the current authority (main agent / main session / human ruling).

## Test facts (re-run this session at the manifested HEAD)

- Normal worktree: `python -B -m unittest validation.test_omp_delivery_diagnostic_context -v` — **Ran 20 tests, OK, exit 0** (1.006 s).
- Staged lifecycle: temporary `GIT_INDEX_FILE` copied from the real index with **exactly the 11 proposed paths force-added** (`git diff --cached` showed exactly those 11 paths) — **Ran 20 tests, OK, exit 0** (0.896 s). Temporary index deleted; no temp index files remain.
- Real index proven byte-for-byte unchanged across both runs: `git ls-files -s | sha256sum` = `c90e0265fe89d5fb2db93b9ce070e92610fa79496f5d62cf3c3ff0917d98d556`, 0 staged diffs, before = after.
- `git diff --check` over the 7 input paths: clean (exit 0).
- Content-independence note: the suite reads none of the four manifest outputs; `exact-paths.txt` (the staging contract) was byte-final before both runs; the three prose/checksum outputs were finalized after the runs, so the proven facts are the staged path set and the candidate/anchor bytes. The independent review's own runs at the same HEAD (20/20 normal 0.448 s; 20/20 staged 0.462 s) are carried in `review.json`.

## Non-claims

This manifest is context-only ingestion; it is not an acceptance, approval, review, or closure action. No ticket-state disposition is claimed for #83, #9, #26, #29, #62, #102, or any other ticket. Barrier gates are preserved verbatim: `.5×/100ms/1ms` runner-built constants with no CLI parameter; CPU-timing out of `result.json`; `rate_timing_probe` diagnostic identity never acceptance evidence; single-run monotonic differencing only, no cross-run subtraction, no catch-up/backfill, full-window begin/end closure without overlapping sums; identity and physics gates preserved; historical failures (`7bdfxkb_/manager99`, `1w6dru32` CLOSED) cited as recorded history only; `0DQQz9/OEvS3W` historical-identity-only. No input file or file outside the output directory was edited; the real index was never staged; nothing was committed or pushed; protected files untouched; no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight execution; no GitHub query/mutation; #83 not rerun.

## Outputs (exactly four)

1. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/exact-paths.txt`
2. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/review.md`
3. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/review.json`
4. `validation/coordination/omp-delivery-diagnostic-context-ingest-manifest-20260914-01/SHA256SUMS`
