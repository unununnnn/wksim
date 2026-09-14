# Independent review — codebuddy-omp-delivery-diagnostic-independent-review-20260914-01

- Reviewer: independent CodeBuddy evidence reviewer (did not author any scoped file)
- Date: 2026-09-14
- Reviewed HEAD (baseline / candidate authoring): `1c5656ed924020b3e626e68739caeeaef9f41a9e` ("Bind rate budget context offline")
- Verified-at HEAD (current verification): `e2ecd62e914e075d0d9e40eef8ea9c034b958d2f` ("Bind scene frontier context offline") — an exact descendant (immediate parent), no HEAD equality required
- Resume note: the review was interrupted after verification and before writing outputs; the atomic scene-frontier commit landed between turns. The output directory did not exist at resume time (no partial outputs); the three outputs were written fresh. The intervening commit changed exactly 10 scene-frontier files, disjoint from this batch; all verification facts were established at the baseline and re-asserted against the current tree by the 20/20 suite re-run.

- Scope (4 candidates, all untracked, none edited by this review):

| Path | SHA256 | Size |
| --- | --- | --- |
| `docs/coordination/omp-delivery-gates-20260912.md` | `df438b44ad94940990d84a6e39504df8327e24b8e0c0a914710417c61104ac21` | 4010 |
| `docs/coordination/omp-diagnostic-entry-20260912.md` | `73bbc35f0db45ee1b3d9925f7ea5bbfff05c5513ce002e078ea10446b065fe0b` | 7530 |
| `docs/coordination/omp-delivery-diagnostic-ingest-note-20260914.md` | `ba21365683e7b5c3661fc448247a075780b2d64f26461a372b21497105ffa653` | 13251 |
| `validation/test_omp_delivery_diagnostic_context.py` | `67d3e642e26f8df046133d490e5c121210ed304520e9272bbf44fc7d882f646f` | 19991 |

## Verified facts (recomputed at both the reviewed baseline and the verified-at HEAD)

1. **Hashes/sizes.** All four recomputed values match the task-stated values and the note §1 / test pins exactly, unchanged across the commit window.
2. **Tracked anchors.** All 13 paths referenced by the two bound docs are tracked and present.
3. **Hash identities.** `joint.py` = `f5433c2e…`, `joint_rate_probe.py` = `a8bac9ac…`, `33-final-combo-rate-candidate.md` current = `6f0e764a…` (historical reading `9516a2cd` registered as drifted, last touch `941d5843` 2026-09-13).
4. **Content seams (not line-number seams).** `joint.py:54` literal `'1'` read; probe three-state gate at `:25-30`; runner PV/MIXED hard gates `:424-427`; `'--'+name` loop; `candidate_environment(control, messages=None)` `:161`; `reset_on_fork`; `add_timing_probe_identity` `:864`; async CLI `:1183`; `audit_joint_rate.py:36` fail-closed; `check-delivery.py` `instrumentation-refused` + `WKSIM_JOINT_CPU_TIMING=1`; shell overlays `MUlZd0`/`FVMjak`; identity table source `39-planner-run-contract.md` (fhuf05l9 / c2IXOr / Rzj3Pf + three FINAL SHAs) — all present.
5. **Five stale facts, all verified.** (1) `git log -S '3d04d53a' -- tools/ap_mixed_candidate.py` yields exactly `0769c3a0` and `941d5843`; the superseded pin is gone from the current file and the FINAL pins `1e6250ef/6fe8c0b3/29969da0` remain. (2) DS-A overwrite gap fixed (`refusing to overwrite retained evidence` in `audit_pv_trajectory.py` within :881-896 and `audit_planner_release.py` within :353-359) while the DS-D gap is still open (`audit_26_closure_readiness.py:1745` unprotected `write_text`, CLI now :1739-1740). (3) plan-33 hash drift. (4) Runner line drift via `c3d4916f` (2026-09-13); line numbers registered as 2026-09-12 historical readings only. (5) Secondary line drifts (`audit_joint_rate.py:36`, audit-26 CLI) within registered ranges.
6. **P2 provenance caveat.** `validation/test_delivery_entry_contract.py` first entered tracking at `d5954380` (2026-09-14, 20 test defs); tracked head `982336cd` (21); worktree 21; no 2026-09-12 revision exists. The gates doc's "9 项，Windows/WSL 双平台通过" is therefore correctly demoted to a recorded historical execution statement that no offline checkout can prove.
7. **External boundaries.** The Linux experimental area, the six /root candidate/overlay paths, the 69-line runner drift, `--planner-release-proof` interaction, and PX4 candidate pairs are registered as outside this checkout and offline-unverifiable (claims only); main-workspace-side hashes independently recomputed; PX4 left blank; raw/live roots untouched.
8. **Staging/fresh-clone safety and mutation coverage.** The suite resolves paths from `__file__`, asserts ancestry only (f333316e / 76f77470 / 1c5656ed as ancestors of symbolic HEAD), never requires HEAD equality, never asserts candidates stay untracked, writes nothing, and its mutation negatives (hash/size drift both directions, missing anchor, bogus ancestry, missing literal, five promotion-wording mutants) all reject with real-value sanity passes.
9. **Wording and barriers.** Note §0 disclaims acceptance/approval/closure/rerun-permission for #83 (and #9/#26/#29/#62/#102); §7 separates reusable historical context from non-reusable authority; `.5×/100ms/1ms` runner-built constants with no CLI parameter; CPU-timing stays out of result.json; `rate_timing_probe` diagnostic identity never acceptance evidence; single-run monotonic differencing, no cross-run subtraction, no catch-up/backfill, full-window begin/end closure without overlapping sums; identity and physics gates preserved; historical failures (`7bdfxkb_/manager99`, `1w6dru32` CLOSED) cited as recorded history only; `0DQQz9/OEvS3W` marked historical-identity-only; "诊断场永不得充当验收场" present in the bound bytes.

## Test results (both runs, at the verified-at HEAD)

- Run 1 (normal worktree): `python -B -m unittest validation.test_omp_delivery_diagnostic_context -v` — **Ran 20 tests, OK, exit 0** (0.448 s).
- Run 2 (staged lifecycle): a temporary `GIT_INDEX_FILE` copied from the real index with exactly the 4 scope candidates staged (`git diff --cached` showed exactly those 4 paths) — **Ran 20 tests, OK, exit 0** (0.462 s). The temporary index was deleted (no temp index files remain), and the real index was proven byte-for-byte unchanged: `git ls-files -s | sha256sum` = `c90e0265fe89d5fb2db93b9ce070e92610fa79496f5d62cf3c3ff0917d98d556`, 0 staged diffs, identical before and after.
- Continuity: the interrupted pre-write session had already run the same suite at the baseline `1c5656ed` with identical outcomes (20/20 OK, 1.051 s normal; 20/20 OK, 0.951 s staged).

## Findings

- **P3-1** (`validation/test_omp_delivery_diagnostic_context.py:203`): vacuous self-guard — `assertNotIn("rev-parse", "require_ancestor uses merge-base only")` inspects a constant literal and can never fail; the no-HEAD-equality constraint is documented but not enforced by this assertion. The constraint itself genuinely holds.
- **P3-2** (`…test_omp_delivery_diagnostic_context.py:235`): `test_current_hash_identities` pins current bytes of three tracked files; legitimate future edits break the suite until the note is re-registered — intended tamper-evidence, but a maintenance seam rather than an ancestry-only invariant.
- **P3-3** (`docs/coordination/omp-delivery-diagnostic-ingest-note-20260914.md:54`): the P2 provenance demotion must travel with every future citation — the 9-test Windows/WSL claim stays an unprovable historical execution statement; only the tracked 20→21 history is checkable.

**Counts: P1 = 0, P2 = 0, P3 = 3.**

## Verdict

**PASS** — zero P1 and zero P2 findings.

## Claims and boundaries

This review grants no approval, is not an acceptance record, and closes nothing. #83 was not rerun and no rerun permission is claimed; diagnostic fields remain permanently non-acceptance evidence. All "current status / may accept / may close" judgments remain with the current authority (main agent / main session / human ruling). No candidate or existing file was edited; the real index was never staged (temp index only, deleted, real index byte-for-byte unchanged); nothing was committed or pushed; no GitHub state was queried or mutated; protected files (`docs/Prometheus.gitmodules.reference`, `validation/coordination/short-cycle-dispatches.json`) untouched; no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight execution. Outputs of this review are exactly the three untracked files in this directory: `review.md`, `review.json`, `SHA256SUMS`.
