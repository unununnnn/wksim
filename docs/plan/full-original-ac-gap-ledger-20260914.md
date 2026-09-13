# Full 原始验收标准缺口账本（只读快照）

- 切片：`deepseek-full-ac-gap-ledger-20260914-01`
- 冻结 HEAD：`6eafdf9c0b734db07a9fe790c86b409d3468c10b`（`main`）；仓库：`unununnnn/wksim`
- 生成时间：2026-09-14T04:15:00+09:00
- 机器可读账本：`validation/full-original-ac-gap-ledger-20260914.json`
- 快照（测试时唯一输入）：`validation/full-original-ac-gap-ledger-snapshot-20260914.json`（SHA-256 `c8af0dcef3dfc3a78141d381a9cb307fc5a0a223cc9c2898a5a34fd0ffae1ef4`；与咨询抓取字节相同，但不依赖被 gitignore 的 coordination 目录）
- 离线校验：`validation/test_full_original_ac_gap_ledger.py`（仅读上述快照；无网络、无 gh、无原生/模型/MATLAB/ROS/DDS/SITL/FC/UE/构建/飞行，#83 未重跑）

**结论：`Full = not-closed`。本切片不宣称任何验收通过，不关闭、不重开、不评论任何 issue。**

本账本只陈述一件事：以当前 GitHub issue 正文为唯一事实来源，逐条列出 #11–#48 的原始验收标准，
以及每条标准当前的勾选状态。勾选状态是 issue 正文里的写作者记账，是本账本**关于账本**的证据，
不是能力证明。**已关闭（CLOSED）不等于原始 AC 已满足。**

## 1. 新鲜度与命令

抓取只使用只读 `gh` 调用，未使用任何写动词：

```
gh issue list --repo unununnnn/wksim --state all --limit 400 --json number,state,title,url,updatedAt
gh issue list --repo unununnnn/wksim --state all --limit 400 --json number,state,title,url,updatedAt,body
```

| 原始抓取文件 | SHA-256 |
| --- | --- |
| `raw_gh_issue_index.json` | `b02b5e9de36e4acd4aa37af9621eed9f26315d52b9e60d30a522075bc59d68e2` |
| `raw_gh_issue_bodies.json` | `f9e5ef37705fd1ea8c3e968b4b0ecef419c45bd8f3b14117b6b5eccf87c71e54` |

抓取返回 163 个 issue（全仓库、未过滤）；本切片取 #11–#48 共 38 个，其正文写入快照。
正文编码 `utf-8-no-bom`；正文摘要按 API 返回的原始正文字节序列计算（不做换行或空白归一化），因此正文任意改动都会改变摘要。

## 2. 冻结总量（独立复算，不沿用任何既有前沿）

| 量 | 值 |
| --- | --- |
| issues（#11–#48） | 38 |
| issue 编号和 | 1121 |
| CLOSED / OPEN | 30 / 8 |
| 解析到的原始 checkbox | **255**（勾选 40） |
| 原始 AC（验收标准节内） | **190** |
| 已勾选 AC | 40 |
| 未勾选 AC | **150** |
| 验收标准节外的 checkbox（子票容器块） | 65 |
| 零 checkbox 的 issue | 0（无） |
| CLOSED 且仍有未勾选 AC | 22 |
| OPEN 且仍有未勾选 AC | 8 |
| 歧义/格式问题 | 0 |

### 2.1 与既有咨询前沿（advisory）的差异，必须显式记录

`validation/coordination/deepseek-full-frontier-refresh-20260914-02/` 是**未提交的咨询材料**，
它把 255 个 checkbox 全部当作 original AC rows（40 已勾选 / 215 未勾选）。
本次独立解析发现：其中 65 个 checkbox 位于**任何 `## Acceptance criteria` 节之外**，
它们是正文顶部的子票容器块（`<!-- lunar-container:v1 -->` … `<!-- /lunar-container:v1 -->`），
内容是“从下列子票执行”的清单，不是本票的验收标准。

因此本账本给出两个数并都给证据：

- **原始 checkbox = 255**（可复核，与咨询前沿一致）；
- **原始 AC = 190**（验收标准节内），**未勾选 AC = 150**。

这 65 个节外 checkbox 全部逐条记录在账本 `ambiguity.non_acceptance_checkboxes`（issue、行号、原文、勾选状态、原因），既不丢失也不冒充 AC。
受影响 issue：#20、#25、#26、#27、#28、#29、#33、#35、#36、#37、#38、#39、#40、#44、#45、#46、#47。

## 3. 校验模型（失败即关闭）

- 每个 checkbox 记录 issue、ordinal、精确归一化文本、勾选状态、来源正文 SHA-256、行号、缩进；
- **AC id 规范**：`{issue}:{k}`，`k` 为该 issue **验收标准节内**第 k 条（1 起），不是该 issue 全部原始 checkbox 的全局 ordinal；节外 checkbox 使用 `{issue}:x{ordinal}` 命名空间（此处 ordinal 才是正文全部 checkbox 的 1 起序号），永不进入 AC 集合；
- 归一化：CRLF/CR→LF、NFC、连续空白折叠为单空格、去首尾空白；另存归一化文本的 SHA-256；
- 离线校验用**两套独立表示**比对：手写字面量注册表（issue 状态、原始 checkbox 数、勾选数、正文摘要）与快照的结构化重解析（按标题分节的提取器 + 扁平 token 扫描），两者与账本三方必须一致；
- 校验必然失败的情形包括：checkbox 丢失/重复、正文摘要变化、总数/分项不一致、勾选状态被提升、凭空证据、issue 区间缺口、未知 schema 键、节外 checkbox 被提升为 AC。

## 4. 逐 issue 结果

| issue | 状态 | 原始 checkbox | 已勾选(原始) | AC | 已勾选 AC | 未勾选 AC | 节外 checkbox |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #11 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #12 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #13 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #14 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #15 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #16 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #17 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #18 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #19 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #20 | OPEN | 9 | 0 | 5 | 0 | 5 | 4 |
| #21 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #22 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #23 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #24 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #25 | CLOSED | 11 | 0 | 5 | 0 | 5 | 6 |
| #26 | OPEN | 8 | 0 | 5 | 0 | 5 | 3 |
| #27 | OPEN | 8 | 0 | 5 | 0 | 5 | 3 |
| #28 | OPEN | 8 | 0 | 5 | 0 | 5 | 3 |
| #29 | OPEN | 8 | 0 | 5 | 0 | 5 | 3 |
| #30 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #31 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #32 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #33 | OPEN | 8 | 0 | 5 | 0 | 5 | 3 |
| #34 | CLOSED | 5 | 5 | 5 | 5 | 0 | 0 |
| #35 | CLOSED | 11 | 0 | 5 | 0 | 5 | 6 |
| #36 | CLOSED | 9 | 0 | 5 | 0 | 5 | 4 |
| #37 | CLOSED | 9 | 0 | 5 | 0 | 5 | 4 |
| #38 | CLOSED | 8 | 0 | 5 | 0 | 5 | 3 |
| #39 | OPEN | 8 | 0 | 5 | 0 | 5 | 3 |
| #40 | CLOSED | 8 | 0 | 5 | 0 | 5 | 3 |
| #41 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #42 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #43 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| #44 | CLOSED | 9 | 0 | 5 | 0 | 5 | 4 |
| #45 | CLOSED | 10 | 0 | 5 | 0 | 5 | 5 |
| #46 | OPEN | 8 | 0 | 5 | 0 | 5 | 3 |
| #47 | CLOSED | 10 | 0 | 5 | 0 | 5 | 5 |
| #48 | CLOSED | 5 | 0 | 5 | 0 | 5 | 0 |
| **合计** |  | **255** | **40** | **190** | **40** | **150** | **65** |

每个 issue 至少有一个 checkbox；没有零 checkbox 的 issue，也没有缺失验收标准节的 issue。

## 5. 精确集合（无解释空间）

- **已勾选 AC（40）**：

  `11:1`、`11:2`、`11:3`、`11:4`、`11:5`、`12:1`、`12:2`、`12:3`、`12:4`、`12:5`、`15:1`、`15:2`、`15:3`、`15:4`、`15:5`、`16:1`、`16:2`、`16:3`、`16:4`、`16:5`、`17:1`、`17:2`、`17:3`、`17:4`、`17:5`、`23:1`、`23:2`、`23:3`、`23:4`、`23:5`、`24:1`、`24:2`、`24:3`、`24:4`、`24:5`、`34:1`、`34:2`、`34:3`、`34:4`、`34:5`

- **未勾选 AC（150）**：

  `13:1`、`13:2`、`13:3`、`13:4`、`13:5`、`14:1`、`14:2`、`14:3`、`14:4`、`14:5`、`18:1`、`18:2`、`18:3`、`18:4`、`18:5`、`19:1`、`19:2`、`19:3`、`19:4`、`19:5`、`20:1`、`20:2`、`20:3`、`20:4`、`20:5`、`21:1`、`21:2`、`21:3`、`21:4`、`21:5`、`22:1`、`22:2`、`22:3`、`22:4`、`22:5`、`25:1`、`25:2`、`25:3`、`25:4`、`25:5`、`26:1`、`26:2`、`26:3`、`26:4`、`26:5`、`27:1`、`27:2`、`27:3`、`27:4`、`27:5`、`28:1`、`28:2`、`28:3`、`28:4`、`28:5`、`29:1`、`29:2`、`29:3`、`29:4`、`29:5`、`30:1`、`30:2`、`30:3`、`30:4`、`30:5`、`31:1`、`31:2`、`31:3`、`31:4`、`31:5`、`32:1`、`32:2`、`32:3`、`32:4`、`32:5`、`33:1`、`33:2`、`33:3`、`33:4`、`33:5`、`35:1`、`35:2`、`35:3`、`35:4`、`35:5`、`36:1`、`36:2`、`36:3`、`36:4`、`36:5`、`37:1`、`37:2`、`37:3`、`37:4`、`37:5`、`38:1`、`38:2`、`38:3`、`38:4`、`38:5`、`39:1`、`39:2`、`39:3`、`39:4`、`39:5`、`40:1`、`40:2`、`40:3`、`40:4`、`40:5`、`41:1`、`41:2`、`41:3`、`41:4`、`41:5`、`42:1`、`42:2`、`42:3`、`42:4`、`42:5`、`43:1`、`43:2`、`43:3`、`43:4`、`43:5`、`44:1`、`44:2`、`44:3`、`44:4`、`44:5`、`45:1`、`45:2`、`45:3`、`45:4`、`45:5`、`46:1`、`46:2`、`46:3`、`46:4`、`46:5`、`47:1`、`47:2`、`47:3`、`47:4`、`47:5`、`48:1`、`48:2`、`48:3`、`48:4`、`48:5`

- **CLOSED 但仍有未勾选 AC（22）**：#13、#14、#18、#19、#21、#22、#25、#30、#31、#32、#35、#36、#37、#38、#40、#41、#42、#43、#44、#45、#47、#48
- **OPEN 且仍有未勾选 AC（8）**：#20、#26、#27、#28、#29、#33、#39、#46
- **CLOSED 且五条 AC 全勾选（8）**：#11、#12、#15、#16、#17、#23、#24、#34

注意：最后一组是“正文里全部打勾”，不是“证据已复核”。#17 的 AC1/AC2 正是打勾但之后代码路径发生漂移的两行：

- #17 AC1、AC2：the two ticked rows depend on the UE forwarded-frame identity, which changed after the evidence pin; a tick is bookkeeping, not current proof

**没有任何 issue 在本账本中被声明为 accepted、fulfilled 或 reopened。**

## 6. 排序后的下一步工作队列

队列由未勾选 AC 生成，分两类：**零原生（zero-native）**切片（只读/离线实现或复核，不碰原生、模型、MATLAB、ROS/DDS、SITL、FC、UE、构建与飞行）与**阻塞（blocked）**切片。
每行给出精确 AC id、本地来源证据与关闭规则；`未覆盖 AC` 明确列出该切片未覆盖但存在的未勾选 AC，避免“看起来做完了”。

| # | 切片 | 门 | 类别 | 引用 AC | 未覆盖 AC | 阻塞/主张 | 本地证据 | 关闭规则 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Q01 Commit the per-quantity error/dwell/recovery budget row for #33 AC5 | G3 | `blocked-owner-decision` | `33:5` | `33:1`、`33:2`、`33:3`、`33:4` | G3 mixed-axis/trajectory acceptance and the #84 promotion | `docs/plan/33-rate-timing-probe.md`<br>`docs/plan/tickets/23-mixed-trajectory.md`<br>`docs/plan/goal-objective.md` | an owner-signed budget row committed in docs/plan naming each quantity, its threshold and its dwell window |
| 2 | Q02 Isolation conflict preflight: deterministic offline units for #13 AC1 and AC4 | G1 | `zero-native-implementation` | `13:1`、`13:4` | `13:2`、`13:3`、`13:5` | G1 independent-run interference claims | `docs/plan/tickets/03-isolated-runs.md`<br>`validation/test_wksim_preflight.py`<br>`validation/test_task_identity.py` | validation test asserting rejection of each colliding identity field and asserting the joint-scene label is refused for independent runs |
| 3 | Q03 Offline generation/anchor rejection table for #14 AC2 and AC4 | G1 | `zero-native-implementation` | `14:2`、`14:4` | `14:1`、`14:3`、`14:5` | G1 stale-command rejection claims | `docs/plan/tickets/03-isolated-runs.md`<br>`validation/test_task_identity.py` | a rejection-table test covering old generation, duplicate id and late ACK with the recorded reason for each |
| 4 | Q04 Source-to-judgement matrix for #18 console entry rows | G1 | `blocked-native` | `18:1`、`18:2`、`18:3`、`18:4`、`18:5` | — | G1 console configuration-to-result entry | `docs/plan/tickets/08-wksim-run-workflow.md`<br>`docs/2026-09-08-console-ui-closure-report.md`<br>`validation/test_wksim_preflight.py` | one current-architecture console entry plus its committed receipt, then row-by-row re-tick authority |
| 5 | Q05 Pin joint-clock semantics offline for #19 AC1 and AC3 | G2 | `zero-native-verification` | `19:1`、`19:3` | `19:2`、`19:4`、`19:5` | G2 single authoritative clock claim | `docs/plan/tickets/09-joint-clock.md`<br>`docs/2026-09-06_joint-clock-ground-report.md` | an offline invariant check over the recorded clock/step evidence with a pinned digest, or an explicit record that the evidence cannot support it |
| 6 | Q06 Lock the pause/step/cold-reset strategy row for #20 AC1 | G2 | `blocked-owner-decision` | `20:1` | `20:2`、`20:3`、`20:4`、`20:5` | G2 pause/step/reset behaviour and the three 1x epochs | `docs/plan/tickets/10-joint-step-reset.md`<br>`docs/plan/20-rate-candidate-contract.md` | a committed strategy contract row naming the pause, step and cold-reset semantics the later observation will be judged against |
| 7 | Q07 Cold-reset generation and rate-recovery budget rows for #20 AC2 and AC4 | G2 | `blocked-native` | `20:2`、`20:4` | `20:1`、`20:3`、`20:5` | G2 cold reset and rate/recovery budget | `docs/plan/tickets/10-joint-step-reset.md`<br>`validation/lunar-20-epoch-1` | one joint pause/step/cold-reset observation with the generation and recovery-budget numbers recorded against the approved strategy |
| 8 | Q08 Joint-display source identity check for #21 AC1 and AC2 | G2 | `zero-native-verification` | `21:1`、`21:2` | `21:3`、`21:4`、`21:5` | G2 shared-scene display claim | `docs/plan/tickets/11-ue-joint-scene.md`<br>`validation/test_ue55_bridge.py` | an offline identity check binding the joint-display source to the contract, or a recorded statement that the current evidence cannot bind it |
| 9 | Q09 Recovery-sequence rule table for #22 AC2 and AC3 | G1 | `zero-native-implementation` | `22:2`、`22:3` | `22:1`、`22:4`、`22:5` | G1 airborne link-loss recovery semantics | `docs/plan/tickets/12-airborne-dds-loss.md`<br>`docs/2026-09-06_joint-dds-recovery-report.md` | an offline rule table reproducing the recorded recovery sequence with a pinned evidence digest |
| 10 | Q10 Hex per-millisecond input/clock checker rerun for #25 rows | G4 | `blocked-native` | `25:1`、`25:2`、`25:3`、`25:4`、`25:5` | — | G4 hexacopter configuration-to-run workflow | `docs/plan/tickets/15-hex-model-workflow.md`<br>`docs/2026-09-09-hex-flight-plan.md` | one hex dual-stack run with the per-ms input/clock checker recorded and each of the eleven rows mapped to that record |
| 11 | Q11 No-MATLAB cold rebuild closure run for #26 rows | G4 | `blocked-native` | `26:1`、`26:2`、`26:3`、`26:4`、`26:5` | — | G4 generated-model import without MATLAB | `docs/plan/26-closure-readiness-manifest.json`<br>`docs/plan/tickets/16-generated-model-import.md`<br>`docs/plan/26-current-source-ac-evidence-20260912.md` | one no-MATLAB cold rebuild whose recorded checklist satisfies the committed manifest rows |
| 12 | Q12 Legacy-ABI isolated host and sample lifecycle for #27 rows | G4 | `blocked-abi-vendor` | `27:1`、`27:2`、`27:3`、`27:4`、`27:5` | — | G4 legacy DLL lifecycle | `docs/plan/tickets/17-legacy-dll-host.md`<br>`docs/plan/9-vendor-abi-defer-boundary.md` | an owner ABI acceptance decision, then one isolated-host sample lifecycle |
| 13 | Q13 New-ABI extended-output adapter and sample for #28 rows | G4 | `blocked-native` | `28:1`、`28:2`、`28:3`、`28:4`、`28:5` | — | G4 modern DLL and extended output | `docs/plan/tickets/18-modern-dll-host.md`<br>`docs/plan/9-vendor-abi-defer-boundary.md` | one new-ABI sample with the extended output fields checked against the committed contract |
| 14 | Q14 Terrain/contact contract-vs-source recheck for #29 AC1 and AC2 | G3 | `zero-native-verification` | `29:1`、`29:2` | `29:3`、`29:4`、`29:5` | G3 terrain physical feedback | `docs/plan/29-contact-observer-contract.md`<br>`validation/test_contact_observer.py`<br>`validation/test_terrain_feedback.py` | an offline source-to-contract diff record stating, per row, whether the current entry still satisfies the pinned contract |
| 15 | Q15 RGB lifecycle loss/reconnect rules for #30 AC3 | G4 | `zero-native-implementation` | `30:3` | `30:1`、`30:2`、`30:4`、`30:5` | G4 camera stream lifecycle | `docs/2026-09-07-rgb-lifecycle-report.md`<br>`validation/test_rgb_consumer.py` | a consumer-side test proving stale generations are dropped and a reconnect is detected |
| 16 | Q16 Depth/cloud lifecycle rules for #31 AC3 | G4 | `zero-native-implementation` | `31:3` | `31:1`、`31:2`、`31:4`、`31:5` | G4 depth camera and point cloud lifecycle | `docs/2026-09-08-depth-lifecycle-closure-report.md`<br>`validation/test_depth_slice.py` | a lifecycle test covering cloud loss, reconnect and stale-generation rejection |
| 17 | Q17 Velocity/yaw output-trimming rules for #32 AC1 and AC2 | G3 | `zero-native-implementation` | `32:1`、`32:2` | `32:3`、`32:4`、`32:5` | G3 velocity/yaw control rows that #33 depends on | `docs/2026-09-08-c1-velocity-yaw-report.md`<br>`docs/plan/tickets/22-velocity-yaw.md` | a mapping test over the committed trimming rules including deadzone and hold behaviour |
| 18 | Q18 Promote the proved PV combination through the formal entry for #33 AC4 | G3 | `blocked-native` | `33:4` | `33:1`、`33:2`、`33:3`、`33:5` | G3 mixed-axis and trajectory acceptance | `docs/plan/33-rate-timing-probe.md`<br>`validation/lunar-20-epoch-1` | one formal-entry promotion run whose receipt carries the per-quantity numbers from Q01 |
| 19 | Q19 PID selector/result-visibility recheck for #35 rows | G3 | `zero-native-verification` | `35:1`、`35:2`、`35:3`、`35:4`、`35:5` | — | G3 PID controller closed loop | `docs/plan/tickets/25-pid-controller.md`<br>`docs/plan/35-product-selector-contract.md`<br>`validation/test_position_pid.py` | a selector/result-visibility check per row against the committed contract, with any live-flight row left explicitly open |
| 20 | Q20 UDE contract-vs-source recheck for #36 rows | G3 | `zero-native-verification` | `36:1`、`36:2`、`36:3`、`36:4`、`36:5` | — | G3 UDE controller closed loop | `docs/plan/36-ude-runtime-contract.md`<br>`validation/test_ude_runtime.py` | per-row contract/source agreement record, leaving flight rows open |
| 21 | Q21 NE contract-vs-source recheck for #37 rows | G3 | `zero-native-verification` | `37:1`、`37:2`、`37:3`、`37:4`、`37:5` | — | G3 NE controller closed loop | `docs/plan/37-ne-runtime-contract.md`<br>`validation/test_ne_runtime.py` | per-row contract/source agreement record, leaving flight rows open |
| 22 | Q22 RC deadzone/expiry/handoff rules for #38 AC2 and AC3 | G3 | `zero-native-implementation` | `38:2`、`38:3` | `38:1`、`38:4`、`38:5` | G3 RC authority handoff | `docs/plan/38-rc-contract.md`<br>`validation/test_rc_input.py` | an input-contract test covering deadzone, expiry and the explicit handoff transition |
| 23 | Q23 Real obstacle-avoidance chain run for #39 rows | G3 | `blocked-native` | `39:1`、`39:2`、`39:3`、`39:4`、`39:5` | — | G3 planner-to-flight acceptance and #102 | `docs/plan/39-planner-contract.md`<br>`docs/plan/tickets/23-mixed-trajectory.md` | one realised obstacle-avoidance chain run with arrival, clearance and rejection-policy outcomes recorded |
| 24 | Q24 ArUco tracking contract-vs-source recheck for #40 AC1 and AC2 | G4 | `zero-native-verification` | `40:1`、`40:2` | `40:3`、`40:4`、`40:5` | G4 camera tracking into public control | `docs/plan/40-aruco-run-contract.md`<br>`docs/2026-09-11-aruco-airborne-scene.md` | an offline binding record for the scene and calibration contracts |
| 25 | Q25 Real MATLAB client config.save and licence record for #41 AC4 | G5 | `blocked-matlab` | `41:4` | `41:1`、`41:2`、`41:3`、`41:5` | G5 MATLAB optional interface | `docs/matlab-bridge.md`<br>`docs/plan/tickets/31-matlab-bridge.md`<br>`validation/test_wksim_matlab.py` | a real MATLAB client run performing config.save with the version and licence result recorded, or an explicit licence-blocked record |
| 26 | Q26 GCS handoff stop-emitting rule for #42 AC3 | G1 | `zero-native-implementation` | `42:3` | `42:1`、`42:2`、`42:4`、`42:5` | G1 GCS view and control handoff | `docs/2026-09-09-gcs-handoff-closure-report.md`<br>`validation/test_gcs_human_handoff.py` | a handoff-state test proving emission stops after the mode change |
| 27 | Q27 Parameter recovery rules for #43 AC3 and AC4 | G1 | `zero-native-implementation` | `43:3`、`43:4` | `43:1`、`43:2`、`43:5` | G1 parameter operations and controller restart recovery | `docs/2026-09-08-parameter-maintenance-workflow.md`<br>`validation/test_wksim_parameter_maintenance.py`<br>`validation/test_wksim_runtime_parameter_storage.py` | a recovery-path test covering self-created-only restart and explicit takeover |
| 28 | Q28 Motor-efficiency fault and reset run for #44 rows | G4 | `blocked-native` | `44:1`、`44:2`、`44:3`、`44:4`、`44:5` | — | G4 fault injection acceptance | `docs/plan/44-motor-efficiency-contract.md`<br>`docs/2026-09-10-motor-efficiency-flight-report.md` | one fault-free baseline plus one fault run with the same seed and a reset check |
| 29 | Q29 GNSS interruption/recovery rows for #45 and #47 | G4 | `blocked-native` | `45:1`、`45:2`、`45:3`、`45:4`、`45:5`、`47:1`、`47:2`、`47:3`、`47:4`、`47:5` | — | G4 GNSS validity handling and global waypoint adaptation | `docs/plan/45-gnss-runbook.md`<br>`docs/2026-09-10-gnss-flight-report.md`<br>`docs/2026-09-10-global-flight-report.md` | one PX4 and one ArduCopter GNSS interruption/recovery run with the raw frame record |
| 30 | Q30 Cross-platform determinism budget and one recomputation run for #46 rows | G6 | `blocked-native` | `46:1`、`46:2`、`46:3`、`46:4`、`46:5` | — | G6 re-execution determinism | `docs/plan/46-reexecution-contract.md`<br>`validation/test_model_reexecution.py`<br>`validation/46-reexecution` | an approved determinism budget plus one recomputation run recording the bounded difference |
| 31 | Q31 Current-architecture product acceptance rerun for #48 rows | G1 | `blocked-native` | `48:1`、`48:2`、`48:3`、`48:4`、`48:5` | — | G1 exit ticket and the whole first-phase product claim | `docs/plan/tickets/38-sitl-product-acceptance.md`<br>`docs/2026-09-09-first-phase-acceptance-report.md`<br>`validation/test_wksim_product_bridge.py` | one black-box product entry run on the approved matrix with the command/FC-action/physics/display chain recorded |
| 32 | Q32 Drifted-row re-baseline for #17 AC1 and #17 AC2 | G1 | `zero-native-verification` | `17:1`、`17:2` | — | G1 UE state-source claim | `docs/plan/tickets/07-ue-product-stream.md`<br>`validation/test_wksim_product_bridge.py`<br>`validation/test_ue55_bridge.py` | an offline identity diff naming whether the ticked rows still hold, with the digest of the compared state source |

零原生切片 17 个，阻塞切片 15 个。
阻塞类别：`blocked-native`、`blocked-matlab`、`blocked-owner-decision`、`blocked-abi-vendor`。
这些切片**只被命名，未被执行**；本切片不运行原生、模型、MATLAB、ROS/DDS、SITL、FC、UE、构建或飞行路径。

## 7. 歧义与无法判定项（不隐藏）

- 格式错误的 checkbox 行：**0**（无）。
- 验收标准节外 checkbox：**65**，已逐条记录（见 2.1）。
- 非 checkbox 的列表方括号行（`## Blocked by` 链接清单）：**87**，已记录行号并明确排除出 AC 集合。
- 同一 issue 内文本完全相同的 AC：**0**（不影响 id 唯一性）。
- 空文本 checkbox 行：**0**（无）。
- 缺少验收标准节的 issue：**0**（无）。

## 8. 本地来源证据（冻结）

队列与被引用工作项都指向本仓库内的文件；账本 `inputs.local_evidence_pins` 记录每个受版本控制文件的
SHA-256 与 Git blob SHA-1（未跟踪文件 blob 记为 null）。这样“本地来源证据”本身可复核，不需要相信叙述。

## 9. 诚实限制

- Checkbox state is owner bookkeeping in the issue body; it is reported as evidence about the ledger and never as capability proof.
- Issue titles, states, updatedAt and bodies are a point-in-time read; any later edit is detected only by re-running the capture and comparing the recorded body digests.
- Parent issues #1 and #10 and every ticket outside #11-#48 are out of scope because they carry no per-AC checkbox rows.
- No native, model, MATLAB, ROS/DDS, SITL, flight-controller, UE, build or flight path and no #83 rerun is included; blocked queue rows are named, not executed.
- docs/agents/issue-tracker.md and CONTEXT-MAP.md do not exist in this checkout, so no tracker convention could be inherited; the absence is recorded rather than invented.
- 未读到的强制文档：`docs/agents/issue-tracker.md`、`CONTEXT-MAP.md` 在本检出中**不存在**（工作区与 HEAD 均无）；本切片记录其缺失，不用臆造约定替代。
- `validation/coordination/deepseek-full-frontier-refresh-20260914-02/**` 为未提交咨询材料，本切片只把它当作**被复核对象**，不作为提交证据引用。
- 原始 DeepSeek 抓取目录 `validation/coordination/deepseek-full-ac-gap-ledger-20260914-01/` 只作咨询溯源，校验器与账本运行时不读取它。
- `validation/gcs-handoff-20260909`、`validation/rgb-lifecycle-20260907-run1`、`validation/depth-lifecycle-20260908-run1` 被 gitignore 且未跟踪，已从 `cited_sources` 移除。Q15 / Q16 / Q26 仍用已提交的报告与 `validation/test_*.py`，分类保持 zero-native。

## 10. 非主张

- This ledger is evidence about the issue bodies, not proof of the underlying capability.
- Closed issue state is never equated with fulfilled original AC.
- No issue is declared accepted, fulfilled, reopened or closed by this slice.

`Full = not-closed`；G0–G6 全部 `not-closed`。
