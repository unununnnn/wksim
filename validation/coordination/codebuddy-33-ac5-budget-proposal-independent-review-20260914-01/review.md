# Independent review — #33 AC5 Q01 decision-ready budget row proposal

- Reviewer: CodeBuddy (independent, read-only slice)
- Date: 2026-09-14
- Slice: `codebuddy-33-ac5-budget-proposal-independent-review-20260914-01`
- Review checkout: HEAD `acf322860831cb2a7c83a45cb4e2586922444c57` (2026-09-14 21:19:40 +0900, "Bind audit-matrix context offline"). Per the dispatch, no exact-HEAD requirement applies; the binding is ancestry from `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` (2026-09-14, "Bind mixed failure context offline") and `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` (2026-09-13, architecture-decoupling commit). Both verified as ancestors of HEAD via `git merge-base --is-ancestor` (exit 0) independently and again by the suite.

## 1. Scope

Exactly two candidates, bytes verified before review:

| File | SHA256 | Bytes |
| --- | --- | --- |
| docs/plan/33-ac5-budget-row-proposal-20260914.md | 998ed98cc668bc36e08acbc401f60e5aa50e356250cd9a82fa6cde5e5c3db5c0 | 5790 |
| validation/test_codebuddy_33_ac5_budget_proposal.py | 9f196f82e0fde227e9ceaae0d5407af5ebdfb195b7d54bc7f00b9269c57d581b | 14993 |

Context read: parent `AGENTS.md` + `CONTEXT-MAP.md`, `wksim/AGENTS.md`, `wksim/CONTEXT.md`. No wksim-local ADR directory exists; per the context map, sibling AeroTwinSim ADRs do not constrain wksim. All seven suite-pinned sources plus `docs/plan/33-rate-timing-probe.md` and the ledger Q01 row were read in full.

## 2. Byte and provenance verification

- Both candidate SHA256/size pins match on-disk bytes (`sha256sum` + `stat`), independently of the suite.
- All seven `SOURCE_ANCHORS` SHA256/size pins match on-disk bytes independently.
- Ledger Q01 row (docs/plan/full-original-ac-gap-ledger-20260914.md:147) matches the proposal §1 quotes verbatim: row title, gate `G3`, category `blocked-owner-decision`, AC `33:5`, and closure rule "an owner-signed budget row committed in docs/plan naming each quantity, its threshold and its dwell window".
- #23 AC5 text (docs/plan/tickets/23-mixed-trajectory.md:19) matches proposal §1 exactly.

## 3. Numeric verification

### 3.1 Frozen approved bounds (proposal §2) — all trace to owner-accepted records

| Proposal row | Source | Match |
| --- | --- | --- |
| 累计墙钟迟到 >100 ms latch `rate_unmet`/`resource_insufficient`, freeze at last complete barrier + revoke; late slides back only, no catch-up | 2026-09-07_joint-rate-contract-accepted.md:11-12 | exact |
| ±2% per non-overlapping 10 s window; ±1% per full 60 s valid segment | joint-rate-contract-accepted.md:14 | exact (contract wording "每个不重叠10s窗口"/"完整60s有效段" preserved) |
| dt = 1 ms, no tick skip, no sensor dilution | joint-rate-contract-accepted.md:10 | exact |
| 共同输入屏障 4 ms (strict four ticks per step); 0.5×/1× group periods 8 ms/4 ms | joint-rate-contract-accepted.md:10,13 | exact |
| 显式恢复就绪等待 5 s | 2026-09-06_joint-wall-supervision-accepted.md:12; joint-rate-contract-accepted.md:19 | exact |
| 故障不得以变速绕过恢复；恢复后须新任务请求 | joint-rate-contract-accepted.md:13 | exact |

### 3.2 Proposed carry-over rows (proposal §3) — five measured maxima are the true cross-report worst values

Sources: 2026-09-09-pv-flight-report.md table (lines 26-32) and 2026-09-13-final-combo-pv-pass.md table (lines 19-25).

| Quantity | Threshold / dwell | 09-09 report (AP1/2, PX4-1/2) | 09-13 report | Proposal max | Worst? |
| --- | --- | --- | --- | --- | --- |
| 轨迹位置误差 | ≤0.5 m, 每连续 12 s 轨迹段 | 0.07168/0.06586, **0.12668**/0.06124 | 0.120215 | 0.12668 m | yes (PX4 seg 1, 09-09) |
| 逐轴速度误差 | ≤0.3 m/s, 12 s | 0.02968/0.02444, **0.07790**/0.02772 | 0.076676 | 0.07790 m/s | yes (PX4 seg 1, 09-09) |
| yaw 角误差 | ≤0.15 rad, 12 s | 0.02174/0.00377, **0.03950**/0.01551 | 0.039097 | 0.03950 rad | yes (PX4 seg 1, 09-09) |
| 停止保持速度 | ≤0.25 m/s, 每连续 4 s 停止保持段 | 0.01188/0.01104, 0.03683/0.02138 | **0.040880** | 0.040880 m/s | yes (09-13) |
| 停止保持漂移 | ≤1 m, 4 s | 0.03608/0.04796, 0.08871/0.04750 | **0.091560** | 0.091560 m | yes (09-13) |

Attribution in §3 preamble is accurate: trajectory maxima come from the 09-09 report PX4 segment 1; stop-keep maxima come from the 09-13 report. Thresholds and dwell windows match the "固定门槛" column of the 09-09 report (各连续12s / 各连续4s) and the 09-13 gate recap. All five are below their thresholds; the proposal presents them as observations, not as acceptance of the true mixed-axis native submode — correct framing.

### 3.3 Owner-choice items (proposal §4) — all genuinely open, none pre-answered

- 0.4 m/s waypoint margin: appears **only** as unchecked §4 checkbox, never as a §3 threshold row. Source is a run-specific measure (2026-09-13-final-combo-pv-pass.md:31: "新任务仅以fresh估计速度≤0.4作为进入航点保持的余量，之后仍按原2秒与0.5门"). Correctly left to the owner.
- Acceleration feed-forward: matches #23 AC wording (23-mixed-trajectory.md:18); undecided — correct.
- Recovery reuse of §3 thresholds: 5 s recovery-ready semantics frozen (09-06 doc), reuse undecided — correct split.
- 3-epochs-per-tier requirement: exists in the frozen record (joint-rate-contract-accepted.md:14 "每档至少3个独立epoch"); whether it carries over is left unselected — correct.
- yaw-rate/native boundaries: 09-09 report line 18 ("两栈原生A/yaw-rate轴均失活") and 09-13 report line 35 ("加速度执行、yaw-rate、其它原生边界…不由本次结果代验") support the undecided framing.
- G6 per-quantity dynamics-equivalence budget: undecided — correct.
- All 7 §4 checkboxes and all 3 §8 checkboxes are `- [ ]`; no `- [x]`/`- [X]` anywhere (10 total checkboxes).

## 4. Status, scope-separation, and nonclosure

- Pending/unsigned state: header line 3 + per-row `PENDING OWNER DECISION` (6 occurrences) + §8 unsigned block with blank signature/date lines. Nothing in the document implies owner approval, Q01 closure, or `33:5` ticking.
- Control-integration vs G6 distinction (§5): accurate. The accepted record itself states the percentages/100 ms are wall-clock performance budget, not dynamics-equivalence error (joint-rate-contract-accepted.md:21); the proposal quotes this correctly and does not let §2/§3 values be read as a G6 budget.
- Frozen-record and probe exclusions (§6): probe fields `classification=diagnostic_only`, `production_performance=false`, and the no-masquerade rule match docs/plan/33-rate-timing-probe.md:53; "两项计时探针均关闭" in the 09-13 run matches 2026-09-13-final-combo-pv-pass.md:9. Preservation/non-re-judgment intent is correct (see finding P3-1 for a wording nuance).
- Nonclosure (§7): "不关闭 #33、#84、Q01、G6 或 Full", "Full = not-closed", G0–G6 all not-closed, and the #84 remainder ("同组合 mixed 能力证明、精确映射和真实正式入口验证") match 2026-09-13-final-combo-pv-pass.md:35. Consistent with the actual repo state (nothing closed by this file).

## 5. Test-suite review and execution

Suite quality: binds proposal bytes, seven anchor docs (SHA256+size+content), all values/units/windows, pending/unsigned state, nonclosure language, probe exclusion, and ancestry (no exact-HEAD pin; a guard test blocks reintroducing one). Mode design is sound: untracked mode asserts no index-touching git call; external-index mode validates only the repo-external index (exactly two candidates, mode 100644, stage 0, blob SHA1 == worktree bytes) and never reads the real index (`_git` strips `GIT_INDEX_FILE` except for the explicit extra-env `ls-files`).

Results (both run from `HEAD acf32286…`):

- Normal (`untracked`) mode: **Ran 17 tests — OK (skipped=1)**, exit 0. Skip is the external-index test, by design.
- External-index mode: temp index at a repo-external non-existent path, `GIT_INDEX_FILE=<tmp> git add -- <two candidates>` produced exactly 2 entries (`2a620fbc…` proposal, `236ecce3…` test, both 100644/stage 0); `WKSIM_33_BUDGET_TEST_MODE=external-index` run: **Ran 17 tests — OK (skipped=1)**, exit 0. Temp index deleted afterwards.
- Real-index proof: `.git/index` sha256 `be6979601355dca3af4d9ce9c65a7417c9da4f2425520e1923a179ed21e54e2f` and `git ls-files -s | sha256sum` `8294fe25d94468c51e69a7fa402fbe30c7b88a83be11e2f143a3268926b80045` are byte-identical before the first run and after the external run — the shared real index was never touched.
- Ancestry: both `31e5b65f…` and `f333316e…` are ancestors of the current HEAD (independently and via the suite).

## 6. Findings

### P3-1 — §6 parenthetical can be misread as a classification of the PV rounds (docs/plan/33-ac5-budget-row-proposal-20260914.md:57)

The sentence "既有 `RateUnmet` / `numerical_failed` 失败记录原样保留（含 docs/2026-09-09-pv-flight-report.md 第 01–04 轮失败样本、…冻结样本）" reads as if rounds 01–04 are `RateUnmet`/`numerical_failed` records. In the cited report, rounds 01–04 are preserved failure samples, but only round 04 is a wall-clock-overrun-class failure (111.68 ms > 100 ms); rounds 01–03 are a diagnostic crash, a ready timeout, and a numpy.float32 JSON-write failure, and the report does not label any of them with the `RateUnmet`/`numerical_failed` tokens. `numerical_failed` is the frozen R1 numerical-conformance status family (#23/G6 chain, e.g. docs/plan/10-g6-remediation-contract.md:7), which the parenthetical does not cite. The preservation/non-re-judgment claim itself is correct and no failure record is altered; this is a wording clarification only. Suggested edit: name round 04 as the wall-clock-overrun sample and cite the frozen R1 record explicitly for `numerical_failed`.

No P1 or P2 findings. All numeric values, units, dwell windows, provenance attributions, frozen boundaries, checkbox states, exclusions, and nonclosure claims verified as accurate.

## 7. Boundaries and hygiene

Read-only slice: no candidate or repo file edited, real index never staged, no commit/reset/clean/checkout/restore/push/ref changes, no network, no native/MATLAB/ROS/DDS/Unreal/SITL/flight/hardware/#83 runs. Only the three artifacts in this directory were created (`validation/coordination/` is gitignored via `.gitignore:53 /validation/*/`). Temp index removed; no other temp artifacts. Scoped `git status` deltas observed during the window belong to concurrent sibling sessions (unfamiliar untracked files left in place, untouched).

## 8. Verdict

**KEEP** — P1: 0, P2: 0, P3: 1 (P3-1 wording clarification; does not affect decision-readiness, pending state, or any numeric claim).

The proposal is decision-ready: it is explicitly a proposal, unsigned, non-closing, correctly scoped to control-integration budgets (not G6), with all five measured maxima verified as cross-report worst values and the 0.4 m/s waypoint margin correctly held as an unselected owner choice.
