# 私有接线选择性迁移方案（新架构 MIXED 候选）— 修订版 v3

- `checked_at`: 2026-09-13（v3 修订；本机实测）
- 工作类别：**new-architecture-acceptance preparation**（只读调查；不运行、不构建、不修改任何 Linux/原生/飞控/UE/MATLAB）
- 独占写入：本文件 + `validation/coordination/ds-architecture-mixed-migration-20260913-01/`。未改实现、未改 native、未改任一 Linux 检出、未提交、未推送。
- 交付后停止写入。本文件是迁移**方案**与**只读身份证据**，不是验收结论，也不把任何旧 PASS 转移给新候选。
- **v2 修订摘要**：(1) 修正倍率算术（旧稿把含初始化的场景总墙钟与锚定速率段混算，得 0.40177 却被写成 0.502）；(2) 修正已跟踪修改文件计数（5 项，不是 4 项）；(3) 将 manager-GC 由“必需”**重分类为条件迁移**，并改为**外科式 feature delta**而非整体复制 donor 文件；(4) rate_probe 新字段重分类为**可选诊断**；(5) 修正 v1 中“保留 owned 标记区”与“删除 owned 开关”的自相矛盾；(6) 更正 v1 的“未见 manager-GC 同名测试文件”错误断言（该测试**存在**，并已定位）。
- **v3 修订摘要（本次）**：(1) 撤回 v2 §5.3 的**错误断言**——`tools/run_joint_flight.py:329` 实为
  `async_model_evidence = getattr(args, 'async_model_evidence', False)`（**受保护读取**），并非直接 `args` 访问；
  该用例在 main 上实跑通过（`python -m unittest validation.test_joint_rate_probe.JointRuntimeTimingProbeEntryTests.test_real_runner_source_manifest_and_source_unchanged_follow_probe_state -v`
  → `Ran 1 test` / `OK`，两条 stop-before-flight 路径均有 mock，无 native），
  因此**删除“现存必跑失败项”与“需要修复命名空间”的整段结论**（含 §6 阶段 C 中相应行、§7 第 6 条）。
  v2 §5.3 违反“先读精确源码再下结论”，本文件不再保留任何未按精确源码核对的断言。
  (2) **加入当前更新指针**：新架构候选已由 main 以 main 分支 bundle **fast-forward** `d45d1da → 386f713`（clean、祖先 0），
  回执 `validation/coordination/architecture-candidate-sync-20260913-02/receipt.json`（`private_wiring_migrated=false`、`native_executed=false`）；
  本文件 v1/v2 的 `d45d1da` 快照转为**历史快照**，下列 §1/§3 处给出当前值。
  (3) 对 v2/v3 全部**硬断言**按精确源码/回执逐条重审（见 §9），并修正两处行号表述（`joint_rate.py` 的 `period_ns` 属性定义在 `:33-35`；MIXED 任务行的精确行号）。

## 0. 开工核验（合同 §派发与开工核验）

```text
工作类别：new-architecture-acceptance preparation（只读迁移调查，无验收运行）
实际 cwd：C:/Users/PC/Documents/odid编译/wksim
分支 main；HEAD 386f713a7752515502fd2224e9186f2219674732（v3 复核；与 v2 相同，未变）
架构祖先检查：git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD → exit 0
已读（当前版本）：AGENTS.md、docs/architecture-implementation-20260912.md、
      docs/coordination/architecture-continuation-20260913.md、
      docs/coordination/module-delivery-policy-20260912.md、
      docs/coordination/short-cycle-goal.md、docs/codebase-memory.md
      （经复核，架构合同与模块边界与 v1 读取时一致，无实质变化）
本次 module / interface：tools/run_joint_flight.py（父/经理接线）、
      tools/manager_gc_candidate.py、Simulator/wksim_runtime/joint_rate_probe.py、
      Simulator/wksim_core/worker.py；interface = 既有 runner CLI 与会话/速率证据 schema
直接依赖：tools/joint_control_candidate.py、tools/ap_mixed_candidate.py、
      Simulator/wksim_runtime/joint_profile.py、Simulator/wksim_runtime/joint_rate.py
独占文件：本文件、validation/coordination/ds-architecture-mixed-migration-20260913-01/*
不在本次范围：main 独占的 native/正式 profile/catalog/joint_profile 接线；不迁整目录；不动 Windows 其它工作树
受影响测试与实际验收：见 §8（本次为接线迁移分析，未执行；新架构 MIXED 验收仍未准入）
交付：稳定源码 SHA、只读身份回执、遗留限制；交付后停止写入
```

Windows 工作树在修订时非干净，全部保留未触碰：
`M docs/Prometheus.gitmodules.reference`、`M validation/coordination/short-cycle-dispatches.json`，以及一批未跟踪文件
（含 `tools/compare_joint_gc_diagnostics.py`、`validation/test_compare_joint_gc_diagnostics.py`、
`validation/test_delivery_entry_contract.py`、`validation/test_scene_frontier_contract.py` 等）。
v1 时存在、修订时已不在 `git status` 中的条目（如 `M validation/coordination/ds-perf-stream-*/…`）：该变化不由本任务产生，本任务从未触碰这些路径。

## 1. 实际检出身份（只读实测）

| 检出 | 分支 | HEAD | 工作树 | `f333316` 祖先 |
| --- | --- | --- | --- | --- |
| Windows 主线 | `main` | `386f713a7752515502fd2224e9186f2219674732` | 2 个已跟踪修改 + 未跟踪（保留） | exit 0 |
| Ubuntu-22.04 新架构候选 | `codex/architecture-acceptance-20260913` | **`386f713a7752515502fd2224e9186f2219674732`（当前，已由 main fast-forward；见 §1.1）**；历史快照 `d45d1dad81600b37fb41c945870ee455a3ee81f0` | **干净**（`git status --porcelain` 0 行、未跟踪 0） | exit 0 |
| Ubuntu-22.04 历史对照（冻结） | `codex/planner-release-validation` | `db1200d115902eb9d47fca19cccb71a7b9c15147` | **5 个已跟踪修改** + 未跟踪 | exit 1（历史豁免，不作新功能落点） |

### 1.1 当前更新指针（v3 新增；v1/v2 的 d45d1da 快照转为历史）

- main 以 main 分支 bundle **fast-forward** 候选：`d45d1da → 386f713a7752515502fd2224e9186f2219674732`（`merge --ff-only`，
  更新前后 `status --porcelain` 均为空、`f333316` 祖先检查均 exit 0）。
- 回执：`validation/coordination/architecture-candidate-sync-20260913-02/receipt.json`
  （`new_head=386f713a…`、`private_wiring_migrated=false`、`native_executed=false`、`architecture_acceptance=false`）。
- **本次 fast-forward 未迁入任何私有接线**：候选侧 `tools/run_joint_flight.py` 仍为 `5527063f…`、
  `Simulator/wksim_runtime/joint_rate_probe.py` 仍为 `a8bac9ac…`、`validation/test_joint_rate_probe.py` 仍为 `c3bfd1cd…`；
  `tools/manager_gc_candidate.py` 及其两个测试仍 **ABSENT**；donor→候选 runner diff 仍为 **472 增 / 50 删**、rate_probe diff 仍为 **+27**。
- 故 v2 的迁移结论不因该同步而改变；发生变化的是候选 HEAD 身份与 `docs/coordination/module-delivery-policy-20260912.md`、
  `docs/coordination/short-cycle-goal.md` 等文档内容（当前派发指针改为 `validation/coordination/perf-next-dispatches-20260913-01.json`）。

历史对照 `git status --short` 的 5 项已跟踪修改（v1 正文误写为“4 个”，此处为更正后的准确计数）：
1. `Simulator/wksim_core/worker.py`
2. `Simulator/wksim_runtime/joint_rate_probe.py`
3. `docs/2026-09-09-final-combo-pv-plan.md`
4. `tools/audit_pv_trajectory.py`
5. `tools/run_joint_flight.py`

未跟踪：`tools/capture_owned_scheduling.py`、`tools/group_work_timing.py`、`tools/probe_release_audit_integrity.py`、
`validation/*.stdout.*`、`validation/test_release_audit_integrity.py`。
`.gitignore:53` 的 `/validation/*/` 使 `validation/` 下的“未跟踪”不等于“新内容”。

## 2. 实测 MIXED 速率与时长（区分“源码派生”与“实测比值”）

### 2.1 源码派生事实（Windows HEAD 与新候选同内容）

| 事实 | 值 | 出处 |
| --- | --- | --- |
| 速率请求硬编码 | `0.5` | `tools/run_joint_flight.py:757` |
| 允许速率集合 | `(0.5, 1.0)` | `Simulator/wksim_runtime/joint_rate.py:5,9-12` |
| 组周期 | `4_000_000/0.5` = **8 000 000 ns** | `Simulator/wksim_runtime/joint_rate.py:33-35` |
| 物理步长 | `STEP_NS = 1_000_000`（1 ms） | `Simulator/wksim_runtime/scene_clock.py:14` |
| 宏组 | `MACRO_TICKS = 4`（4 ms 仿真） | `Simulator/wksim_runtime/scene_clock.py:14`；`tools/run_joint_flight.py:857,875` |
| 晚限（硬门） | `LATE_LIMIT_NS = 100_000_000` | `Simulator/wksim_runtime/joint_rate.py:6,81-87` |
| tick / 墙钟上限 | `MAX_TICKS=180000`、`WALL_LIMIT=900` | `tools/run_joint_flight.py:49` |
| 记录身份 | `request_id='config'` | `Simulator/wksim_runtime/joint_rate.py:25` |

**源码派生的配置倍率 = 0.5×，即每 8 ms 墙钟推进 4 ms 仿真时间。** 这是配置事实，与任何实测比值分开陈述。
独立佐证：`tools/analyze_joint_rate_intervals.py:55` `PERIOD_NS = 8_000_000`、`:104` “requested_rate must be exactly 0.5”、`:111-112` “ideal group period must be exactly 8 ms”。

### 2.2 实测回执（`joint-public-flight-oayggl_s`）

| 回执 | SHA256 |
| --- | --- |
| `result.json` | `e9ac61dc4d52c10db7b396001273e5367d1a328148d85227189047add0636d0a` |
| `rate.jsonl` | `d65849e69f3b36ad655473d7d7a5d46319f9e441787549d2673c7e8391988ff3` |
| `manager-gc-candidate.json` | `614ccd051d6c37244536da54d656289eab57292bb426891953243aa330fb7bbb` |

记录字段（原样）：`rate_request` 1 条、`rate_anchor` 1 条（tick 40，`anchor.wall_ns=100427426404`）、
`rate_group_start` 26991、`rate_group_end` 26991、`rate_boundary_check` **0**、`rate_unmet` 1 条
（tick 108004、`issued_monotonic_ns=316456162907`、`lateness_ns=100644532`、`requested_rate=0.5`、`request_id="config"`、`segment_id=1`、`latched=true`）、
`rate_segment_end` **0**。`result.json`：`status=failed`、`wall_seconds=268.72185634100003`、`error=RateUnmet('rate_unmet/resource_insufficient')`、`tasks={}`、`rate=null`。

### 2.3 正确的算术（**已在回执上逐项重算**）

| 量 | 值 | 算法 |
| --- | --- | --- |
| 段墙钟 | `316456162907 - 100427426404` = **216 028 736 503 ns** = **216.028736503 s** | 锚点 → 失败记录（同一段、同 request/rate） |
| 段仿真 | 26991 组 × 4 ms = **107.964 s**（tick 40 → 108004，`(108004-40)/4 = 26991` 组，每组恰 4 tick） | 组数 × 4 ms |
| **段平均** | `107.964 / 216.028736503` = **0.49976684466930027 ≈ 0.499767×** | 段仿真 / 段墙钟 |
| 场景总墙钟（**不得用于速率**） | `268.72185634100003 s` | `result.json.wall_seconds`，含锚点前的初始化 |
| v1 的错误混算 | `107.964 / 268.721856341 = 0.40176858507183316` | **作废**：混入了初始化段 |

**表述纪律**：
- 只声明**观测到的段内聚合比值 0.499767×**。
- **完整滑窗/倍率门未通过**（见 §2.4），因此**不得**声称“平均倍率要求已通过”或任何等效说法；段平均只是描述性聚合，不是门。
- 源码派生的 0.5× 与实测 0.499767× 分开陈述，不互相替代。

### 2.4 门与失败判定的准确归属

获批倍率合同要求：每档 ≥3 个独立 epoch、每次 ≥60 连续墙钟秒有效段；每个不重叠 **10 s 窗 ±2%**、完整 **60 s 段 ±1%**，
且累计相位迟到 ≤ **100 ms**；所有窗口与最差值均须报告，任何失败窗口不得称该档通过
（`docs/2026-09-07_joint-rate-contract-accepted.md:14`；`docs/2026-09-09-final-combo-pv-plan.md:32`；`docs/2026-09-09-mixed-flight-plan.md:3`）。

本场实测：段长 216.03 s 足以覆盖多个 10 s 窗与 3 个 60 s 段，但**第一组起点即迟到 `lateness_ns=133809`（0.1338 ms，量级无害，但段并非从 0 开始计时）**，
且失败前最后一组起点迟到 `lateness_ns=97822909`（97.82 ms，逼近 100 ms 门），随即 latch 于 100644532 ns。
因此：**100 ms 相位迟到门失败**，滑窗/倍率门**未通过**；`rate_segment_end` 为 0 说明该段不是正常收尾，而是被 latch 中止（`joint_rate.py:81-87` 在 `begin_group`/`end_group` 均可触发）。
**不对该失败做因果归因，不重跑该配置**（与 `short-cycle-goal.md:21,32` 既有结论一致）。单一 boot（`470ea486-9e18-4535-9d91-69de5a3a4572`）单次样本。

### 2.5 时长

该场在 108004 tick（108.004 s 仿真）失败，**从未接近**上限：0.5× 下 `MAX_TICKS=180000` ↔ 360 s 墙钟；`WALL_LIMIT=900` s ↔ 450 s 仿真。
两者取先到者：正常收尾时物理 tick 上限先到（360 s 墙钟），严重落后时才由 900 s 墙钟先到。
完整 MIXED 任务时长由窗口之和决定（`tools/mixed_control_task.py:95-128`：腿 1 的 `moving/window/dwell/zero/absolute_stop` 与 AP 专用 `invalid_world_yaw_rate`，腿 2 的 `wait/window/body_step/body_zero/body_absolute_stop`；`stable_hold` 上限 12 墙钟秒，`:64-71`）——**本文件不把粗算写成实测时长**，本轮无正常收尾场。

## 3. 三方对账：已有 / 条件迁移 / 不得迁（文件级）

对账基准（实测 sha256）：

| 路径 | Windows `main` (386f713 工作树) | 新候选 d45d1da | 历史对照工作树（db1200d + 本地修改） | 判定 |
| --- | --- | --- | --- | --- |
| `Simulator/wksim_core/worker.py` | `38f34a8f…` | 同 | 同 | 已有，不迁 |
| `Simulator/wksim_runtime/joint_rate.py` | `0b53a16a…` | 同 | 同 | 已有，不迁 |
| `Simulator/wksim_runtime/joint_profile.py` | `575adb53…` | 同 | 同 | 已有，不迁（main 独占） |
| `Simulator/wksim_runtime/evidence_stream.py` | `74cd79b8…` | 同 | 同 | 已有，不迁 |
| `Simulator/wksim_core/model_parameters.py` | `9289c09f…` | 同 | `b339ae24…`（旧 12 行） | 新候选更正确，**禁止回流** |
| `tools/capture_owned_scheduling.py` | `a3f3badd…` | 同（已跟踪） | 同（未跟踪） | 已有，不迁 |
| `tools/group_work_timing.py` | `a14d5e9c…` | 同（已跟踪） | 同（未跟踪） | 已有，不迁 |
| `tools/rate_spin_cpu_probe.py` | `d3115c14…` | 同 | 同 | 已有，不迁 |
| `tools/probe_release_audit_integrity.py` | `51342c48…` | 同 | `92a83f4e…`（旧） | 已有，**禁止回流** |
| `validation/test_release_audit_integrity.py` | `dff20f4b…` | 同 | `07997136…`（旧） | 已有，**禁止回流** |
| `tools/run_joint_flight.py` | `5527063f…`（无 manager-GC） | 同 Windows | `1c600d7f…` | **条件迁移（主项）**，见 §4 |
| `tools/manager_gc_candidate.py` | **ABSENT** | **ABSENT** | `cbf7b018…`（已跟踪） | **条件迁移**，见 §5.1 |
| `validation/test_manager_gc_candidate.py` | **ABSENT** | **ABSENT** | `637c403c…`，15726 B，385 行 | **条件迁移（作者测试）** |
| `validation/test_gc_candidate_entry.py` | **ABSENT** | **ABSENT** | `85801943…`，8869 B | **条件迁移（入口测试）** |
| `Simulator/wksim_runtime/joint_rate_probe.py` | `a8bac9ac…` | `f2da167…`(blob) | `7855409d…` | **可选诊断增量**，见 §5.2 |
| `validation/test_joint_rate_probe.py` | `c3bfd1cd…` | 同 | `66ad209b…` | 见 §5.3（命名空间需同步） |
| `tools/compare_joint_gc_diagnostics.py` | `808706c2…`（**未跟踪**） | ABSENT | ABSENT | main 侧消费者，见 §0.1/§5.1 |
| `validation/test_compare_joint_gc_diagnostics.py` | `832d2896…`（**未跟踪**） | ABSENT | ABSENT | 同上 |
| `tools/planner_release_handoff.py` | ABSENT | ABSENT | `b1eeaf2d…`，688 行 | 暂不迁 |
| `tools/planner_release_task.py` | ABSENT | ABSENT | `e0c3ae00…`，100 行 | 暂不迁 |
| `tools/early_manager_work_probe.py` | ABSENT | ABSENT | `a5def2ba…`，304 行 | 暂不迁（诊断专用） |
| `tools/audit_pv_trajectory.py` | — | — | 工作树 `920aab3c…` / HEAD blob `cf703523…` | 不在本范围（PV 审计） |

### 3.1 新证据：manager-GC 与 GC 诊断消费者在三条线上的真实分布

| 事实 | 证据 |
| --- | --- |
| manager-GC 的完整提交是 `7cb7e8401776848fcb11e0a8dd2237c1eee2337b`（2026-09-12 22:43:12 +0900），共 6 文件 939 增 21 删 | `git show 7cb7e84 --stat` |
| 该提交**只存在于** `codex/planner-release-validation` 分支 | `git branch -a --contains 7cb7e84` → 仅该分支；`git merge-base --is-ancestor 7cb7e84 386f713a…` → **exit 1** |
| 该提交新增 `tools/manager_gc_candidate.py`(273)、`validation/test_manager_gc_candidate.py`(385)、`validation/test_gc_candidate_entry.py`(195)，并改 `tools/run_joint_flight.py`(**+53**)、`validation/test_joint_evidence.py`(+33)、`validation/test_joint_rate_probe.py`(+21) | 同上 |
| main 的**工作树**却在消费该分支的产物：`tools/compare_joint_gc_diagnostics.py`（未跟踪）把 `tools/manager_gc_candidate.py` 固定到 `cbf7b018…` 并直接加载 | `tools/compare_joint_gc_diagnostics.py:45,48-49,141-170` |
| 该消费者/测试**不在**新架构候选 | 新候选 `tools/compare_joint_gc_diagnostics.py`、`validation/test_compare_joint_gc_diagnostics.py` 均 ABSENT |
| 比较器已内建路径覆盖点，便于迁移到新候选后指路 | `validation/test_compare_joint_gc_diagnostics.py:38-43`：`WKSIM_MANAGER_GC_CANDIDATE` 环境变量 → `\\wsl.localhost\Ubuntu-22.04\root\wksim-release-acceptance-fe3\…` → `/root/wksim-release-acceptance-fe3/…`，并在 `:69-73` 对 SHA 不符直接抛错 |
| 该比较器**不是**正式准入门：`joint_profile.py` 中不存在任何 manager-GC / gc-freeze / compare_joint_gc 引用 | `Select-String joint_profile.py` 无命中 |

**由此得出的重分类**：`--manager-gc-freeze` 与 manager-GC 模块属于**条件迁移**——它不是 MIXED 准入的形式依赖（`joint_profile.py` 不检查它），
但它是当前主线**实验控制与证据通道**的一部分（现役启动器传该 flag；`docs/2026-09-09-final-combo-pv-plan.md:18` 的已验收 PV 命令含 `--async-model-evidence --manager-gc-freeze`，其 2026-09-13 入场修复正由新场 `1w6dru32` 在原命令下验证）。
**缺少该可选 flag 本身不会使 GC 成为新架构的强制依赖**；是否迁入取决于是否保留该启动开关。

## 4. 待迁主项：`tools/run_joint_flight.py` 的**外科式**做法

实测 diff（历史对照工作树 → 新候选）：**472 增 / 50 删**。差异分类：

1. **条件必需（仅当保留 `--manager-gc-freeze` 时）**：`--manager-gc-freeze` 全链 18 处引用——
   argparse（历史 `:1443`）、`sources` 登记（`:571-572`）、构造与 `arm()`（`:586-594`）、`prepare()`（`:1105-1106`）、
   `finally` 内 `restore()` 与 `manager-gc-candidate.json` 落盘（`:1305-1314`）、`main()` 的 PV/MIXED 门（`:1494-1495`）。
   同一提交 `7cb7e84` 对 runner 的增量就是 **53 行**，即该特性本身是一个小而完整的 delta。
2. **可选诊断（各自开关默认关）**：`--rate-spin-cpu-timing`（含 `collections.deque(maxlen=1)` 与 `JointRateSpinCpuProbe` 接线）、
   `--early-work-timing`（6 处包裹点）、`--owned-scheduling-snapshot`（9 个 `# --- owned-snapshot-wiring begin/end N ---` 标记区）。
3. **不得进入新架构默认路径**：`--planner-release-proof`（`PlannerReleaseTask`、`verify_planner_execution`、`planner_prewarm` 校验、`status→observed`、`nominal_pv_acceptance=False`）。依赖 688 行 `planner_release_handoff.py` 与 `planner_release_task.py`，#102 未完成。

**推荐做法（v2 更正，替代 v1 的“整体换 donor”建议）**：**不整体复制 donor 文件**，改为在**现有新架构 runner** 上做特性级 delta：
- 若**保留** `--manager-gc-freeze`：只补 manager-GC 那 53 行 + 其 argparse 门；其余（planner-release / early-work / spin-cpu / owned-snapshot）一律不引入。
- 若**不保留**该开关：runner 完全不改，manager-GC 整包不迁；此时使用新候选启动器时必须去掉 `--manager-gc-freeze`（否则 argparse 直接退出），并接受 GC 诊断通道在该候选上为 `unavailable`。
- 无论哪种选择，**`sources` 中必须保留 `Simulator/wksim_core/model_parameters.py`**（新候选 `tools/run_joint_flight.py:386` 已在列；donor 把它删掉了，属旧件退化，不得回流）。

**v1 矛盾更正**：v1 同时写“成对保留 owned 标记区”与“删除 owned 开关”，二者不可兼得。
本项目对 owned-snapshot 的**唯一自洽选择**为：
- 选择 A（推荐，最小面）：**整段删除** 9 个 owned 标记区 + `--owned-scheduling-snapshot` 的 argparse 与 `main()` 门。
  代价：`result['status']='observed'` 的 owned 语义与 `result['owned_scheduling']` 字段在该候选上不存在（也不再有该开关）。
  影响面已核实**很小**：`validation/test_owned_scheduling.py` 只测 `tools/capture_owned_scheduling`（`from tools.capture_owned_scheduling import …`，无 runner 引用），
  `validation/test_joint_parent.py` 测父进程身份，均不依赖 runner 的 owned 分支。
- 选择 B（保留）：**保留整段**（runner 与已跟踪的 `capture_owned_scheduling.py`/`group_work_timing.py` 同源），并**同时保留** `--owned-scheduling-snapshot` 开关。
  该 flag 自带“独立使用”门（不得与 pause/scene/DDS/planner/spin/early-work 组合），因此不会与其他开关并存。

## 5. 次项：条件迁移与可选诊断

### 5.1 manager-GC 包（条件迁移）

**迁入清单（若保留该开关）**：
1. `tools/manager_gc_candidate.py`（`cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66`，273 行，仅标准库 `gc`/`time`）。
2. `validation/test_manager_gc_candidate.py`（`637c403c3fe5ea44d097fb89479b10d353d51b2684c4fb52cdcf5d017a6aa6ad`，385 行）。
   **v1 更正**：v1 写“历史对照未见同名测试文件”，这是错误的；该测试已存在并由 `docs/coordination/codebuddy-gc-freeze-review-20260912.md:138` 记录独立复跑 **23/23 OK**。
3. `validation/test_gc_candidate_entry.py`（`8580194384d843948ee4fa55435454558730d459cd9da201b0d2d7003dffd975`，195 行）——导入**真实** `run_joint_flight`，断言默认命名空间含 `manager_gc_freeze=False`（`:95-100`）且 PV/MIXED 允许该 flag（`:104-109`）。它是迁移后验证入口接线的现成测试。
4. runner 的 53 行 delta（§4）。
5. （可选）若同时要求新候选能跑 GC 诊断比较：把 main 的两件未跟踪消费者复制到新候选——`tools/compare_joint_gc_diagnostics.py`（`808706c2…`）与 `validation/test_compare_joint_gc_diagnostics.py`（`832d2896…`），并用 `WKSIM_MANAGER_GC_CANDIDATE` 指向新候选模块路径（比较器已支持该变量，且会校验 SHA）。

**边界**：`report()` 明确 `classification=candidate_not_performance_pass`、`performance_pass=false`（历史 `oayggl_s` 实测 `armed/prepared/restored=true`、`froze_own_graph=false`）。**不得**把该候选的运行写成性能通过或 MIXED 通过。

### 5.2 `joint_rate_probe.py` 新增字段（**可选诊断**，v2 重分类）

`7855409d…` 相对新候选基线（blob `f2da167…`）是 **+27 / -0** 纯增量：`TimingSample` 与 `_ActiveSample` 各增
`last_sleep_before_ns`、`last_sleep_after_ns`、`last_sleep_requested_ns`、`last_health_before_ns`、`last_health_after_ns`，
`_raw_sleep` 完成后原子写入三元组，loop-health 完成时记录 before/after。

**重分类理由**：这些字段只在 `WKSIM_JOINT_RATE_TIMING_PROBE=1` 时写入；无探针场（如 `oayggl_s`，`pre-run-identity.json:20-23` 两变量为 `null`）行为完全相同。
新候选的 `validation/test_joint_rate_probe.py`（`c3bfd1cd…`）**不引用**这些字段名（grep `last_sleep|last_health|as_dict` 无命中），
因此**不迁入该增量不会使任何现有测试失败，也不阻断无探针准入**。它的价值仅在于下一次带探针诊断时能区分“睡醒晚”与“health 晚”。

### 5.3 `validation/test_joint_rate_probe.py`（**v3 撤回 v2 的错误结论**）

**事实（精确源码，v3 重读）**：
- `tools/run_joint_flight.py:329` = `async_model_evidence = getattr(args, 'async_model_evidence', False)` —— **受保护读取**；
  `:332` `model_promotion_flight = getattr(args, 'model_promotion_flight', False)` 同样受保护。
- `validation/test_joint_rate_probe.py`（Windows 与新候选均 `c3bfd1cdd4328c5a084bd7c5f9b9acfec774d008bc9b7ef448b69b2050bf47cb`）
  第 401-438 行的用例只构造 `SimpleNamespace` 与之交互，**在 main 上实跑通过**：
  `python -m unittest validation.test_joint_rate_probe.JointRuntimeTimingProbeEntryTests.test_real_runner_source_manifest_and_source_unchanged_follow_probe_state -v`
  → `Ran 1 test` / `OK`（两条 stop-before-flight 路径均由 mock 覆盖，无 native）。

**v2 错误**：v2 §5.3 断言 `run()` “以普通属性读取 `async_model_evidence`”，并据此断言该用例必然 `AttributeError`、需要补全 `SimpleNamespace`。
该断言与精确源码不符，**整段结论作废**；相应的“必跑失败项”与“命名空间修复”要求一并撤回。

**仍然成立的相关事实**：donor 的 `7cb7e84` 对 `validation/test_joint_rate_probe.py` 的 +21 行确实补全了命名空间
（供体 runner 读取更多普通属性，如 `planner_release_proof`、`manager_gc_freeze`）。这是**供体侧**的需求：
**若**按 §5.1/§5.2 迁入相应 wiring，则该测试的命名空间需与实际生效属性集合同步；**若**只保留现有 runner 行为（不迁任何 wiring），
本用例保持通过，**无需任何测试改动**。不得以历史对照的 `66ad209b…` 覆盖新候选测试文件。

## 6. 最低风险 变更 / 构建 / 准入 序列

**阶段 A：只读身份固化（已完成）**
1. 固化三棵树身份、待迁清单与 SHA（§1/§3 + `migration-identity.json`）。2. 生成并保存 diff（`commands.md` §4）。

**阶段 B：候选树内逐文件迁移（由 main 执行；一个文件一个写入者）**
3. 决策点：是否保留 `--manager-gc-freeze`（记录决策再动手）。
4. 若保留：迁 `tools/manager_gc_candidate.py` + 两个测试文件 → 校验 SHA 等于 `cbf7b018…` / `637c403c…` / `85801943…`；
   在现有 runner 上补 53 行 delta（**不整体替换 donor**）。
5. 若不保留：runner 不动；启动器去掉该 flag；在候选收据中记录 GC 通道 `unavailable` 的原因。
6. 可选：按 §5.2 迁 rate_probe 增量；**仅当**同时迁入 §5.1/§5.2 的 wiring 时，才需要按 §5.3 同步 `validation/test_joint_rate_probe.py` 的命名空间。
   不迁任何 wiring 时该用例保持通过，不做测试改动。
7. 不改：`joint_profile.py`、`worker.py`、`joint_rate.py`、`evidence_stream.py`、`capture_owned_scheduling.py`、
   `group_work_timing.py`、`rate_spin_cpu_probe.py`、`run-joint-flight.sh`（新候选已同 SHA）。
8. 禁止整目录覆盖；禁止把 `model_parameters.py`、`probe_release_audit_integrity.py`、`test_release_audit_integrity.py` 的旧副本回流。

**阶段 C：离线验证（不启动 native/SITL/UE）**

| 测试（实际路径） | 覆盖点 | 受影响原因 |
| --- | --- | --- |
| `validation/test_gc_candidate_entry.py` | 真实 runner 的 flag 解析、默认命名空间、PV/MIXED 门 | 迁移后入口接线 |
| `validation/test_manager_gc_candidate.py` | `arm/prepare/restore/report`、外部占用拒绝、失败后所有权、23 项 | 若迁 manager-GC |
| `validation/test_joint_rate_probe.py`（第 401 行用例） | runner 的 sources/source_unchanged 与探针状态 | **当前通过**（main 实跑 `Ran 1` / `OK`）；仅当迁入 wiring 时按 §5.3 同步命名空间 |
| `validation/test_joint_profile.py` | MIXED 剖面契约、篡改拒绝、探针标记拒绝 | runner/身份口径变化 |
| `validation/test_owned_scheduling.py` | `capture_owned_scheduling` 本体（无 runner 依赖） | 仅在选择 B 时作护栏 |
| `validation/test_compare_joint_gc_diagnostics.py` | 真实 `ManagerGCFreeze` + 注入 `FakeGC` 的合同比较 | 仅在阶段 B 第 5 项执行时 |
| `validation/test_joint_rate.py`、`test_analyze_joint_rate_probe.py`、`test_joint_rate_intervals.py`、`test_rate_tail_contract.py`、`test_rate_fault.py`、`test_audit_joint_rate.py` | 段/组边界、100 ms 晚限、latch、滑窗 | 仅在迁 §5.2 时 |
| `validation/test_mixed_profile_admission.py`、`test_mixed_candidate.py`、`test_mixed_control_evidence.py`、`test_mixed_control_task.py`、`test_ap_mixed_timeout.py` | MIXED 准入与任务证据 | MIXED 是目标剖面 |
| `validation/test_worker_serialization_reuse.py`、`test_joint_model_worker.py` | worker 侧 | 本次不迁，作回归护栏 |

**阶段 D：准入（本轮不做）**
9. 新候选上确认冻结组合引用（AP mixed `1e6250ef…`、Control `6fe8c0b3…`、Message `29969da0…`、PX4 `d7e905b3…`）；不改哈希放行。
10. 两 WSL 前检（`found=[]`、同 boot、≤60 s 新鲜度），再由入口在启动时校验（交付策略规则 14）。
11. 新候选启动器跑一次**无探针** MIXED，按原门判定：1 ms tick / 4 tick 组 / 无追赶 / 100 ms 晚限 / 完整滑窗（10 s ±2%、60 s ±1%）/ 组数覆盖 / `source_unchanged`。
12. `RateUnmet` 复现则保留原件、不重跑该配置、不做因果归因；正式 MIXED 证据集在此之前保持 `ok=false`。
13. 只有“祖先 exit 0 + 迁移后 runner SHA 冻结 + 离线测试通过 + 实跑落在原门内”同时成立，才可声明新架构 MIXED 准入；**不得**用历史对照的任何旧 PASS 代替。

## 7. 遗留限制

1. 本轮**没有**执行任何运行/构建/原生动作；§2.5 的任务时长是**由上限推导与代码上界粗算**，不是实测完成时长。
2. `oayggl_s` 的 `tasks={}`、`rate=null`：失败场没有任务报告；段内组数与 latch 由 `rate.jsonl` 逐行文本统计，未使用场级分析器（所述工具链不在工作区，且属禁止执行范围）。
3. 迁移供体是**工作树内容**而非 git 对象：`1c600d7f…`、`cbf7b018…` 等均为文件 sha256，`git cat-file -e <sha256>` 不成立；核对必须按内容 SHA。
4. 历史对照 HEAD `db1200d` 的 `joint_rate_probe.py` 与 `run_joint_flight.py` 都**旧于**其工作树（blob `f2da167…` / 另有基线），且 `joint_profile.py` blob 为 `82a53b00…`。按 HEAD 推断工作树内容会出错。
5. `7cb7e84` 的 53 行 runner delta 是否与候选当前 runner（`5527063f…`，`d45d1da` 与 `386f713` 两处相同）精确兼容，尚未验证（本轮禁止改动/构建）；迁移时应按内容核对而非直接 `git cherry-pick` 后假定干净。
6. `tools/audit_pv_trajectory.py` 历史本地修改的用途未取得结论，登记为待确认。
7. 未运行 Codebase Memory 图查询：`tools/`、`docs/` 按 `docs/codebase-memory.md:151` 显式排除，新件在 `docs/codebase-memory.md:25` 亦记为 tools 排除；本轮全部直接读取，未依赖图结论，也未为只读调查重刷索引。
8. 本文件不是 Full/G6 台账的替代，不构成任何新架构验收结论。
9. v2 §5.3 曾给出未经精确源码核对的断言（见 v3 摘要与 §5.3）；本文件其余硬断言已在 v3 按精确源码/回执逐条重审（§9）。

## 8. 复现命令

见 `validation/coordination/ds-architecture-mixed-migration-20260913-01/commands.md`（全部只读：`git`/`stat`/`sha256sum`/`head`/`grep`）。

## 9. 硬断言重审（v3；逐条按精确源码/回执核对）

| # | 断言 | 核对命令（只读） | 结果 |
| --- | --- | --- | --- |
| 1 | Windows `main` HEAD 与 `f333316` 祖先 | `git rev-parse HEAD`；`git merge-base --is-ancestor f333316… HEAD` | `386f713a…`；exit 0 ✔ |
| 2 | 候选当前 HEAD（已 fast-forward） | `git -C <候选> rev-parse HEAD`；`status --porcelain` 行数 | `386f713a…`；0 行 ✔ |
| 3 | 候选祖先检查 | `git -C <候选> merge-base --is-ancestor f333316… HEAD` | exit 0 ✔ |
| 4 | 同步回执内容 | 读 `validation/coordination/architecture-candidate-sync-20260913-02/receipt.json` | `new_head=386f713a…`，`private_wiring_migrated=false`，`native_executed=false` ✔ |
| 5 | 配置倍率 0.5（源码派生） | `tools/run_joint_flight.py:757`；`joint_rate.py:5,33-35`；`scene_clock.py:14` | `.5`；`RATES=(0.5,1.0)`；`period_ns=int(4_000_000/requested_rate)`（属性 `:33-35`）；`STEP_NS, MACRO_TICKS = 1_000_000, 4` ✔（v2 曾把 `:33-35` 写成 `:33-36`，已修正） |
| 6 | 上限与晚限 | `tools/run_joint_flight.py:49`；`joint_rate.py:6,81-87` | `WALL_LIMIT, MAX_TICKS = 900, 180000`；`LATE_LIMIT_NS=100_000_000` ✔ |
| 7 | 段墙钟 = latch − anchor | `rate.jsonl` 逐行读（`python3` 文本统计） | `316456162907 − 100427426404 = 216028736503 ns` ✔ |
| 8 | 段仿真 = 26991 组 × 4 ms | 同上（组数计数 = 26991） | `107.964 s`；`(108004−40)/4 = 26991` ✔ |
| 9 | 段平均 0.499767（不作门） | `107.964 / 216.028736503` | `0.49976684466930027` ✔ |
| 10 | 禁用混算值 0.401768 | `107.964 / 268.72185634100003` | `0.40176858507183316` ✔ |
| 11 | 滑窗/100 ms 门失败 | `rate.jsonl` 的 `rate_unmet` 记录 + 合同文档 | latch `lateness_ns=100644532`；`rate_segment_end` 计数 0 ✔ |
| 12 | main 侧 runner 无 manager-GC | `Select-String tools/run_joint_flight.py -Pattern 'manager_gc\|manager-gc'` | 无命中 ✔ |
| 13 | manager-GC 提交不在 main | `git branch -a --contains 7cb7e84`；`git merge-base --is-ancestor 7cb7e84 386f713a…` | 仅 `codex/planner-release-validation`；exit 1 ✔ |
| 14 | manager-GC 非正式准入门 | `Select-String Simulator/wksim_runtime/joint_profile.py -Pattern 'manager_gc\|gc-freeze'` | 无命中；且 `joint_profile.py:274-276` 仅拒 `rate_timing_probe`/`group_work_timing` 标记 ✔ |
| 15 | 交付启动器传该 flag | `Select-String validation/coordination/*/launch.sh -Pattern 'manager-gc-freeze'` | `last-callbacks-run…:25`、`manager99-*:26`、`parent-probe-run…:26` ✔ |
| 16 | 已验收 PV 命令含该 flag | 读 `docs/2026-09-09-final-combo-pv-plan.md:18` | 含 `--async-model-evidence --manager-gc-freeze` ✔ |
| 17 | donor→候选 runner diff 472/50（同步后不变） | `git diff --no-index --stat` | `472 insertions, 50 deletions` ✔ |
| 18 | rate_probe donor diff +27（同步后不变） | `git diff --no-index --stat` | `1 file changed, 27 insertions(+)` ✔ |
| 19 | 候选三件套 SHA 与 Windows 相同 | `sha256sum` 双侧 | runner `5527063f…`、probe `a8bac9ac…`、test `c3bfd1cd…` ✔ |
| 20 | manager-GC 三件在候选 ABSENT | `test -f` 三路径 | 全部 ABSENT ✔ |
| 21 | `model_parameters.py` 保留在 sources | `tools/run_joint_flight.py:386` | 在列 ✔；donor 删除该行（旧件退化）✔ |
| 22 | owned 测试不依赖 runner owned 分支 | 读 `validation/test_owned_scheduling.py` 导入行 | 仅 `from tools.capture_owned_scheduling import …` ✔ |
| 23 | **v2 §5.3 断言（已撤回）** | `tools/run_joint_flight.py:329`；`python -m unittest …test_real_runner_source_manifest… -v` | 实为 `getattr(...)`；用例 `Ran 1` / `OK` ⇒ v2 断言**错误，已撤回** ✘→修正 |
| 24 | MIXED 任务上界位置 | `tools/mixed_control_task.py:64-67,96-98` | `stable_hold` 定义 `:64`、`wall_limit_s=12.` `:66`；腿 1 从 `:96-98` 起 ✔ |
