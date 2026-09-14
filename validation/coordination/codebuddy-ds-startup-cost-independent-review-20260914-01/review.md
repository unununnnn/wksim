# Independent CodeBuddy review — DS startup-cost historical-context batch (2026-09-14)

Verdict: **PASS** (0 P1, 0 P2, 3 P3 non-blocking). Review performed read-only at
authoritative HEAD `011818876c1b94875fd67cedaaa73abfac866633`
("Bind OMP delivery diagnostic context offline"). I did not author any candidate.

## Scope (4 candidates, byte-verified)

| Path | SHA256 | Size |
|---|---|---|
| docs/coordination/ds-startup-cost-evidence-20260912.json | `675026ab4f13b1a61e44fa60a208483faa26a3b08794a30118a453103689e709` | 18778 |
| docs/coordination/ds-startup-cost-evidence-20260912.md | `a1df834b37241f7dc8fb2e1a9ec4407f330a05158e8e8b11f31ca6911800e2c4` | 17495 |
| docs/coordination/ds-startup-cost-evidence-ingest-note-20260914.md | `2ce0ac2d86999543eb4789f5a3502078dc441d93a678f6c1e755865c140c89a1` | 12417 |
| validation/test_ds_startup_cost_evidence_context.py | `b79ede1df0f59cafd0607c96f37c984649eb629a28e34513c51d27e483d06366` | 26826 |

All four are untracked in the worktree; neither protected file
(`docs/Prometheus.gitmodules.reference`, `validation/coordination/short-cycle-dispatches.json`)
is in scope.

## Independent verification performed

1. **Bytes and strict JSON.** All four hashes/sizes recomputed and match the task
   statement. The candidate JSON strict-parses (`wksim.ds-startup-cost-evidence.v2`,
   revision 2); `terminal_shas` = 5 source pins (after dropping the
   `analyze_joint_rate_intervals.py_role` annotation key) + 6 retained-raw pins = 11.
2. **11-of-11 consistency.** The MD 终态 SHA table matches the JSON pins 11/11
   (re-checked independently, including the annotated analyzer row).
3. **Arithmetic/trace/latch/phase-partition anchors** (note §2.1), re-verified
   against tracked artifacts:
   - `validation/33-rate-profile/diagnostic-triple-20260912/{ztdsk269,vwen35gc,7bdfxkb}.json`:
     groups 24146 / 21763 / 27434; creep 99687759 / 99636668 / 99717577;
     work_over 33372289 / 34868504 / 25703958; release_excess 66315470 / 64768164 /
     74013619. Exact identity creep − work_over = release_excess holds bitwise in
     all three. The candidate's ns values are nearest-1000-ns roundings of these
     (P3-4 qualifier accurate).
   - All three `trace_sha256` values equal the candidate's three retained-raw
     `rate.jsonl` pins, including `484016e7…ebea30fea…` for 7bdfxkb_.
   - `phase_partition`: early intervals 246 / 248 / 249 and
     groups_at_or_before_boundary 247 / 249 / 250 — exactly as the note and
     `ds-c1-actual-analysis-20260912.json` record.
   - c1 `terminal_latch_closure`: `recorded_latch_lateness_ns` 100129488,
     boundary tick 96624, `identity_sums_to_recorded: true`, `closure_holds: true`,
     `authoritative_source` labeled `analyzer c3ba9de8` (P3-1 reading applies).
   - The 6 retained-raw files are NOT present in this checkout (fe3 side); their
     bytes are not locally re-verifiable and are corroborated only via the tracked
     triple `trace_sha256` pins — the note declares exactly this (§4.4).
4. **Source pin resolution** (all recomputed):
   - `joint.py` current tree == `f5433c2e…` (introduced `d78d279d`); line anchors
     :32-67/:102-129/:143-149/:157-170/:197-199/:202-206/:215/:256-267 hold in the
     current tree.
   - `joint_rate.py` current tree == `0b53a16a…` (introduced `767bd659`);
     `begin_group` :89-130 structure (1 ms spin threshold, 2 ms sleep cap) holds.
   - `worker.py` pin `0becd1f3…` == blob at `acf81d56` (2026-09-11); current tree
     drifted at `1abf5f39` (2026-09-13); snapshot branch :88-92, tick-0/state-None
     :151-152, initial sidecar :238-245 verified on the pinned blob; current-tree
     anchors :93-96/:114/:249 verified in place.
   - analyzer pin `14ed9d64…` == blob at `e1c16314` (the expired fe3 private copy,
     as the candidate itself declares).
   - **runner pin `fd0b7ee6…` == content SHA256 of `tools/run_joint_flight.py` at
     commit `7cb7e8401776848fcb11e0a8dd2237c1eee2337b`** (branch
     `codex/planner-release-validation`, 2026-09-12 22:43:12 +0900, "Add opt-in
     manager GC freeze candidate with lifecycle and entry checks");
     `git merge-base --is-ancestor 7cb7e840 HEAD` exits 1 — the pin is outside
     main ancestry, exactly as the note's corrected registration states. Cited
     blob lines spot-checked: :296-305 request_graph_ready gate, :901-903
     snapshot=True request, :916-919 reanchor gate, :963-967 in-loop `import math`.
   - Current-tree runner anchors :959 (read-only snapshot request) and :975
     (reanchor gate) verified in place; current runner differs from the pin.
5. **Four P3 corrections in the note** — all verified accurate at their cited
   locations: P3-1 (phase_partition exists only from `75353c06` / content
   `1c43ac9c…`, not in the `c3ba9de8…` generation; triple outputs pin
   `analyzer_sha256 1c43ac9c…`; c1 file carries the same stale label), P3-2
   (worker.py:182-193 attribution actually sits in `joint.py:189-193` current
   tree — request-dict rebuild at :184/:189 and the 120-element
   `list(response['state'])` copy at :193; `worker.py:228-236` correct on the
   `acf81d56` blob), P3-3 (MD :75 "24147 组" is a typo; header and tracked truth
   are 24146), P3-4 (nearest-1000-ns rounding; 100129000 vs 100129488, 488 ns
   < 500).
6. **Continuity-snapshot semantics.** `precommit-state.json` and
   `pre-main-switch-state.json` are untracked (0 tracked files in
   `validation/architecture-decoupling-20260912/`), both record the two candidate
   hashes by bytes, and the note correctly scopes them as byte-stability
   attestations only ("只证明字节稳定，不证明内容正确"), never tracked anchors.
7. **C2 / current performance unresolved.** The note does not adjudicate C2
   ("C2 处置状态仍未解决", "不声称其已完成或已放弃") and keeps all six unexcluded
   items open on the current tree; the candidates themselves claim no fix and no
   exclusive attribution.
8. **Boundaries.** Historical-context-only / non-authority wording, barrier
   preservation (`.5×/100ms/1ms`, in-run monotonic timing, identity and physics
   gates fail-closed, diagnostic-trace fail-closed), historical identities only,
   historical failures as recorded history, no #83 rerun, no GitHub query/mutation,
   protected files untouched — all present in the note (:7, :19, :56-65, :71, :73,
   :80-82) and asserted by the test's phrase pins.
9. **Mutation coverage.** `TestNegativeMutations` performs hash-drift, size-drift,
   duplicate-key/NaN/overflow, 11-of-11 break, arithmetic-mutation and
   phrase-elision rejections in memory only; no file is modified by the suite.
10. **Tests.** `python -B -m unittest validation.test_ds_startup_cost_evidence_context -v`
    → **Ran 19 tests, OK, exit 0** at `01181887` (normal worktree). Re-run under a
    temporary `GIT_INDEX_FILE` with exactly the 4 candidates force-added (staged
    set diff-verified as exactly those 4) → **Ran 19 tests, OK, exit 0**. Real
    index SHA256 `c3f83d45432294559230eb32978dd7a4ca8b92be1b9a08bea25afffaf243cd3b`
    byte-for-byte unchanged across both runs; real staged-diff count 0; temporary
    index and its directory removed. The suite is staging-safe by construction
    (its `git ls-files` probes cover only tracked anchors unaffected by staging
    the 4 candidates).

## Findings

- **P3-A (this review): fresh-clone object availability of the runner pin.**
  `7cb7e840` is contained in no `refs/remotes` ref of this checkout (exhaustive
  scan). Origin branch `codex/planner-release-validation` exists (tip `90bb3e1d`,
  confirmed by one read-only `git ls-remote` query — no mutation) but does NOT
  contain `7cb7e840` (`git merge-base --is-ancestor 7cb7e840 90bb3e1d` exit 1,
  both objects local). A fresh clone therefore cannot resolve the runner pin or
  the note's §6 step-4 seam without out-of-band object transfer; the two runner
  tests take their documented skip path and the registration degrades to
  "stale, re-verify" exactly as the note's §6 closing line prescribes. No code
  change required; citation of the runner pin should carry this caveat.
- **P3-B (this review): malformed 63-character hash in an older tracked
  artifact.** `docs/coordination/ds-7bdfxkb-diagnostic-analysis.json` (tracked at
  `e8defc1d`) records its rate.jsonl input as a 63-character string
  (`…1761ebe30fea…`), while the analyzer-produced triple output and this
  candidate both pin the 64-character `484016e746bfad78ef5d46f0d85d19e1761ebea30fea2d22e63649ea57e07d0b`.
  The candidate is correct; the older tracked record is the defective one. Left
  for the current authority; not a defect of this batch.
- **P3-C (carry-forward, verified accurate):** the note's four registered P3
  corrections (P3-1 analyzer generation, P3-2 attribution site, P3-3 24147 typo,
  P3-4 rounding qualifier) must travel with any future citation of the bound
  snapshot, as the note itself requires.

## Boundaries asserted by this review

This review and the candidate batch assert no acceptance, approval, closure,
review or rerun permission for #83 (or #9/#26/#29/#62/#102 or any ticket); the
bound snapshot is historical context only; no native/build/MATLAB/ROS/DDS/SITL/
FC/UE/model/flight was executed; no file outside my own review directory was
created, edited, staged or committed; no GitHub state was mutated; protected
files were not touched.

Reviewed by: independent CodeBuddy evidence reviewer, 2026-09-14.
