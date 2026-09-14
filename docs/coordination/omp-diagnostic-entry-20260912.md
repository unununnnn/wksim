# OMP 诊断入口核验（2026-09-12，只读）

范围：Windows 主工作区 `codex/independent-rgb-integration` 与 Linux 实验区
`/root/wksim-release-acceptance-fe3` 的 `tools/run_joint_flight.py`、
`Simulator/wksim_runtime/joint_rate_probe.py`、
`docs/plan/33-final-combo-rate-candidate.md`。未改审计/源码/已有文档，未运行
native/ROS。

## 1. 真实存在的 timing 诊断环境变量（字面值已核）

| 变量 | 读取点 | 取值门 | 生效内容 | 落点 |
|---|---|---|---|---|
| `WKSIM_JOINT_CPU_TIMING`（Claude19a 推荐名，**正确**） | `Simulator/wksim_core/joint.py:54`（`os.environ.get(...)=='1'`，两工作区 joint.py SHA256 同为 `f5433c2e…`） | 仅 `'1'` 开启，其余即关 | GC 回调样本 `diagnostic_gc_timing`（:63）、step 分段 `diagnostic_step_cpu_timing`（:216）、native 输入等待 `diagnostic_native_input_timing`（:275）；关闭时零时钟读取（:227-229 注释实证） | **仅原始 trace/truth 行**（`self.record` 注入回调，joint.py:36）；**不进 result.json** |
| `WKSIM_JOINT_RATE_TIMING_PROBE` | `Simulator/wksim_runtime/joint_rate_probe.py:25`；runner 门 `tools/run_joint_flight.py:326` | 仅允许 unset/0/1，其他值 raise（:30） | `make_joint_rate(..., diagnostic=True)` 换 `JointRateTimingProbe`（run_joint_flight.py:52-53,757）；**仅限 PV/MIXED task profile**（:327-328 硬门） | **进 result.json**：`result['rate_timing_probe']` 诊断身份（:377）；原始 rate.jsonl 出 `rate_timing_probe` 行（probe 记录，`add_timing_probe_identity` :754 并入字段） |

关键互斥（验收 vs 诊断）：验收候选入口拒绝 `WKSIM_JOINT_CPU_TIMING`
（`validation/20-rate-candidate-profile/check-delivery.py:34` 期望 exit 1）；
`tools/audit_joint_rate.py:32-36` 对 `rate_timing_probe` 记录 fail-closed。
**诊断场永不得充当验收场。**

## 2. CLI flags 与证据落点（run_joint_flight.py，主工作区行号）

- 候选身份：`--control-manifest/--control-sha256`（:1067-68）、
  `--ap-manifest/--ap-sha256/--ap-pv-manifest/--ap-pv-sha256/--ap-mixed-manifest/--ap-mixed-sha256`（:1069）、
  `--message-manifest/--message-sha256`（:1071-72，**可选**：`candidate_environment(control, messages=None)` :64-66 容许无消息候选）、
  `--px4-manifest/--px4-sha256`（:1074-75）、`--task-profile {position, full_xyz_pv_yaw_v1, mixed}`（:1073；PV/MIXED 常量 :46-47）。
- `--async-model-evidence`（:1065）：仅限 PV/MIXED（:330-331 硬门）；model worker argv 追加
  `--async-evidence`（:787-789）；manager/model reset_on_fork（:117）；落点：
  `result['async_model_evidence_requested']`（:375）+ 收尾 `result['async_model_evidence']`
  = 两侧 `*-truth.jsonl.writer.json` sidecar 无损核验（:132-150，校验 sidecar 摘要而非行类型）。
- 其他诊断 flags（--pause-probe/--scene-lifecycle/--native-state-trace 等）为 alternate
  workflow；`tools/audit_pv_trajectory.py:298` 对 `diagnostic_land_step_period_s` 等
  `require(not result.get(key))` —— 诊断场不得交 PV 审计。

## 3. 工作区差异（实测哈希）

- `joint_rate_probe.py`、33 候选文档：两区**逐字节一致**（`a8bac9ac…`、`9516a2cd…`）。
- `run_joint_flight.py`：实验区多 `--planner-release-proof` 与 planner transport 模块必需集，
  sources 少 `model_parameters.py`（69 差异行）；**诊断语义两区一致**。

## 4. 可审核诊断命令模板（原 .5×/100ms/1ms 不变——runner 内建，无对应参数）

当前允许考虑的候选身份（全部逐字核验：sha256sum 实读一致；来源
`docs/plan/39-planner-run-contract.md:113-122`）：
- AP mixed：`/root/wksim-ap-mixed-fhuf05l9/mixed-build.json`
  `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`
- Control：`/root/wksim-joint-control-c2IXOr/build.json`
  `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e`（实读复核一致）
- Message：`/root/wksim-ros2-Rzj3Pf/message-build.json`
  `29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219`（实读复核一致）

**`0DQQz9`/`OEvS3W` 仅历史身份；本模板不得暗示可直接运行旧身份。**

```bash
# Linux，预约独占运行资源后；诊断场，绝不作验收（#83 不因此通过）。
WKSIM_JOINT_CPU_TIMING=1 \
WKSIM_JOINT_RATE_TIMING_PROBE=1 \
bash tools/run-joint-flight.sh \
  --task-profile full_xyz_pv_yaw_v1 \
  --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
  --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
  --control-manifest /root/wksim-joint-control-c2IXOr/build.json \
  --control-sha256 6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e \
  --message-manifest /root/wksim-ros2-Rzj3Pf/message-build.json \
  --message-sha256 29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219
  # 可选同场异步模型证据（见 §5 兼容要求）：
  # --async-model-evidence
```

PX4 候选（--px4-manifest/--px4-sha256）按当场实际组合显式给出；本报告不代填。

## 5. `--async-model-evidence` 与诊断的兼容要求

1. 两者共享同一硬门：仅 `--task-profile` 为 PV/MIXED 合法（:327-331）。
2. 可同场：async 证据核验 writer sidecar 完整性（complete/closed/无损字节），
   CPU timing 的额外 trace 行不改变 writer 调度身份核验；但 probe/timing 行使该场
   **永久只是诊断证据**——不得交 `audit_joint_rate.py`/`audit_pv_trajectory.py` 验收。
3. reset_on_fork（manager/model）与诊断采样同开时的交互**未经实跑验证**（本核验只读）。

## 6. 未核实条件（如实）

- 两 env 同开的原始行量级与 trace 体积未实跑评估。
- `--async-model-evidence` + 双 env 的组合无既有运行证据；上面结论来自源码读取。
- 实验区 runner 的 `--planner-release-proof` 与本诊断的交互未核（不同切片）。
- 当前有效消息候选清单路径/哈希本报告未定位，需主会话按实场给值。

## 7. S2 静态 parser 核对（2026-09-12，仅对本模板命令）

模板全部 CLI 参数在两工作区 parser 均存在（主工作区 `run_joint_flight.py` /
实验区同名文件，行号分别列出）：

| 参数 | 主工作区 | 实验区 |
|---|---|---|
| `--task-profile`（choices 含 `full_xyz_pv_yaw_v1`） | :1073 | :1135 |
| `--ap-mixed-manifest` / `--ap-mixed-sha256` | :1069（`'--'+name` 循环） | :1131（同构） |
| `--control-manifest` / `--control-sha256` | :1067（同构） | :1129（同构） |
| `--message-manifest` / `--message-sha256` | :1071-1072 | :1133-1134 |
| `--async-model-evidence`（PV/MIXED 硬门） | :1065、:331 | :1127、:361 |

入口 `tools/run-joint-flight.sh` 两侧均在。两环境变量字面值核验见 §1
（`WKSIM_JOINT_CPU_TIMING` → joint.py:54；`WKSIM_JOINT_RATE_TIMING_PROBE` →
joint_rate_probe.py:25 + run_joint_flight.py:326）。

**尚需主会话确认的环境/候选前置**（本核验只读，未触）：
1. 三份清单路径当前仍在且内容未变（本次 sha256sum 实读一致，但运行前必须复核）。
2. PX4 候选组合（--px4-manifest/--px4-sha256）需按当场给出。
3. 独占运行资源预约与 run/live 目录由入口自生成。
4. 实验区 `--planner-release-proof` 与本诊断组合的关系由主会话裁定（模板未含该 flag）。
5. 诊断场结果只交 `validation/33-rate-profile/` 式分析，不交 #83 验收审计。
