# ArduCopter 原生DDS位置与偏航能力验证

2026-09-05。**候选补丁通过，原版同条件负对照失败；不代表Prometheus产品适配完成。** 本机固定ArduCopter源码的 `GlobalPosition` 接入层原先只执行位置，忽略消息中的偏航。现有4文件补丁已从仓库资产重新应用、独立构建并完成真实SITL任务，没有覆盖旧固件。复用既有ROS2、Agent、模型与诊断程序，未增加运行依赖。

范围为已授权的本机隔离SITL，普通技术报告，无恶意软件/漏洞报告flavor。Prometheus仍是移植主体；ArduPilot补丁只解决下游命令语义缺口，不改变既定运行分工，不修改厂商安装或用户飞控进程。关联[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。

## 复现

在 `wksim` 的WSL Ubuntu22.04目录执行。前置为已安装Humble及 `/root/wksim-dds-VxM6Ni` 工具链；缺少该本地构建时按[原DDS报告](2026-09-05_native-dds-report.md)恢复，不自动下载其他版本。

```bash
bash tools/build-ap-dds-yaw.sh /root/wksim-dds-VxM6Ni
```

构建器验证干净的固定源码，新建 `/root/wksim-ap-dds-yaw-*` 并打印路径。以下命令使用本次已存在且验证过的候选目录；重建后应选择该次打印的目录。

```bash
python3 tools/validate_ap_dds_yaw_boundary.py /root/wksim-ap-dds-yaw-mVgItN
bash tools/run-dds-validation.sh arducopter /root/wksim-dds-VxM6Ni \
  --ap-dds-candidate /root/wksim-ap-dds-yaw-mVgItN --yaw-gate
bash tools/run-dds-validation.sh px4 /root/wksim-dds-VxM6Ni
```

原固件负对照命令如下，**预期在首个偏航目标超时并返回1**。这不是一次完成降落的任务；失败后仅终止本次创建的仿真进程，不影响其他飞控。

```bash
bash tools/run-dds-validation.sh arducopter /root/wksim-dds-VxM6Ni --yaw-gate
```

基础回归命令：

```bash
source /root/wksim-ros2-ByQNy1/install/setup.bash
python3 -m unittest discover -s validation -p 'test_*.py' -v
```

## 实现与验收

[补丁](../patches/arducopter/0001-dds-global-position-yaw.patch)针对 ArduPilot `1511f27194f1dcc3728270883047bdf022b3fd53`，增加43行、删除17行，改动4个文件。位置接口保持原签名；新增位置＋绝对NED偏航虚函数，非Copter实现默认拒绝。Copter沿用已解锁/Guided门控及目的地/围栏检查。

DDS接入层只接受完整位置与可选偏航：`map` 的ENU弧度按 `wrap_PI(pi/2-yaw)` 转换为NED。缺失位置轴、激活速度/加速度/偏航速率、FORCE、未知mask位、不支持坐标/高度frame及非有限/越界数值均拒绝；被忽略的偏航允许无有效值。旧客户端若曾依赖“激活字段被静默丢弃”，会被此候选更严格地拒绝，不宣称无条件向后兼容。

候选二进制SHA256：`a8da0d8f4a9fee65b55b474577bda07f2b5047a6f9ae5265e6f1802d847e934d`。补丁SHA256：`e588bdd6250d42d3ed8a45ade0c6e14eb6443c035aad1c9c46c5af2d1d649621`，与实际候选工作树diff哈希相等。旧二进制仍为 `cb90d1ea220d636e77c45b9833b9dc8b4dda43b13480cf8619ee0645754191fd`。

普通解锁、3m起飞、5仿真秒高度保持、NED `[3,2,-3]` 航点之后，依次发送ENU偏航 `0,-pi/2,pi/3`。在15墙钟秒内，DDS与MAVLink偏航误差须≤0.15rad，收敛转速≤0.15rad/s；然后保持至少2秒FC时间及2秒模型时间。位置误差≤0.5m，物理真值逐样本另验，不能用“已发送”替代动作完成。下表为最终候选结果：

| ENU目标rad | 物理保持秒/样本 | DDS最大偏航误差rad | MAVLink最大偏航误差rad | 真值最大偏航误差rad | 真值最大位置误差m |
| --- | --- | --- | --- | --- | --- |
| 0 | 2.02 / 102 | 0.1011 | 0.1347 | 0.0920 | 0.0450 |
| -1.5708 | 2.00 / 101 | 0.0905 | 0.0899 | 0.0862 | 0.0759 |
| 1.0472 | 2.00 / 101 | 0.1152 | 0.1150 | 0.1261 | 0.1505 |

随后完成LAND、落地解除解锁，地面Agent中断3墙钟秒，物理/飞控继续9仿真秒；0.635墙钟秒内恢复状态与服务并确认未重新解锁。原版负对照在目标0处超时，最终DDS偏航仍约0.9497rad；目标位置保持正常。正负对照的诊断与DDS发送脚本哈希完全相同。

## Evidence

### E-001 — 可复现构建与回归清单

- observed_at: 2026-09-05T08:36:46Z
- source_type: file
- source_ref / artifact_path: [manifest.json](../validation/ap-dds-yaw-checks-d6e1fdfd/manifest.json)
- content_hash: `bf0706f6115ae1ff9abca7af0d67914ed4d103c87d4dd14afe12a902cd5b5ce7`
- repro_command: 本报告构建、基础回归命令；编译日志位于候选目录 `build.log` / `configure.log`，哈希在清单中。
- raw_excerpt: `41 tests ... OK`；新目录完整构建成功，约1m50s。清单固定补丁、工具、测试和各结果文件哈希。
- linked_workitem: n/a
- supersedes: none

### E-002 — 候选真实飞行与三路反馈

- observed_at: 2026-09-05T08:33:46Z
- source_type: file
- source_ref / artifact_path: [候选结果](../validation/arducopter-dds-zsptkjlj/result.json)；同目录保留DDS、MAVLink与物理真值JSONL及飞控/Agent日志。
- content_hash: `a38086a930012801233abd0b863943f9550b5a4c87efd45fc5efd8b18a283b17`
- repro_command: 本报告带 `--ap-dds-candidate` 和 `--yaw-gate` 的命令。
- raw_excerpt: `status=pass, children_reaped=true`；三方向均通过，地面重连通过。
- linked_workitem: n/a
- supersedes: none

### E-003 — 原固件负对照

- observed_at: 2026-09-05T08:33:46Z
- source_type: file
- source_ref / artifact_path: [负对照结果](../validation/arducopter-dds-43cmiv5e/result.json)
- content_hash: `6bcde1309dc1ddbf49eff508e46d2853e611b0f85b0c70918a781b4d2e90467e`
- repro_command: 本报告不带候选参数、带 `--yaw-gate` 的命令。
- raw_excerpt: `status=failed`，`yaw ENU 0.000000 reached` 等待超时；`children_reaped=true`。
- linked_workitem: n/a
- supersedes: none

### E-004 — 编译后的输入与派发边界

- observed_at: 2026-09-05T08:33:45Z
- source_type: file
- source_ref / artifact_path: [原生接入层断言结果](../validation/ap-dds-yaw-boundary-bug6j6s0/result.json)
- content_hash: `0735e847fdfd6b347dfc7156be1dbcefd3120480019428503299d7999a57674d`
- repro_command: `python3 tools/validate_ap_dds_yaw_boundary.py /root/wksim-ap-dds-yaw-mVgItN`
- raw_excerpt: `status=pass, assertions=111`。使用真实生成消息头和从候选源码抽取的原方法，以UBSan/float-cast-overflow检查；位置对象、控制端点及角度辅助函数是测试替身，不是完整飞控或AP数学库测试。
- linked_workitem: n/a
- supersedes: none

### E-005 — PX4既有路径回归

- observed_at: 2026-09-05T08:26:54Z
- source_type: file
- source_ref / artifact_path: [PX4任务结果](../validation/px4-dds-4gfbryao/result.json)
- content_hash: `0731fe811ee8247ae6e29a6fcbf4adbac8b0991573c686f793961ad0805c2e72`
- repro_command: 本报告PX4命令，不带偏航扩展参数。
- raw_excerpt: `status=pass, children_reaped=true`；原生DDS起飞、航点、降落、地面重连通过。该测试不声称验证PX4三方向偏航扩展。
- linked_workitem: n/a
- supersedes: none

## Findings与调用路径

### F-001 — 原生消息能力不等于执行能力

- severity / category / status: n/a_re / design / validated
- evidence_ids: E-001, E-002, E-003, E-004
- location: 固定ArduPilot的 `AP_DDS_External_Control::handle_global_position_control`。
- impact: 仅发布既有 `GlobalPosition.yaw` 无法保留Prometheus位置＋偏航语义；候选补丁补齐这一路径。
- confidence: high；只针对固定源码、该候选和已测场景。
- repro_steps: 使用相同诊断分别运行候选和原固件，核对三路反馈与目标误差。
- remediation: 产品适配显式声明/检查固件能力；未覆盖模式拒绝，不能静默删字段或以MAVLink偷偷补发。

### F-002 — 最小复用方案已可重建，但边界有限

- severity / category / status: n/a_re / other / validated
- evidence_ids: E-001, E-002, E-004, E-005
- location: [构建器](../tools/build-ap-dds-yaw.sh)、[飞行诊断](../tools/validate_sitl_physics.py)、[DDS诊断](../tools/sitl_dds.py)。
- impact: 既有环境足以验证此能力缺口；默认固件、Prometheus上游和用户PID828均未修改。
- confidence: high；未涵盖真机、其他机型或所有控制模式。
- repro_steps: 新建候选、编译边界测试、运行候选飞行与PX4回归；检查日志和本次进程收尾。
- remediation: 下一步接入真实Prometheus ROS2节点与显式原生能力适配，不把诊断节点直接当产品。

### P-001

- path_type: callflow
- start: 诊断发布带激活偏航的原生全局位置目标。
- goal: 实际飞行姿态与位置在持续时间窗口内满足目标。
- steps:
  1. 生成固定schema、设置mask和ENU目标 — E-001/E-004，F-001。
  2. DDS接入校验并将位置＋NED偏航派发至Guided — E-001/E-004，F-001。
  3. 物理闭环运行，由DDS、MAVLink及模型真值独立核对完成 — E-002/E-003，F-001。
  4. LAND、地面断流恢复及本次进程收尾 — E-002/E-005，F-002。
- residual_risks: 未实现Prometheus产品任务链、全部原生控制能力、空中失联矩阵或联合场景共享时间；此次角度/位置门槛不是CopterSim动力学等价预算。

## 开发失败与未完成项

首轮[保留失败](../validation/arducopter-dds-mqmtexvr/result.json)：刚进入0.15rad范围时仍以约1.6rad/s转动，随后DDS偏航误差达0.1965rad。先增加转速收敛判据，未放宽角度/位置门槛；早期候选通过后，再拒绝未知mask位，并加强为至少2秒独立物理真值窗口。最终版本由仓库补丁重新构建，通过E-002。早期通过记录也保留在[开发结果](../validation/arducopter-dds-e5fvdx79/result.json)，不混作最终哈希/验收标准。

本次并发的正负对照是独立网络与独立时间线，不是联合场景。Agent断流仅在地面，UE与MATLAB未参与本次测试。MATLAB的TCP/JSON可选桥传输已确认，但功能范围的用户答复仍待处理，未关闭该HITL决策。候选固件未切换为默认，完整Prometheus适配、MATLAB桥、插件/场景反馈和Full功能覆盖继续推进。

Codebase Memory仍为07:54:03 UTC快照；新工具被设计性排除，新C++测试与patch尚未追踪，已记录[真实覆盖边界](codebase-memory.md)。本阶段直接读取本地/WSL已知源码，没有用旧图声称新补丁已被索引，也没有为了文档无条件重建全图。
