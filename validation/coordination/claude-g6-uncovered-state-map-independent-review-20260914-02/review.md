# Independent re-review — remediated G6 36-state uncovered-state map (2026-09-14 candidates)

- Reviewer role: independent final re-reviewer (read-only on the four candidates; no staging to the real index, no commit, no push, no #83 run, no MATLAB/native/ROS/DDS/Unreal/SITL/flight/build, no candidate or protected-file modification). Solve-form and time-field manifest files are owned by other agents and were not read as review inputs nor touched.
- Review date: 2026-09-15 (candidates are dated 2026-09-14).
- Repo HEAD at review time: `0b10f786e808eebe7698e9a277766bf2f68a4d35` (branch `main`).
- Ancestry gates (live): `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0; `git merge-base --is-ancestor ee6eb88819cefe255f22e788c39a77c0bbab490e HEAD` → exit 0.
- Prior review: `validation/coordination/claude-g6-uncovered-state-map-independent-review-20260914-01/` (verdict REWORK; F1 P1 blocker, F2–F4 P2, F5–F6 P3). This re-review checks the remediated candidates against that finding set.

## 1. Candidate identity (verified before review)

| File | Expected SHA256 | Observed | Size exp/obs | Status |
|---|---|---|---|---|
| `tools/map_g6_uncovered_states.py` | `d204fcd3563599bc1afb50f15a49636ca17a6cbb5544261428e6f6df863513a0` | same | 65196 / 65196 | MATCH |
| `validation/g6-uncovered-state-map-20260914.json` | `19fc85f32c040218896e6d3a3785074f6e782756b00849d519bcb68bf61cb468` | same | 99845 / 99845 | MATCH |
| `validation/test_map_g6_uncovered_states.py` | `955fbfa742119c172f067e9f93164e8c1d9f0499dc5d14d9e54ab105807389f1` | same | 40622 / 40622 | MATCH |
| `docs/plan/59-g6-uncovered-state-map-20260914.md` | `67beeb7c12daa43cfb948667801de17dd8041e32901081d202c12ff3b2264297` | same | 8074 / 8074 | MATCH |

Command: `sha256sum` + `stat`. All four untracked (`git status --porcelain` → `??`). None edited. These hashes differ from the prior review's set, confirming the candidates were remediated.

## 2. Sources read

`AGENTS.md`, `../AGENTS.md`, `../CONTEXT-MAP.md`, `CONTEXT.md`, `docs/coordination/short-cycle-goal.md`, `docs/coordination/module-delivery-policy-20260912.md`, the prior `-01` review, the four candidates, and the pinned tracked evidence re-read directly: `validation/coordination/g6-target-first-step-20260913/{first-step-trace.jsonl,comparison-v2.json}`, `docs/coordination/g6-pqr-derivative-path-20260913.md` (lines 16/18/28/36), and the builder `tools/build_first_step_trace.py` (`STATE_LAYOUT`, `MRDIVIDE_CTX`).

## 3. Prior-blocker closure (F1–F4 required; F5–F6 rechecked)

### F1 (was P1 blocker) — `output_encoding.hex_stage2` — **CLOSED**
Committed `index_map[11].output_encoding.hex_stage2 = ["3c47b1ebce4a1e30","bc56d4db33a987b9","36f8ccceed35d6fd"]` — exactly the p/q/r triple required. **Independently re-derived from the pinned trace**: `first-step-trace.jsonl` stage-2 (`ode4_stage`, stage 2) `deriv_hex` has length 36 and `deriv_hex[10:13] = ['3c47b1ebce4a1e30','bc56d4db33a987b9','36f8ccceed35d6fd']`. The three values now match the trace byte-for-byte. The false "comparator-checked" claim is gone: the note reads "the three stage-2 derivative bytes are transcribed from the pinned target trace deriv[10..12] … recorded as encoding, with no physical interpretation". No comparator-checked assertion remains.

### F2 (was P2) — stale/unenforced `head` + red suite — **CLOSED**
The self-defeating recorded-`head` model is gone. The document now pins a frozen `anchor = ee6eb888…` plus `base_ancestor = f333316…`, carries **no `head` key**, and records `anchor_policy.observed_head_embedded = false`. HEAD is observational only:
- Live-verified: anchor is an ancestor of HEAD (exit 0), and `git diff --name-only ee6eb888… HEAD -- <the 10 evidence pins>` is **empty** (zero drift), re-run independently here.
- The current HEAD literal `0b10f786…` does **not** appear anywhere in the map JSON (`grep -c` → 0).
- The suite is green in both modes (was red before): the old head-drift test is replaced by `test_anchor_and_ancestors_are_recorded_and_verified`, which asserts ancestry, zero drift, no `head` key, and that validate() itself flags no `anchor_not_ancestor`/`evidence_drift`.
- Fail-closed confirmed by independent monkeypatch of `_git_text` (not the shipped tests): **non-ancestor** (merge-base rc=1) → `anchor_not_ancestor`; **unavailable probe** (git unlaunchable) → `anchor_not_ancestor` + `evidence_drift_unverifiable` (plus `base_ancestor_not_ancestor`, `pin_tracked_flag_mismatch`); **overlap / pinned-evidence drift** (diff returns a pinned path) → `evidence_drift`. All fail closed.

### F3 (was P2) — validation blind spots on evidence fields — **CLOSED**
`validate()` now binds the previously-blind fields, and each delete/corrupt mutation fails closed. Verified with an **independent reviewer-authored harness** (own mutations, `validate()` called directly — not the shipped tests):

| Mutation | Resulting code(s) |
|---|---|
| delete `output_encoding.hex_stage2` | `output_encoding_hex_value` |
| corrupt `hex_stage2` → deadbeef×3 | `output_encoding_hex_value` + `output_encoding_hex_mismatch` (trace-bound) |
| delete `output_encoding` | `output_encoding_missing` |
| delete `mrdivide_output_evidence` | `mrdivide_output_evidence_missing` |
| corrupt `mrdivide_output_evidence` (ulp / target hex) | `mrdivide_output_evidence_content` / `_hex` |
| corrupt top-level `line_bindings[0].text` | `line_bindings_mismatch` |
| drop one top-level `line_bindings` entry | `line_bindings_keys_mismatch` + `_mismatch` |
| delete top-level `line_bindings` key | `missing_key` |
| corrupt `doc_refs[0].sha256` | `doc_refs_mismatch` |
| delete `doc_refs` key | `missing_key` |

Baseline (unmutated) returns `ok:true, codes:[]`. `hex_stage2` is bound two ways — against the recorded constant **and** against a live re-read of the pinned trace (`_trace_stage2`), so the F1 class of error is now caught.

### F4 (was P2) — symbol-conflict mis-scoped / mischaracterized — **CLOSED**
- `symbol_conflicts[0].scope = "indices 19..35"` and `unresolved.transferfcn_motor_symbol_order.scope = "indices 19..35"` — exactly the required scope.
- Indices **19..24 are no longer "resolved TransferFcn"**: every index 19..35 records `symbol_resolution = "conflicted_requires_archive_input"` (full sweep: 0..18 all `resolved`, 19..35 all `conflicted`; no index misclassified). The `block_symbol` for 19..24 is shown as `IntegratorSecondOrderLimited__n` with `symbol_evidence = "tracked_builder_state_layout_plus_requirement_text"`, i.e. the builder attribution is surfaced but its ownership is declared conflicted, not resolved.
- The disagreement is exposed as the real **builder STATE_LAYOUT vs requirement-text** boundary conflict: `observed_a` = builder puts `IntegratorSecondOrderLimited__n` at 19..24 / `TransferFcn4/1/2_CSTATE` at 25..27; `observed_b` = requirement text `g6-pqr-derivative-path:36` assigns 19–27 to TransferFcn. Independently confirmed against `tools/build_first_step_trace.py STATE_LAYOUT` (19..24 `__n`, 25..27 TransferFcn, 28..35 Motor) and line 36 ("19–27(TransferFcn)、28–35(MotorNonlinearDynamic…)"). No residual "per-index order"/"逐索引顺序" mischaracterization in JSON or plan doc (grep → 0).

### F5 (was P3) — dead / mislabeled generator data — **CLOSED**
- `SYM_TABLE` is now 3-element `(lo, hi, symbol)` tuples; the dead 4th/5th (`source`, `exact_binding`) elements (including the copy-paste `SYM_INTN` on the 0..5 row) are removed.
- `first_step_mapping` renamed to **`first_step_timeline`** (a timeline, not a mapping); the committed `line_bindings` keys contain `first_step_timeline` and no `first_step_mapping`.
- Reference-probe wording no longer overclaims index ownership: the covered-range `symbol_note` attributes flat-index placement to `comparison-v2.json target_indices` and says only that the reference probe "registers listeners on the same named rigid-body integrators".

### F6 (was P3) — minor wording — **no new concern**
`entry_classes.mrdivide_output_indices = [10,11,12]` persists, but the generator comment and plan doc now frame it as the solve-result vector span (`Product2[0..2]`), with per-index output-encoding evidence attached only to index 11 and its note saying so explicitly. This is an honest characterization, not a per-index evidence overclaim; it is a validator-fixed constant. Not a blocker.

## 4. Totals & non-closure preserved (required)

`counts` = total 36, covered 13 (`6..18`), uncovered 23 (`0..5`, `19..35`), with `covered_indices`/`uncovered_indices` matching exactly; `entry_classes` residual/output indices `[10,11,12]`, `physical_semantics_inferred:false`. Non-closure intact: `open_items` = issue_84/g6/full all `open`; `r1_status = numerical_failed`; `g6_acceptance`/`physical_accuracy`/`issues_closed`/`budget_approved`/`effective` all `false`; `authority:none`; `pending_approvals:[]`. No budget or physical-accuracy acceptance is present.

## 5. Test execution (required)

Mode A — normal (untracked):
```
python -B -m unittest validation.test_map_g6_uncovered_states -v
→ Ran 27 tests: 26 ok, 1 skipped (exact4), OK
```

Mode B — repo-external temporary `GIT_INDEX_FILE` with exactly the four candidates force-added:
```
TMPD=$(mktemp -d); export GIT_INDEX_FILE="$TMPD/index"; git read-tree --empty
git add -f <four candidates>
python -B -m unittest validation.test_map_g6_uncovered_states
→ Ran 27 tests: 27 ok (exact4 ran, no skip), OK
```
Exact path/status/blob equality proven: the temp index held exactly 4 entries (mode `100644`, stage 0) and each staged blob SHA1 equals `git hash-object` of the on-disk file (`core.autocrlf=false`, no mangling):
- `docs/plan/59-g6-uncovered-state-map-20260914.md` `44b08f41b5e12da9c51bdef64c3e2df93411b485`
- `tools/map_g6_uncovered_states.py` `89c275458f30da81cad9d9abeabf42a97e059f56`
- `validation/g6-uncovered-state-map-20260914.json` `d6a2f68ed7476909a3c0b2a53aa655605bb6033b`
- `validation/test_map_g6_uncovered_states.py` `fff9293e3f8ef17557605eda4ac830997760e2f9`

Real index/HEAD preserved: real `.git/index` sha256 `cf249890d18567a9f62173ff1e8ac717362fe531ecea02a545a72ee185319a32` identical before and after both modes; HEAD `0b10f786…` unchanged; temp index removed.

## 6. CLI, determinism, drift (required)

- `python -B tools/map_g6_uncovered_states.py --repo-root . --validate` → `{"ok": true, "codes": [], "errors": []}`, exit 0.
- Deterministic regeneration: pure-Python `dumps(build_map('.'))` is **byte-identical** to the committed JSON (sha256 `19fc85f3…1cb468`, size 99845), LF-only with a single trailing LF.
- Candidate drift: all four hashes/sizes recomputed and match the pinned values (§1); the four files remain untracked and were not modified.
- Untracked provenance: `work/quad-parameters-source-review-20260909/Exp1_MinModelTemp.cpp` present on disk, sha256 `a35d7c8f…` matches `expected_sha256`, size 324922 — the recorded `available_on_disk:true` / `matches_expected:true` is truthful, and it never decides a coverage/class claim.

## 7. Verdict

**GO** — all four remediated candidates held together.

All prior blockers are closed: F1 (`hex_stage2` now matches the pinned trace and is trace-bound in the validator, no false comparator-checked claim), F2 (frozen-anchor provenance replaces the stale/self-defeating `head`; HEAD is observational only and non-ancestor/unavailable/overlap all fail closed; suite green in both modes), F3 (the evidence-field blind spots are now bound, proven by independent mutation), and F4 (conflict scope is exactly 19..35, indices 19..24 are conflicted rather than "resolved TransferFcn", and the builder-vs-requirement boundary disagreement is exposed). The F5 cleanup is honest and F6 raises no new concern. Totals (36/13/23) and the #84/G6/Full non-closure with `r1_status = numerical_failed` are preserved exactly, with no budget or physical-accuracy acceptance. Tests pass 26 ok + 1 skip in normal mode and 27 ok in exact4 mode; `--validate` is clean; regeneration is byte-identical; the real index/HEAD were never touched.

This review keeps #84, G6, and Full open and changes nothing about `r1_status = numerical_failed`.
