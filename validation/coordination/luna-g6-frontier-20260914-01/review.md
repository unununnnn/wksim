# G6 / Full 剩余验收前沿审计

审计时间：2026-09-14（Asia/Tokyo）。范围是 `wksim` 当前工作区的只读证据审查；没有修改既有文件，没有运行或启动 ROS、飞控、模型、UE、MATLAB、native 或 build。新增文件只在本目录。

结论：G6 仍为 `blocked / not accepted`，Full 仍为 `incomplete`。现有 G6 首步材料证明了一个有限诊断接缝，但没有形成 G6 数值验收。R1 保持 `numerical_failed`，不能改判为通过。

工作区身份在本轮 probe 与交付收口时为 `main` / `9815355d0c325bc84512dc3a48d354ccbb6ac47f`，`f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 祖先检查退出码为 0。工作树已有大量他方未提交修改；本审计没有覆盖、回滚或整理这些修改。G6 budget audit 自身声明的历史 checkout HEAD 是 `abf1ac3934e3ad8dcfbcb5c7b4dc49712d407c18`，与当前 HEAD 不同，因此它是可重核的历史证据摘要，不是当前源码候选的干净身份。

已证明的事实：

- G6 诊断目标端首步 trace 的既有收据显示 g++ 编译退出码 0、记录器运行退出码 0，trace SHA256 为 `343509972eb3233cd8b4c32c8f0747c2e959cefeb2dab57ea747930c40e3fb86`。比较范围明确为一个 case、一个 `k=0→1` step、13/36 个映射刚体状态；不是全模型比较。
- 在这一个有限范围内，最早差异位于 `p,q,r` 的 stage 2 derivative index 1：参考 `bc56d4db33a987b8`，目标 `bc56d4db33a987b9`，为 1 ULP。`g6-pqr-derivative-path-20260913.md` 已把下一观测点缩小到残差、惯量矩阵及其上游力矩子项，但双引擎完整 operand chain 尚未形成。
- R1 既有诊断完整性收据仍给出 5684 个失败值（C0/C2G/C3G 为 2/1943/3739），最早是 C3G `k=1` 的 `Vehicle60[3]` 2 ULP。报告明确把浮点求值差异标为 `unproven`，没有排除坐标、单位或时序合同问题。
- 本轮只运行纯 Python 校验：`python -B -m pytest validation/test_compare_first_step_trace.py validation/test_g6_first_divergence.py -q -p no:cacheprovider` 得到 `82 passed, 1 skipped, 18 subtests passed`；`python -B tools/validate_e0_source_to_slot_manifest.py` 得到 `status=pass, errors=[]`。这些是离线结构/证据校验，不是 G6 运行验收。
- Full 机械账本生成于 2026-09-09，共 96 项，96/96 为 `partial-evidence` 且 `gap=true`。账本的判定规则明确：父票 CLOSED 或已有报告只表示子集证据，不能关闭 Full 行。

未证明的关键事项：

- 120 个 G6 数值量没有任何已批准的逐量 `abs_budget` / `rel_budget` / `rms_budget`；动态 56 个量均没有 frame 或 datum 绑定。预算审计的 `slots_with_any_approved_epsilon=0`、`slots_with_frame_binding=0`、`slots_with_datum_binding=0`。
- 同源入口已经存在，但入口在合同和执行身份检查前 fail-closed；当前状态是 `blocked (no approved per-quantity budget, no execution block)`。因此没有完整 120 槽、501 样本的同源 G6 数值执行，也没有 physical acceptance。
- 四条时间/相位记录仍是 `prospective_for_review` / `acceptance=false`；product 与 division 时间形式出现差异（vehicle 72 行、sensor/GPS 61 行），尚未有批准的时间规则。
- 13/36 首步对齐、5 个 mrdivide 观测或对角快速路径候选都不能替代完整时序、完整 36 状态、全 120 量或物理精度验收。对角候选的离线结果本身也保留了参考求解器内部未决的限制。
- Full 的硬件、协议、模型族、DLL/许可、完整模式、联合场景、规划器和正式入口义务仍由账本保留。当前 GitHub 状态中 #1、#9、#10、#26、#29、#33、#59、#60、#62、#84、#102 仍 OPEN；#83 已 CLOSED。#59 标记 `needs-triage`，#60/#84/#102 标记 `ready-for-agent`。父票关闭不改变 96 条 Full gap 的判定。

阻塞项按可解除条件归纳如下：

1. `B1`：为每个量建立误差分析/校准/传感器规格依据、适用域和 owner approval，才能批准预算。
2. `B2`：补齐动态量的 frame、datum、GPS 航向包络、WGS84/高度基准及 eph/epv 语义。
3. `B3`：批准时间字段属于排除的调度元数据，或为它们建立绑定的时间预算。
4. `B4`：冻结包含 120 个批准预算和完整 MATLAB/export/native execution identity 的新同源合同；不能使用旧 R1 合同替代。
5. `B5`：继续首步深层观测，至少在 stage 2 的 `p,q,r` 导数处取得双引擎 `rtb_IntegratorSecondOrderLimi_d[0..2]`、`Selector2[0..8]` 以及 `M1/Fd/Sum1_a/TT0gLR/Sum4_f` 的 binary64 对照，并逐步映射其余状态。

零冲突的最小下一切片：由主会话在新 staging/evidence 目录完成一次 C3G、`k=0→1`、stage 2 的二级 operand boundary probe。只观察上述残差/惯量/力矩项，保留双侧原始 hex、来源身份、输入 SHA 和退出/清理收据；不修改 `run_e0_same_source_conformance.py`、旧 R1 合同、正式 profile、Full 账本或现有 builder/recorder。判定树很小：若残差和矩阵逐位相同而结果不同，问题落在两侧 mrdivide 求解核；若残差已不同，再按 M1/Fd/陀螺/阻尼子项回溯。该切片只解除 B5 的局部不确定性，不批准预算、不关闭 #59、不宣称 G6，通过后才进入预算审批和新同源合同阶段。它与当前单一 native/正式 profile 写入权不冲突，因为由主会话使用独立 staging，既有证据保持不可变。

主要复核原件及稳定身份：

- `docs/plan/10-g6-remediation-contract.md` SHA256 `48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0`
- `docs/plan/59-e0-same-source-command.md` SHA256 `345caff0fd354717a64ed1dfac2c3ad33f87c72713cf3362483c395fb66b197e`
- `docs/plan/59-e0-dynamic-budget-source-map.md` SHA256 `35a56084105409329131add7d4b9e35be6d1a145c6e18268c96324805313cd42`
- `docs/plan/full-remaining-ledger.json` SHA256 `61a58c9065d5f6b0f243aa49cbd476f38a17ce29c7bf12175c194ba582c51b54`
- `validation/coordination/g6-target-first-step-20260913/comparison-v2.json` SHA256 `2a6b8fe9338224d64f0cc91fd4c66139b3422ca23c3032049cd529d6387ea3c9`
- `validation/coordination/g6-first-divergence-20260913/v3/diagnosis.json` SHA256 `f326f392a4de7f8171aec22d13de569f862e82f08da6b4979a2ba0791b14c73e`
- `validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json` SHA256 `04604840d3b79f6cfe26e2cc4e2547f6c15b3f7cc66aa1da0cb69527f0bf0d66`

可重跑的纯只读 probe 是同目录 `probe.py`；它只读取上述文档/JSON、计算 SHA256、读取 git 身份并输出 JSON，不启动任何受禁程序。机器可读结论在 `review.json`，本目录自身文件的最终 SHA256 见 `SHA256SUMS`。
