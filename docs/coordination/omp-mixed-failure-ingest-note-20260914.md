# OMP mixed 场失败独立复核 历史语境绑定与取代登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`。本文件写作时的**权威写作 HEAD**为 `011818876c1b94875fd67cedaaa73abfac866633`（"Bind OMP delivery diagnostic context offline"）；证据审计基线 HEAD 为 `e2ecd62e914e075d0d9e40eef8ea9c034b958d2f`，且 `git merge-base --is-ancestor e2ecd62e… HEAD` 成立（退出码 0）：两者之间**恰有一个提交**，其变更为且仅为 11 个 OMP 交付门/诊断入口语境文件（两份 2026-09-12 历史文档、其 ingest note、`validation/test_omp_delivery_diagnostic_context.py`、独立审查目录三件、语境清单目录四件），与被绑定文件及下文所有锚点**完全不相交**，不影响本绑定的任何输入。架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 已验证为当前 HEAD 祖先（`git merge-base --is-ancestor` 退出码 0）。

## 0. 本文件的地位

本文件只做两件事：把下述历史文件**按字节绑定**为历史语境（historical context only），并登记其后的取代/漂移事实。它自身不构成 #83（或 #9/#26/#29/#62/#102 或任何工单）的验收、批准、收口、复核或重跑许可，不构成任何当前速率门通过、模型/物理权威或 native 执行证明；被绑定的历史文件同样**不再**构成这些。一切"当前是否满足 / 是否可关闭"的判定必须由当前权威（主代理 / 主会话 / 人类裁决）基于**当下**的工件重新作出。本文件写作过程为纯只读复核：未启动任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行，未重跑 #83，除本文件外未创建、修改或删除任何文件，未暂存、未提交、未推送，未查询或改动 GitHub 状态，未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`）。

## 1. 历史语境绑定（字节级，均在权威写作 HEAD `011818876` 现场重算）

| 项 | 值 |
| --- | --- |
| 被绑定文件 | `docs/coordination/omp-mixed-failure-review-20260913.md` |
| SHA256 | `2417c299d57ccdc79b7368e03180bd0b767aabb91c012257e1443a17fca331c3` |
| 大小 | 4448 bytes |
| 自述日期 | 2026-09-13（OMP mixed 场失败独立复核，只读） |
| 当前 git 状态 | **未跟踪**（`??`） |
| 性质 | **历史语境（historical context only）、非权威**。同日对 `joint-public-flight-oxv29042`（epoch `18c96a7e…`）失败场的只读诊断复核记录 |

**非权威声明**：被绑定文件的任何 latch 复算、分区结论、诊断分类或"下一诊断问题"均**不是**当前的权威、批准、验收或收口状态，也不是模型/物理权威或 native 证明。引用它只能作为"2026-09-13 当时复核到了什么"，不能作为"现在是什么状态"或任何许可。

## 2. 本次复核验证的事实（全部现场重算，HEAD `011818876`）

### 2.1 字节与存在性

- 被绑定文件 `sha256sum`/`wc -c` 与 §1 表逐字一致；未跟踪状态不变。
- **引用路径已 relocation**：被绑定文件引用的 `validation/current-mixed-20260913-01/main-rate-analysis.json` 在本检出**不存在**（`validation/current-mixed-20260913-01/` 目录不存在）。字节相同的 **tracked** 工件现位于 `validation/33-formal-promotion/current-mixed-oxv29042/main-rate-analysis.json`，SHA256 = `b4c7f44e12f96ac63b720b217cd102afeba5c846b3ecbf41c6e4dbd275c410cc`（现场重算一致）。此为**路径漂移登记**，不是缺陷裁定；引用必须回到 tracked 路径。

### 2.2 tracked bundle 证据锚（与本检出内可核）

- `validation/33-formal-promotion/current-mixed-oxv29042/` 为 **tracked** 目录（`git ls-files` 计 20 个文件），其中 `bundle-manifest.json`（严格 JSON 解析通过）逐字 pin：run `oxv29042`、epoch `18c96a7e…`、原始 trace `rate.jsonl` SHA256 `8725b63c568783199b4a5e7d3de7df532003749b73d4c255131da4bcedee8b91`、分析件 `main-rate-analysis.json` SHA256 `b4c7f44e…`；`rate.jsonl.gz` 同目录 tracked 在场。原始场目录（如 `validation/joint-public-flight-oxv29042`）**不在主检出**，属外部 WSL 侧 raw 证据；本检出内的身份闭合仅由上述 tracked manifest 承担。
- `main-rate-analysis.json`（严格 JSON 解析通过，无重复键）内下列数值逐字在场并被本登记重算确认：analyzer `1c43ac9c…`（= 当前 `tools/analyze_joint_rate_intervals.py` 现值，现场重算一致）；epoch `18c96a7e…`；anchor tick 40 / wall `110030174978`；**墙钟域分区**早期 249 区间 / 975,731 ns、跨界 1 区间 / 4 ns、稳态 32,679 区间 / 98,805,073 ns（合计 99,780,808 ns，与 creep 总量精确一致）；work_over 15,139,984 ns；latch lateness **100,034,744 ns** 于 **tick 131,760**、完成组端 **32,930** = (131760−40)/4 精确；终末闭链 115,732 + 99,780,808 + 138,204 = **100,034,744** 精确闭合；最大区间 tick 127940→127944 creep 5,547,162 = 前组 work_over 5,140,957 + release 超额 406,205，等式精确；超 100 ms 门 34,744 ns。

### 2.3 untracked 工件声明

被绑定文件的 xtj8wk8i 诊断分类节引用 `validation/33-formal-promotion/20260913-mixed-failure-review/classify_xtj8wk8i_probe.py` 与 `xtj8wk8i-probe-classification.json`——该目录现为**未跟踪**（gitignored）工作树工件；`residual_note` 为 `"removed: the difference is not an attributable residual…"`（与 §3.2 撤回一致）。引用该节事实时必须注明"untracked 工件，按仅声明收存，除非其后入库"。

## 3. 保留的历史撤回（被绑定文件自身的两处显式更正，按原样保留）

1. **tick≤2040 墙钟分区已作废**：此前把 tick 2040 误当 2 墙秒的划分（500/32429 区间）错误；正确分区按 `actual_start_ns` vs `steady_after_ns`（墙钟域），即 §2.2 所列 249/975,731、1/4、32,679/98,805,073。引用时不得复活 tick 域分区。
2. **v1 "15.19 ms 已归因残余" 叙述已撤回**：睡眠越界只是它自身统计量，与 release 总量重叠未知，不得相减得"已归因残余"；分类工件 `residual_note` 亦记 `removed`。

## 4. 外部边界（本检出外，离线不可证）

- raw 场目录与运行 live 目录：外部 WSL 侧（`/root/...` 等），本绑定未触碰、未重扫；WSL 侧执行环境声明按**仅声明**收存。
- 实验区路径与任何 native 侧工件：不在本检出内核。
- PGID 等进程态历史声明：**临时态**，不可复现，按仅声明收存。

## 5. 屏障与门（不得被本绑定削弱）

- **速率门**：1 ms tick、4-tick 组、no-catch-up、100 ms lateness 门、全窗（begin/end 闭合）均为 runner 内建常量；计时只允许 **run 内单调差分**，禁止跨 run 原点相减、禁止追赶/回填式修正、不得叠加重叠区间。
- **身份门**：四控制候选（`0DQQz9`/`rWolCy`/`ZlTVa4`/`c2IXOr`）、清单 SHA、epoch 两两相异，永不混用；身份冻结规则原样保留。
- **物理门**：固定飞行边界，未达标即 fail-closed；`land_accepted` 未达 landed/disarmed 终态**不得计 pass**；latch 时刻 AP 正常下降、PX4 已落地为当时观察，不构成物理异常判定。
- **历史失败**：`zzmg3k47`/`tpwl1k4p`/`nqyqcagl`/`8fmacpgy` 及 `7bdfxkb_`/manager99、`1w6dru32` 已 CLOSED 等仅作**已记录历史**引用，不重跑、不改写。
- **#83**：本场为诊断证据，mixed 能力证明行仍 **MISSING**；诊断场永不得充当 #83 通过证据；本绑定全程未重跑 #83，不授予任何重跑许可。

## 6. 有界复用 / 不可复用

**可复用（历史语境）**：作为 2026-09-13 oxv29042 失败场只读复核的"当时复核到了什么"记录；latch/分区/闭链算术的交叉参考；两处历史撤回的更正记录。

**不可复用**：不得作为 #83 或任何工单的验收、批准、收口、重跑或许可依据；不得当作当前速率门状态、模型/物理权威或 native 证明；不得把诊断场结果当验收证据；不得引申为主/实区现状或 rate-budget/G6/交付门语境的当前权威。

## 7. 离线复核配方（在仓库根、UTF-8 环境）

1. `sha256sum docs/coordination/omp-mixed-failure-review-20260913.md` + `wc -c` → 逐字等于 §1 表值（SHA `2417c299…`、4448 bytes）。
2. `ls validation/current-mixed-20260913-01` → 不存在；`sha256sum validation/33-formal-promotion/current-mixed-oxv29042/main-rate-analysis.json` → `b4c7f44e…`；`git ls-files validation/33-formal-promotion/current-mixed-oxv29042/` → 20 个 tracked 文件。
3. `git ls-files --error-unmatch` 上述 tracked 锚 → 退出码 0；`tools/analyze_joint_rate_intervals.py` sha256 == `1c43ac9c…`。
4. 严格 JSON 解析（拒绝重复键）`bundle-manifest.json` 与 `main-rate-analysis.json`；grep §2.2 各数值锚（分区、latch、闭链三项）→ 全部在场。
5. 祖先关系（**只锚祖先，不锚 HEAD 相等**）：`git merge-base --is-ancestor f333316e… HEAD` 与 `git merge-base --is-ancestor e2ecd62e… HEAD` 均退出码 0。
6. 全程不得运行 native/build/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行，不得重跑 #83，不得查询/改动 GitHub，不得改动受保护文件。

## 8. 确定性声明

本文件由单轮只读复核后一次性写出；除本文件外未创建、修改或删除任何文件；未使用临时文件；未暂存、未提交、未推送；未执行任何 native/模型/ROS/构建/飞控/UE/飞行工作；未重跑 #83；未查询或改动任何 GitHub 状态。被绑定的源文件在写作前后哈希与大小逐字不变。本登记本身不新增任何验收语义。
