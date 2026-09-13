# 模块交付与即时接续（策略）

- `checked_at`: `2026-09-13T16:43:22+09:00`（unix 1789285402）
- 本文是**静态策略/交接文档：不执行、不启动、不恢复任何后台调度**；队列与派发 JSON 同样只是记录。
- 来源：`validation/coordination/perf-open-admission-20260913-01/`（`dispatches.json`/`receipt.json`/`prechecks.json`，派发于 unix 1789285339）、`validation/coordination/manager99-unprobed-20260913-01/`、HEAD `820f532`。
- Goal 字符串中的阵容为历史值；**实时席位不在本文维护**，唯一指针为 [perf-open-admission dispatches](../../validation/coordination/perf-open-admission-20260913-01/dispatches.json)。

## 1. 交付节奏

1. 完成一项即验收、返修或接续独立任务，不等整批结束。每项任务自带内部修复、纯测试、真实原件复核和稳定 SHA，减少主会话重复接手内部工作。
2. 每席**只有一个**正在执行的任务，并预先标明下一项及依赖。没有合法 ready 项时如实记录等待原因，不制造重复报告填满席位。
3. 交付稳定 SHA 后交付方停止写入，等审查者复核；主会话只提交已验证的精确版本。
4. 跨主题的新任务用简短独立会话；同一模块返修保留原负责人。新会话是否更快需实测，不据历史长度宣称性能提升。

## 2. 写入权与所有权

5. **一个文件只有一个写入者**；交付并确认终态后才转移写入权。审查者只审稳定版本，主会话提交精确已验证版本，保护其它工作区修改。
6. 主会话独占 native、正式 profile/catalog 与 `joint_profile.py` 接线。Linux 执行检出 `Ubuntu-22.04 /root/wksim-release-acceptance-fe3`（分支 `codex/planner-release-validation`），第二发行版 `RflySim-20.04`。
7. Windows `tools/run_joint_flight.py` 属其它工作，本策略不改。实验 runner 只在上述 Linux 检出修改，并保留实际源 SHA 快照；私有 runner 现为 `1c600d7f…`（manager50，已回退），`9b97c124…`（manager99）已弃用。
8. 只精确 `git add`；禁止全库 `git add`、禁止覆盖他方 controller/runtime/UE/rover 修改，不发布厂商源码或 `.so`。

## 3. 状态依据

9. **精确 thread read/wait 是唯一状态依据**；`THREAD_BUSY` 不算排队、cancel 回执不算终态。JSON/文档**不自动执行调度**。
10. 根 Goal 仍 active；`#83` 已 CLOSED（`1w6dru32` PV 真实 PASS，见 [final-combo PV pass](../2026-09-13-final-combo-pv-pass.md)）；`#84`/G6/Full 未完成，以已验收交付与解除依赖衡量效率。
11. 历史记录仍可从 Git 读取；当前检查点为 [short-cycle-goal.md](short-cycle-goal.md)。该页被压缩前的上一版全文用 `git show 820f532:docs/coordination/short-cycle-goal.md` 取回；`short-cycle-goal-history-20260912*.md` 是更早的历史页，不是压缩前全文。

## 4. 允许与禁止

12. 代理可跑纯测试与既有原件只读分析；**禁止**模型、MATLAB、ROS、飞控、UE 与构建。
13. 保留全部原门：`1ms` tick / native 屏障 / `4tick` 组 / 无追赶 / `100ms` 晚限 / 完整滑窗 / 原物理与身份门。已通过飞行不重跑，失败原件不覆盖，不操作用户进程，不改全局内核或调度设置。
14. 主会话新 native 前分别核查两 WSL（`found=[]`、同 boot），确认无竞争重负载；随后由**入口在启动时**校验 boot 与 ≤60 秒新鲜度。同一启动器顺序检查后，以独立 subprocess 启动**即满足要求**（`open_self` 的真实启动即如此）；**不要求每次跨工具调用**，前检与启动也不必拆成两个工具调用。不相符就重做前检。
15. WSL 保持进程必须有自有 `PID`/`start_ticks`/`boot` 身份，结束时核验后清理。使用干净 env；Bash 脚本用 Python 写入并清除 CR。

## 5. 当前席位与交付

**不在本文维护负责人表**（重复表会立刻过期）。席位、thread/turn、deepLink 与不可用席位只指向
[perf-open-admission-20260913-01/dispatches.json](../../validation/coordination/perf-open-admission-20260913-01/dispatches.json)：
5 席派发时 `status_at_dispatch=running`（3 DeepSeek + Claude + OMP），CodeBuddy 三席 `quota_blocked`/429
（`reset_jst=2026-09-13T20:54:20+09:00`，`retry_submitted=false`）；旧表已删除，不保留副本。

## 6. 当前运行状态（唯一来源指针）

实时状态**不在本文件**重复维护，只指向原件，避免同文件内自相矛盾：

- manager99 无探针 `oayggl_s` 失败、无诊断标记、无 native/keeper：[terminal-cleanup.json](../../validation/coordination/manager99-unprobed-20260913-01/terminal-cleanup.json)；回退收据（`9b97c124…` → `1c600d7f…`，manager 目标恢复 50）：[rollback.json](../../validation/coordination/manager99-unprobed-20260913-01/rollback.json)；决策：[decision.json](../../validation/coordination/manager99-unprobed-20260913-01/decision.json)。
- 启动/前检/身份与冻结组合、mixed 证据集为空、G6 状态：见 [short-cycle-goal.md](short-cycle-goal.md)（本文不复制这些数字）。

## 7. 未完成与停止条件

- `#84`/G6/Full 未完成；`aligned` 只表示结构对齐，缺口仍是有依据且 approved 的逐量预算。
- `perf_event_open` 自线程侧：主会话已**真实编译并运行** `open_self.c`，两种 `exclude_kernel`（0/1）均 open/close 成功（errno 0），但事件未 enable、`switch_records_verified=false`、**完整 D recorder 仍未验收**，且只证 root 环境下可用、不证非特权可用。范围仍限 `pid=0`/`cpu=-1`/`inherit=0`、软件 DUMMY、`TID/TIME/CPU`、`CLOCK_MONOTONIC`；D v1 已拒，修 v2 后主会话才编译自测。收据：[receipt.json](../../validation/coordination/perf-open-admission-20260913-01/receipt.json)、[prechecks.json](../../validation/coordination/perf-open-admission-20260913-01/prechecks.json)、[README.md](../../validation/coordination/perf-open-admission-20260913-01/README.md)。
- 本文件只描述策略与指针；任何实跑、编译、清理或恢复动作都需要主会话在一次带前检的启动中显式执行（见规则 14）。
