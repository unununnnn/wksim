# OMP 交付门/诊断入口双件历史语境绑定与取代登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`。本文件写作时的**权威写作 HEAD**为 `1c5656ed924020b3e626e68739caeeaef9f41a9e`（"Bind rate budget context offline"）；证据审计基线 HEAD 为 `76f77470e91ecc742148df0f3eba6f5b5494511c`，且 `git merge-base --is-ancestor 76f77470… HEAD` 成立：两者之间**恰有一个提交** `1c5656ed`，其变更为且仅为 10 个 rate-budget 语境文件（`docs/coordination/ds-rate-budget-20260912.json`、其 ingest note、两套 coordination 审查/清单工件、`validation/test_ds_rate_budget_context.py`），与本双件及下文所有锚点文件**完全不相交**，不影响本绑定的任何输入。架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 已验证为当前 HEAD 祖先（`git merge-base --is-ancestor` 退出码 0）。

## 0. 本文件的地位

本文件只做两件事：把下述两个历史文件**按字节绑定**为历史语境（historical context only），并登记其后的取代事实。它自身不构成 #83（或 #9/#26/#29/#62/#102 或任何工单）的验收、批准、收口、复核或重跑许可；被绑定的历史文件同样**不再**构成这些。一切"当前是否满足 / 是否可关闭"的判定必须由当前权威（主代理 / 主会话 / 人类裁决）基于**当下**的工件重新作出。本文件写作过程为纯只读复核：未启动任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行，未重跑 #83，未改动除本文件外的任何文件，未暂存、未提交、未推送，未查询或改动 GitHub 状态，未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`）。

## 1. 历史语境绑定（字节级，均在权威写作 HEAD `1c5656ed` 现场重算）

| 项 | 值 |
| --- | --- |
| 被绑定文件 1 | `docs/coordination/omp-delivery-gates-20260912.md` |
| SHA256 | `df438b44ad94940990d84a6e39504df8327e24b8e0c0a914710417c61104ac21` |
| 大小 | 4010 bytes |
| 自述日期 | 2026-09-12（OMP 交付包可执行性门） |
| 被绑定文件 2 | `docs/coordination/omp-diagnostic-entry-20260912.md` |
| SHA256 | `73bbc35f0db45ee1b3d9925f7ea5bbfff05c5513ce002e078ea10446b065fe0b` |
| 大小 | 7530 bytes |
| 自述日期 | 2026-09-12（OMP 诊断入口核验，只读） |
| 当前 git 状态 | 两件均**未跟踪**（`??`） |
| 性质 | **历史语境（historical context only）、非权威**。同一切片（OMP）同日的两份互补记录：交付门清单 + 诊断入口/命令模板核验 |

**非权威声明**：两文件的任何核验结论、"可执行"判定、最小验收列表或命令模板均**不**是当前的权威、批准、验收或收口状态。引用它们只能作为"2026-09-12 当时核对到了什么"，不能作为"现在是什么状态"或任何许可。

## 2. 本次独立复核验证的事实（审计基线 HEAD `76f77470` 现场重算；两 HEAD 间差集与本绑定无关）

### 2.1 字节与存在性

- 两文件 `sha256sum` / `wc -c` 与上表逐字一致；两 HEAD 下重算值相同。
- 两文件引用的 13 个路径全部为**已跟踪**文件：`tools/audit_pv_trajectory.py`、`tools/run_joint_flight.py`、`tools/run-joint-flight.sh`、`tools/audit_26_closure_readiness.py`、`tools/audit_joint_rate.py`、`validation/test_delivery_entry_contract.py`、`validation/20-rate-candidate-profile/check-delivery.py`、`Simulator/wksim_core/joint.py`、`Simulator/wksim_runtime/joint_rate_probe.py`、`docs/plan/26-closure-readiness-manifest.json`、`docs/plan/33-final-combo-rate-candidate.md`、`docs/plan/39-planner-run-contract.md`、`docs/coordination/omp-83-freeze-check-20260912.md`。

### 2.2 实质接口声明逐条成立（内容锚，非行号锚）

- `WKSIM_JOINT_CPU_TIMING` 字面 `os.environ.get(...)=='1'`（`Simulator/wksim_core/joint.py:54`，行号未漂移）；关闭时零时钟读取注释在场。
- `WKSIM_JOINT_RATE_TIMING_PROBE` 三态门（unset/0/1，其余 raise）与 runner 硬门在场；PV/MIXED-only 门与 `--async-model-evidence` 同型门（现 `tools/run_joint_flight.py:424-427`）。
- `audit_joint_rate.py` 对 `rate_timing_probe` 记录 fail-closed（现 :36，原 :32-36 区间内）；`validation/20-rate-candidate-profile/check-delivery.py` 对 CPU-timing 期望 exit 1（`instrumentation-refused`）。
- `'--'+name` 循环构造 control/ap 旗标（现 :1185-1188）、`candidate_environment(control, messages=None)`（现 :161）、`reset_on_fork`（现 :214-216）、`add_timing_probe_identity`（现 :864）在场。
- `tools/ap_mixed_candidate.py:22-24` FINAL 三个 SHA 逐字在场（`1e6250ef…`/`6fe8c0b3…`/`29969da0…`）；admit 硬拒字符串 `'Message candidate path/SHA pair is incomplete'`（:109）与 `'…requires the exact final manifests'`（:116）在场；`joint_control_candidate.py:148` / `joint_message_candidate.py:109` 的 `[0-9a-f]{64}` fullmatch + 字节比对在场。
- 壳入口 `tools/run-joint-flight.sh:12,15` source 历史 `MUlZd0`/`FVMjak` overlay，逐字在场。
- 三身份表来源锚 `docs/plan/39-planner-run-contract.md:113-122` 逐字在场（fhuf05l9/`1e6250ef…`、c2IXOr/`6fe8c0b3…`、Rzj3Pf/`29969da0…`）。
- 哈希仍成立：`Simulator/wksim_core/joint.py` = `f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50`；`Simulator/wksim_runtime/joint_rate_probe.py` = `a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653`。

## 3. 取代/漂移登记（五项）

1. **主工作区 FINAL_CONTROL 分叉已被取代**：交付门件称主工作区 `FINAL_CONTROL_SHA` 为 `3d04d53a…`（≠ c2IXOr）、诊断包"只能实验区执行"。`git log -S '3d04d53a' -- tools/ap_mixed_candidate.py` 证实：`0769c3a0`（09-12）引入 `3d04d53a`，`941d5843`（2026-09-13）已将主工作区收敛为 `6fe8c0b3…`（c2IXOr）。该分派结论**在本写作 HEAD 已不再成立**；本登记只记录取代事实，不重新裁定两区现状。
2. **DS-A 覆写缺口已在主工作区修复**：`tools/audit_pv_trajectory.py` 现有 lexists 保护（"refusing to overwrite retained evidence"，:881-896）+ 证据根目录包含性拒绝；`tools/audit_planner_release.py:353-359` 同型保护。交付门件所记 `:877 write_text` 直写覆写形态已被取代。**DS-D 缺口仍然开放**：`tools/audit_26_closure_readiness.py:1745` 仍为无保护 `write_text`（原 :997）。
3. **`docs/plan/33-final-combo-rate-candidate.md` 哈希漂移**：诊断入口件记 `9516a2cd…`，现值 `6f0e764ad3961ee9441ef9715ca4d95466e6f7e3aeb5fd9ee5a158ae0dd942cd`（`941d5843`，09-13 修改）。原值为当时读数，非现在事实。
4. **`tools/run_joint_flight.py` 行号全部漂移**（`c3d4916f`，09-13 修改）：门 :326-331→:424-427、CLI :1065-1075→:1183-1194、`candidate_environment` :64-66→:161 等。**字节身份锚以内容/符号/哈希为准，行号只是 2026-09-12 的历史读数**，不得作为绑定缝。
5. **次级行号漂移**：`audit_joint_rate.py` 门现 :36（原 :32-36，区间内）；`joint_control_candidate.py` / `joint_message_candidate.py` 引用均在原区间内；`audit_26_closure_readiness.py` CLI 现 :1739-1740（原 :990-992）。

## 4. P2 溯源警示：契约测试计数与创建日期不符

交付门件称"自动拒绝测试：`validation/test_delivery_entry_contract.py`（**9 项**，Windows/WSL 双平台通过）"。跟踪历史显示该文件**首次入库为 2026-09-14**（`d5954380` "Add delivery entry contract checks"，20 项；`982336cd` 21 项）；**不存在任何 09-12 的 9 项跟踪修订**，"9 项"与"双平台通过"无法由本检出离线证实，只能作为**已记录的历史执行声明**收存。被绑定文件仍可按历史语境收存，但任何后续引用不得把该声明当作已证事实。现仓同名为 21 项测试（写作 HEAD 现值）。

## 5. 外部边界（本检出外，离线不可证）

- Linux 实验区 `/root/wksim-release-acceptance-fe3` 及 `/root/wksim-ap-mixed-fhuf05l9`、`/root/wksim-joint-control-c2IXOr`、`/root/wksim-ros2-Rzj3Pf`、`/root/wksim-ros2-MUlZd0`、`/root/wksim-joint-control-FVMjak` 等候选/overlay 路径均在本检出之外；其"逐字节一致/实读一致"声明按**仅声明**收存（主工作区一侧的对应哈希已独立复算成立）。
- 实验区 runner 的 `--planner-release-proof` 增补、69 行主/实区漂移、WSL 侧执行环境：均未在本检出内核。
- raw 证据根与运行 live 目录由入口自生成，本绑定未触碰。
- PX4 候选组合（`--px4-manifest/--px4-sha256`）两件均明确留白待当场给出；本登记不代填。

## 6. 跟踪锚清单（未来引用必须回到这些锚）

`docs/plan/39-planner-run-contract.md:113-122`（身份表与模板来源）；`docs/coordination/omp-83-freeze-check-20260912.md`（三清单 SHA 当日实读快照，跟踪在库）；`tools/ap_mixed_candidate.py:22-24`（FINAL pins；取代史 `0769c3a0`→`941d5843`）；`tools/run-joint-flight.sh:12,15`（overlay 层）；`Simulator/wksim_core/joint.py:54`（哈希 `f5433c2e…`）；`Simulator/wksim_runtime/joint_rate_probe.py`（哈希 `a8bac9ac…`）；`tools/audit_joint_rate.py:36`（fail-closed）；`validation/20-rate-candidate-profile/check-delivery.py`（CPU-timing exit-1）；`tools/audit_pv_trajectory.py:877-896`（覆写保护，取代 DS-A 缺口）；`tools/audit_planner_release.py:353-359`（同型保护）；`tools/audit_26_closure_readiness.py:1739-1745`（**缺口仍开放**）与 `docs/plan/26-closure-readiness-manifest.json`；`tools/run_joint_flight.py` 现行号图 ：161/:214-216/:424-427/:864/:1183-1194；`docs/plan/33-final-combo-rate-candidate.md`（哈希漂移登记）；`validation/test_delivery_entry_contract.py`（`d5954380`/`982336cd` 溯源）；屏障锚 `docs/plan/33-rate-measured-candidate-20260912.md:5,13`（"#83 不重跑"、诊断场"永不得充当 #83 通过证据"）。

## 7. 有界复用 / 不可复用

**可复用（历史语境）**：作为 2026-09-12 交付门与诊断入口核验的"当时核对到了什么"记录；两区接口/旗标/硬门/身份表的交叉参考；`0DQQz9`/`OEvS3W` 为**仅历史身份**、模板不得暗示可直接运行旧身份的约束记录。

**不可复用**：不得作为 #83 或任何工单的验收、批准、收口、重跑或许可依据；不得把诊断场结果（`rate_timing_probe`、`diagnostic_*`、CPU-timing trace 行）当验收证据——`audit_joint_rate.py`/`audit_pv_trajectory.py` 对其 fail-closed；不得以本绑定代替 DS-D 覆写缺口的修复（缺口仍开放，验收输出必须指向全新路径）；不得引申为主/实区现状或 rate-budget/G6 当前权威；不得暗示可运行历史身份或重跑 #83。

**屏障保留（不得被本绑定削弱）**：`.5×/100ms/1ms` 为 runner 内建常量、无对应参数（诊断入口件 §4）；诊断 trace 仅落原始 trace/truth 行或显式诊断字段，`WKSIM_JOINT_CPU_TIMING` 结果**不进 result.json**，`WKSIM_JOINT_RATE_TIMING_PROBE` 诊断身份**进 result.json 但永不得作验收**；native 输入等待仅作诊断采样，本绑定全程未执行 native；计时只允许**run 内单调差分**，禁止跨 run 原点相减、禁止对已记录窗口做追赶/回填式修正，区间账目须按 begin/end 全窗闭合、不得叠加重叠区间；身份门（四控制候选/清单/epoch 两两相异、身份冻结规则）与物理门（固定飞行边界，未达标即 fail-closed）原样保留；历史失败（如 7bdfxkb_/manager99、1w6dru32 已 CLOSED 等）仅作**已记录历史**引用，不重跑、不改写。

## 8. 离线复核配方

在仓库根（UTF-8 环境）执行：

1. `sha256sum docs/coordination/omp-delivery-gates-20260912.md docs/coordination/omp-diagnostic-entry-20260912.md` 与 `wc -c` 同名两件 → 应逐字等于 §1 表值。
2. `git rev-parse HEAD` → `1c5656ed…`（或其**后代**；本绑定锚定祖先关系而非 HEAD 相等）；`git merge-base --is-ancestor f333316e… HEAD` → 退出码 0。
3. `git log -S '3d04d53a' -- tools/ap_mixed_candidate.py`、`git log -1 -- docs/plan/33-final-combo-rate-candidate.md` → 复现 §3 取代事实。
4. `grep` §2.2/§6 各内容锚（字面字符串/符号/SHA 前缀）→ 全部在场。
5. 可选离线套件：`python -B -m unittest validation.test_delivery_entry_contract -v`（现 21 项，非 native）；其结果只证明当前接口层，不增加本绑定的权威。
6. 全程不得运行 native/build/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行，不得重跑 #83，不得查询/改动 GitHub，不得改动受保护文件。

## 9. 确定性声明

本文件由单轮只读复核后一次性写出；除本文件外未创建、修改或删除任何文件；未使用临时文件；未暂存、未提交、未推送；未执行任何 native/模型/ROS/构建/飞控/UE/飞行工作；未重跑 #83；未查询或改动任何 GitHub 状态。被绑定的两个源文件在写作前后哈希与大小逐字不变。本登记本身不新增任何验收语义。
