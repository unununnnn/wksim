# #83 倍率诊断就绪包：可执行的一次诊断场（2026-09-12）

## 当前结论（2026-09-14）

- **#83 不重跑**：`1w6dru32` PV 已通过并 CLOSED。下文命令是 2026-09-12 的历史诊断包，**不得**由本模块或其它会话再执行。
- **MIXED / G6 / Full 未通过**；#84 仍开放。
- **99 不满足倍率门**：最新无探针实证是 `oayggl_s` / `RateUnmet`，停止重复 99 配置。
- **下一 native 场仅主会话执行**。1ms / native 屏障 / 无追赶 / 100ms / 完整窗口不改。
- `oayggl_s` / `x39qjvkw` / `5lfbcy43` / `rfw9nmbb` 不得误配为受控对照或因果结论。
- 离线比较器新增类型/结构/pairing 身份门：非负 `int` 时钟与 lost·overflow（拒绝 `bool`）；有限 CPU/代价；`result.json` 与 source map 必须是 object；已知场不得对匿名 run；双方空 `source_sha256` 不得 `controlled_pairing`。`causal` 恒 false，`performance_pass` 恒 false。

本文件曾是主会话可以直接执行一次的**诊断包**，不是验收计划，也不是修复方案。诊断场永不得登记为
#83 通过证据：正式 mixed/PV 促进路径会在证据含 `rate_timing_probe` 时直接 raise
（`Simulator/wksim_runtime/joint_profile.py:219-220`，原文 `Formal mixed/PV evidence cannot
include rate_timing_probe`）。#83 已 CLOSED，本包不再保持 OPEN。

**两个审计工具的实际行为（只读源码核对，不要指望它们替本场做拒绝）**：
`tools/audit_joint_rate.py:32-42` 只校验 probe 的**密封身份块**（缺失或不符才 fail-closed），
带正确身份的 `rate_timing_probe` 行会通过校验，并在 `schedule()`（:44-106）的 kind 分派里
**被静默忽略**（无 `rate_timing_probe` 分支、无 else）；该文件全文没有针对本诊断两个开关的
字面检查。`tools/audit_pv_trajectory.py` 全文 **0 处** `rate_timing_probe`/`timing_probe`，
其 :297-299 检查的是 `pause_probe_requested`、`scene_lifecycle_requested`、
`scene_lease_loss_requested`、`dds_loss_requested`、`diagnostic_land_step_period_s`，与本场的
probe/CPU-timing 开关无关。因此"本场仅诊断、不充当 #83"是**操作边界**，不是靠这两个工具主动
拒绝来实现的。

本模块只做只读数据分析与纯单测：未启动 native/ROS/model/build，未改 `joint_rate.py`、
`physics`、调度，未新增代理，未提交 Git。

## 1. 本次只读复算已确认的事实（分析基础）

用修复后的区间核算（`tools/analyze_joint_rate_intervals.py`
`c3ba9de8f4ac61d6b39750bdabed737915d85d3bee53d56fed8157237bca98b8`）对四场真实失败逐场复算，
`首组起始迟到 + creep_total + 末段剩余增量 == 记录的 rate_unmet latch` 全部精确闭合
（差 0 ns），无外来 identity 混算：

| 场次 | rate.jsonl SHA256（前 12） | 首组迟到 | creep_total | 末段增量 | 记录 latch | latch 形态 / tick |
|---|---|---:|---:|---:|---:|---|
| zzmg3k47 | `62596ed95ce9` | 118903 | 99881013 | **92179** | 100092095 | begin_group 释放等待 / 98700 |
| tpwl1k4p | `41b1e2a6bc57` | 116719 | 99877507 | **44659** | 100038885 | begin_group 释放等待 / 26636 |
| nqyqcagl | `d385de34204e` | 115025 | 97921130 | **6224284** | 104260439 | end_group 组内 work-over / 53128 |
| 8fmacpgy | `16f05a808e6e` | 114791 | 70719737 | **63993754** | 134828282 | end_group 组内 work-over / 67996 |
| bomvjsmg（对照） | `1a4cc6a00b34` | 118524 | 75203176 | `null` | `unavailable` | 无 latch，`no_rate_unmet_for_identity` |

关键含义：**zzmg3k47 / tpwl1k4p 的记录组起始从未达到 100 ms**（最大 99999916 / 99994226 ns），
守卫是在下一组 `begin_group` 释放等待里被这 92179 / 44659 ns 的增量推过去的。这 92 µs / 45 µs
落在哪一段，现有正式记录没有任何字段能回答；`rate_timing_probe` 是唯一既有、可测量的工具。
bomvjsmg 的 75321700 ns 只是较轻的单段 release 场，不参与上述结论，也不外推到两段。

## 2. 冻结身份（本会话重新实读 sha256sum，逐字节核对）

| 角色 | 路径 | SHA256 |
|---|---|---|
| AP mixed | `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json` | `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c` |
| Control（当前冻结候选） | `/root/wksim-joint-control-c2IXOr/build.json` | `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e` |
| Message | `/root/wksim-ros2-Rzj3Pf/message-build.json` | `29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219` |
| PX4（profile 钉值，须复核） | `/root/wksim-px4-state-ONa1Kw/wksim-build.json` | `d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6` |

执行源码身份（`/root/wksim-release-acceptance-fe3`，本会话实读）：`tools/run_joint_flight.py`
`92e3c7dc9d4dde2b7ca38e16705c47a115e8f2a07cbecdd3eb84d7d1cacd073b`、
`tools/run-joint-flight.sh` `ea012da68bd8fcb3e25383197bf5a9f076aecfe5d3fd9a966675aa0d69fdc883`、
`Simulator/wksim_runtime/joint_rate.py` `0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4`、
`Simulator/wksim_runtime/joint_rate_probe.py` `a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653`、
`Simulator/wksim_core/joint.py` `f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50`。

不得使用旧身份：`0DQQz9`（`25edbf81…`，固定 profile `joint_quad_dds_mixed_pv_v1` 仍钉此值）、
`rWolCy`（`a6a17b42…`）、`ZlTVa4`（`3d04d53a…`）只作历史对照，不参与本诊断场。

## 3. 要消除的唯一主要不确定性

> **在最终组合 0.5× PV 场上，把守卫推过 100 ms 的那一段释放等待（含累积 creep 的逐组分布）
> 由监督器哪些阶段构成——entry→首次 health、循环 health 调用、`sleep` 实际 vs 请求、
> 终段自旋/其余、以及 check 前的记录写入？**

判定标准（可反驳）：诊断场 `rate.jsonl` 的 `rate_timing_probe` 行（尤其 latch 时
`outcome="rate_unmet"` 的那一行）必须给出闭合的阶段分解，使该增量能落到具体阶段；若分解显示
增量均匀落在大量组的循环 health/睡眠超时上，则"末段偶发"被反驳；若集中在 latch 前最后几次
health 或 `sleep_max_overshoot_ns`，则确认。同一场次顺带给出 end_group 形态（组内 work-over）
的 `diagnostic_step_cpu_timing` 分段作为次要观测量。

**明确不测/不声称**：不测 OS 抢占与 wake-to-run（没有 sched tracepoint/BPF，本场不开），
因此即使阶段分解闭合，也不得给出"CPU/AP/PX4 根因"的排他归因。

## 4. 完整命令（一次诊断；前置 + 运行）

前置（全部由主会话现场执行，本模块未触）：

1. 预约独占运行资源；入口自生成唯一 run/live 目录，**不复用任何旧目录**。
2. 复核 §2 四处 SHA（`sha256sum`）与 `/root/wksim-release-acceptance-fe3` 工作区干净度。
3. PX4 身份**不在本命令里给**：PV 入口把 `--px4-manifest/--px4-sha256` 当"alternate probe"
   直接拒绝（`run_joint_flight.py:1092-1099`）。PX4 由准入的固定 profile 链核验，见 §4.2。
4. 确认 `WKSIM_JOINT_CPU_TIMING` / `WKSIM_JOINT_RATE_TIMING_PROBE` 未被验收入口使用（互斥）。

```bash
cd /root/wksim-release-acceptance-fe3

WKSIM_JOINT_CPU_TIMING=1 \
WKSIM_JOINT_RATE_TIMING_PROBE=1 \
bash tools/run-joint-flight.sh \
  --task-profile full_xyz_pv_yaw_v1 \
  --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
  --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
  --control-manifest /root/wksim-joint-control-c2IXOr/build.json \
  --control-sha256 6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e \
  --message-manifest /root/wksim-ros2-Rzj3Pf/message-build.json \
  --message-sha256 29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219 \
  --async-model-evidence
```

- 两个开关的**值域不同**：`WKSIM_JOINT_RATE_TIMING_PROBE` 只接受 unset/`0`/`1`，其他值 raise
  （`joint_rate_probe.py:25-30`）；`WKSIM_JOINT_CPU_TIMING` **只在取值恰为 `1` 时启用**，其他值
  静默关闭、不 raise（`joint.py:54`：`os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'`）。本命令
  两者都写 `1`，属于两种开关各自的"开"取值。
- `--async-model-evidence` 由主会话裁定加入：与当前 #83 合同及最近 `nqyqcagl` 的
  "请求且两栈 writer 正常 closed" 配置一致（§4.3）。两个 timing env 是本诊断的**明确仪器**，
  async 是**证据写入形态**，二者并列同场。**本包不把"去掉 async"写成已证明必要**：本模块只做过
  字段实读，没有证明 async 对等待读数的影响。
- 本条命令**不含** `--px4-manifest/--px4-sha256`，也**不含** `--ap-manifest/--ap-sha256`、
  `--ap-pv-manifest/--ap-pv-sha256`、`--pause-probe`、`--scene-lifecycle`、`--scene-lease-loss`、
  `--dds-loss`、`--native-state-trace`、`--probe-land-freshness`：PV 分支要求"恰好一对 AP
  manifest（PV 或 mixed）+ message 对 + 无 alternate probe"（`run_joint_flight.py:1092-1099`）。
  message 对在 PV 分支是**必需**的（`:1095`）。
- async + 两个 timing env 三者同场没有既有实跑证据（OMP 冻结报告 §4/§6 已标未证），故本包把它
  作为**一次**执行并在 §7 给出"只测到一半"时的处置，而不是当场重试。

### 4.1 参数验证（纯 parser + mock `run()`，本模块实跑，未触 native）

方法：按 `tools/run-joint-flight.sh:22` 的真实 argv 形态
（`python3 -B <repo>/tools/run_joint_flight.py run "$@"`）导入真实 runner，用
`unittest.mock.patch.object(module, "run", return_value=0)` 替换 `run`，再调用
`main(["run", …上述 flag…])`；`run` 被替换后不创建任何进程、不读任何清单字节。

| 用例 | 结果（主仓库 runner 与 Linux 实验区 runner 一致） |
|---|---|
| 上面这条命令（含 `--async-model-evidence`） | `exit 0`，`run_called=1`，`native_called=false`，`async_model_evidence=true`，`px4_manifest=None` |
| 上面这条命令去掉 `--async-model-evidence` | `exit 0`，`run_called=1`（两种形态 parser 都允许；不是被 parser 强制的） |
| 上面这条命令 + `--px4-manifest/--px4-sha256` | `SystemExit(2)`，`run_called=0`，错误 `P+V requires exactly one explicit PV or mixed AP manifest/SHA pair and no alternate probes` |
| 上面这条命令 + `--ap-manifest/--ap-sha256` | `SystemExit(2)`，`run_called=0`，同上错误 |
| 上面这条命令 + `--pause-probe` | `SystemExit(2)`，`run_called=0`，同上错误 |

结论：修正后的命令（含 async）在真实 parser 上能进入 mock `run()`；退回报告里的 exit 2 由
`--px4-manifest/--px4-sha256` 触发，与 `run_joint_flight.py:1097` 的
`args.px4_manifest or args.px4_sha256` 判定一致。

### 4.2 PX4 身份的离线核验（不写进 PV CLI，也不假设有 `px4-build.json`）

PV 分支不接 PX4 override，PX4 来自固定 profile `joint_quad_dds_mixed_pv_v1`
（`Simulator/wksim_runtime/joint-profiles.json:50-70`，其 `manifests.px4` 指向
`/root/wksim-px4-state-ONa1Kw/wksim-build.json` `d7e905b3…`）。运行前只做**只读**核对：

```bash
sha256sum /root/wksim-px4-state-ONa1Kw/wksim-build.json   # 期望 d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6
```

**产物事实（不要声明不存在的文件）**：runner 只在传了 `--px4-manifest` 时才复制
`live/px4-build.json` 并写 `result['manifest_sha256']['px4']`（`run_joint_flight.py:497-499`）；
本命令不传该 flag，因此**本场不会产生 `live/px4-build.json`**，`manifest_sha256` 里也没有 `px4`
键。本场实际会复制到 run 目录的清单是：`live/ap-build.json`（mixed 候选，`:500`）、
`live/control-build.json`（`:501`）、`live/message-build.json`（`:443`）、
`live/model-build.json`（`:473`）、mixed 情况下的 `live/mixed-source.json` 与
`live/baseline-pv-build.json`（`:506-507`）。

PX4 的**实际身份证据**改从 `result.json` 的 `mixed_admission` 读（字段名与实读值，来源
`validation/joint-public-flight-nqyqcagl/result.json`）：

| 字段 | 实读值 |
|---|---|
| `mixed_admission.identities.baseline.manifests.px4.path` | `/root/wksim-px4-state-ONa1Kw/wksim-build.json` |
| `mixed_admission.identities.baseline.manifests.px4.sha256` | `d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6` |
| `mixed_admission.identities.baseline.px4.path` | `/root/wksim-px4-state-ONa1Kw/src/build/px4_sitl_default/bin/px4` |
| `mixed_admission.identities.baseline.px4.sha256` | `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a` |
| `mixed_admission.configs.px4.px4_root` | `/root/wksim-px4-state-ONa1Kw/src` |

主会话可**另行保留**（不在 run 目录内、需要显式拷走）的原清单，路径同样来自该 admission：

- PX4 钉值清单 `/root/wksim-px4-state-ONa1Kw/wksim-build.json`（`d7e905b3…`）；
- 基线 AP clock-stop 清单 `/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json`（`f347ba25…`）；
- 基线 PV 清单 `/root/wksim-ap-pv-vn04950x/pv-build.json`（`e05e5c9d…`，同一哈希已作为
  `live/baseline-pv-build.json` 落盘）；
- 基线控制清单 `/root/wksim-joint-control-FVMjak/build.json`（admission 只记哈希
  `f02edf15…`，不复制）。

并注意 profile 钉档同时仍钉着历史 Control `0DQQz9`；候选 flag 路径
（`--control-manifest/--message-manifest`）覆盖它，而 legacy/`model_promotion_flight` 路径会
解析出旧身份，本诊断只走候选 flag 路径（OMP 冻结报告 §1）。

### 4.3 证据写入形态（主会话裁定：加 `--async-model-evidence`）

保留场次里 `--async-model-evidence` 的实读值（各场 `result.json`）：

| 场次 | Control | 实际字段 | 含义 |
|---|---|---|---|
| zzmg3k47 | 0DQQz9 | 无 `async_model_evidence` 字段 | 未请求 |
| tpwl1k4p | rWolCy | `async_model_evidence_requested=true`，无 `async_model_evidence` 块 | 请求了但 writer 未完成（summary.json: `writer_summaries_complete=false`，"Both model evidence writer summaries are required"） |
| nqyqcagl | ZlTVa4 | `async_model_evidence_requested=true`，`async_model_evidence` 两栈 `complete=true`/`closed=true`/`submitted_bytes==written_bytes` | 请求且完整 |
| 8fmacpgy | c2IXOr | `async_model_evidence_requested=false`，无 `async_model_evidence` 块 | 未请求 |

**本诊断采用 `async_model_evidence_requested=true`（命令里带 `--async-model-evidence`）。**
依据：

1. 主会话已裁定本场加该 flag，与当前 #83 合同及最近 `nqyqcagl` 的"请求且两栈 writer
   `closed=true`/`complete=true`"配置保持一致；`nqyqcagl` 证明该形态在 `full_xyz_pv_yaw_v1`
   上可与真实倍率锁存共存。
2. 两个 timing env 是本诊断的**明确仪器**（测量监督器释放等待的阶段分解）；async 是**证据
   写入形态**，不是被测量对象，两者并列合法（`run_joint_flight.py:1090` 只要求 PV/MIXED）。

**明确不作的两项断言**：本包不声称 async 写入对等待读数"有害/污染"，也**不声称去掉 async 是
已证明必要的**——上表只是字段实读，本模块没有做过 async 的对照或因果测量。若 §4.1 的对照形态
（不带 async，parser 同样 `exit 0`）被需要，那是主会话可另行选择的配置，不是本包的结论。

## 5. 运行后立即固定的原件与预期原始字段

固定：`rate.jsonl`、`result.json`、两机 `*-truth.jsonl`/`*.writer.json`、`clock.jsonl`、
`arducopter-control.log`、`px4-control.log`、`children-start.json`、`experimental-admission.json`
及三份 build 清单原件；逐件 SHA256，落到新的 `validation/33-rate-profile/<run>/` 式目录。

`rate.jsonl` 中预期出现（生产者 `Simulator/wksim_runtime/joint_rate_probe.py:50-77,193`）：

- `kind="rate_timing_probe"`，字段：`outcome`（`started` / `rate_unmet` / `rejected`）、
  `start_tick`、`end_tick`、`entry_ns`、`initial_health_end_ns`、`terminal_ns`、
  `ideal_start_ns`、`earliest_start_ns`、`entry_to_initial_health_ns`、`loop_health_ns`、
  `loop_health_calls`、`sleep_requested_ns`、`sleep_elapsed_ns`、`sleep_calls`、
  `sleep_max_overshoot_ns`、`final_spin_other_ns`、`release_excess_ns`、
  `observed_elapsed_ns`、`phase_total_ns`，并内嵌身份块
  `rate_timing_probe={"diagnostic":"joint_rate_timing_probe","classification":"diagnostic_only","production_performance":false,…}`。
- 闭合约束（分析器会断言）：`phase_total_ns == observed_elapsed_ns == 四阶段之和`；
  `release_excess_ns == max(0, terminal_ns − earliest_start_ns)`；
  `sleep_max_overshoot_ns ≤ sleep_elapsed_ns`。
- **latch 行**：若守卫在 `begin_group` 触发，失败的那次尝试也会产出一行
  `outcome="rate_unmet"`（`JointRateTimingProbe.begin_group` 的 `finally`），它的阶段分解
  就是"推过 100 ms 的那一段"；同一 tick 另有 `kind="rate_unmet"` 的原有 latch 记录。
- 既有 `rate_group_start` / `rate_group_end` 保持不变；`rate_request`/`rate_anchor`/
  `rate_bootstrap` 照旧。
- `WKSIM_JOINT_CPU_TIMING=1` 的产物只在原始 trace/truth：`diagnostic_gc_timing`、
  `diagnostic_step_cpu_timing`、`diagnostic_native_input_timing`（**不进 result.json**）。
- `result.json` 预期带 `rate_timing_probe` 身份字段；若 latch，另有 `faulted_authority` 与
  `error=RateUnmet(...)`。
- `result.json` 的 `async_model_evidence_requested` 预期为 `true`，并应有 `async_model_evidence`
  两栈块（§4.3）：`complete`/`closed` 为真、`submitted_bytes == written_bytes`、`error` 为空。
  若该块缺失或 `complete=false`，按 tpwl1k4p 先例如实记录配置偏差；它不改变 probe 行的阶段
  测量是否成立（主测量只依赖 probe 行），但主会话应把它记入本场配置差异。
- PX4 身份：**不会有 `live/px4-build.json`**（`run_joint_flight.py:497-499` 仅在传
  `--px4-manifest` 时复制）；以 `result.json` 的 `mixed_admission.identities.baseline.manifests.px4`
  与 `identities.baseline.px4`、`configs.px4.px4_root` 为准（§4.2 表）。

## 6. 运行后分析命令（必须用主仓库修复版分析器）

注意：实验区 `/root/wksim-release-acceptance-fe3/tools/analyze_joint_rate_intervals.py` 仍是
未修复的 `14ed9d64…`；本模块修复版在主仓库，SHA `c3ba9de8…`。分析必须用后者（或用
`/mnt/c/Users/PC/Documents/odid编译/wksim/tools/...` 显式路径调用），否则拿不到 latch 核算。

```bash
# Windows 主仓库根目录（先只读保留原件，再写新输出，分析器拒绝覆盖已有文件）
python -B tools/analyze_joint_rate_intervals.py <rate.jsonl> --output <NEW>/intervals.json
python -B tools/analyze_joint_rate_probe.py    <rate.jsonl> --output <NEW>/probe.json
python -B tools/analyze_joint_rate_tail_phases.py <rate.jsonl> --output <NEW>/tail-phases.json
python -B -m unittest validation.test_rate_tail_contract validation.test_joint_rate_intervals
```

预期输出：
- `intervals.json`：`latch_reconciliation.status="reconciled"`、
  `recorded_latch_lateness_ns`、`terminal_unreconciled_ns`、
  `first_group_start_lateness_ns + creep_total_ns + terminal_unreconciled_ns == latch`；
  若本场未跨限，则 `status="unavailable"`、两值为 `null`（不是 0）。
- `probe.json`：`phases` 各阶段 total/max/mean/observed_share、
  `release_excess_ns` 的 entry_lateness / post_entry_excess 拆分、`counters`（含
  `sleep_max_overshoot_ns`）、`outcomes`（含 `rate_unmet` 行数）。
- `tail-phases.json`：100–500 µs release-excess 桶（区间下开上闭）与各阶段的相关表；
  参考量级：zzmg3k47 该桶 319 个区间 / 54343233 ns，8fmacpgy 178 个 / 30236171 ns。

## 7. 判定规则：什么算"测到"，什么算"没测到"

测到（本诊断的目标达成）：
1. `rate.jsonl` 有 ≥1 行 `rate_timing_probe`，身份块 `classification="diagnostic_only"`；
2. 每行阶段闭合（分析器四条断言全过）；
3. latch 行的阶段分解能明确给出主要阶段（entry→首 health / 循环 health / sleep elapsed /
   final_spin_other 之一占优），并给出 `sleep_max_overshoot_ns` 与 `loop_health_calls` 量级；
4. 报告明确写出"probe 自身开销计入测量"，故本场绝对迟到不可与正式场直接比较。

没测到（如实报告，不得推断）：
- 无 `rate_timing_probe` 行或身份块缺失 → 开关/入口没用上，本次**未测量**；
- 有行但阶段不闭合 → 分析器 fail-closed，本次**未测量**，不得手工分摊；
- 运行在形成任何 timed group 前终止（准入/启动失败）→ **未测量**；
- 只拿到 CPU timing 行、拿不到 probe 行 → 主要不确定性仍在，次要观测可报但要标注。

## 8. 停止与失败边界（硬边界）

- 门槛与形态**一律不变**：0.5×、1 ms 物理、4 tick 屏障、单锚、无追赶、累计 100 ms 上限、
  10 s/60 s 滑窗预算、900 s/180000 tick 上限；不得重锚、缩短轨迹或驻留、放宽门槛。
- latch 即停（`RateUnmet` 原样传播）；**本场 latch 或提前 latch 都不算回归**，因为 probe 有
  自身开销；不得据此改门槛或宣称性能回退。
- 准入/预检失败、任一子进程失败、证据写入失败 → 停止并如实上报，**本次不重试**；
  需要再跑就是新票据、新目录、新决策，不得在同一场次里换身份续跑。
- 身份不一致（清单 SHA 或 epoch 与 §2 不符）→ 本场只作废件保留，不进任何比较。
- 诊断产物只进分析目录；**不得**登记为 rate/PV/Full/production 通过。#83 已 CLOSED，本包
  **不重跑**。注意这是**操作边界**，不是工具替我们拦：带密封身份的 probe 行能通过
  `tools/audit_joint_rate.py` 的身份校验并被其 `schedule()` 静默忽略，`tools/audit_pv_trajectory.py`
  也不检查 `rate_timing_probe`；真正让本场无法当正式证据的是 `joint_profile.py:219-220`。
- 不发布厂商源码/二进制，不终止用户进程。

## 9. 明确不做、不声称

- 不改 `joint_rate.py`、物理、调度、门槛、profile 钉值；本模块只交付测量入口与离线核算。
- 不声称任何优化有效：本包不含源码收益主张，也没有 A/B 结论。
- 不把 bomvjsmg 的 75321700 ns 或本次诊断场结果外推到完整两段 PV 的通过/失败。
- 不做 OS 抢占/wake-to-run 归因（未开 sched tracepoint/BPF）。
- 不把 "probe 场跑完没 latch" 当作通过；那只是"本场未跨限"，不是验收。

## 10. 若测量显示必须修复：本模块的下一可执行交付

诊断结果出来后，只有出现下述**具体**测量形态才谈最小修复；否则继续补测量，不猜修复：

| 测量形态 | 可选的最小动作（需另立票据、单独测量） |
|---|---|
| latch 前最后几次 `loop_health_ns` 占优 | 缩减释放等待内的 health 调用次数（不改 health 内容语义） |
| `sleep_max_overshoot_ns` / `sleep_elapsed` 远超 `sleep_requested` | 缩短最后一次 sleep 的保守余量（不动 1 ms 保护区语义） |
| `final_spin_other_ns` 占优且与写记录同段 | 减少每组的记录写入/缓冲（不改倍率合同） |
| `outcome="rate_unmet"` 行的 `entry_to_initial_health_ns` 占优 | 把首次 health 移到 entry 之前（需重新论证合同） |
| end_group work-over 中 `diagnostic_step_cpu_timing` 指向某一段 | 仅针对该段做测量化候选 |

任何动作都必须是**先测后改**、单变量、同身份，并重新走原验收；本模块不再以"报告"形式停机，
但也不会在没有上述测量形态时提交源码改动。
