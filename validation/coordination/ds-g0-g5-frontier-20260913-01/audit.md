# G0–G5 当前收口前沿（只读审计）

- `audit_id`: `ds-g0-g5-frontier-20260913-01`
- `generated_at`: `2026-09-13T22:24:03+09:00`（unix `1789305843`）
- 工作类别：**new-development / read-only closure audit**
- 机器可读主体：[audit.json](audit.json)；实测记录：[checks/checks.json](checks/checks.json)
- 范围：**G0–G5**。排除已关闭 `#83`、由其他代理审计的 `#84`（真实 MIXED perf hook）、`#9`（DLL ABI 分支）与 **G6**。
- 纪律：本文件**不把任何历史 aligned/候选结果写成通过**，不关闭或修改任何 issue，不改共享账本或既有文件；只写本目录，交付后停止写入。

## 0. 开工核验（按 [架构接续合同](../../../docs/coordination/architecture-continuation-20260913.md) 格式）

```text
工作类别：new-development / read-only closure audit（无验收运行）
实际 cwd：C:/Users/PC/Documents/odid编译/wksim
分支：main
HEAD（审计开始时，按任务给定值复核）：7e1e137879a779f2b051b384c044e6e936878d53  ✅ 一致
HEAD（审计期间被并发推进；共观测到 4 个值）：
    7e1e137 → 0239f0e 2026-09-13T22:19:59+09:00 “Record continued DeepSeek closure audit”
            → 09105fa 2026-09-13T22:24:29+09:00 “Record MIXED hook and DLL ABI audits”
            → 33c2b06 2026-09-13T22:26:20+09:00 “Reject perf diagnostics from formal MIXED evidence”
    三次推进均由其他代理在**被排除的分支**（perf/MIXED、DLL ABI）或纯记录上完成：
      0239f0e = +three-deepseek-expansion-20260913-01/continuations.json
      09105fa = +ds-dll-abi-evidence-20260913-01/*、+ds-perf-mixed-hook-audit-20260913-01/*（入库）、
                +three-deepseek-main-review-20260913-02/*
      33c2b06 = Simulator/wksim_runtime/joint_profile.py + validation/test_joint_profile.py
                + validation/test_mixed_profile_admission.py（`#84` MIXED perf 诊断分支；
                `joint_profile.py` 属 main 独占，由该工作触碰，非本审计）
    每次推进后本审计**重新哈希全部 44 个被引用原件，均为 0 处不一致**；其中
    validation/coordination/ds-perf-mixed-hook-audit-20260913-01/audit.json 保持
    5fcb917f3ff9f3769f78d72f723724a4e3bced5a5a974e68ee9b9e6ba36e4ef0 不变。
    **本审计的稳定身份是它自己的 SHA256SUMS，而不是某个 HEAD 值。**
架构祖先检查：git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD
    在上述每个观测 HEAD 下均 exit 0
已读：AGENTS.md、docs/coordination/short-cycle-goal.md、
    docs/coordination/module-delivery-policy-20260912.md、
    docs/coordination/architecture-continuation-20260913.md、
    docs/plan/goal-objective.md、docs/plan/full-migration-spec.md、
    docs/plan/full-scope-expansion.md、docs/plan/full-remaining-ledger.{md,json}
    以及每关对应的 ADR/决策/证据原件（见各关“权威原件”表）
只读核对：gh issue list --repo unununnnn/wksim --state all（163 项：OPEN 23 / CLOSED 140）
本次 module / interface：无代码改动；只读消费既有 interface（证据 JSON、清单、审计器 CLI）
独占文件：validation/coordination/ds-g0-g5-frontier-20260913-01/*
不在本次范围：native、构建、ROS、飞控、模型、UE、MATLAB；#9/#27/#28/#73/#74/#76/#77/#78；G6；#84
受影响测试与实际验收：无实现变更，故无回归义务；本次只新增只读校验脚本与证据
交付：稳定 SHA、实测检查结果、可直接派发的互斥工作包；交付后停止写入
```

工作树非干净（36 项：2 项已跟踪修改 + 34 项未跟踪），全部属于其他代理并发工作，本审计原样保留。

## 1. 结论摘要

| 关卡 | 名称 | 对应 issue（实时） | 最新权威原件所属修订 | 仍失败/缺失的精确门 | 纯 Python/只读可执行 | 需 main 独占 native | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **G0** | 可执行范围 | `#1`/`#10` OPEN（图/规格，本就不关）、`#60` OPEN | 09-07 复核 + 当前台账 | 共享前沿快照过期（仍写 `#83` OPEN）；`#60` 交付物 `docs/plan/full-acceptance-report.md` 不存在 | **是** | 无 | not-closed |
| **G1** | 首期双栈产品闭环 | `#11`–`#18`、`#48` 全 CLOSED | pre-f333316 | 无 open 票；缺的是**在当前架构上重验** | 否（仅身份复核） | 是 | not-closed |
| **G2** | 联合场景 | `#19`/`#21`/`#22`/`#83` CLOSED；`#20`/`#33`/`#62`/`#63`/`#64` OPEN；`#84` 排除 | `#83` 在历史分支 `95da8809`；最新无探针失败在 Linux 私有检出 | 持续 1×：最新无探针场 `oayggl_s` 在 tick 108004 **latch RateUnmet**（`lateness_ns=100644532` ≥ 100 ms）；合同要求 ≥3 个独立 60 s epoch | 部分 | 是 | not-closed |
| **G3** | Prometheus 实验 | `#39`/`#102`/`#33` OPEN；控制模式类票多数 CLOSED | pre-f333316 | 真实规划绕障飞行未做；`#29` AC2/AC3 仍 PARTIAL | 部分 | 是（ROS） | not-closed |
| **G4** | Full 工具与互操作 | `#25`/`#47` CLOSED；`#26`/`#29`/`#46`/`#60` OPEN | 混杂（多处为仓库外 `/root` 构件） | **`#26` 当前检出就绪性实测 `not_ready`（exit 2，5 条违例）**，含 `model.cpp` 源码 pin 漂移；`#46` AC3/AC4；`#60` 交付物缺失 | 部分 | 是 | not-closed |
| **G5** | MATLAB 可选接入 | `#5`/`#41`/`#42`/`#43` 全 CLOSED | `git_head 6d2e371`（pre-f333316） | 协议/双栈实飞/cancel 证据真实且 `ok=true`，但**全部绑定 09-07 修订**，当前架构未重验 | 部分 | 是（MATLAB） | not-closed |

**一句话结论：六关全部 `not-closed`。** G1/G5 的票已全部关闭、G2 的 `#83` 已通过，但**它们的证据全部属于 f333316 之前的修订**；当前唯一在 f333316 之后仍在推进的实跑线是 perf/HOOK（`#84` 范畴，本次排除）。

## 2. 方法与只读边界

- 全部结论来自**直接读取精确文件 + 重新计算 SHA256**；没有任何 SHA 是从其它文档照抄而未在本检出重新哈希。
- 实际执行的三类只读检查：
  1. `verify_frontier.py`：对每关引用的原件逐个重算 SHA256；机械核对 96 行台账；统计能力清单；解析 live issue 快照；**直接 import** `tools/analyze_joint_rate_intervals.py` 对保留下来的 `#83` rate trace 复算。
  2. `tools/audit_26_closure_readiness.py`（仓库自带、纯 Python）：对 `#26` 做当前检出就绪性复验。
  3. `gh issue list --repo unununnnn/wksim --state all`（只读），结果封存为 `issues-snapshot.json`。
- 未执行：native、构建、ROS、飞控、模型、UE、MATLAB；未改动 issue、共享账本、既有文件、模块负责人源码或测试。
- 部分权威原件**不在本检出**（Linux 私有检出/`/root`），只能按记录 SHA 引用，见 XF-4。

## 3. 跨域发现（先读这一节）

### XF-1（高）f333316 架构基线上**没有任何 native 验收证据**

- `f333316` 提交时间 `2026-09-13T17:51:18+09:00`。
- 新架构验收候选回执 `validation/coordination/architecture-candidate-sync-20260913-02/receipt.json`（sha256 `6c276d72…`）自述：`new_head=386f713a…`、`private_wiring_migrated=false`、`native_executed=false`、`architecture_acceptance=false`。
- 已关闭 `#83` 的 PV 实跑执行提交是 `95da8809b7af3c47e42457c6dea0cdb96c563407`；`git merge-base --is-ancestor 95da8809 HEAD` → **exit 1**，`… 95da8809 f333316` → **exit 1**。即该实跑在历史分支 `codex/planner-release-validation` 上，不在当前架构主线。
- 历史对照 HEAD `db1200d…` 对 HEAD 亦 **exit 1**。
- G5 的真实 MATLAB 实飞 `report.json` 记录 `git_head=6d2e371d918f202acd64e822dee4300e86942bcd`（2026-09-07），是 HEAD 的祖先但**早于 f333316**。

**后果**：按接续合同「旧 PASS 不转移给新候选」，G1–G5 全部处于「**某 pre-f333316 修订上确有真实证据，但当前架构未重验**」。这不是说功能失败，而是说验收被绑定在哪个修订上。

### XF-2（中）共享前沿快照 `docs/coordination/acceptance-frontier.json` 已过期

- 该文件（sha256 `885ea287…`）版本 `1.1`、`generated_at 2026-09-12T08:58:00+09:00`，**仍把 `#83` 记为 OPEN**；而本次只读 gh 实测 `#83` 已于 `2026-09-12T18:23:27Z` CLOSED。
- 任何按它派发的动作都会用到被取代的快照。刷新该共享文件属于其现有写入者；本审计只记录漂移，不改该文件。

### XF-3（中）`#26` 当前检出就绪性**实测失败**，且失败点在检出内

`python -B tools/audit_26_closure_readiness.py --manifest docs/plan/26-closure-readiness-manifest.json --output <本目录>/checks/audit-26-closure-readiness.json` → **exit 2 / status `not_ready`**，5 条违例：

1. `build manifest` 记录的 staged 源 `Simulator/wksim_core/model.cpp` 为 sha256 `3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c` / 1864 B，**当前已跟踪文件**为 sha256 `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290` / 4070 B（本审计自行重算确认）。→ `#26` AC1 的“当前检出来源链”存在**真实 pin 漂移**。
2–4. 三个 `/root` 构件（build output library、cold library、cold probe）在本机不可映射 → `#26` AC3 **无法在本检出复核**。
5. 5 个文件名命中“厂商产物”规则的已跟踪文件（`validation/coordination/*/precheck-RflySim-20.04.json`）。

**关于第 5 条的本审计独立阅读**：直接读内容显示这 5 个文件是 WSL 第二发行版的进程扫描前置检查回执（字段 `distro="RflySim-20.04"`、`boot_id`、`uptime`、`found=[]`），是**关于**某发行版的记录，不是厂商源码或二进制。命中是**基于文件名的**。是否收紧检查器或重新归类这些文件，属于模块负责人的决定；本审计不作判断，也不修改任一文件。

### XF-4（信息）部分权威原件不在本检出

- 最新 G2 失败原件 `joint-public-flight-oayggl_s` 在本检出**完全不存在**（全树 0 个匹配），其 SHA 只记录在 `docs/coordination/ds-architecture-mixed-migration-20260913.md` §2.2（`result.json e9ac61dc…`、`rate.jsonl d65849e6…`、`manager-gc-candidate.json 614ccd05…`）。
- `#26` 的 lifecycle 库与 cold 构建 probe 仅在 Linux `/root`。

**后果**：对这些原件做复核必须进入 Linux 私有检出；本审计明确标记为 external，不冒称已在本检出校验字节。

## 4. 逐关前沿

### G0 可执行范围 — `not-closed`

**退出条件**（`docs/plan/goal-objective.md:23`）：已批准规格、验收接缝、逐票阻塞关系和运行能力清单；每项需求有票据或明确待决策归属。

**issue**：`#1`（Wayfinder 图，设计上不关）、`#10`（已批准规格父票，未关）、`#60`（最终 Full 复核，唯一还能交付的 G0 票）全部 OPEN。

**已证明的最新权威原件与 SHA**

| 原件 | SHA256 | 角色 |
| --- | --- | --- |
| `docs/plan/goal-objective.md` | `e035a9a467708fd0240a39866f56d69ca64fa58a4a1e555c0c0aac1894d020a5` | G0–G6 退出条件（本审计全部关卡的规范来源） |
| `docs/plan/full-migration-spec.md` | `384335c180e7f7fca6d87332318e5defe94caf3969ec93ffeda277d004350542` | 已批准规格：48 故事 + 10 条验收接缝 |
| `docs/plan/full-scope-expansion.md` | `85c15ad817afe35fcd325435f02ccb894ad33015e223537daa3cc3706a564fee` | 48 行 Full 扩展范围 |
| `docs/plan/full-remaining-ledger.json` | `61a58c9065d5f6b0f243aa49cbd476f38a17ce29c7bf12175c194ba582c51b54` | 96 行台账 + G0–G6/HARDWARE-HITL 保留行 |
| `docs/plan/full-remaining-ledger.md` | `95d4439f4bec9f274b369f52f5760235a6ff2e6c82e8228a81317c752f3a47b5` | 人类可读台账与闸门表 |
| `docs/plan/lunar-issued.json` | `07b110cd0a05811b12adabe44ce8ef34d2eeb409900615413efb37f09ad79923` | 已发布票与阻塞关系记录 |
| `docs/plan/published-issues.json` | `a63005c7fd959b0c19c9d9801f2657e073a85b5580c049114fdac8c01e706c90` | 原生阻塞边逐条核对所依据的发布清单 |
| `Simulator/wksim_runtime/capability-index.json` | `9089b99197147a27859b04b49701fad7a11c4fbebac1435938996f76f9207b02` | 运行能力清单（87 项） |
| `docs/2026-09-07_accelerated-integration-report.md` | `85cfe6b9d33e7388a86e2ff94b667c44659a7d6f01f620421cad3bfbf374f0b0` | **唯一一次** G0 只读复核（48 故事有归属、38 票 87 条阻塞边一致），修订为 pre-f333316 |
| `docs/coordination/acceptance-frontier.json` | `885ea287c58ee412a1577cff18428a8b9425ff4b70e0c0ed9433bf18d46a16c2` | 共享前沿快照，**已过期**（XF-2） |
| `docs/plan/full-acceptance-report.md` | **不存在** | `#60` 声明的交付物 |

**已证明**：台账机械自洽（96 行 / 96 唯一 id / 源 id 集合 = 台账 id 集合 / 无重复，本次复算 `True`）；分类计数与声明结构完全一致（US 48、SIM 12、COMM 7、MODEL 16、OPS 13）；7 条闸门行 + HARDWARE-HITL 边界行均在，状态均为 `preserved-not-complete`，96 行按台账自述**全部仍是 gap**；能力清单存在且可解析（87 项）。

**仍失败/缺失的精确门**：共享前沿快照过期；唯一一次 G0 复核是 pre-f333316 且未在新架构重跑；`#60` 交付物不存在。按台账自身规则，发布规格或接口占位不算验收。

**纯 Python/只读可执行**：**是**（台账核对、能力清单解析、gh 只读回读与过期比较，均已完成）。
**下一条最小可执行命令**：`python -B validation/coordination/ds-g0-g5-frontier-20260913-01/verify_frontier.py`
**需 main 独占 native**：无。
**依赖**：上游无；下游为所有其它关。`#60` 在 `#9`/`#20`/`#59` 未解前只能产出“未解决清单”，不能产出通过结论，也不能关闭 `#1`/`#10`/Goal。

### G1 首期双栈产品闭环 — `not-closed`

**退出条件**（`:24`）：同一配置/任务入口分别选择 PX4 与 ArduCopter，启动、飞行、UE 查看、停止、回看；真实双栈任务与独立真值；产品节点发送控制、观察者静默；UE 不是诊断日志尾读依赖；无 MATLAB/Gazebo/原版程序亦可运行；子进程隔离收尾。

**issue**：`#11`–`#18` 与 `#48` **全部 CLOSED**（`#48` 于 `2026-09-08T17:35:14Z`）。

**已证明的最新权威原件与 SHA**

| 原件 | SHA256 | 角色 / 修订 |
| --- | --- | --- |
| `docs/2026-09-07_joint-product-entry-report.md` | `bacee32ca37ca0464c6fff36afa994f767a5a24fd71dcab105e16d63d94df51a` | 真实联合产品入口：公开入口、双栈、无 CopterSim/Gazebo/MATLAB 运行库、进程身份前后实读、干净退场（pre-f333316） |
| `docs/2026-09-06_joint-public-flight-report.md` | `3960e7611450520473463b959333fc007e477ed745f39f5d0576efa59ce2caa6` | 首个公开入口下的真实连续联合飞行证据（pre-f333316） |
| `docs/2026-09-07_accelerated-integration-report.md` | `85cfe6b9d33e7388a86e2ff94b667c44659a7d6f01f620421cad3bfbf374f0b0` | 加速整合轮，含显示接缝与清理实读（pre-f333316） |
| `docs/2026-09-13-final-combo-pv-pass.md` | `d3c70b49da4f090748ee19fc6101d0d86f5021b5daafef1ede5ef15dd146e512` | 最新的限定双栈公共任务（`#83` PV 切片），修订 `95da8809`（历史分支） |

**已证明**：真实双栈公开入口运行 + 独立真值存在；这些运行记录了进程身份与映射检查，并报告未加载 CopterSim/Gazebo/MATLAB 运行库；`#48` 首期集成票已关闭；`2026-09-13` 限定 PV 运行保持原门（单锚 0.5×、1 ms、4 tick 屏障、无追赶），最坏累计迟到 89,299,145 ns < 100 ms。

**仍失败/缺失的精确门**：所有 G1 原件都绑定 pre-f333316 修订，**当前架构上没有 G1 运行**（XF-1）；“产品节点发控/观察者静默”与“UE 非诊断尾读”两条属性只在历史修订上成立，未在当前架构重演。**没有 G1 专属 open 票，因此 G1 最容易被误判为已完成。**

**纯 Python/只读可执行**：否（仅身份/SHA 复核可只读完成）。
**下一条最小可执行命令**：只读 `verify_frontier.py` 重哈希 G1 原件；关门需要当前架构上的真实双栈产品入口运行（main 独占 native）。
**需 main 独占 native**：双栈产品入口飞行、UE 显示观察与停止/回看、WSL 双发行版前检与入口 boot/新鲜度校验。
**依赖**：上游 G0；下游与 G2 共用联合入口。**需 owner 决策**：或在 f333316 候选上重跑已接受的 G1 切片，或明确把其归类为历史对照并单列迁移验收义务——接续合同默认是前者。

### G2 联合场景 — `not-closed`

**退出条件**（`:25`）：一个 PX4 与一个 ArduCopter 共享物理场景与唯一权威仿真时间，含暂停/单步/继续/倍速、掉队和重置证据。

**issue**：OPEN `#20`（父容器）、`#62`/`#63`/`#64`（三个 1× epoch，串行依赖，`#62` 现处 `needs-triage`）、`#33`；CLOSED `#19`/`#21`/`#22`/`#83`；**排除** `#84`。

**已证明的最新权威原件与 SHA**

| 原件 | SHA256 | 角色 |
| --- | --- | --- |
| `docs/2026-09-07_joint-rate-contract-accepted.md` | `6a68840d3cb5612cba921468a370014b38e1416c81d6dc2c9c41ebc816ff71ab` | 已批准倍率合同：每档 ≥3 独立 epoch、各 ≥60 连续墙钟秒、10 s 窗 ±2%、完整 60 s 段 ±1%、累计相位迟到 ≤100 ms |
| `docs/2026-09-09-final-combo-pv-plan.md` | `b24703244351709ddda84f9c70120ece58bf86fcc41b0b82c68ba03527139440` | 冻结的最终组合 PV 调用与预先声明的门 |
| `docs/2026-09-09-mixed-flight-plan.md` | `9dc3809c16909b30a06510ffea34c91c62f1225d4b6956e45712638a0d6a322f` | MIXED 计划，沿用同一窗口门 |
| `docs/coordination/short-cycle-goal.md` | `d6339f23b61e3b1fee4e5d729b283bf1378da2622d9538a8ce29affaa606c71c` | 当前检查点：最新无探针失败身份、无 native/keeper、停止重复 99 配置 |
| `validation/coordination/manager99-unprobed-20260913-01/decision.json` | `6fd265b76d50130171cb68d6179638d139576219c0e01e32692d132ed314df34` | 无探针 manager99 配置的决策记录 |
| `validation/coordination/manager99-unprobed-20260913-01/rollback.json` | `5b6413ef7cc46f5a52ed41c2aa3e8df2a69a4103710c1e648b631ebc9525b91b` | runner 回退收据 `9b97c124…` → `1c600d7f…`，manager 目标恢复 50 |
| `validation/coordination/manager99-unprobed-20260913-01/terminal-cleanup.json` | `0222ee2445c119fddfb2c79219b03e105d25cde2922e5719455dfadb07acbcc5` | 终态清理：无存活 native 进程、无 keeper |
| `docs/coordination/ds-architecture-mixed-migration-20260913.md` | `f3cbe35a996167217a03fdf6a883b697c9fd20de6f36e6d85b7aa150878c1741` | 唯一按 SHA 标识**不在本检出**的 `oayggl_s` 原件（`result.json e9ac61dc…`、`rate.jsonl d65849e6…`、`manager-gc-candidate.json 614ccd05…`）并附重算算术语境 |
| `validation/33-final-combo-luna/pv-settle-1w6dru32/bundle-manifest.json` | `4663185be8b74b41801b17669f55a0b3ff15f551e3650eef5a28701fce3c3d8b` | `#83` 已关闭 PV 运行的 Windows 保留包（含冻结审计器源码） |
| `validation/33-final-combo-luna/pv-settle-1w6dru32/rate.jsonl.gz` | `f7d1a5318c83cd6cec9fe42d5437549e46f6b054519e616d2924432b957fabe1` | 本审计**独立复算**的保留 rate trace |

**本审计对 G2 的独立只读检查**：用仓库自带 `tools/analyze_joint_rate_intervals.py`（sha256 `1c43ac9c4b80f2dcc8eb52ffd9c3fe061f5cd2ef9206d839fe20e7af2f783fc7`）直接 import 复算保留 trace（解压后 sha256 `92a415dfb85e136f154ba56eef1028b24ac0a3c107e265b7e3d066b705aa4283`，22,640,267 B）：`status=analyzed`、`groups=28992`、`intervals=28991`、`creep_total_ns=87617368`、`work_over_total_ns=12423738`、`release_excess_total_ns=75193630`、`first_group_start_lateness_ns=111393`、**`latch_status=unavailable`（该保留字节内不存在 `rate_unmet` latch）**。
**含义**：与 `#83` 记录的 PV 通过一致，区间算术闭合。这**只**重新推导区间算术，**不把任何 PASS 转移给 f333316 架构，也不是持续 1× 的验收**。

**已证明**：倍率合同门值已冻结；`#83` 限定最终组合 PV 切片在冻结历史分支上通过（最坏累计迟到 89,299,145 ns < 100,000,000 ns；27,493 个完整 10 s 窗最大相对误差 0.001305497 < 0.02；21,245 个完整 60 s 窗最大 0.000513893 < 0.01）；本审计独立复算保留 trace（28,992 组 / 28,991 区间、无 latch）；`#19`/`#21`/`#22` CLOSED；runner 回退已记录，无残留 native 进程或 keeper。

**仍失败/缺失的精确门**：

- 持续 1× 未达：最新无探针 manager99 场 `oayggl_s` 于 tick 108004 **latch `RateUnmet`**，`lateness_ns=100644532` ≥ `LATE_LIMIT_NS=100000000`，`wall_seconds=268.721856341`，`error=RateUnmet('rate_unmet/resource_insufficient')`。单 boot 单样本，**不作因果归因、不重跑该配置**。
- 合同要求每档 3 个独立 60 s epoch；`#62`/`#63`/`#64` 全部 OPEN 且串行依赖，`#62` 处 `needs-triage`。
- `oayggl_s` 原件不在本检出，只能按记录 SHA 引用（XF-4）。
- 当前架构上不存在 MIXED/perf-hook 接线——那正是被排除的 `#84` 范畴。
- 整个 G2 结果集受修订绑定（XF-1）：`#83` 的通过发生在历史分支。

**纯 Python/只读可执行**：**部分**——对既有 trace 的窗口/latch 算术复算可只读完成（本次已完成 `#83`）；决定性的 epoch 与 boot/新鲜度前检必须 native。
**下一条最小可执行命令**：只读 `verify_frontier.py` 复现 `#83` 区间复算；关门则是**一次**冻结组合的无探针 MIXED 运行（1 ms tick / 4 tick 组 / 无追赶 / ≤100 ms 迟到 / 完整滑窗 / `source_unchanged`），在两会话 WSL 前检（`found=[]`、同 boot、≤60 s 新鲜度）之后由 main 独占执行。
**需 main 独占 native**：`#62`/`#63`/`#64` 持续 1× 空中 epoch、1 ms/4 tick/无追赶原生屏障调度、双发行版 WSL 前检与入口 boot/新鲜度校验、冻结 AP mixed/Control/Message 身份准入。
**依赖**：上游 G0、`#8`（CLOSED）、`#19`（CLOSED）；串行链 `#62 → #63 → #64`（失败即保持 OPEN 并阻塞下一 epoch）；下游 `#33` 供 G3 规划器与 `#46` AC4，`#46`（G4）形式上被 open `#20` 阻塞。`#84` 由他方审计，本前沿不消费其结论。

### G3 Prometheus 实验 — `not-closed`

**退出条件**（`:26`）：按迁移矩阵执行控制模式、单机/多机任务、规划/感知 demo，支持/拒绝能力与动作完成均有真实证据。

**issue**：OPEN `#39`（父）、`#102`（子）、`#33`（与 G2 共用）；CLOSED 含 `#12`/`#15`/`#25`/`#30`/`#31`/`#32`/`#34`/`#35`/`#36`/`#37`/`#38`/`#40`/`#44`/`#45`/`#47`/`#48`/`#104`。

**已证明的最新权威原件与 SHA**

| 原件 | SHA256 | 角色 |
| --- | --- | --- |
| `docs/plan/29-terrain-closure-report.md` | `edff1cd2d9a77ea218937616b512a964deb40e42d47a91b6c7a24392ff1cfcd6` | 地形/接触 AC 映射：AC1/AC4/AC5 在各自声明层 PASS，AC2/AC3 PARTIAL；`#29` 仍 OPEN |
| `docs/plan/102-trajectory-scene-admission-contract.md` | `cf0042f4db2aa32de82bc7725362403eb24b240bb2d2651ca2ff74fff9ab5b24` | 规划器轨迹路径的冻结准入合同 |
| `docs/coordination/next-acceptance-goal.md` | `566a6b9d3217e3f24e0044865da9b20efdb536321dd99c5491e3d14212944c4a` | M2 陈述：真实 11,000 点云与 GridMap 占用已验证；真实 ROS1 反向状态/共享 clock 与真实规划绕障仍缺（pre-f333316） |

**已证明**：控制模式与实验批次多数已 CLOSED（速度/偏航、姿态/推力、PID、UDE、NE、RC、ArUco、电机效率、GNSS、RGB、深度点云、全球航点、相机跟踪入口）；场景/地形表示与陈旧反馈合同在声明层有 PASS 记录，并附静态接触审计（85 assertions / 13 cases / pass）；规划路径的**地图输入半程**已记录（完整 EGO 构建与真实 11,000 体素进入 GridMap 占用，且静态 odom 被明确标注为夹具）。

**仍失败/缺失的精确门**：真实规划绕障未完成——`#102` 仍缺 map → planner → 公共控制 → 真实飞行，且需在实飞中验证到达、无接触、净空、取消/无路/重规划与严格递增命令 ID；`#29` AC2（闭环接触力/坡度/侧碰动力学）与 AC3（真实 UE 断开/重连与实时视觉/物理绑定）仍 PARTIAL；`#29` 额外被排除的 `#9` 与 open `#33` 阻塞，故 G3 规划分支同时继承 G2 节奏链与 ABI 决策；规划材料为 pre-f333316 修订，未在新架构重验。

**纯 Python/只读可执行**：**部分**（复验冻结点云/GridMap 占用证据、重跑地形静态审计）。
**下一条最小可执行命令**：只读复跑冻结静态地形/接触审计与重哈希规划原件；关门需构建完整 EGO 并把冻结 11,000 点云经准入泵送入 `TrajectorySession`，再在实飞中验证真实净空——ROS + main 独占 native。
**需 main 独占 native**：ROS1 EGO 规划器节点与真实点云话题、真实轨迹执行与净空/接触观测、`#33` 双栈混合轴飞行、`#29` AC3 真实 UE 断开/重连。
**依赖**：上游 G0、G2（`#33`）、G4（`#29` 场景联动）、`#9`（排除，`#29` 的形式 Blocked-by）；下游 `#102` 供 `#39` 父票。

### G4 Full 工具与互操作 — `not-closed`

**退出条件**（`:27`）：配置、模型/场景导入、CLI/NoUI/UI、协议、日志、故障和公开模式逐项可操作；缺口不能隐藏。

**issue**：OPEN `#26`/`#29`/`#46`/`#60`；CLOSED `#16`/`#24`/`#25`/`#47`/`#55`/`#56`；**排除** `#9` 与整个 ABI 分支 `#27`/`#28`/`#73`/`#74`/`#76`/`#77`/`#78`。

**已证明的最新权威原件与 SHA**

| 原件 | SHA256 | 角色 |
| --- | --- | --- |
| `docs/plan/full-remaining-ledger.json` | `61a58c9065d5f6b0f243aa49cbd476f38a17ce29c7bf12175c194ba582c51b54` | 96 行全部仍声明为 gap |
| `docs/plan/26-closure-readiness-manifest.json` | `229eb94c8bc4cec71693719b32ad86f716b8a92ac4a2e19b541fc701bc72a1d7` | 自述当前检出就绪性未主张，关闭被 OPEN `#9` 的形式 Blocked-by 阻塞 |
| `docs/plan/26-generation-contract.md` | `6a8e7eace06581bcd74d7e68a017bcffcc60c74c862172c058f6e149e2855d20` | 记录 `blocked_source_authorization_and_generation_entry` 结论 |
| `docs/plan/26-current-wrapper-recheck-plan.md` | `5f3b7f4178bff503fc79a58e85ae2c40465997c3d635eeb804be4196e05b0728` | 计划中的当前检出 wrapper 重核 |
| `validation/codegen-e0-lifecycle-01/audit.json` | `3d5c7896de10d10521ff4a1881eaffc8c96e73b196be72f9a044f2fc1aed346d` | 无 MATLAB 生命周期审计：`status=pass`、4 cycles、480,000 比较值、两个独立进程身份；**库本体在 `/root`（仓库外）** |
| `docs/2026-09-09-numerical-conformance-report.md` | `82539300993f12fc6509e35ad8147caa57a2777d84e9a1aafac2a6a22c2d4561` | R1 仍 `numerical_failed`：180,360 值中 5,684 不等，涉及 49 个 case/轴；保留不改判 |
| `docs/coordination/ds-full-frontier-20260912.json` | `3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4` | 同分支的前序槽位审计 |
| `validation/coordination/three-deepseek-main-acceptance-20260913-01/main-verdict.json` | `a1d2fd695ff6508f877909d653c9c4a5d099ca15ed3a6ea44fc14c5720f79251` | 三项组件交付的主会话判定 |
| `validation/coordination/three-deepseek-main-acceptance-20260913-01/linux-receipt.json` | `98f6dd0bfc7fa28a3070dfe77b349badf958b3fbb05a8c40d5a375a527ecca6b` | 64 项 Linux 检查通过，受测源码未变、进程已清理 |
| `docs/2026-09-13-three-deepseek-delivery.md` | `88684f69ef215813428e211b95a499c2c58bcabc57e81a68a1a7ee5038e83271` | 明确这些组件检查**不完成 G4/#46**，且不转移旧飞行 PASS |

**本审计对 G4 的独立只读检查**：`tools/audit_26_closure_readiness.py` 复验 → **exit 2 / `not_ready`**，5 条违例（逐字见 `checks/audit-26-closure-readiness.json`）。本审计另行重算确认 pin 漂移：`Simulator/wksim_core/model.cpp` 记录 `3f325678…`/1864 B 对当前 `150ddf3b…`/4070 B。

**已证明**：生成模型链（生成、编译、无 MATLAB 生命周期）有冻结本地证据与 pin/SHA，生命周期审计 `pass`、4 cycles、480,000 比较值、两个独立进程身份；生成模型源未提交进库；三项独立组件交付（实验/部署输入身份、Ackermann 响应上界、有界离线回放）在 Linux 通过 64 项检查（Windows 同组 64 项中 1 项权限相关 symlink 跳过、由 Linux 覆盖）；三个诊断开关与交付入口契约的 Windows 边界检查有绿色记录。

**仍失败/缺失的精确门**（本次实测）：

- `#26` 当前检出就绪性检查失败（XF-3），含 `model.cpp` **真实源码 pin 漂移**。
- `#26` AC5 仍无主代理复核/批准记录；`#26` 形式上被排除的 open `#9` 阻塞。
- `#26` AC3 在本检出**完全无法复核**：pinned 库/probe 仅存在于 `/root`。
- `#46` AC3 无“预先声明的工程误差预算”（零容差相等来自冻结静态 profile，不是声明的误差包络），AC4 的暂停/单步身份半程属于 open `#20`；`#46` 形式上被 `#20` 阻塞。
- `#29` AC2/AC3 仍 PARTIAL（见 G3）。
- `#60` 声明的交付物 `docs/plan/full-acceptance-report.md` 不存在；在 `#9`/`#20`/`#59` 未解前 `#60` 只能产出“未解决清单”。
- R1 仍 `numerical_failed`、5,684 个失败值保留；**不得**读作向 G6 的进展。

**纯 Python/只读可执行**：**部分**（`audit_26_closure_readiness.py`、台账/manifest pin 重哈希、5 个 `precheck-RflySim-20.04.json` 的内容归类，均已完成）。
**下一条最小可执行命令**：`python -B tools/audit_26_closure_readiness.py --manifest docs/plan/26-closure-readiness-manifest.json --output <新路径>`
**需 main 独占 native**：当前架构上的生成模型构建/导入；任何真实固件互操作或 DLL 宿主生命周期（排除分支）；`#29` 的闭环接触/坡度动力学与真实 UE 断开/重连。
**依赖**：上游 G0、`#9`（排除，人工决策，阻塞 `#26`/`#27`/`#28`/`#29`）、`#20`（阻塞 `#46`）、`#16`/`#24`（CLOSED）；下游 `#60` 汇总全部。**需 owner 决策**：`#9`。

### G5 MATLAB 可选接入 — `not-closed`

**退出条件**（`:28`）：在已确认范围使用真实 MATLAB 客户端与可选 TCP/JSON 桥，覆盖断开、粘包/碎片、非法输入、身份、超时与不重放；本机版本/许可实际验证；缺许可时明确阻塞，不能用其它客户端冒充 MATLAB 通过。

**issue**：`#5`、`#41`（`2026-09-06T22:27:50Z`）、`#42`、`#43` **全部 CLOSED**。

**已证明的最新权威原件与 SHA**

| 原件 | SHA256 | 角色 |
| --- | --- | --- |
| `docs/matlab-bridge.md` | `8814656101378ed61096f39b933ccb54c508e759559b4cd0125731520c62a6e7` | 协议 v1 合同、白名单、错误语义与本切片自述的未验证清单 |
| `docs/plan/tickets/31-matlab-bridge.md` | `54f73ecb5217ea2380192be80fe16f1207ec57bc460e5c2b13ad0b3226f1fb40` | 桥定义票 |
| `docs/2026-09-07_accelerated-integration-report.md` | `85cfe6b9d33e7388a86e2ff94b667c44659a7d6f01f620421cad3bfbf374f0b0` | 双栈真实 MATLAB 实飞 + 独立原始审计 + 两个篡改反例（pre-f333316） |
| `validation/matlab-bridge-20260907-run1/report.json` | `e5278e22853930c4cd8f9a0e5f29a0b4f35ac2c86f6564cab593084c38abf607` | 桥协议运行，`ok=true`，未启动任何作业；真实 MATLAB `9.13.0.2049777 (R2022b)`、PCWIN64、`license('test','MATLAB')=1`、exit 0 |
| `validation/matlab-bridge-20260907-isolated/report.json` | `e44f116ecb45914d6ae4942f79587e98c85d9cc08ae1eb1bb58be551ac7c4c7d` | 使用私有 `startup.m` + `-sd` 的隔离重跑，`ok=true` |
| `validation/matlab-flight-px4-20260907-run3/report.json` | `06547df09b261c89561c9286299ef08cad1bec05033cdb2306dc7b91c0798f47` | 真实 MATLAB → 公开 Console HTTP → WSL 真实 PX4 飞控/物理；`ok=true`；`git_head=6d2e371…` |
| `validation/matlab-flight-ap-20260907-run2/report.json` | `823c9602c1a83f145e0909bf3a26050d3ddc17b2f2de8c6d0475cbd9260cbf9c` | 同链路的 ArduCopter 案例；`ok=true`；`git_head=6d2e371…` |
| `validation/matlab-cancel-px4-20260907-run1/report.json` | `01d83dc3bcfbc9235f5cb015a6a75025e7fbc4836ee375c0a2b84c089c192440` | 真实 MATLAB 客户端 cancel + 正常自主 LAND；`ok=true`；MATLAB pid 已退出 |
| `validation/migration-resume-20260907/matlab-flight-audit-verified.json` | `bec351cee25eb01fd120a1cc30f46710357717a8020bec0fcfe140fba1481c36` | 独立审计：重算物理窗并核对公共请求、原生确认、任务动作文件与 UE Actor 误差 |

**已证明**：真实本机 MATLAB 客户端已实际执行并核验（版本、平台、许可、exit 0）；协议边界集合已实测且为绿（碎片/粘包、旧会话/重复 ID、未知方法、非法 JSON/NaN/Infinity/溢出/重复键/非法 UTF-8/超长帧拒绝、超时/断开、重连零重放）；经桥的双栈真实实飞完成且 `ok=true`，MATLAB 退出后主 SITL 继续（PX4 run3 与 AP run2，`git_head=6d2e371`），并有独立审计重算物理窗；真实 cancel/LAND 案例记录且 MATLAB 进程确认退出；四个 G5 issue 实时均为 CLOSED。

**仍失败/缺失的精确门**：

- 全部 G5 证据绑定 main 提交 `6d2e371`（2026-09-07），**早于 f333316 架构基线**（2026-09-13T17:51）；G5 未在当前架构重验（XF-1）。
- `docs/matlab-bridge.md` 自身边界段声明该切片未验证 MATLAB 触发的预检/起飞/航点/暂停/恢复/取消/日志回看、飞行中断开后主 SITL 继续、以及 G5 整体；后续运行覆盖了其中一部分，故这些条目在**当前架构上的逐项映射仍为未证**。
- 首次真实 MATLAB 启动经用户 `Documents/MATLAB/startup.m` 触发了外部 RflySim 配置更新；启动前文件集未知且未回滚。后续运行改用私有 `startup.m` + `-sd` 与 `which()` 断言。这是**已记录、未修复**的环境副作用。
- 本审计环境禁止 MATLAB，故本次无法推进关门。

**纯 Python/只读可执行**：**部分**（重哈希并重读保留的 MATLAB 审计 JSON、抽取 `git_head` 并做祖先判定，均已完成）。
**下一条最小可执行命令**：只读 `verify_frontier.py` 重哈希 G5 原件；关门需要在当前架构上用私有 `startup.m` 隔离跑一次真实 MATLAB 客户端——main 独占 MATLAB + native，本审计环境禁止。
**需 main 独占 native**：真实 MATLAB 执行与许可检出、公开 Console HTTP 背后的真实 FC/SITL、显示相关案例的 UE 观察。
**依赖**：上游 G0、`#5` 决策（CLOSED）；下游无（MATLAB 明确可选，不得阻塞 SITL 核心）。**需 owner 决策**：已关闭的 `#41`/`#42`/`#43` 验收是保留为历史，还是必须在 f333316 候选上重演。

## 5. 排除项（各自的原因与残留警示）

| 排除对象 | 当前状态 | 排除原因 | 残留警示 |
| --- | --- | --- | --- |
| `#83` | CLOSED `2026-09-12T18:23:27Z` | 审计开始前已关闭；其限定 PV 切片仅作为区间算术的保留原件交叉核对 | **不得**把 `#83` PASS 读成 G2 或 `#33` 通过；其报告自述不完成 `#84`/`#33`/Full/G0–G6、加速度执行、yaw-rate、其它原生边界与 G6 零预算失败 |
| `#84` | OPEN（`ready-for-agent`） | 真实 MIXED 提升/perf hook 接线，正由其他代理只读审计（`validation/coordination/ds-perf-mixed-hook-audit-20260913-01/`，`audit.json` sha256 `5fcb917f…`，本审计期间入库且内容未变） | G2 关门需要 `#84` 持有的 MIXED 能力证明；本前沿只记录依赖，不评判其结果 |
| `#9` | OPEN（`wayfinder:grilling`） | 可选模型插件/场景反馈决策（未知厂商 RflySim DLL ABI），是**人工决策**而非代理可执行任务 | ABI 分支 `#27`/`#28`/`#73`/`#74`/`#76`/`#77`/`#78` **全部 OPEN 且带 `ready-for-agent`**，但在 `#9` 未决前**不可派发**；`#28` AC3 的“批准预算”还依赖被排除的 G6 逐量预算链。本审计期间 `validation/coordination/ds-dll-abi-evidence-20260913-01/` 被提交入库（他方），本审计**未读取也未评判** |
| G6 | `preserved-not-complete` | 按指示排除 | 保留指针：`docs/plan/10-g6-remediation-contract.md`（`48da61ad…`）、`docs/plan/59-e0-dynamic-budget-source-map.md`（`35a56084…`）。R1 `numerical_failed` 与 5,684 个失败值**不得**重新解释；结构 `aligned` 不是 G6 通过 |

## 6. 最短收口顺序

| # | 关卡 | 动作 | 为何在此位置 | 现在阻塞在哪 | 需 native |
| --- | --- | --- | --- | --- | --- |
| 1 | **G0** | 只读刷新前沿 + 产出 `#60` 式“未解决清单” | 唯一无上游依赖、可在无 native 下推进的关；所有派发都读它的前沿 | 共享快照过期（XF-2）、`#60` 交付物缺失 | 否 |
| 2 | **G2** | 决定并执行持续倍率路径：一次一个冻结组合无探针 epoch（`#62` → `#63` → `#64`） | 关键路径：`#20` 阻塞 `#46`、`#33`，并经 `#33` 阻塞 `#102` | 最新无探针 epoch latch `RateUnmet`（100,644,532 ns）；仍需 3 个 epoch | **是** |
| 3 | **G1/G5/G2/G3/G4 证据** | 架构重验决策：在 f333316 候选上重跑已接受切片，或明确归类为历史并单列迁移验收义务 | XF-1：现有 G1–G5 PASS 全属 pre-f333316 修订，不做此决策任何关都无法在当前架构关闭 | 候选回执 `native_executed=false`、`architecture_acceptance=false` | **是** |
| 4 | **G4** | 处理 `#26` 当前检出 pin 漂移与 AC4 归类，然后在当前检出重验 `#26` AC1–AC5 | 现在就能用纯 Python 执行，且独立于倍率链；只有形式关闭等 `#9` | `model.cpp` pin 漂移；5 个 AC4 文件名命中待裁定；AC5 复核记录缺失 | 否 |
| 5 | **G4/G3** | `#29` AC2/AC3（闭环接触/坡度动力学、真实 UE 断开/重连）与 `#20` 之后的 `#46` AC3/AC4 | `#46` 依赖步骤 2；`#29` 依赖被排除的 `#9` 决策与步骤 2 的 `#33` | AC 仍 PARTIAL；`#9` 未决 | **是** |
| 6 | **G3** | `#102` 真实 点云 → GridMap → 规划器 → 准入泵 → `TrajectorySession`，再实飞验证净空；随后收 `#39` 父票 | `#102` 自身前置含 `#29` 与 `#33` | 地图输入已验证，但无真实反向状态/共享 clock 链路，也无真实规划绕障飞行 | **是**（ROS） |
| 7 | **G0/G4** | `#60` 最终 Full 复核：逐行验收或产出显式“未解决清单”保持 `#1`/`#10`/Goal 开放 | `#60` 前置含 `#9`/`#20`/`#26`/`#27`/`#28`/`#29`/`#33`/`#46`/`#59` | 以上全部 | 否 |

## 7. 可直接派发的互斥工作包

每个包的**一个文件只有一个写入者**；包与包之间文件集不相交。

| 包 | 关卡 | 标题 | 类别 | 独占范围 | 依赖 | 验收 | 纯 Python/只读 | 需 native |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **WP-1** | G0 | 刷新可执行前沿并产出 `#60` 式未解决清单 | 只读分析 + 新独占目录 | 仅 `validation/coordination/<新目录>/**`；**不**触碰 `docs/coordination/acceptance-frontier.json`、`docs/plan/full-acceptance-report.md` 或任何 issue | 无 | 纯 Python 核对 + gh 只读回读 | ✅ | 否 |
| **WP-2** | G4 | 裁定 `#26` 当前检出 pin 漂移与 AC4 文件名命中 | 只读分析（修复归模块负责人） | 仅新证据目录；只读 `tools/audit_26_closure_readiness.py` 与 pinned manifest | 无 | `python -B tools/audit_26_closure_readiness.py --manifest … --output <新路径>` | ✅ | 否 |
| **WP-3** | G2 | 一次一个执行持续倍率 epoch（`#62`→`#63`→`#64`） | **main 独占 native** | 各票声明的 `validation/lunar-20-epoch-{1,2,3}/**` | `#61`（CLOSED）、冻结组合 `1e6250ef`/`6fe8c0b3`/`29969da0`、双 WSL 前检 | 原 100 ms + 完整 10 s/60 s 窗 + 独立原始审计与清理 | ❌ | **是** |
| **WP-4** | G3 | 接入真实规划器并验证一次真实绕障（`#102`） | ROS + **main 独占 native** | `validation/39-planner-flight/**`、`docs/plan/39-planner-run-contract.md`；**不**触碰 `#29`/`#33` 文件 | `#101`（CLOSED）、`#29`、`#33` | 冻结障碍 AABB 上的真实净空观测；离线路径与既有场景渲染不关闭父票 | ❌ | **是** |
| **WP-5** | G2/G3 | `#84` 真实 MIXED 提升与 perf hook 接线 | **排除** | 由现有负责人持有；本前沿不派发也不重复 | — | — | — | **是** |
| **WP-6** | G1/G5（及 G2/G3/G4 的 native 主张） | 在 f333316 验收候选上做架构重验 | **main 独占 native** | 候选检出 `/root/wksim-architecture-acceptance-20260913`（分支 `codex/architecture-acceptance-20260913`）自己的证据目录（独立检出，不与本 Windows 树冲突） | 私有接线迁移决策（manager-GC flag、owned-snapshot 开关）、候选 HEAD 同步 | 原门 + 接续合同的派发核验清单 | ❌ | **是** |

## 8. 禁止声明（写进任何后续派发与报告）

1. 不得把任何 G0–G5 关卡写成通过；台账对七关一律保持 `preserved-not-complete`。
2. 不得把已关闭 `#83` 的 PV PASS、2026-09-07 的双栈实飞或 2026-09-07 的 MATLAB 实飞转移给 f333316 架构候选：它们属于 pre-f333316 修订，且 `#83` 的实跑位于**不是 HEAD 祖先**的分支。
3. 不得把 87 项能力清单、已发布规格、96 行台账或接口占位读作验收。
4. 不得把已关闭的子票（`#26` 的 `#70`/`#71`/`#72`、`#46` 的 `#113`/`#114`/`#115`、`#33` 的 `#82`/`#83`）读作父票关闭。
5. 不得改判 R1 的 `numerical_failed` 与其保留的 5,684 个失败值；不得把静态 profile 上的零容差相等当作已声明的误差预算。
6. 不得把结构 `aligned` 当作 G6 通过（G6 本次排除，但该警示对所有引用仍然有效）。
7. `#9` 未决前不得派发 ABI 分支（`#27`/`#28`/`#73`/`#74`/`#76`/`#77`/`#78`），尽管它们带 `ready-for-agent`。
8. 不得把 `docs/coordination/acceptance-frontier.json` 当作当前状态：它仍把 `#83` 记为 OPEN。
9. 不得声称对 `oayggl_s` 原件或 `/root` 模型库做过**本检出内**的字节校验；它们是 external，只按记录 SHA 引用。
10. 不得把本审计自己的检查当作任何事物的验收；它们是只读的身份、对账与区间算术核对。

## 9. 自查、字节固定与复现

- `.gitattributes` 在本目录声明 **`* -text`**，git 对本目录任何文件不做行尾转换（实测该文件 8 字节）。
- 目录内所有文件的 SHA256 与大小记录在 `SHA256SUMS` 与 `manifest.json`。
- 复现顺序：
  1. `python -B validation/coordination/ds-g0-g5-frontier-20260913-01/verify_frontier.py`
  2. `python -B tools/audit_26_closure_readiness.py --manifest docs/plan/26-closure-readiness-manifest.json --output <新路径>`
  3. `python -B validation/coordination/ds-g0-g5-frontier-20260913-01/write_manifest.py`
- 交付后本审计**停止写入**。
