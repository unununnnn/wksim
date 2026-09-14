# CodeBuddy independent evidence review — ds-model-closure context slice

2026-09-14. Reviewer: independent CodeBuddy evidence reviewer. Working checkout: `C:/Users/PC/Documents/odid编译/wksim`, reviewed HEAD `cc42c19f1b06538cf5bfd326d7dcd11f7b1ed6a5` (verified with `git rev-parse HEAD`). Architecture ancestor check `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` exit 0.

## 0. Verdict summary (no approval or closure claim)

**Verdict: PASS** — zero P1 and zero P2 findings; four P3 findings (test-quality / wording-consistency observations only).

This review is an independent evidence audit of three untracked candidate files. It does **not** approve, accept, close, or re-validate issue #26, any condition A/C/D, or any acceptance claim. Conditions A (contract-block disposition marker), C (named main-agent AC5 review record), and D (formal dependency #9 disposition) remain **open observations** per the ingest note; this review does not dispose of them.

## 1. Scope (exactly three candidate files, read-only)

| File | Status at review | SHA256 | Size (bytes) |
| --- | --- | --- | --- |
| `docs/coordination/ds-model-closure-20260912.md` | untracked | `a869117ff88c3e594fb44240b8970ee463aaedd39dca67e578b80f03dbe51d28` | 15346 |
| `docs/coordination/ds-model-closure-ingest-note-20260914.md` | untracked | `979b37553f9716b58559df38d36a4070182d2b84d092e21f797a17d0533c11e9` | 9394 |
| `validation/test_ds_model_closure_context.py` | untracked | `68ead196f66caa3b794ec830d5d2978c1ad2b68f386d0310cebc9b9dd6859884` | 13058 |

No candidate file was edited. No existing file was edited. No `git add/commit/push` was executed.

## 2. Method and governance

Read before review: parent `AGENTS.md`, `CONTEXT-MAP.md`, `wksim/AGENTS.md`, `wksim/CONTEXT.md`, `wksim/docs/coordination/architecture-continuation-20260913.md`. No ADR files exist under `wksim/docs/` (glob verified); the continuation contract and context doc are the governing texts for this slice. All hashes below were recomputed independently by this reviewer (`sha256sum`, byte mode) — not taken from the candidates — before the test was run.

## 3. Independent verification results

### 3.1 Strict hash/size pins (all recomputed, all hit)

- Original doc: SHA256 `a869117f…be51d28`, size 15346 — matches ingest note §1 and test pins (`ORIGINAL_SHA256`, `ORIGINAL_SIZE`).
- Ingest note: SHA256 `979b3755…33c11e9` — matches test pin `NOTE_SHA256`.
- Six manifest pins (`docs/plan/26-closure-readiness-manifest.json` `acceptance_evidence`): manifest parsed as exactly 5 groups / 6 unique pins; manifest-recorded SHA256 equals both the ingest-note §2.1 table and the recomputed current bytes for all 6 (`60a22362…`, `85c40213…`, `e5f32bd2…`, `3d5c7896…`, `42bc11a2…`, `0669730a…`).
- Three generated-source pins (`work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw/`): recomputed == pinned for `.cpp`/`.h`/`rtwtypes.h` (3/3), matching note §2.2.
- Wrapper `Simulator/wksim_core/model.cpp`: current SHA256 `150ddf3b…72d0290`, 4070 bytes; `git show 7126d4d7…:…` and `git show HEAD:…` both hash to `150ddf3b…`; `git log 7126d4d7..HEAD -- Simulator/wksim_core/model.cpp` empty. This directly corroborates ingest note §3.4's reclassification of `68c6965b…` as an export line-ending artifact with no current object identity.
- Supersession artifact pins: `docs/plan/full-acceptance-report.md` = `daded672…caf514`, 31086 bytes; `docs/plan/26-current-source-ac-evidence-20260912.md` = `4070bf4b…4a79` — both match ingest note §3 claims.

### 3.2 Ancestry

- `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` ancestor of HEAD: exit 0.
- `7126d4d774a33c7d4b2504b9931a93ac27d7fa51` (original doc's self-declared HEAD) ancestor of HEAD: exit 0.

### 3.3 Tracked supersession anchors

`git ls-files --error-unmatch` tracked: `docs/plan/full-acceptance-report.md`, `docs/plan/26-current-source-ac-evidence-20260912.md`, `docs/plan/9-vendor-abi-defer-boundary.json`. `git ls-files` over the two current-wrapper evidence dirs returns exactly 22 tracked files (test floor `>= 22`; ingest note §3.2 "22", §5.6 "≥22").

### 3.4 Non-authority wording

- Ingest note §0 explicitly disclaims acceptance/approval/closure/review authority for itself and for the bound file, and keeps conditions A/C/D as open observations (§4). Grep over the note for authority phrasing found matches only inside negations, binding registrations, and the §5.7 rule text itself — no promotion.
- Original doc is a read-only cross-check with explicit non-claims (§7 "明确不得据此声称的结论", §8 boundary declaration); the note binds it as historical context only, superseding its stale statements (report-missing, condition-B disposition, `68c6965b`) while registering conditions A/C/D as still open.
- The test's own wording checks assert the note contains the historical-context and open-observation phrasing and that `gh issue view` output is not cited; promotion regexes are exercised on mutated strings (negative tests).

### 3.5 Test quality

`validation/test_ds_model_closure_context.py`: 14 tests, all offline (no network, no model/MATLAB/build/flight execution). Strengths: byte bindings with size pin; manifest is cross-checked both ways (manifest pins not rewritten AND current bytes match pins); blob identity checked at two revs plus empty log range; ancestry; tracked-anchor existence and non-shrink floor; four negative-mutation tests proving the helpers actually detect drift. `REPO_ROOT` resolves to the wksim root via `parents[1]`; all git subprocess calls pass `cwd=REPO_ROOT`; read-only (no file writes). Findings P3-1..P3-3 below.

### 3.6 After-staging lifecycle safety

- The test binds **content** (SHA256/size), never tracking status; its docstring states it never asserts candidates stay untracked. Staging/committing the three candidates does not break the suite.
- `REPO_ROOT = Path(__file__).resolve().parents[1]` stays correct at `validation/test_ds_model_closure_context.py` after staging; git subprocesses are cwd-independent of the caller.
- No writes anywhere in the test; safe as a standing post-staging re-verification seam per ingest note §5.
- The note's self-hash pin (`NOTE_SHA256`) means any later amendment to the note breaks the binding — that is the intended tamper-evidence (note §6), not a hazard.

## 4. Findings

| ID | Severity | Location | Finding |
| --- | --- | --- | --- |
| P3-1 | P3 | `validation/test_ds_model_closure_context.py:262` (with `:76-88`) | `assert_no_authority_promotion` is enforced only against the test's own `REFERENCE_PHRASING`, not against any repository document. Note §5.7's wording-containment intent covers "后续文档", which a self-contained test cannot reach. No current violation observed; the guarantee is demonstrative, not repository-wide. |
| P3-2 | P3 | `validation/test_ds_model_closure_context.py:162-163` | The ingest note is bound by SHA256 only, without a size pin (the original doc binds both hash and size at `:159-160`). Slightly weaker tamper-evidence for the note; current note size is 9394 bytes. |
| P3-3 | P3 | `validation/test_ds_model_closure_context.py:82-88` | `FORBIDDEN_PROMOTION_PATTERNS` are English-only while the bound documents are Chinese-dominant; Chinese authority wording (e.g. "已批准", "已收口") would not match even if the patterns were applied to files. |
| P3-4 | P3 | `docs/coordination/ds-model-closure-ingest-note-20260914.md:52` vs `:77`; `validation/test_ds_model_closure_context.py:73` | Minor internal wording variance: §3.2 states exactly "22 个" tracked current-wrapper files while §5.6 and the test floor say "≥22". Currently exactly 22, so no contradiction; aligning to "≥22" everywhere would remove ambiguity. |

P1: 0. P2: 0. P3: 4.

## 5. Test execution

- Command: `python -m unittest validation.test_ds_model_closure_context -v` (run from the wksim repo root, non-native, offline).
- Result: **OK — Ran 14 tests in 0.282s, 0 failures, 0 errors, exit code 0.**

## 6. Boundaries observed

- No native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight execution; ticket #83 not touched.
- Candidate files and all existing files unmodified; nothing staged, committed, or pushed.
- Protected files `docs/Prometheus.gitmodules.reference` and `validation/coordination/short-cycle-dispatches.json` were **already modified in the worktree before this review started** (pre-existing `M` entries in `git status`); this review did not read them for judgment, did not modify, stage, or revert them.
- Real-time GitHub state was not queried; no live-issue status is asserted anywhere in this review.

## 7. Artifacts

- `review.md` (this file), `review.json` (strict JSON, verdict PASS), `SHA256SUMS` (covers `review.md` and `review.json`; self-exclusive by construction).
- All three artifacts are untracked and located under `validation/coordination/codebuddy-ds-model-closure-independent-review-20260914-01/`.

**Verdict: PASS** (evidence-audit pass only; not an approval, acceptance, or closure of #26 or any condition).
