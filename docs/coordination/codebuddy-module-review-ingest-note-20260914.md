# CodeBuddy module-review-20260912 历史语境绑定与折叠登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时权威 HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`；架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 经 `git merge-base --is-ancestor` 验证为当前 HEAD 祖先（exit 0）。

## 0. 本文件的地位

本文件只做两件事：把下述模块复核快照**按字节绑定**为历史语境，并登记其五项缺陷发现（D1–D5）在当前树上的折叠/活性状态。它自身不构成任何验收、批准、收口或复核记录；被绑定文件同样不构成这些。绑定只说明"2026-09-12 复核时刻观察到了什么"；一切当前判定由当前权威（主会话/人类裁决）基于当下工件重新作出。本文件为纯只读复核产物：未修改被绑定文件或任何既有文件；未运行 native/构建/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行；未重跑 #83；未提交 Git；未查询/改动 GitHub；未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`、`rolling-six-plan`、`claude-native-wait-next-probe`、`validation/_probe_delivery_contract.py`）。

## 1. 历史语境绑定（字节级，写作 HEAD 现场重算）

| 项 | 值 |
| --- | --- |
| 被绑定文件 | `docs/coordination/codebuddy-module-review-20260912.md` |
| SHA256 / 大小 | `7fd97029dfd4c0a8f301badfdc3abadb02a097b184c9908a07aa9f85e6f2e2db` / 7544 bytes |
| 性质 | CodeBuddy 模块稳定交付复核快照（2026-09-12，复核时刻 21:42–22:08 JST），只读、历史语境（historical context only）、非权威 |

## 2. D1–D5 当前树折叠/活性分类（2026-09-14 于 HEAD `31e5b65f` 现场复核）

### 2.1 D1（audit_pv_trajectory 错误引用）——已折叠

正确语义已进入 tracked `docs/coordination/ds-rate-budget-20260912.json`：其 `parser_coverage.structural_reason` 载明 "Correction to the first edition"，`tools/audit_pv_trajectory.py` 全文 **0 处** `rate_timing_probe`/`timing_probe` 检查，其 :297-299 循环检查的是 `pause_probe_requested`、`scene_lifecycle_requested`、`scene_lease_loss_requested`、`dds_loss_requested`、`diagnostic_land_step_period_s`。tracked `docs/plan/33-rate-next-diagnostic-20260912.md` 同步载明同一更正（"全文没有针对本诊断两个开关的字面检查…`audit_pv_trajectory.py` 全文 **0 处**"）。被绑定文件对 plan:5 原错误引用的批评由此被 tracked 锚吸收；plan 现文已是更正后语义（正式 mixed/PV 促进路径对 `rate_timing_probe` 直接 raise）。

### 2.2 D2（fail-closed 机制被夸大）——已折叠

tracked `docs/coordination/ds-rate-budget-20260912.json` 的 `parser_coverage.structural_reason` 载明：`tools/audit_joint_rate.py` 的 `timing_probe_identity()`（:32-42）仅对**缺失或不符的身份块** fail-closed；带正确密封身份的 `rate_timing_probe` 行通过校验后在 `schedule()`（:44-106，无该 kind 分支、无 else）被**静默忽略**；`tools/audit_pv_trajectory.py` 无 probe 检查；真正拒绝含 probe 证据进入正式 mixed/PV 促进路径的是 `Simulator/wksim_runtime/joint_profile.py` 的 marker 循环 `raise ValueError('Formal mixed/PV evidence cannot include '+marker)`，marker 元组含 `'rate_timing_probe'`，**当前树位于 :274-276**（2026-09-14 于 HEAD `31e5b65f` 现场复核）；tracked JSON 内保留的 `joint_profile.py:219-220` 引用系**历史读数**（2026-09-12 复核时点成立，当时 raise 位于 :220、守卫位于 :219），本登记不以行号为字节身份缝。

### 2.3 D3（两环境变量语义不实）——已折叠

tracked `docs/plan/33-rate-next-diagnostic-20260912.md`（命令模板的值域小节）载明两门值域不同：`WKSIM_JOINT_RATE_TIMING_PROBE` 只接受 unset/`0`/`1`，其余 raise；`WKSIM_JOINT_CPU_TIMING` 以 `os.environ.get(...)=='1'`（`Simulator/wksim_core/joint.py:54`）判定，任何非 `"1"` 值**静默关闭、不 raise**。tracked `docs/coordination/claude-native-input-timing.md` 同步载明 CPU-timing 启用条件沿用现有 `=='1'` 门、默认关闭。现场内容锚仍成立：`joint_rate_probe.py` 的三态 raise 文本与 `joint.py` 的 `=='1'` 谓词（测试以内容锚复核，不以行号为字节身份缝）。

### 2.4 D5（test_build_generated_e0 行数不实）——**仍是活性事实纠错（未折叠）**

tracked `docs/coordination/ds-26-host-recheck-20260912.json` 的 `plan_package.key_discovery.why_it_matters` **仍写**"已带 **782** 行测试"（现场定位在场）；而当前 `validation/test_build_generated_e0.py` 现场重算为 **886 行**（2026-09-14，HEAD `31e5b65f`，`wc -l` 现算；文件 tracked、工作树干净）。两数之差是**当前树上仍然存在的活性事实**。本收编批次**只记录该事实**：不修改 tracked D5 源（`ds-26-host-recheck-20260912.json`），不声称任何 closure/approval，不声称 #83 相关结论；782→886 的更正须由当前权威按自身流程处置，本登记不代办。

### 2.5 D4——未列收编范围

D4（`26-current-wrapper-recheck-plan.md:3` 的过期 HEAD 引用，原文已自带"执行时重新钉住"的再核对步骤 §4.1）不在本批登记范围；引用该文件时按其自带步骤处理。

## 3. 边界与不声称

- 被绑定文件是历史快照：其"无缺陷/可交付"等结论仅对 2026-09-12 复核时刻成立，不是当前状态。
- 本登记不声称：D5 已修复；任何工单（含 #83/#26/#9/#29/#62/#102）的验收、批准、收口、复核权限；诊断场结果可作 #83 证据。
- 不声称：折叠即"源文件缺陷声明失效"——源文件按字节保留原样，折叠只表示正确语义已进入 tracked 锚。
- 离线复检：`sha256sum` 被绑定文件 == §1 值；对 §2 各 tracked 锚做内容锚复核（不依赖行号作字节身份）；对 D5 现算 `wc -l`。任一失配表示树已漂移，应以当时权威工件重建登记。

## 4. 不声称清单（显式）

- 未修改 `docs/coordination/ds-26-host-recheck-20260912.json` 或任何 tracked 文件；
- 未把历史语境升格为验收/批准/关闭；
- 未重跑 #83 或任何诊断场/正式场；
- 未触碰受保护文件；未联网；未提交。

## 5. 独立审查 -01 与五项 P3 处置（本修订登记）

独立审查 `validation/coordination/codebuddy-module-review-independent-review-20260914-01/`（verdict PASS，P1=0/P2=0/P3=5）原样保留为证据，不因本修订改动。五项 P3 的处置映射（本修订 = note+test 的当前修订版）：

| ID | 原发现 | 处置 |
| --- | --- | --- |
| P3-1 | note §2.2 以现在时引用 `joint_profile.py:219-220` 为当前门 | **已修**：§2.2 改为当前内容锚（marker 循环 raise 文本，当前树 :274-276），并保留 219-220 系历史读数（2026-09-12 时点）的登记 |
| P3-2 | note §2.2 把 D2 更正归于 `parser_coverage.structural_reason` 与 `diagnostic_constraint`，后者并非顶层键 | **已修**：更正归属仅 `parser_coverage.structural_reason`（JSON 中 `diagnostic_constraint` 仅嵌套于 `next_minimal_diagnosis`，非更正载体） |
| P3-3 | 测试 :151 注释重复过期的现在时 219-220 引用 | **已修**：注释改写为"历史引用由 tracked JSON 保留；当前门 :274-276 以内容锚现场断言"并新增 live 内容锚测试 |
| P3-4 | 同义重复/同义反复的 mutation 测试（`test_missing_d2_gate_text_is_detected` 同义反复；行数负例断言平凡） | **已修**：mutation 负例统一经由与正例相同的生产式 helper（`d1_folding_ok`/`d2_folding_ok`/`count_lines`/`sha256_of_bytes`/`strict_load`）重跑断言，撤除同义反复测试 |
| P3-5 | 重复键 mutant 依赖替换首个 `{`，构造脆弱 | **已修**：重复键负例改为确定性最小构造 `{"schema": "a", "schema": "b"}`，经同一 `strict_load` 生产式加载器断言拒绝 |

处置不改变任何绑定、D5 782-vs-886 活性事实或非验收/历史边界；不声称 P3 "清零"仅陈述修正完成，最终判定归独立审查/当前权威。
