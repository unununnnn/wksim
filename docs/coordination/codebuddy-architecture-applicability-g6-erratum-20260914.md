# wksim 架构适用性澄清与 G6 门引用勘误（erratum，context-only）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时 HEAD `acf322860831cb2a7c83a45cb4e2586922444c57`；`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 退出码 0；`git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD` 退出码 0。绑定测试：`validation/test_codebuddy_architecture_applicability_g6_erratum.py`。

## 0. 地位（documentation / context only）

本文件是纯文档/语境（documentation/context only）工件：只做一项适用性澄清（§1）与一项文献引用勘误（§2），不改任何门（changes no gate）、不批准任何架构变更（approves no architecture change）、不重跑 issue 83（reruns no #83）、不收口 #84、不收口 G6、不收口 Full；不授予任何验收、批准、收口、复核或重跑许可。一切"当前是否满足 / 是否可关闭"的判定仍由当前权威（主代理 / 主会话 / 人类裁决）基于当下工件重新作出。

## 1. 适用性澄清（applicability，对 wksim 迁移工作）

父仓库 `CONTEXT-MAP.md` 的关系原文为："**AeroTwinSim → wksim**：提供已有环境、工具和产物的复用参考；不替代 Prometheus 移植主体，既有 ADR 不自动约束 wksim。"

据此澄清：对 wksim 迁移工作而言，治理本地权威（governing local authority）依次是：

1. `wksim/AGENTS.md`（本仓库代理指令与项目边界）；
2. `wksim/CONTEXT.md`（wksim 语境与术语）；
3. 已获批准的 wksim 契约（`docs/*-accepted*.md` 等 accepted 记录）；
4. 迁移架构（`docs/architecture-implementation-20260912.md` 实施基线与 `docs/coordination/architecture-continuation-20260913.md` 后续合同）。

父 ADR（`../docs/adr/`）**不自动约束 wksim，除非被 wksim 明确采纳**（explicitly adopted）。本澄清只引用 CONTEXT-MAP 的既有措辞，不修订、不修改、不取代任何父 ADR；父 ADR 在其自身语境（AeroTwinSim）内继续有效。

逐件登记（本文件写作时现场读取，字节身份见绑定测试）：

- **一致指引（consistent guidance，非自动约束）**：
  - 父 ADR 0009（公共边界 NED/FRD/SI）：与 wksim 已实施的统一 SI/NED/FRD `VehicleState` 与具名执行器边界（实施报告与后续合同）方向一致，属一致指引。
  - 父 ADR 0014（比较不变量与误差包络而非相同轨迹）：与 wksim 的数值对照验收（在固定条件下按预先约定的误差阈值比较）方向一致，属一致指引。
- **含未被 wksim 采纳的假设（assumptions not adopted by wksim）**：
  - 父 ADR 0005（版本化 Python 契约 + gRPC + ROS 2 仅作可选桥接）：wksim 已采纳的目标是 WSL Ubuntu22.04 + ROS2/DDS 运行时与 Prometheus 消息移植，未采纳其 gRPC 与"ROS 2 仅作可选桥接"假设。
  - 父 ADR 0010（固定 Gazebo Harmonic）：wksim 的 SITL 目标是 PX4 与 ArduCopter SITL，未采纳 Gazebo Harmonic pin。
  - 父 ADR 0011（固定 Cosys-AirSim v3.3 与 Unreal 5.5）：wksim 的显示目标是 UE5.5 加自研 `WksimVehicleVisual` 视觉模块，未采纳 Cosys-AirSim 后端。
  - 父 ADR 0016（Gazebo 物理权威 + Cosys 异步视觉镜像）：其前提依赖 0010/0011 的 Gazebo/Cosys 组合，未被 wksim 采纳。

以上"一致指引"不因本登记而升格为约束；"未被采纳"也不构成对父 ADR 的否定或修订。

## 2. G6 门引用勘误（不改被勘误文件）

`docs/coordination/omp-g6-first-step-ingest-note-20260914.md`（字节身份 `c7f034535096047e321ab654fac418d7de5775854ac0e5ff06d97db2369308bc`，14459 B）§5 把既有时间/机制前提的锚写作 "锚：`docs/2026-09-07_joint-rate-contract-proposal.md:58`、`ds-g6-major-time-binding` v3 记录"。**文献勘误**：该提案文档是历史文档（historical），自身不承载门权威——其标题即"提案（未批准）"，其批准状态由批准记录另行登记；把 G6 门锚定到提案行属于**文献引用错误**（bibliographic error）。

当前权威的门出处是批准记录 `docs/2026-09-07_joint-rate-contract-accepted.md`（其封存的提案不可变副本为 `validation/joint-rate-contract-20260907/approved-proposal.md`，SHA256 `54dcd1df7d70caeb483ab101e7071f8d48168f29e22a93da594e455a459a02a5`）。门数值为：

1. 物理步精确 **1 ms**（tick），共同输入屏障 **4 ms**，单步严格**四 tick（four ticks）**；
2. 首轮档位 **0.5×/1×**（默认 0.5×），组周期分别为 **8 ms/4 ms**；
3. **不追赶补发**、不连续补跑积压组、不暗中重锚；迟到只向后滑动；唯一例外是显式分段重锚（显式继续/恢复，含 `start-recovery-task`）；
4. 累计墙钟迟到**超过 100 ms** 即报 `rate_unmet/resource_insufficient`，在最后完整屏障冻结并撤销控制；不自动降档、不自动恢复、不补发动作；
5. 全窗（full-window）验收：每个不重叠 **10 s** 窗口相对请求倍率误差 **±2%**，完整 **60 s** 有效段 **±1%**，并满足 100 ms 相位迟到上限；所有窗口和最坏值均报告，不得以分位数掩盖失败窗口。

上述百分比与 100 ms 属墙钟性能预算，不是 G6 动力学数值等价误差（批准记录原文边界，原样保留）。

## 3. 取代声明（仅限错误引用）

本勘误的取代范围**仅限于 §2 所述错误引用本身**：即在 `omp-g6-first-step-ingest-note-20260914.md` §5 中把 `docs/2026-09-07_joint-rate-contract-proposal.md:58` 用作 G6 门锚这一引用。被勘误文件的**字节不被取代、保持不变**（`c7f03453…`，14459 B）；其绑定的两份历史审查文档、comparison-v2、三个工件身份、context-ingest manifest `-02` 与独立审查 `-03` 的全部既有字节身份同样保持不变。今后引用 G6 门时应引用 `docs/2026-09-07_joint-rate-contract-accepted.md`；引用该 note 的历史证据字节时仍按其原字节身份引用。

## 4. 消费者规则（compact consumer rule）

未来任何代理在 wksim 内工作时：

1. **权威顺序**：适用性/权威问题按 `wksim/AGENTS.md` → `wksim/CONTEXT.md` → 已批准 wksim 契约（accepted 记录）→ 迁移架构文档的顺序解决；父 ADR 仅在被 wksim 明确采纳时适用（CONTEXT-MAP 原文："既有 ADR 不自动约束 wksim"）。
2. **门引用**：门数值一律引用 accepted 记录（`docs/*-accepted*.md`），不得把提案文档当门权威引用；引用时给出 path:line 并在使用时重验锚行内容。
3. **历史证据**：历史证据按其字节身份（SHA256 + 大小）引用，区分"历史语境"与"当前权威"，不把历史措辞读作当前状态。

## 5. 本文件边界

本次仅创建两个文件：本文件与 `validation/test_codebuddy_architecture_applicability_g6_erratum.py`。除这两个新文件外未改动任何文件；未暂存到真实 index、未提交、未推送、未 reset/clean/checkout/restore；未改动任何引用；无网络。全程纯只读复核（SHA256 重算、`git ls-tree` / `cat-file` / `merge-base --is-ancestor`）；未运行任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行，未重跑 issue 83，未运行 #83 相关任何场。被勘误 note 及全部既有 manifest/review 字节在本次保持不变（绑定测试逐字节核验）。
