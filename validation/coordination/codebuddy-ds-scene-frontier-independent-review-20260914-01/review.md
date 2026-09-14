# Independent review — codebuddy-ds-scene-frontier-independent-review-20260914-01

- Reviewer: independent CodeBuddy evidence reviewer (did not author any scoped file)
- Date: 2026-09-14
- Reviewed HEAD: `76f77470e91ecc742148df0f3eba6f5b5494511c` ("Bind Full frontier context offline")
- Scope (3 candidate files, all untracked, none edited by this review):

| Path | SHA256 | Size |
| --- | --- | --- |
| `docs/coordination/ds-scene-frontier-20260912.md` | `9922942f3e13d712d02c050e62825dcc004f9cac41205de8b169b83c232a557e` | 7691 |
| `docs/coordination/ds-scene-frontier-ingest-note-20260914.md` | `f4804e46035c3f9be4c2ae5300ad51b84bc71068d469ef65e19e0eb4a7ebfe3e` | 9376 |
| `validation/test_ds_scene_frontier_context.py` | `9699c84836f03fdf5e639524321abc7fb437686f6c5e29eb5b79604a273aa719` | 17763 |

- Reference (tracked, **not** a candidate): `validation/test_scene_frontier_contract.py` — SHA256 `3f593d8f…6c3de2`, 7115 bytes, identical to its blob at `cf509f5361f468e78bb81e47b3992ddf7db02957` (single-commit history).

## Verified facts (all recomputed at the reviewed HEAD)

1. **Exact hashes/sizes and note bindings.** The frontier doc's SHA256+size match the note §1 binding and the test candidate pins; the note's own SHA256+size match the test candidate's pins (the note deliberately does not self-pin; §6 defers its identity to the delivery report). All four commits cited by the batch — binding HEAD `9c581ad5`, architecture ancestor `f333316e`, companion commit `cf509f53`, manifest audit `c3f0d319` — are ancestors of HEAD (exit 0 each).
2. **Tracked anchors.** All 12 anchor paths (manifest, two contracts, closure report, `9-vendor-abi-defer-boundary.json`, three runtime modules, probe tool, companion test, two existing test modules) are tracked and present; the three `lunar-29-*` fixture directories hold 32 tracked files (≥ 3 floor).
3. **Manifest semantics.** `docs/plan/29-terrain-evidence-manifest.json` is `status=partial_open`, `acceptance=false`, `blocking_issue=9`, with exactly the three `unproven_boundaries` keys (`missing_real_ue_physics_colocation`, `missing_fc_closed_loop`, `missing_slope_contact_force_dynamics`), all non-empty. The doc's "current valid status" claim holds: the date-only `git log --since=2026-09-12` over the manifest, contracts, runtime modules, and probe tool reproduces empty, and the files' last touches (`7a08bd52` 02:51:36 +0900, `c3f0d319` 04:05:42 +0900, both 2026-09-12) precede the doc's same-day writing.
4. **Three scene identities and the frozen seam.** Manifest identities `static-plane-box-v1` / `60ae5097…` @[2.0, 0.0, 0.5] and `static-plane-box-v1-real-tick0` / `4889e2ea…` @[0.0, 0.0, 0.5] match the runtime constants: `LEGACY_SCENE_ID/HASH` (`planner_scene_binding.py:64-65`), `EXPECTED_SCENE_HASH` = `40ee9281…` (`:77`), `EGO_SINGLE_BOX_BINDING` (`:1072`), and `FROZEN_SCENE_SHA256` (`contact_observer.py:26`) = the visual fixture hash. The three layers are pairwise distinct and the terrain seam stays on the frozen visual fixture, never the probe identity.
5. **Supersessions.** (a) *Zero-occurrence*: the note registers the historical doc's zero-occurrence claim as superseded; the per-file token pattern of all four listed files verifies exactly (companion True/True; `check_g3_closure.py` False/True; omp-g4 `probe.py` True/False; deepseek `probe.py` False/True), and no other tracked `validation/*.py` carries either token. (b) *Ticket table*: scoped as a 2026-09-12 snapshot requiring live re-query; no live GitHub query anywhere. (c) *Delivery asymmetry*: companion tracked and clean at `cf509f53`, frontier doc still untracked — registered as fact, not defect or instruction.
6. **Non-authority wording.** Note §0 disclaims acceptance/approval/closure/review for #29, #102, #9, live ticket rulings, and native-execution permission; §6 disclaims git add/commit/push, protected files, and #83. The historical doc's "关闭本父票仍需…" is a quoted requirement and "本轮不关闭、不改写任何 Issue" is a negative — no promotion wording found. The test enforces forbidden patterns on its reference phrasing with five rejection mutants.
7. **Meaningful negatives.** Hash/size drift (both directions), missing-anchor, bogus-ancestry, wording-promotion, and manifest-drift mutants are all rejected; the reference test proves probe identity is refused as planner identity and that foreign-epoch injected observers freeze fail-closed at the real seam.
8. **Descendant/staging safety.** The binding test resolves the repo root from `__file__`, asserts `9c581ad5` as an *ancestor* of symbolic HEAD (not equality), reads current content only via symbolic HEAD or pinned historical blobs, never asserts candidates stay untracked, and writes nothing. Its only live tracking assertion is the companion's, which staging cannot undo.

## Test results (both runs)

- Run 1 (normal worktree): `python -B -m unittest validation.test_ds_scene_frontier_context validation.test_scene_frontier_contract -v` — **Ran 23 tests, OK, exit 0** (0.434 s).
- Run 2 (staged lifecycle): a temporary `GIT_INDEX_FILE` copied from the real index with exactly the 3 scope candidates staged (`git diff --cached` showed exactly those 3 paths); both modules under that index — **Ran 23 tests, OK, exit 0** (0.425 s). The temporary index was then deleted (no temp index files remain), and the real index was proven unchanged: `git ls-files -s | sha256sum` = `905998f11b4212a07df2d30d3b64af7cd7acef02c9be888992f770668bd130a4`, 10714 entries, 0 staged diffs — identical before and after.

## Findings

- **P3-1** (`docs/coordination/ds-scene-frontier-ingest-note-20260914.md:14`): the §1 binding table records the companion test's size as 6364 bytes; the file and its blob at `cf509f53` are 7115 bytes. The SHA256 cell is correct and the §5.1 seam re-checks the companion by SHA only, so the error cannot produce a false acceptance (it errs toward false rejection). Correct size 7115 recorded here.
- **P3-2** (`…ingest-note-20260914.md:28`): the §3.1 four-file supersession list includes `validation/coordination/deepseek-102-residual-20260914-01/probe.py`, which is untracked and gitignored (`.gitignore:53` `/validation/*/`); a fresh clone at HEAD would show only three token-bearing tracked files. The supersession substance survives via the three tracked files, and the binding test reads the worktree so it would fail loudly if that file vanished.
- **P3-3** (`…ingest-note-20260914.md:28`): the §3.1 count "共 4 个 `validation/*.py` 文件" is a writing-time snapshot (HEAD `9c581ad5`); at the reviewed HEAD the batch's own binding test also carries both tokens (fifth file). The drift strengthens the supersession but the count should be read as time-scoped, like the claim it supersedes.

**Counts: P1 = 0, P2 = 0, P3 = 3.**

## Verdict

**PASS** — zero P1 and zero P2 findings.

## Claims and boundaries

This review grants no approval, is not an acceptance record, and closes nothing. The ticket states in the historical doc are cited as a 2026-09-12 snapshot only; no live GitHub state was queried and no current ticket-status judgment is asserted — any such judgment requires live re-query or current-authority ruling (main agent / main session / human ruling). No candidate or reference file was edited; the real index was never staged; nothing was committed or pushed; the protected files `docs/Prometheus.gitmodules.reference` and `validation/coordination/short-cycle-dispatches.json` (pre-existing worktree modifications) were left untouched; no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight execution was performed; #83 was not rerun. Outputs of this review are exactly the three untracked files in this directory: `review.md`, `review.json`, `SHA256SUMS`.
