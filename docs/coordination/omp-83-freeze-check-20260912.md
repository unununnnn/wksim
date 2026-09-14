# OMP #83 冻结复核（2026-09-12，只读）

范围：Linux 实验区 `/root/wksim-release-acceptance-fe3` 的 AP mixed / Control c2IXOr /
message 三身份与完整 PV 入口要求的 SHA 吻合度；三个诊断开关的诊断专用性。
未启动、未重建、未改代码/阈值/Issue；未复用截断 release 证明完整 PV。

## 1. 三身份复核（今日 sha256sum 实读，全部一致）

| 角色 | 清单 | SHA256 | 状态 |
|---|---|---|---|
| AP mixed | `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json` | `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c` | ✅ 与入口要求一致 |
| Control | `/root/wksim-joint-control-c2IXOr/build.json` | `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e` | ✅ 与入口要求一致 |
| Message | `/root/wksim-ros2-Rzj3Pf/message-build.json` | `29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219` | ✅ 与入口要求一致 |

入口要求来源：`docs/plan/39-planner-run-contract.md:113-122`（当前完整 PV 执行入口
记录的实际参数）。runner 侧校验：`check_control(manifest, sha)`（run_joint_flight.py:468）
与 `joint_message_candidate.py:110-113` 按字节核对清单与给定 SHA——候选路径自洽。

**钉档分叉（须注意）**：固定 profile `joint_quad_dds_mixed_pv_v1`
（`Simulator/wksim_runtime/joint-profiles.json:50-70`）仍指向历史 Control `0DQQz9` 与
message `MUlZd0`。候选 flag 路径（--control-manifest/--message-manifest）覆盖它；
但 legacy/`model_promotion_flight` 路径（run_joint_flight.py:337-338、:465-467）读取
profile 钉值会解析出**旧身份**。诊断场只走候选 flag 路径；旧身份不得直接运行。

## 2. 三开关的诊断专用性（源码实证）

| 开关 | 实证 | 诊断专用依据 |
|---|---|---|
| `WKSIM_JOINT_CPU_TIMING=1` | joint.py:54 读取；样本为 `diagnostic_*` 行（:63/216/275），仅原始 trace | 验收候选入口硬拒（`validation/20-rate-candidate-profile/check-delivery.py:34` 期望 exit 1） |
| `WKSIM_JOINT_RATE_TIMING_PROBE=1` | joint_rate_probe.py:25 读取；身份 `classification="diagnostic_only"`（:35-36）；result 记 `rate_timing_probe`（run_joint_flight.py:377） | `tools/audit_joint_rate.py:32-36` 对 probe 记录 fail-closed；仅限 PV/MIXED（run_joint_flight.py:327-328） |
| `--async-model-evidence` | 仅限 PV/MIXED（:330-331）；改变 manager/model fork 调度（`reset_on_fork` :117）；落点 `result['async_model_evidence']`（writer sidecar 无损核验 :132-150） | 改变调度形态即非验收配置；产物是证据字段，非通过判据 |

三者同场均只产诊断证据；**该场永不得充当 #83 验收**。

## 3. 主会话"进入一个诊断"的准确前置与完整参数

前置（全部须主会话现场确认）：
1. 独占运行资源预约；入口自生成 run/live 目录，不复用旧目录。
2. 三清单路径存在且 SHA 运行前复核（本报告为今日实读快照）。
3. PX4 候选按当场组合显式给 `--px4-manifest/--px4-sha256`（profile 钉值为
   `/root/wksim-px4-state-ONa1Kw/wksim-build.json` `d7e905b3…`，joint-profiles.json:63-66；
   若沿用须复核）。
4. 运行环境与 39 合同一致：实验区 `/root/wksim-release-acceptance-fe3` 内执行。
5. 诊断产物只交分析（如 `validation/33-rate-profile/` 式），不交验收审计。

完整参数（候选身份已核验；.5×/100ms/1ms 为 runner 内建不变）：

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
  --px4-manifest <当场PX4清单> --px4-sha256 <当场SHA>
  # 可选：--async-model-evidence（同 PV/MIXED 门；改变 fork 调度，诊断专用）
```

## 4. 未证结论（标未证）

- 三清单在运行时刻的字节一致性（本报告为静态快照）。
- 候选运行期准入（`preflight`/admission :455-464）未实跑验证。
- profile 钉档仍指 0DQQz9/MUlZd0 是否需随 c2IXOr/Rzj3Pf 换钉：超出本切片，未裁定。
- `--async-model-evidence` 与双 timing env 同场的实测行为无既有证据。
- 诊断输出量级/对倍率门的影响未测量（诊断固有开销，33 文档已声明不计入收益）。
