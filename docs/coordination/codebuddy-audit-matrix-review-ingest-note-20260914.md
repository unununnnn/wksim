# CodeBuddy 审计矩阵复核 历史语境绑定与漂移登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`。本文件写作时的**权威写作 HEAD**为 `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（"Bind mixed failure context offline"），且 `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 退出码 0（架构连续性锚成立）。本绑定在**恰好该 HEAD**现场完成，未依赖任何中间提交；被绑定文件为只读历史文档，与本节所列全部 tracked 锚点在写作现场逐字节重算一致。

## 0. 本文件的地位

本文件只做两件事：把下述历史复核文件**按字节绑定**为历史语境（historical context only），并登记其后的漂移/现状事实。它自身不构成 #83（或 #84/#9/#26/#29/#62/#102 或任何工单）的验收、批准、收口、复核或重跑许可，不构成任何当前 G0-G6/Full 门通过、native 结果或飞行证据；被绑定的历史文件同样**不再**构成这些。`#83` 已 CLOSED/PASS，**永不重跑**；`#84`、G6、Full 按当前 tracked 权威（`docs/coordination/short-cycle-goal.md`、`docs/coordination/module-delivery-policy-20260912.md`）仍**未完成**，本文件不改变这一点。一切"当前是否满足"的判定必须由当前权威基于**当下**的工件重新作出。本文件写作过程为纯只读复核：未启动任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行，未重跑 #83，除本文件与 `validation/test_codebuddy_audit_matrix_review_context.py` 外未创建、修改或删除任何文件，未暂存、未提交、未推送，未查询或改动 GitHub 状态，未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`、`docs/coordination/rolling-six-plan-20260912.md`、`docs/coordination/claude-native-wait-next-probe.md`、`validation/_probe_delivery_contract.py`）。

## 1. 历史语境绑定（字节级，在权威写作 HEAD `31e5b65f` 现场重算）

| 项 | 值 |
| --- | --- |
| 被绑定文件 | `docs/coordination/codebuddy-audit-matrix-review-20260912.md` |
| SHA256 | `fbb2568bea73167997ee62782fb71f1aba98dd54cd3e2f99108c591f41abcbf1` |
| 大小 | 5805 bytes |
| 自述日期 | 2026-09-12（CodeBuddy 独立复核：冻结发行审计器 + probe-run-02 一正四负矩阵，只读，两轮） |
| 当前 git 状态 | 写作时**未跟踪**（`??`）；本绑定不要求其保持未跟踪 |
| 性质 | **历史语境（historical context only）、非权威**。对 2026-09-12 冻结发行审计矩阵证据的只读复核记录 |

**非权威声明**：被绑定文件中的任何绑定复算结论、F1–F5 状态、boundary 判定或 "no finding" 记录，均**不是**当前的权威、批准、验收或收口状态，也不是审计器/探针工具的现行规范。引用它只能作为"2026-09-12 当时复核到了什么"，不能作为"现在是什么状态"或任何许可。

## 2. 本次复核验证的事实（全部现场重算，HEAD `31e5b65f`）

### 2.1 引用的审计工件目录：tracked 且逐字节在场

`validation/39-planner-flight/audit-matrix-20260912/` 为 **tracked** 目录，恰含 5 个文件，全部 `git ls-files --error-unmatch` 通过，SHA256/大小现场重算为：

| 文件 | SHA256 | bytes |
| --- | --- | --- |
| `main-verification.json` | `d4624624be96c67d173191fc0c2025832887701019d6d13d12df055f6c8953d7` | 785 |
| `probe-executed.py` | `92a83f4e593c1d399722a3dc57862da902b374872d475bc953131c6503d65815` | 41773 |
| `probe-report.json` | `4b21beca2a755992f3d76be514c32e5ea3f291a1695856d4de15c72f6f42c496` | 95429 |
| `auditor-executed.py` | `e8d33c5d6562f75cb3f3e5baacf33737af91281d646fefe0cc5db369d374177e` | 24691 |
| `probe.log` | `a3d164a011a5f19561211465d5fa2014e5db2e489c4af417108174280a075b07` | 1566 |

被绑定文件三条记录绑定**逐字复算成立**：`probe_sha256=92a83f4e…` ↔ `probe-executed.py`；`source_report_sha256=4b21beca…` ↔ `probe-report.json`；`auditor_sha256=e8d33c5d…` ↔ `auditor-executed.py`。`main-verification.json`（严格 JSON 解析通过、无重复键）记录 `status=pass`、`complete_matrix_pass=true`、`positive_count=1`、恰四项 `required_negatives`、`baseline_unchanged=true`、**`full_acceptance=false`**、scope 字面量含 "no new flight, no Full acceptance"；且该文件**自身无 self-hash 字段**（恰 11 个键，与被绑定文件 F1 残余备注一致）。

### 2.2 review 期冻结审计器的可恢复身份

review-time 冻结审计器 `e8d33c5d…` 与 tracked `auditor-executed.py` 逐字节一致，并恰等于 **`git show e897fb8e:tools/audit_planner_release.py`** 的 blob（`e897fb8e` = "Verify complete publication coverage and real corruption matrix"，2026-09-12 21:25:12，已验证为 HEAD 祖先）。当前 `tools/audit_planner_release.py` 已漂移（见 §4），历史身份由上述两条 tracked 途径完整承载。

### 2.3 run-02 数据锚（tracked 报告/日志内可核）

`probe-report.json`（严格 JSON 解析通过）记录：`kind="offline release-audit negative-case probe"`、`verdict="pass"`、恰 5 个 scenario（`positive_unmodified=accepted` + `ledger_command_gap`/`command_payload_tamper`/`ledger_tail_truncation`/`retained_source_change` 全 `rejected`）、`baseline.file_count=319` 且 `unchanged=true`、`auditor_sha256=e8d33c5d…`。`probe.log` 逐字含 "baseline files hashed: 319"、"audit inputs : 66 files (70 retained sources derived from manifests)"、四条负例各自的预期 `ValueError` 与正例 `accepted`。这些即被绑定文件"一正四负、baseline_unchanged=true (319 files)"主张的 tracked 证据。

### 2.4 F4 的源内容锚（tracked 现行源码，行号以现状为准）

- 生成侧：`Simulator/wksim_runtime/planner_transport_node.py` `def _publish_setup_envelope`（现 **449** 行）只以 `mode/stamp_ns/run_id/control_epoch/request_id` 调 `Simulator/wksim_runtime/trajectory_bridge.py` 的 `def build_ros_mode_request`（恰在现 **91** 行，行号引用精确成立），后者写 `setup.cmd = UAVSetup.SET_PX4_MODE`、`setup.px4_mode = mode`。
- 消费侧：`ros2/src/prometheus_control/prometheus_control/node.py` `elif msg.cmd == UAVSetup.SET_PX4_MODE:` 恰在现 **512** 行，分支内只读 `msg.px4_mode`，校验集恰为 `('POSCTL', 'AUTO.LOITER', 'AUTO.LAND', 'AUTO.RTL', 'BRAKE')`，`BRAKE` 要求 `self.native.external_mode == 'GUIDED'`，随后 `self.native.request('mode', msg.px4_mode)`；分支不读 `arming`/`control_state`/`header`。
- 身份门：`ros2/src/prometheus_control/prometheus_control/session.py` `def accept` 现在位于 **86** 行（被绑定文件写 "session.py:88–101"，行号漂移 −2，内容锚不变）：`unsupported_request_version`（version 整型且等 `self.VERSION`）、`wrong_run_or_control_epoch`（`run_id`+`control_epoch`）、`request_id_not_increasing`（单调 request_id）。
- helper 自身记录无 envelope：`validation/39-planner-flight/release-bomvjsmg/arducopter/planner-release/planner-release-handoff.json`（SHA256 `4f3e752e813c180b40e69da55ac58c058a998c5db043471be1336d65234f0ca1`，9497 bytes，tracked，严格 JSON 解析通过）恰含 16 键，含 `mode`/`expected_native_mode`/`adopted_request_high_water`/`verified_command_high_water`/`verified_request_high_water`，**无** `setup`/`envelope`/`cmd`/`px4_mode` 之外的 envelope 载荷键。

## 3. 发现状态辨析（历史 vs 现状，逐条）

- **F1/F2（历史 run-02 报告缺自证）**：被绑定文件记录"由外部锚 resolved"。本登记将其定性为**历史陈述**：其外部锚链（executed tool 字节 + 冻结审计器 + derived flag）在被绑定复核时成立，且本检出内对应 tracked 副本（§2.1 三条 SHA）使绑定离线可复算。这不构成任何当前审计通过。
- **F2b（工具自报 + optional overall flag）**：review 时为 open、交 DS-A，针对当时 **47554 B 未提交进行中副本**。现状登记（不构成任何工单关闭）：当前 tracked `tools/probe_release_audit_integrity.py`（`51342c48d1f7550fa2e353e107ec2a1005add409b514f469285dfc5381209a97`，49128 bytes，提交 `5ec3d389` 2026-09-12 21:45:53，HEAD 祖先）含 `def probe_tool_identity` 且报告写入 `probe_tool_sha256`（producer self-hash 已存在）；其 `summarize_coverage` docstring 逐字声明 "deliberately stricter than ``verdict``" 并列出 `blocked_or_error`，`complete_matrix_pass = required_matrix and verdict_pass`。工单层面状态仍归工单所有者。
- **F3（`summarize_coverage` optional-scenario 不一致）**：同上，现行工具的 stricter `complete_matrix_pass`/`blocked_or_error` 实现即对应修复方向；本登记不裁定工单状态。
- **F4（Setup66 三方对账范围）**：被绑定文件的可辩护主张是 **boundary-only**：helper envelope **无 full-field source-side ledger**，审计器因此对 `Setup66` 不做 full-field source↔CDR 三方对账，且 captured CDR **不得**被当作该 source ledger。这是文档边界，**不是**"完整 source-to-CDR 台账已对账"的主张，也不是功能性缺口裁定。§2.4 的现行源码锚与之一致。
- **F5（`derived_retained_sources` 重复多计）**：**reporting-only**，70 listed vs 66 unique **resolved** files（`probe.log`："66 files (70 retained sources derived)"；报告内 `audit_inputs.resolved` 66 项、`derived_retained_sources` 70 项），**不是**正确性或验收主张。历史 executed 副本（`probe-executed.py`）逐字为 `sorted(inputs["derived"])`（无去重）；现行工具为 `sorted(set(inputs["derived"]))`，且 tracked `validation/test_release_audit_integrity.py` 含 `test_derived_retained_sources_are_deduplicated` 回归。
- **"no finding" 三项（ROS-wire 归一化、event_id 端点有界、PX4 water level）**：历史复核结论按原样保留；`auditor-executed.py` 内对应逻辑字面量在场（`event_id_contiguous`、`source event_id gap`、request_id 连续列表断言）。其中 "1..127" 的具体数值来自 run-02 原始数据，**本检出内不可离线复算**，按仅声明收存。

## 4. 漂移登记（诚实边界）

| 项 | review 时 | 现状（HEAD `31e5b65f`） | 漂移事件 |
| --- | --- | --- | --- |
| `tools/audit_planner_release.py` | `e8d33c5d…`（冻结） | `bd90c75a03fbc1f4e95c7b56ead58732b3efc66ce6ecc4144f4438b471a2eaa5`，25573 bytes | `09b9729e`（2026-09-13 02:12:47，"Protect release audit outputs…"），HEAD 祖先 |
| `tools/probe_release_audit_integrity.py` | 47554 B，DS-A **未提交**进行中副本（无可提交对应物） | `51342c48…`，49128 bytes | `5ec3d389`（2026-09-12 21:45:53）首次入库即 49128 B |
| `session.py` accept 行号 | 88–101 | 86–95 | 行号漂移，内容锚不变（§2.4） |
| run-02 原始报告 | 外部 WSL `/root/wksim-release-acceptance-fe3/validation/coordination/six-end-20260912/probe-run-02/probe-report.json` | 不在本检出；tracked 副本 §2.1 | `main-verification.json.original_report` 逐字 pin 该外部路径 |

## 5. 外部边界（本检出外，离线不可证，按仅声明收存）

- run-02 原始报告、raw baseline（`/root/wksim-release-acceptance-fe3/validation/joint-public-flight-bomvjsmg`）、executed WSL `tools/probe_release_audit_integrity.py`（`92a83f4e…` ↔ 该外部检出副本，被绑定文件原话）均在**外部 WSL 检出**；本绑定未触碰、未重扫、未复算其字节。
- `main-verification.json` 的 `probe_sha256 ↔ executed WSL tools/…` 一条为对外部副本的**仅声明**身份；本检出内的可核对应物是 tracked `probe-executed.py`（同 `92a83f4e…`）。
- 任何进程态、wall 时长或 "319/66/70" 之外的 run 数据数字：不作为本检出内证明。

## 6. 屏障与门（不得被本绑定削弱）

- **保留全门**：`1ms` tick、native 屏障、`4-tick` 组、no-catch-up、`100ms` 晚限、完整滑窗/全窗、原物理门与身份门，原样保留（`docs/coordination/module-delivery-policy-20260912.md` 规则 13）。
- **#83**：已 CLOSED/PASS，**永不重跑**；本绑定的对象（bomvjsmg 发行审计矩阵）是历史发行验证证据，**不充当** #83 或任何当前门通过证据，本绑定全程未重跑 #83，不授予任何重跑许可。
- **#84 / G6 / Full**：按当前 tracked 权威仍**未完成**；被绑定文件自身 scope 即声明 "no new flight, no Full acceptance"、`full_acceptance=false`，本登记不改变任何门状态，不构成 G0-G6/Full 准入、native 结果或飞行证据。

## 7. 有界复用 / 不可复用

**可复用（历史语境）**：作为 2026-09-12 对冻结发行审计器 + probe-run-02 矩阵两轮只读复核的"当时复核到了什么"记录；§2.1/§2.2 三条 SHA 绑定与 `e897fb8e` blob 恢复途径的交叉参考；F4 boundary 表述与 F5 reporting-only 定性的原始出处。

**不可复用**：不得作为 #83/#84 或任何工单的验收、批准、收口、重跑或许可依据；不得当作现行审计器/探针工具的规范或当前审计通过状态；不得把 run-02 矩阵结果引申为当前 G0-G6/Full 门、native 或飞行证据；不得将 F4 boundary 引申为"完整 source-to-CDR 台账已对账"；不得将 F5 引申为任何正确性/验收主张。

## 8. 离线复核配方（在仓库根、UTF-8 环境）

1. `sha256sum docs/coordination/codebuddy-audit-matrix-review-20260912.md` + `wc -c` → 逐字等于 §1 表值（SHA `fbb2568b…`、5805 bytes）。
2. 对 §2.1 表 5 文件逐一 `sha256sum`/`wc -c` + `git ls-files --error-unmatch` → 全部一致且 tracked；严格 JSON 解析（拒绝重复键）`main-verification.json` 与 `probe-report.json` → §2.1/§2.3 值全部在场。
3. `git show e897fb8e:tools/audit_planner_release.py | sha256sum` → `e8d33c5d…`；`git merge-base --is-ancestor` 对 `f333316e…`、`e897fb8e`、`5ec3d389`、`09b9729e` 逐一退出码 0。
4. `grep -n "def build_ros_mode_request" Simulator/wksim_runtime/trajectory_bridge.py` → 行 91；`grep -n "SET_PX4_MODE" ros2/src/prometheus_control/prometheus_control/node.py` → 行 512 分支；`grep -n "def accept" ros2/src/prometheus_control/prometheus_control/session.py` → 行 86。
5. 运行 `python -B validation/test_codebuddy_audit_matrix_review_context.py`（正常模式与 `GIT_INDEX_FILE` 临时索引候选子集模式均须通过）。候选子集校验 `verify_staged_index_candidates` 要求 3 个候选路径（review、本 note、该测试文件）全部在场、恰一次、`mode 100644`/`stage 0` 且 blob 与工作区字节一致；允许存在额外的独立复核/manifest 路径——暂存集的恰路径等式由 manifest/final verifier 强制，不由本候选套件强制。
6. 2026-09-14 生命周期复检（P2 修复登记）：原"`GIT_INDEX_FILE` 临时索引恰 3 路径"校验使同一套件无法验证最终准入批（10 路径），已按上述候选子集语义修正。因此前次 exact-10 失败的 `validation/coordination/codebuddy-audit-matrix-context-ingest-manifest-20260914-01/` 仍为 superseded/blocked，其失败结论不变；先前独立复核 -01 亦因候选文件哈希变化而 superseded，以 -02 独立复核为准。本节修改不使上述任一失败批次合格。
7. 全程不得运行 native/build/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行，不得重跑 #83，不得查询/改动 GitHub，不得改动受保护文件。

## 9. 确定性声明

本文件由单轮只读复核后一次性写出；除本文件与 `validation/test_codebuddy_audit_matrix_review_context.py` 外未创建、修改或删除任何文件；未使用临时文件；未暂存、未提交、未推送；未执行任何 native/模型/ROS/构建/飞控/UE/飞行工作；未重跑 #83；未查询或改动任何 GitHub 状态。被绑定的源文件在写作前后哈希与大小逐字不变（`fbb2568b…`、5805 bytes）。本登记本身不新增任何验收语义。
