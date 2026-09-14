# DS-B · ds-rate-budget-20260912 历史语境绑定与取代登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时 HEAD `cc42c19f1b06538cf5bfd326d7dcd11f7b1ed6a5`；`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 退出码 0。

## 0. 本文件的地位

本文件只做两件事：把下述历史文件**按字节绑定**为历史语境（historical context only），并登记其后的取代事实。它自身不构成 #83 的验收、批准、收口、复核或重跑许可；被绑定的历史文件同样**不再**构成这些。一切"当前是否满足 / 是否可关闭"的判定必须由当前权威（主代理 / 主会话 / 人类裁决）基于**当下**的工件重新作出。本文件写作过程为纯只读复核：未启动任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行，未重跑 #83，未改动除本文件外的任何文件，未暂存、未提交、未推送。

## 1. 历史语境绑定（字节级）

| 项 | 值（本次在 HEAD `cc42c19f` 现场重算） |
| --- | --- |
| 被绑定文件 | `docs/coordination/ds-rate-budget-20260912.json` |
| SHA256 | `b6db16e282e670177eba0b9ce43d5b637ff0845279d8101a430a808d39681b37` |
| 大小 | 32100 bytes |
| 解析 | 严格 JSON，schema `wksim.ds-rate-budget.v1`，顶层 dict，解析通过 |
| 自述生成时间 | `2026-09-12T21:18:00+09:00`（Asia/Tokyo / JST） |
| 生成时检出 | `codex/independent-rgb-integration @ 7126d4d` = `7126d4d774a33c7d4b2504b9931a93ac27d7fa51`（"Start six-slot goal with DeepSeek replacing agy"，2026-09-12 20:01:49 +0900；已验证为当前 HEAD 祖先，exit 0） |
| 当前 git 状态 | **未跟踪**（`git status` 显示 `?? docs/coordination/ds-rate-budget-20260912.json`） |
| 性质 | **历史语境（historical context only）、非权威**。DS-B / #83 诊断就绪模块 2026-09-12 的离线只读速率诊断证据快照 |

**非权威声明**：该文件的任何测量、结论、边界或"下一步诊断"均**不**是当前的权威、批准、验收或收口状态。它自述 "This file is diagnostic evidence only; it is not a rate pass, PV pass, or production performance claim"，且 limitations 明言 "does not close #83, does not re-open any rate gate"。引用它只能作为"当时观察到了什么"，不能作为"现在是什么状态"或任何许可。

## 2. 本次独立复核验证的事实（全部现场重算，HEAD `cc42c19f`）

### 2.1 字节与解析

- `sha256sum` 现场重算 = `b6db16e2…81b37`；`wc -c` = 32100；`json.load` 严格解析通过。三项均与交付的审计证据一致。

### 2.2 工具哈希为历史锚（f21fc3af），已被 75353c06 取代

| 文件 | 原 JSON pin 的 SHA256 | 验证 |
| --- | --- | --- |
| `tools/analyze_joint_rate_intervals.py` | `c3ba9de8f4ac61d6b39750bdabed737915d85d3bee53d56fed8157237bca98b8` | = 提交 `f21fc3affa43df22e4a10c2b47ffae8f20361230`（"Reconcile recorded rate faults with measured interval totals"，2026-09-12 21:52:44 +0900）中该文件 blob 的内容 SHA256 |
| `validation/test_rate_tail_contract.py` | `8b468bb727213339962a3f42dac05f396bb898eafce564262499000a58c4fac0` | = 同一提交中该文件 blob 的内容 SHA256 |

两个 pin 因此是**历史哈希**。提交 `75353c0600652a062491f306b584feeacb942255`（"Retain full PV failure and reconcile startup wall-clock losses"，2026-09-12 23:26:23 +0900）修改了两个文件（analyzer +181 行；test 206 行变更），取代了上述锚。现场对照：

- 当前工作树 analyzer = `1c43ac9c4b80f2dcc8eb52ffd9c3fe061f5cd2ef9206d839fe20e7af2f783fc7`（≠ pin）。
- 当前工作树 test = `cf665b416dcd4a28e12d3c103a4741a94185b94f30e699d7039fe69c2847eb28` = `75353c06` 处 blob（≠ pin，= 取代版）。

### 2.3 引用行漂移与拒绝范围扩大

- 原 JSON 引用 `Simulator/wksim_runtime/joint_profile.py:219–220`（`'Formal mixed/PV evidence cannot include rate_timing_probe'`）。在生成检出 `7126d4d7` 处，该判断确实位于 219–220 行（现场核验一致）。在当前 HEAD，该拒绝已移至 **274–276 行**，且 marker 元组扩为 `('rate_timing_probe', 'group_work_timing', 'perf_switch_capture')`。行号引用按生成时点理解，不得按当前行号读取。
- 原 JSON 引用 `tools/run_joint_flight.py:1092–1099`（P+V 备选探针门）、`:497–499`、`:500–507`、`:1090`。在 `7126d4d7` 处 1092–1099 行确为该门（现场核验一致）；当前 HEAD 的 1090–1100 行已是其他代码，行号引用同样漂移。
- 拒绝范围在原 JSON 之后**扩大**：提交 `33c2b06e8794ad865a25b307852d08d4c0845a26`（"Reject perf diagnostics from formal MIXED evidence"，2026-09-13 22:26:20 +0900）向 `_mixed_proofs` 的 marker 元组加入 `perf_switch_capture`。原 JSON 描述的拒绝机制窄于当前门。
- 上述漂移不影响结论本身："诊断场 / probe 场不得充当 #83 通过证据"在当前门下仍然成立且覆盖更宽。

### 2.4 checks.json 引用的性质

被跟踪的清单 `validation/coordination/ds-g0-g5-frontier-20260913-01/checks/checks.json`（schema `wksim.ds-g0-g5-frontier-checks.v1`）提及本被绑定文件时，仅以其**未跟踪工作树条目**的形式出现（`"?? docs/coordination/ds-rate-budget-20260912.json"`）。该清单**不含**被绑定文件的 SHA256，不构成对其字节的 SHA 认证。被绑定文件当前唯一的字节身份 pin 是本文件 §1 重算的 SHA256。

## 3. 其后的取代锚点（均为 tracked）

| 锚点 | 内容 |
| --- | --- |
| `docs/coordination/ds-7bdfxkb-diagnostic-analysis.json`（tracked，schema `wksim.ds-rate-diagnostic-analysis.v1`） | 原文件 `next_minimal_diagnosis`（经 `docs/plan/33-rate-next-diagnostic-20260912.md`，该文件存在）提出的下一次最小诊断，其后已被真实诊断场 `joint-public-flight-7bdfxkb_` 的只读分析执行并登记（analyzed 2026-09-12T22:45 +0900）。原 JSON 中的"待测不确定性"以该 tracked 记录为准，不再以原 JSON 的提案为准 |
| `docs/plan/33-rate-measured-candidate-20260912.md`（tracked） | 记录 **#83 已经由公共 PV `1w6dru32` 通过并 CLOSED**；C1 仍是假说；`7bdfxkb_` / manager99 失败不得写成 #83 未完成；诊断场永不得充当 #83 通过证据；**#83 不重跑** |

另注：未跟踪的评审文档 `docs/coordination/codebuddy-module-review-20260912.md` 曾对本被绑定文件提出 D1/D2 修正（`audit_pv_trajectory.py` 无 probe 拒绝、`audit_joint_rate.py` 仅对身份块 fail-closed）；被绑定文件自身 `parser_coverage` 的 "Correction to the first edition" 已折叠该修正（本次核对其 319/330 行原文一致）。该评审文件未跟踪，不作为权威。

## 4. 保留的历史失败含义与门（不因本绑定而改变）

以下含义按被绑定文件的记录原样保留，仅作历史事实引用：

- 四个正式速率失败按原始记录时间序为 `zzmg3k47`（2026-09-11T12:49 JST，begin_group release wait）、`tpwl1k4p`（2026-09-12T00:21，begin_group release wait，未起飞）、`nqyqcagl`（2026-09-12T12:52，end_group）、`8fmacpgy`（2026-09-12T18:34，end_group，planner release writer silent）；`bomvjsmg` 仅是未越界的单段轻量对照，禁止外推到完整两段 P+V。
- 身份门：四场使用四个互不相同的 control manifest（`0DQQz9` / `rWolCy` / `ZlTVa4` / `c2IXOr`），**永不混用**；AP `1e6250ef`、message `29969da0`、PX4 pin `d7e905b3` 等冻结身份按原记录理解。
- 时间门：不同 run 的 monotonic / wire wall 值来自不同原点，**永不跨 run 相减**；重叠不等于因果。
- 物理与验收门：无任何 CPU / AP / PX4 / 调度器 / DDS 根因被指派；`zzmg3k47` / `tpwl1k4p` 的记录组开始未达 100 ms 上限，"因组开始迟到超 100 ms 而失败"的表述不被记录支持；诊断 probe 场不能充当 #83 验收（当前门在 `joint_profile.py:274–276`）。
- 原 JSON 对既有失败的解释力已被其后的 tracked 诊断与 #83 CLOSED 记录取代；其失败**记录本身**仍是这些 run 的历史证据，含义不变。

## 5. 本文件的边界

- 本次仅创建本文件（`docs/coordination/ds-rate-budget-ingest-note-20260914.md`，未跟踪）；未编辑被绑定文件或任何其他文件。
- 未暂存、未提交、未推送。
- 全程只读复核（哈希重算、`git show` blob 内容 SHA256、`git log`、`sed` 行读取、严格 JSON 解析）；未运行单元测试、未启动任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行；未重跑 #83。
- 本文件不授予任何验收、收口、owner 批准或 native 重跑许可。
