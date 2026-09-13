# 当前 Goal 执行检查点

- `checked_at`: 2026-09-13T16:59:17+09:00
- 本文件是**静态交接文档，不执行也不启动后台调度**；调度事实只以精确 thread read/wait 与 JSON 收据为准。
- 来源：`validation/coordination/perf-open-admission-20260913-01/`（`dispatches.json` 派发于 unix 1789285339）、`validation/coordination/manager99-unprobed-20260913-01/`（`decision.json`/`rollback.json`/`terminal-cleanup.json`/`inflight.json`）、HEAD `820f532`、私有 Linux 检出实测 SHA。
- 根 Goal 字符串中的"阵容"是创建时的历史值，**不是**实时状态；本文件不改写 Goal DB。

## 工作区与所有权

- 主仓库：`C:/Users/PC/Documents/odid编译/wksim`，分支 `codex/independent-rgb-integration`，remote `unununnnn/wksim`。大量 controller/runtime/UE/rover 他方修改保留，禁止 `git add` 全库或覆盖。
- 主会话独占 native、正式 profile/catalog、`joint_profile.py` 接线。实验 runner 只在 Linux 检出 `Ubuntu-22.04 /root/wksim-release-acceptance-fe3`（分支 `codex/planner-release-validation`）修改，第二发行版 `RflySim-20.04`。
- Windows `tools/run_joint_flight.py` 属其它工作，本次未改。**一个文件只有一个写入者**，交付并确认终态后才转移写入权；审查者只审稳定版本。
- 队列/派发 JSON 是交接记录，**不是后台自动调度程序**；`THREAD_BUSY` 不算送达，cancel ack 不算终态。

## 当前状态（唯一有效快照）

- 上一已提交基线 `a781749`；本轮新增自线程perf能力实证，当前提交以 `git log -1` 为准。
- 最新无探针场 **`oayggl_s` 失败**：`failed@tick108004`，epoch `afa75a2cb5eb45f48f34526780299ec3`，wall `268.721856341s`，`RateUnmet`。结果**无** `rate_timing_probe`/`owned_scheduling`/`group_work_timing` 键，`markers={}`，`source_unchanged=true`，`cleanup_errors=[]`；boot `470ea486-9e18-4535-9d91-69de5a3a4572` 下 PGID `2109–2118` 独立全空。flight session `48029` 终态；keeper `637`/`start 422` 身份核验后 SIGTERM、session `7873` 终态。
- 私有 runner 已**回退**：`9b97c124…` → `1c600d7f…`（manager50）；`parent 7855409d`、`worker 38f34a8f` 及所有原门保持。`rollback.json` 记录 `manager_target_restored=50`、未改运行中进程与全局设置。
- **当前无 native、无 keeper**；不重复 poll/restart `48029`、`637`、`7873`。
- 结论：99 未满足原倍率门槛 ⇒ 停止重复 99 配置，不宣称修复、不做因果归因。

## 为什么这是"当前"

| 场次 | 角色 | 终态 | 说明 |
| --- | --- | --- | --- |
| `oayggl_s` | 无探针 manager99 | failed@108004 | 唯一最新的无探针实证，取代一切旧描述 |
| `x39qjvkw` | **有探针**诊断 manager99 | failed@109436 | 历史诊断，不再是最新状态 |
| `5lfbcy43` | **有探针**诊断 manager50 | failed@89468 | 与上者不同 boot，不构成受控配对 |
| `rfw9nmbb` | **带 `group_work_timing` 诊断的** MIXED | failed | 不是无探针场：该诊断标记在即被正式门拒绝 |

两者回调后尾段 `57419470ns`(50) / `54569053ns`(99)、`>=10µs` 组 `653`/`607`、最大 `3368965ns`/`359077ns`、中位均 `45ns`；窗口总 `57554662ns`/`55740918ns`。差异有限、**不同 boot 单次样本**，不能据此宣称修复或因果。

## 运行资源与必须保持的规则

- 冻结组合：AP `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json` `1e6250ef…`；Control `/root/wksim-joint-control-c2IXOr/build.json` `6fe8c0b3…`；Message `/root/wksim-ros2-Rzj3Pf/message-build.json` `29969da0…`。`ZlTVa4` 是旧构建，已失配 8 份当前支持模块。
- PX4 固定 `/root/wksim-px4-state-ONa1Kw/wksim-build.json` `d7e905b3…`，本场模型库 `e59ab914…` 的原准入链；不要给 PV/MIXED 传 PX4 override，两 native 参数必须同时启用。
- 保留 `1ms` tick / native 屏障 / `4tick` 组 / 无追赶 / `100ms` 晚限 / 完整滑窗与全部原物理和身份门。
- 新 native 入口规则：先做两 WSL 进程扫描（`found=[]`、同 boot），再由**入口在启动时**校验 boot 与 ≤60 秒新鲜度；在同一启动器的顺序检查之后，以独立 subprocess 启动即满足要求（`open_self` 的真实启动就是这样完成的），**不要求每次跨工具调用**。禁止终止用户进程或改全局内核/调度。
- 干净 env；Bash 脚本用 Python 写入并清除 CR。ROS 离线审计需要 `/opt/ros/humble`、DDS、AP 消息与 `Rzj3Pf` 环境。
- 已通过飞行不重跑，失败原件不覆盖，不发布厂商源码或 `.so`，只精确 `git add`。

## 仍然成立的门与未完成项

- `#83` 已 CLOSED（`1w6dru32` PV 真实 PASS，详见 [final-combo PV pass](../2026-09-13-final-combo-pv-pass.md)）。
- `#84`、G6、Full 均**未完成**，Goal 不可 complete；正式 mixed 证据集仍为空，`ok=false`。
- G6：三参考首列 product `501/501`、division `429/501`，输出分别 vehicle `72` 处、sensor/GPS `61` 处与 division 形式不同（已推送 `1de316d`）。`aligned` **仅**表示结构对齐，不能据此宣称 G6 通过；缺口仍是有依据且 approved 的**逐量预算**。

- 自线程 perf 能力已实证：32作者检查、13独立用例和超时拒绝反例通过后，实际0.600490334秒记录4次切出/4次切入，无丢失、异身份或畸形；所有自有进程退出。源码SHA `02669b424c04…`，持久构建 `/root/wksim-perf-c-tests-k769545e`。见 [能力实证](../2026-09-13-self-thread-perf-capability.md)。这不证明整场开销或迟到原因；下一阶段录制必须保存raw记录并拒绝overflow。

## 当前任务与负责人

**不在本文件维护负责人表**（重复表会立刻过期）。实时席位、thread/turn、deepLink 与不可用席位只指向
[profile-sync-20260913-01/dispatches.json](../../validation/coordination/profile-sync-20260913-01/dispatches.json)：
该文件记录 5 席在派发时的 `status_at_dispatch=running`（3 DeepSeek + Claude + OMP），以及 CodeBuddy 三席
`quota_blocked`/429（`reset_jst=2026-09-13T20:54:20+09:00`，`retry_submitted=false`）。旧表已删除，不保留副本。

## 历史明细（不删除原件）

以下内容已从本页移出，原件与长段保留在各自提交与文档中；按链接或命令读取，**不删除任何原件**：

- **本页被压缩前的上一版全文**（唯一正确取法）：`git show 820f532:docs/coordination/short-cycle-goal.md`。不要把它与 `short-cycle-goal-history-20260912*.md` 混同：那两个文件是更早（09-12）的历史页，不含本次压缩前的内容，不能当"上一版本页全文"。
- 99 决策/回退/终态/启动/身份：[decision.json](../../validation/coordination/manager99-unprobed-20260913-01/decision.json)、[rollback.json](../../validation/coordination/manager99-unprobed-20260913-01/rollback.json)、[terminal-cleanup.json](../../validation/coordination/manager99-unprobed-20260913-01/terminal-cleanup.json)、[launch.sh](../../validation/coordination/manager99-unprobed-20260913-01/launch.sh)、[pre-run-identity.json](../../validation/coordination/manager99-run-20260913-01/pre-run-identity.json)。
- 调度快照与对比：[owned-scheduling-snapshot-20260913.md](owned-scheduling-snapshot-20260913.md)、[owned-scheduling-comparison-20260913.md](owned-scheduling-comparison-20260913.md)、[codebuddy-owned-scheduling-review-20260913.md](codebuddy-owned-scheduling-review-20260913.md)。
- 工作超额/尾段：[mixed-work-overrun-20260913.md](mixed-work-overrun-20260913.md)、[mixed-work-overrun-20260913-v2.md](mixed-work-overrun-20260913-v2.md)、[main common-prefix result](../../validation/coordination/manager99-run-20260913-01/main-common-prefix.json)。
- 带标记 MIXED 失败与审计器：[group audit FINDINGS](../../validation/coordination/ds-group-audit-20260913-01/FINDINGS.md)、[admission review](../../validation/coordination/cb-admission-review-20260913-01/admission-review.md)。
- 释放等待/直接扩展：[direct release wait](../2026-09-13-direct-release-wait-evaluation.md)、[native release wait benchmark](../2026-09-13-native-release-wait-benchmark.md)。
- G6/模型：[first-step solve boundary](../2026-09-13-first-step-solve-boundary.md)、[diagonal solve experiment](../2026-09-13-diagonal-solve-experiment.md)、[g6-first-step-static](g6-first-step-static-20260913.md)、[g6-first-divergence](g6-first-divergence-20260913.md)、[current wrapper lifecycle](../2026-09-12-current-wrapper-lifecycle.md)。

## 其他接续约束

- G6 同源入口 `tools/run_e0_same_source_conformance.py` 已存在；缺完整获批逐量预算，不能写成入口缺失，也不能用首步240标量对齐代替完整G6。旧R1的5684处失败保留。
- #9 DLL ABI材料仍缺；#102依赖#29/#33真实场景，#62失败后#63/#64未解锁。这些不构成全局停工理由。
- 根heartbeat `wksim` 保持PAUSED，由根Goal协调。卡死任务34386db2的Codex重启尚未获准；不运行重启脚本，不修改Goal数据库或补写turn/end。
- 私有Linux正式准入已同步并提交 `db1200d`：joint_profile.py `575adb530944…`、原测试 `4a7ce076f24f…`；18项Linux测试通过，冻结Control c2IXOr current/sealed两路实际校验通过。只同步两文件且有备份，config/preflight等他方修改未复制。见 [同步收据](../../validation/coordination/profile-sync-20260913-01/receipt.json)。正式MIXED仍缺通过证明。

- 下一步并行模块：自线程有界raw记录器、严格离线消费者、独立17组合成夹具；合同见 [perf-stream contract](perf-stream-contract-20260913.md)。末尾pending LOST的完整性与C启动/停止线程安全仍阻断飞行接线，不能凭collector_complete或无LOST记录宣称无损。
