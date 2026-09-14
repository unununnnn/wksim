# OMP G6 首步对照 · 历史语境绑定与取代登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时 HEAD `e2ecd62e914e075d0d9e40eef8ea9c034b958d2f`；`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 退出码 0；`git merge-base --is-ancestor 1c5656ed924020b3e626e68739caeeaef9f41a9e HEAD` 退出码 0。

## 0. 本文件的地位

本文件只做两件事：把下述两份历史文件**按字节绑定**为历史语境（historical context only），并登记其后的取代事实与边界。它自身不构成 G6 的验收、批准、收口、复核或任何重跑许可；被绑定的两份文件同样**不再**构成这些。一切"当前是否满足 / 是否可关闭"的判定必须由当前权威（主代理 / 主会话 / 人类裁决）基于**当下**的工件重新作出。本文件写作过程为纯只读复核（哈希重算、`git cat-file` / `ls-tree` / `merge-base` / `diff --name-only`、JSON 字段读取）：未启动任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行，未重跑 issue 83，除本文件外未改动任何文件，未暂存、未提交、未推送。

## 1. 历史语境绑定（字节级，本次在 HEAD `e2ecd62e` 现场重算）

| 项 | 被绑定文件 A | 被绑定文件 B |
| --- | --- | --- |
| 路径 | `docs/coordination/omp-reference-first-step-review-20260913.md` | `docs/coordination/omp-first-step-comparison-review-20260913.md` |
| SHA256 | `7973f0220c05861547283fbc47f3cfb8e5875a6101023e64593ad7b2664bc17a` | `728bce90e0e2da893746e9113954694b6fb7147537db18f564e186dfa5769c14` |
| 大小 | 2979 bytes | 3985 bytes |
| 当前 git 状态 | 未跟踪（`??`） | 未跟踪（`??`） |
| 性质 | 历史语境、非权威：参考端首步证据独立审查（run-03 + execution-03） | 历史语境、非权威：两端对照独立审查（comparison-v2 + trace + instrumentation-check），并更正 A 的两处错误；2026-09-14 精度更正版取代旧版 `8b222e1d1d93ab6710b0e7bb887b3d46203f0053f7f6516457f45e15a0a1a5e6`（3182 bytes；旧版"均 1 ULP/次正规"精度措辞不实，见 `codebuddy-omp-g6-first-step-independent-review-20260914-01` P2-1/P3-2） |

两份文件均为 OMP G6 首步模块 2026-09-13 的离线只读审查记录。B（对照审查）在后，按其 §"先更正"明文取代 A 的两处结论（见 §3）；B 自身的"均 1 ULP/次正规"精度措辞已于 2026-09-14 更正（q 块 stage3 `derivatives[3]` 传播差异为 **64 ULP**、q 块末态 index3 为 **44 ULP**、3.46e-47 为规格化 normal double），本表所绑为更正版字节；A 其余核对在未被取代范围内仍按原样作为历史记录引用。

## 2. baseline / 祖先 / 间隔增量

- baseline `1c5656ed924020b3e626e68739caeeaef9f41a9e` 与架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 均为本文件写作 HEAD `e2ecd62e914e075d0d9e40eef8ea9c034b958d2f` 的祖先（`merge-base --is-ancestor` 退出码均 0）。
- 间隔增量（baseline..HEAD）恰为一个提交：`e2ecd62e` "Bind scene frontier context offline"，`git diff --name-only` 只触及 `docs/coordination/ds-scene-frontier-20260912.md`、`docs/coordination/ds-scene-frontier-ingest-note-20260914.md`、scene-frontier 审查目录与 `validation/test_ds_scene_frontier_context.py` —— 纯 scene-frontier 话题，与两份被绑定文件、`tools/run_numerical_conformance.py` 及两个 g6 首步证据目录**零交集**（disjoint，本次以 `diff --name-only` 现场核验）。

## 3. 其后的取代事实（comparison-v2 更正 reference review 两处错误）

1. **同时间观测的区分**：A 原文"两次相邻同时间观测只能靠内容区分"**不完整**。JSON 数组保存真实回调顺序，两个相邻 t=0.0005 观测**可由序位（order index）严格区分**；"状态 hex 相同、导数 hex 不同"的内容差异降级为佐证。以时间为键的合并仍会折叠两次观测，但严格区分以序位为准。
2. **执行未使用已分叉的 staged 驱动**：A 原文"本次执行用的是 staged 副本"**错误**。本次新 probe **既不调用仓库也不调用 staged 的 `run_numerical_conformance.py`**；input-checks 中该条 False 是 `unused_changed_driver` 的如实记录（staged 期望 `7f3bc0c8…` ≠ 仓库实际 `42212463…`，登记为已变更且未使用），不是"使用了 staged 版本"。
3. 附带：Java 输出 CREATE_NEW 无 tmp+fsync+rename 的半成品边界属**有意保留证据**，后续一律用新目录，不再建议覆盖原路径。

## 4. 身份与仪表事实（现场重算核验）

| 身份 | 值 | 对象 |
| --- | --- | --- |
| `reference_sha256` | `99fc1ec84a110bea1e5998a97b4f9c66231966474268ba74bfc343b584e03f85` | 参考端 `g6-reference-probe-20260913/run-03/reference-first-step.json`，与 comparison-v2 引用逐字一致 ✓ |
| `target_trace_sha256` | `343509972eb3233cd8b4c32c8f0747c2e959cefeb2dab57ea747930c40e3fb86` | **顶层** `g6-target-first-step-20260913/first-step-trace.jsonl` ✓ |
| with-major 变体 | `d55542d743c456073d2d362ed3f71232d6d4697f450eaa8f8333b88699436360` | `with-major/first-step-trace.jsonl`，与顶层是**不同身份**；v2 引用对象明确无误，不得混用 |

仪表事实（按 B/A 记录保留）：72 = PreOutputs 20 + PostOutputs 20 + PreDerivatives 16 + PostDerivatives 16，dropped=0；PostDerivatives 时点分布 0×4、0.0005×8、0.001×4；目标 trace 行序 stage0(0)→stage1(0.0005)→stage2(0.0005)→stage3(0.001)→**ode4_update(0.001)**，v2 末态取最后 0.001（update，RK4 积分终态），不取第四级 minor。major [0, 0.001]，(30+30+60)×2=240 个 f64 全核、对冻结 C3G 前 2 行**零位失配**，`legacy_target_bit_mismatches=[]`，`parse_int=Decimal` 保全 `-0` 符号。跨块最早差异：p,q,r 块 stage2 `derivatives[1]`（0 基）1 ULP（`bc56d4db33a987b8`→`…b9`）。−4.95e-18 是该差异 double 的**值量级**，不是 ULP 差值——该处 1 ULP 的格点差约 −7.7e-34。其后 stage3 传播逐项为：q 块 `derivatives[2]` 1 ULP（`bba76121ffa77473`→`…74`）；q 块 `derivatives[3]` **64 ULP**（`36494aa6d36ff400`→`36494aa6d36ff3c0`）；p,q,r 块 `cont_states[1]` 1 ULP（`bbb76121ffa77473`→`…74`）；ub,vb,wb 块 `derivatives[0]` 1 ULP（`baa3bfd397a2d0d5`→`…d6`）——**不存在"后续传播均 1 ULP"的普遍规律**。末态（最后 0.001 PostOutputs）差异：q 块 index3 **44 ULP**（`3581440763f7c6a8`→`3581440763f7c67c`）、ub,vb,wb 块 index0 1 ULP（`b9e48cb0f57301da`→`…db`）。3.46e-47 及上述全部差异 double 均为规格化（normal）double，非 subnormal。差异源未定（编译器/库差异候选未证）。

## 5. 边界（全部保留，不因本绑定改变）

- **覆盖范围**：对照仅覆盖 36 个连续状态中 **13 个已映射刚体状态**（q / p,r / 位置 / 机体系速度四块），23 个未覆盖；**13/36 不构成全模型一致，也不构成 G6 通过**。
- **阶段映射**：`ode4_stage_mapping: unverified; event order alone is not a solver-stage proof`；**事件数 72 不是 G6 通过**。
- **工具哈希分歧（owner 裁定已下，2026-09-14 补记；原两选项措辞明确取代/superseded，见 §8）**：仓库当前 `tools/run_numerical_conformance.py` = `4221246303642b26290b63c118ced5209a6e928a6101140cc00dc4cd12278040`（本次重算；Git blob `1cedff93bd8fd48d7e867541ed83423edaa03089`，提交于 `3f40ba03`），是**当前源**；与冻结 R1 驱动逐字节比对，恰差一个类型门与一次 float 强转（L137 `type(x) in (int, float)` 类型门、L148 `float(...)` 强转），再无其他差异。冻结 R1 驱动 `7f3bc0c88263a6e1c94a3f42658fe43db2a0b75abca7a5fb59fcfaafdba99cde`（execution-03 input-checks 登记）存在于 `validation/numerical-conformance-u56ce17a/C0`、`validation/numerical-conformance-gxxh6xhr/C2G`、`validation/numerical-conformance-gxxh6xhr/C3G`，是"当时实际执行了什么"的**不可变证据**，不得变更。owner 裁定：**既不更新冻结副本，也不回填仓库，两者均未获授权**；本文件原先"两选项悬而未决"的措辞（更新 staged 或回填仓库）被本裁定**明确取代**。execution-03 probe 既不调用冻结副本也不调用仓库驱动，故 `unused_changed_driver` 为**非缺陷**，不影响 R1 证据，也不影响首步对照证据。旧引用 `7f3bc0c8…` 属 **R1 时期的历史身份**，不是当前仓库 pin。今后每次执行该 Python 驱动，都必须在启动时重算并记录其 SHA，并对实际执行的字节做快照。本裁定**只关闭 owner-ruling 子议题**：不构成 G6/Full 通过；23 个状态、`ode4_stage_mapping`、native/full-window 工作仍未完成；issue 83 不重跑。该分歧**未影响本次被对照的运行**（probe 两个副本都未调用，见 §3.2）。
- **证据目录状态**：`/validation/*/` 属 gitignore 领地（本仓库 `.gitignore:53`），证据默认本地留存、不进跟踪树；两个首步证据目录 `g6-reference-probe-20260913/`、`g6-target-first-step-20260913/` 的现有文件在本次 HEAD 已被显式提交跟踪（101 个跟踪文件，无未跟踪残留），其余 20260914 g6 证据目录保持未跟踪且被忽略。其中 timing 锚 `ds-g6-major-time-binding` v3 记录目录 `validation/coordination/ds-g6-major-time-binding-20260913-01/` **未跟踪且被忽略**（HEAD 树 0 文件），**不能作为 tracked 锚**——§6 复用第 2 条的 tracked 锚标准对它不适用，其离线复现仅依赖本地留存。sleep 数字为审方自原始记录离线复算所得，非工具自证输出；PGID 主张属**临时性**（进程组身份仅在被捕获会话内有效，不作为跨会话持久证据）。
- **既有时间/机制前提不变**：1ms 物理精确 major 步（相位 `k*0.001`，501/501 核验）；RK4 每 major 4 个 minor 阶段（4-tick，阶段时点 0/0.0005/0.0005/0.001 + update）；**不追赶补发**；**超 100ms 迟到冻结撤销且显式恢复**的门；**全窗（full-window）口径**而非单点事件。锚：`docs/2026-09-07_joint-rate-contract-proposal.md:58`、`ds-g6-major-time-binding` v3 记录。
- **AP 与 PX4 物理/身份分离**：混合场中 AP 与 PX4 是不同载具、不同物理与不同身份，观测、manifest 身份与失败解读按侧分开，**永不合并**（如 mixed-failure review 的 latch 时刻读数：AP 0.905m 正常下降、PX4 已落地，两侧分开陈述）。
- **mixed 能力证明行仍 MISSING**（`omp-mixed-failure-review-20260913.md:59`）；本场为诊断证据。
- **xtj8wk8i 永不充当 issue 83 证据**：xtj8wk8i 是诊断场（release 路径分类见 `omp-mixed-failure-review-20260913.md`），诊断/probe 场永不得充当 #83 通过证据；#83 已由公共 PV `1w6dru32` 通过并 CLOSED，**issue 83 不重跑**。历史失败记录（2026-09-11/12 四个正式速率失败、mixed 失败等）含义不变，仅作历史证据引用。
- 本文件与两份被绑定文件均不授予任何验收、收口、owner 批准或重跑许可。

## 6. 有界复用 / 不复用与离线配方

**可复用（仅离线、哈希/锚点/祖先三件事）**：
1. `sha256sum` 重算本文件 §1 的两个字节身份与 §4 的三个工件身份；
2. `git cat-file blob` / `git ls-tree HEAD -- <path>` 读取跟踪锚（`docs/coordination/g6-first-divergence-20260913.md`、execution-03 `input-checks.json` 等）与存在性；
3. `git merge-base --is-ancestor <sha> HEAD` 复验 `1c5656ed…`、`f333316e…` 祖先关系；`git diff --name-only <baseline>..HEAD` 复验间隔增量的话题分离。

**不复用**：被绑定文件与本文件的任何测量、结论、边界**不得**读作"现在是什么状态"、当前 G6/OMP 进度、验收/收口状态或许可；不得据此重跑任何场或 issue 83；不得以事件数、单点差异或 13/36 覆盖推断全模型一致；staged 与仓库驱动的分歧已由 owner 裁定闭合（见 §5）：不更新冻结副本、不回填仓库、不单方"修复"，任何一方都不得被变更；分歧以裁定而非字节变更闭合。

## 7. 本文件的边界

本次仅创建本文件（`docs/coordination/omp-g6-first-step-ingest-note-20260914.md`，未跟踪）；未编辑两份被绑定文件或任何其他文件；未暂存、未提交、未推送；全程只读复核，未运行任何 native / build / MATLAB / ROS / DDS / SITL / 飞控 / UE / 模型 / 飞行，未重跑 issue 83。

## 8. 补记（2026-09-14 owner 裁定 remediation）

后续独立 CodeBuddy 审查在本文件 §5 发现 P2：原"两选项悬而未决"措辞（更新 staged 或回填仓库）留下活的未决选项，而**两个动作都不安全**。owner 已裁定并登记于 §5 工具哈希分歧条：冻结 R1 驱动 `7f3bc0c8…`（现存于 `validation/numerical-conformance-u56ce17a/C0` 与 `validation/numerical-conformance-gxxh6xhr/C2G`、`C3G`）是不可变证据；仓库当前驱动 `42212463…`（blob `1cedff93…`，提交于 `3f40ba03`）是当前源，恰差一个类型门与一次 float 强转；**既不更新冻结副本，也不回填仓库，两者均未获授权**；`unused_changed_driver` 为非缺陷；旧 `7f3bc0c8…` 引用属 R1 时期历史身份，不是当前仓库 pin；今后每次执行该 Python 驱动都必须在启动时重算并记录其 SHA 并对实际执行字节做快照；本裁定只关闭 owner-ruling 子议题，不构成 G6/Full 通过（23 个状态、`ode4_stage_mapping`、native/full-window 工作仍未完成；issue 83 永不重跑）。

本补记为 remediation 结果：仅改动本文件与 `validation/test_omp_g6_first_step_context.py`，未改动两份被绑定文件、任何冻结证据目录、任何跟踪文件或任何既有审查/manifest 目录。原独立审查 `-02`（`codebuddy-omp-g6-first-step-independent-review-20260914-02`）与 context-ingest manifest `-01`（`omp-g6-first-step-context-ingest-manifest-20260914-01`）所绑定的本文件旧字节（`e9f74bfc…`，11165 B）与本测试旧字节（`f1db73fc…`，45920 B）自此**被取代**；两个目录原样保留、不再更新，其身份不再作为当前权威；后续复核由新的独立审查（`-03`）与新的 manifest 写手（`-02`）基于 remedi 后字节重新作出。本补记不授予任何验收、收口、批准或重跑许可。
