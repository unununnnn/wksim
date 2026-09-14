# Independent adversarial review — #59 G6/B5 solve-form-decision stable-evidence repair

- **Reviewer**: independent adversarial reviewer (Claude Opus 4.8, 1M context)
- **Review date**: 2026-09-14 (repo TZ +09:00); live checks re-run against the repository as found
- **Verdict**: **GO**
- **Object under review**: the *uncommitted* worktree repair that replaces exact-HEAD pinning with the
  stable-evidence (baseline-ancestor + per-path zero-diff) contract for the #59 G6/B5 solve-form decision packet.
- **Authority of this review**: proposal-only assessment. It does not accept G6, Full, #84, physical accuracy,
  any B1 budget, any B4 freeze, or any owner option. It mutates no issue, no git ref, no real index, no worktree
  file other than this review's own directory.

## 1. Method

I derived every fact independently with read-only git probes and an in-memory driver of the shipped verifier; I did
not trust the packet, the test suite's self-report, the recheck record, or the markdown as evidence of their own
claims. Commands used: `rev-parse`, `cat-file`, `merge-base --is-ancestor`, `rev-list --count` (default and
`--full-history`), commit-vs-commit `diff`, `show`, `log --diff-filter=A`, plus throwaway merge repos under `/tmp`
to probe `rev-list` history-simplification behaviour. No model/MATLAB/ROS/FC/UE/build/#83 was run. No path was
staged, committed, pushed, or edited except this review directory.

## 2. Candidate identity and integrity (matches expected exactly)

| Candidate | SHA256 (worktree) | Size (bytes) | Expected match |
| --- | --- | --- | --- |
| `validation/e0-g6-solve-form-decision-20260914.json` | `bc8302e970bf703622c0f57a1966398bc5f71b04ce9b223668b4103c83580507` | 11435 | ✔ |
| `validation/test_e0_g6_solve_form_decision.py` | `86c96dff53a0e2201922cbf9d123277b61a87209605345a2ac1d251f6c7ce49a` | 48045 | ✔ |
| `docs/plan/59-g6-solve-form-decision-20260914.md` | `4c773018b5ee45d6a521fb50453401b3237dbff4ffea51387e45b8f3f7cdb7ce` | 7079 | ✔ |

The three candidates are **uncommitted worktree modifications** (`git status` = ` M`, `git diff --cached` empty —
nothing staged in the real index). Their HEAD blobs are the *pre-repair* versions and exactly equal the self-hashes
recorded in `recheck.json` (see §7). This is the expected pending-repair state, not drift.

## 3. Live repository facts (diagnostic-only observed HEAD confirmed)

- Live `HEAD` = `0b10f786e808eebe7698e9a277766bf2f68a4d35`, branch `main`.
- Anchor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` **is** an ancestor of `HEAD` (`merge-base --is-ancestor` exit 0).
- Packet `observed_at.head` = `768526aafa1e48c342c5c8840a9154e8ed90f68d`. It **differs** from live HEAD and **is a
  genuine ancestor** of live HEAD — i.e. a real past observation, not a fabricated or current value.
- `observed_at.head_pinned=false`; `baseline_ancestor` = `f333316…` matches the contract anchor.
- The live HEAD literal `0b10f786…` appears **nowhere** in the packet JSON, the test file, or the markdown
  (verified by direct substring search). The suite asserts `observed["head"] != _live_head()` and rejects any packet
  that pins the live HEAD (`test_no_exact_current_head_pinning`). **No exact current-HEAD equality or literal is
  required anywhere.**

## 4. The difficult point — does the per-path rev-list count prove "introduced once, never modified"?

The contract: a pinned path **tracked at the anchor** must have **0** touching commits in `f333316..HEAD`; a pinned
path **first introduced after the anchor** must have **exactly 1** touching commit. The reviewer concern is whether
`git rev-list --count A..HEAD -- path` (default history simplification) is weaker than a *concrete later
content-anchor plus zero-diff window*.

### 4.1 The window is linear, so the count is exact here

`f333316..HEAD` contains **0 merge commits** (82 linear commits). On a linear history, default `rev-list -- path`
shows a commit iff the blob at the path differs from its parent (TREESAME pruning); there is no merge topology that
could undercount. So the count is a faithful count of blob-changing commits on this window.

### 4.2 Per-pin counts (default == full-history ⇒ nothing hidden)

| Pin | Path | At anchor? | `rev-list` (default) | `--full-history` |
| --- | --- | --- | --- | --- |
| reference_run05 | `g6-reference-probe-20260913/run-05/reference-first-step.json` | yes | 0 | 0 |
| target_mrdivide | `g6-target-mrdivide-20260913/first-step-trace.jsonl` | yes | 0 | 0 |
| diagonal_candidate | `g6-diagonal-solve-candidate-20260913/first-step-trace.jsonl` | yes | 0 | 0 |
| comparison_v2 | `g6-target-first-step-20260913/comparison-v2.json` | yes | 0 | 0 |
| division_vs_reference | `cursor-g6-solve-form-20260914-01/division-vs-reference.json` | **no** | 1 | 1 |
| diagonal_vs_reference | `cursor-g6-solve-form-20260914-01/diagonal-vs-reference.json` | **no** | 1 | 1 |
| stage2_operand_boundary | `cursor-g6-solve-form-20260914-01/stage2-operand-boundary.json` | **no** | 1 | 1 |

Default equals full-history for every pin, confirming simplification hides nothing in this window.

### 4.3 Independent content-anchor + zero-diff cross-check AGREES (the "stronger" method)

I applied the stronger method the reviewer named, independently of the implementation:

- **Derived pins** — the single touching commit is `0785f0e69c8756f34ea95425145fde0a3668e015` ("Track G6 solve-form
  replay evidence", 2026-09-14T02:14:26+09:00), which `--diff-filter=A` confirms as the genuine **add** commit for all
  three (no rename). For each: `show(intro:path)` sha256 **==** `show(HEAD:path)` sha256 **==** worktree sha256 **==**
  the packet pin, and `git diff intro..HEAD -- path` is **empty**.
- **Source pins** — `show(f333316:path)` sha256 **==** `show(HEAD:path)` sha256, and `git diff f333316..HEAD -- path`
  is **empty** (content anchored at the baseline, not merely at HEAD).

So on this repository the count-based check and the content-anchor+zero-diff check produce **identical** verdicts.

### 4.4 Across merges, default simplification is content-faithful for this property

To test whether a merge could let `rev-list` undercount a *real* modification (making count weaker than
content-anchor), I built throwaway merge histories:

- modify-on-side then merge-take-side → count **2** (both shown); content-anchor diff **non-empty**. Both catch it.
- add/add conflict resolved to side's content → count **1**, and the single shown commit is exactly that content's add
  (the discarded add is correctly *not* counted); `--diff-filter=A` agrees; diff intro..HEAD empty. Both accept, and
  both are *correct* — the discarded change never reached HEAD.
- add/add resolved to a *third* value (neither parent) → count **3** (merge is !TREESAME, both parents shown). Caught.

This confirms default simplification prunes only changes that were **discarded** (do not affect final content), while
showing the effective content lineage. For the property that matters here — *path absent at the anchor and present at
HEAD with a pinned digest* — `count==1` is **content-faithful**: it is equivalent to "introduced once as the pinned
digest and never effectively modified." Any modification that reaches HEAD either changes the HEAD blob (caught
independently by the `sha256` pin) or is reflected in the count.

### 4.5 rename / delete / re-add edge cases fail closed

Driven directly against the verifier (and present as shipped tests):

- derived re-modified (`count=2`) → `tampering`
- derived delete/re-add (`count=3`) → `tampering`
- derived `count=0` (absent-at-anchor yet untouched — an impossible real state, still fails closed) → `tampering`
- source/anchored path touched (`count=1`) → `tampering`
- delete-then-absent at HEAD → caught earlier because `git show HEAD:path` fails (`missing_pins`)

A rename-*into* the pinned path would yield `count==1`, but the content is still pinned at HEAD and worktree and the
actual pins were genuine adds (`--diff-filter=A`), so this is not a live gap.

### 4.6 Conclusion on the difficult point

The count-based check is **not weaker** than a concrete later content-anchor plus zero-diff window for the property
the contract needs: (a) the current window is verifiably linear so the count is exact; (b) I independently ran the
stronger content-anchor method and it agrees for all 7 pins; (c) simplification is content-faithful for the
absent→present(digest) property, so the equivalence survives merges; and (d) the evidence content is *always*
independently `sha256`-pinned at HEAD and worktree, so the count check is a provenance signal layered on top of
content integrity, never the sole content guarantee. **The reviewer's NO-GO conditional ("if it is weaker") is not
triggered.**

## 5. Fail-closed verification (independently driven, all reject with correct codes)

| Case | Result | Code |
| --- | --- | --- |
| real packet (control) | `verified` | — |
| live ancestry failure (`anchor_is_ancestor_of_head=false`) | `rejected` | `tampering` |
| source overlap (anchored path touched, `count=1`) | `rejected` | `tampering` |
| derived re-modification (`count=2`) | `rejected` | `tampering` |
| malformed observed head (`"not-a-sha"`) | `rejected` | `malformed_hex` |
| `head_pinned=true` | `rejected` | `tampering` |
| `baseline_ancestor` tampered | `rejected` | `tampering` |
| `g6_acceptance=true` | `rejected` | `g6_or_physical_acceptance_claim` |

The shipped suite additionally covers wrong case/stage, non-diagonal Selector2, solve-form mismatch, missing/extra
pins, unknown option keys, a fourth option, unknown top-level key, B1 approval, B4 freeze, owner-choice, and
acceptance-flag flips — all `rejected`.

## 6. Change confinement and decision-semantic preservation

A JSON-level diff of the pre-repair packet (`HEAD` blob `5086c3fb…`) against the post-repair worktree packet
(`bc8302e9…`) shows the **only** changed top-level key is `observed_at`:

- removed: `baseline_ancestor_is_ancestor_of_head`, `ancestor_check_exit` (the old exact-ancestry snapshot fields)
- added: `head_role="runtime_diagnostics_only"`, `head_pinned=false`, `anchor_required_ancestor_of_head=true`,
  `evidence_stability_window="baseline_ancestor..HEAD"`
- unchanged values: `head`, `branch`, `baseline_ancestor`, `origin_main`, `recorded_utc`

Everything else is byte-identical in meaning: `fail_closed_on` (12 codes), `require_tracked_at_head`, all 7 pins and
their shas, `owner_options` (exactly three, none chosen), `owner_decision` (`not_made`, `chosen_option=null`),
`b1_b4_effects` (`B1=unapproved`, `B4=unfrozen`, `chosen_for_owner=false`), and the acceptance flags
(`g6_acceptance=false`, `physical_accuracy=false`, `effective=false`, `issues_closed=false`,
`r1_status="numerical_failed"`). **The solve-form owner-decision meaning is unchanged and the existing closed code
set is preserved.** Independent grep finds no `G6/Full 已通过`, `宣称 G6 通过`, or any `*_acceptance=true` in the
markdown, and the required `g6_acceptance=false` / `physical_accuracy=false` / `不是数值验收或 G6 通过` markers are
present. **No G6/physical/#84/Full acceptance is claimed.**

## 7. Immutable recheck evidence — handled honestly

`recheck.json` is itself pinned (worktree sha256 `ba140e42…` == its HEAD blob; single intro commit `6eafdf9`,
count 1, never modified). The suite treats its **stale** fields as historical record, not as live fact:

- `checkout.head=768526a…`, `packet_sha256=5086c3fb…`, `markdown_sha256=ada0a77a…`, `test_sha256=21ea73e2…` are the
  *pre-repair* values. The suite validates the recorded head **only for shape** (`_full_sha`) and **never** asserts it
  equals the live HEAD, and never asserts the self-hashes equal the live files. (Confirmed: HEAD blobs of the three
  owned files == these recorded self-hashes, i.e. they are exactly the committed pre-repair state.)
- The suite cross-checks **live** only the fields that are genuinely unchanged by the repair: `source_pins`
  (reference/mrdivide/diagonal) and `recomputed_outputs` (the three derived pins) against the current packet — these
  evidence shas did not change, so the live cross-check is legitimate.

No stale self-hash or checkout-head claim is accepted as live. ✔

## 8. Test execution (both modes), real index/HEAD proven untouched

- **Normal**: `python -B -m unittest validation.test_e0_g6_solve_form_decision` → **Ran 36 tests, OK (skipped=2)**
  (the two `exact3` tests skip when not in staged mode). HEAD and real `.git/index` byte-identical before/after.
- **Repo-external `GIT_INDEX_FILE` (exact3)**: staged exactly the three candidates into an empty external index
  (`/tmp/.../exact3-index`). Proven: staged set == exactly the three paths; each staged blob sha256 == worktree bytes;
  `git status` shows them as the only staged entries. Suite → **Ran 36 tests, OK (0 skipped)**. Real HEAD and real
  `.git/index` byte-identical before/after. (The `git add` wrote only the external index; blob objects added to
  `.git/objects` are content-addressed and touch no ref, no real index, no worktree.)
- Real index `cf249890d18567a9f62173ff1e8ac717362fe531ecea02a545a72ee185319a32` and HEAD `0b10f786…` were **constant**
  across both runs and the whole review. Candidate hashes/sizes recomputed at the end with **no drift**.

## 9. Observations (non-blocking)

- **Hardening option, not a defect.** The count check would be marginally more direct and unconditionally
  merge-immune if `_check_evidence_stability` also content-anchored each derived pin at its `--diff-filter=A` commit
  and asserted `git diff --quiet intro..HEAD -- path` (and, for source pins, `git diff --quiet f333316..HEAD -- path`).
  This is defense-in-depth only: the current window is linear, I verified the stronger method agrees, and the evidence
  content is independently `sha256`-pinned regardless. Not required for GO.
- The suite intentionally requires `observed_at.head != live HEAD` (a regression guard proving the recorded head is a
  historical observation). Running the suite from a checkout exactly at `768526a…` would fail that assertion; this is
  documented behaviour, not a soundness issue.

## 10. Non-claims of this review

This review does **not** accept G6, Full, #84, or physical accuracy; does not approve any B1 budget; does not freeze
B4; does not choose or endorse any owner option; does not close #59. It assesses only that the stable-evidence repair
correctly and honestly implements its stated contract and preserves every non-acceptance and owner-decision boundary.
