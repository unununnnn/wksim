# #33 正式 mixed/P+V profile 的资源准入

2026-09-09。本文件记录有界准入实现及主代理的后续证据接入合同。代码接线与实飞提升是分开的结果：本子任务没有构建或启动 SITL，没有修改历史 flight/build 记录，没有写工单或提交。子代理实际模型/推理强度经主代理核实为 `gpt-6-astra/high` 后开始；无嵌套代理。

新增 `joint_quad_dds_mixed_pv_v1`，AP 固定为 `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json`，SHA256 `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`；control 于 2026-09-11 随当前 RC 构建输入刷新为 `/root/wksim-joint-control-0DQQz9/build.json`，SHA256 `25edbf816e1b417028be73f409b211b48a1579cce4d63b0d9c6c9b5277e6d610`。PX4、模型、消息和 Agent 来源沿用原固定资源，但必须由两份新能力证明绑定到同一真实资源。

当前新增行的 `evidence` 是空数组，故 `check_resources` 在平台检查、全源遍历或启动前返回 `ok=false`、`children_created=0`、`capabilities=[]`，原因是缺少最终 mixed/PV 能力飞行证明。本文不把候选构建的历史 `production_admitted=false` 或 `flown=false` 改写为 PASS。

## Profile 与公开身份合同

新行使用固定选择器 `manifest_kinds={ap:ap_mixed_v1,px4:wksim_build_v1,control:joint_control_v1}`、`control_source=current`、`evidence_schema=joint_mixed_pv_v1`。能力列表顺序为 `public_position`、`public_velocity_yaw`、`full_xyz_pv_yaw_v1`、`xy_velocity_z_position_yaw_v1`。调用者不能通过添加 `promotion_flight`、替换路径、删改能力或改为封存控制来源绕过：描述符必须与所选 catalog 行完全一致，且新 ID 的 source/schema/capability 合同固定。

成功结果新增顶层 `capabilities`，供正式 launcher 从已通过准入的能力推导参数；失败结果不授予任何能力。原有字段继续为 `configs`、`model_library`、`control_package`、`identities`、`scope`。

`identities.ap` 和 `.px4` 均为 `{path,sha256,commit,source_files}`。AP 额外保留 `identities.ap_mixed` 的完整只读 verifier 输出；`identities.manifests` 保留三个 manifest pins；`identities.model` 保留原模型 build record；`identities.message_packages` 与 `identities.arducopter_agent` / `.px4_agent` 保留实际包和可执行文件身份。没有将 mixed manifest 伪装成旧 `wksim-build.json`。

AP 通过现有 `ap_mixed_candidate.verify` 验证真正的 mixed schema、源清单、当前全部源文件/子模块、补丁、准备脚本、构建日志、可执行产物和 mixed→PV→固定 clock AP 的封存链。正式模块仅在资源核验时延迟导入只读 verifier；模块初始化不运行 admit，亦不启动进程。

## 两份能力证明的接入格式

`evidence` 必须恰好包含两行，分别对应 `full_xyz_pv_yaw_v1` 与 `xy_velocity_z_position_yaw_v1`。每行字段仅为 `task_profile`、`result`、`audit`、`admission`；后三项均为 `{path,sha256}`。`result` 指实际候选运行的 `result.json`；`audit` 指对应原始 PV/mixed 审计结果；`admission` 指同一运行目录的 `experimental-admission.json`。所有摘要由真实封存文件计算，不能填测试数据或把旧 PV 记录改为 mixed 固件。

每行需同时满足：

- 运行完成、源码未变化、控制正常关闭、cleanup 无错误；审计 PASS、无 outstanding checks，task/run/scene/result 摘要一致。
- `mixed_admission` 与独立 admission 文件完全一致，仍保留其实验范围和构建时未提升状态；任务能力描述使用其真实 PV 或 mixed schema。
- result 与 admission 的 AP/control 两钉及完整 candidate/control records 匹配新行；PX4 三钉中的第三钉来自 admission 的实际 baseline，且当前完整 PX4 核验结果相等。
- retained AP/control manifest、mixed 源清单、PV baseline、全部 retained execution source 和 admission/execution source 映射都被 audit 摘要覆盖；raw evidence 文件不得逃出运行目录。
- 当前 AP verifier 与两份证明的完整 candidate/binary/source counts/source-manifest/baseline-verification 相同；两份证明的 PX4、模型、消息包和双 Agent 相同。随后仍核验当前模型库/归档/包装代码、消息内容、Python/ament/linker overlay 和 Agent 可执行字节。
- 两场实际 AP control argv 均恰好带 `-p arducopter_pv_profile:=full_xyz_pv_yaw_v1` 和 `-p arducopter_mixed_profile:=xy_velocity_z_position_yaw_v1`；审计 `identity.control_profiles` 也必须确认两项。旧 mixed 单参数 PASS 不满足新行的双参数证明。

正式任务的执行、scene/observer/ready-go 接线、错误拒绝和真实使用流程由主代理的运行集成负责；资源准入本身不声称已完成正式实飞或全部原生异常边界。

## 旧行与离线检查

`joint_quad_dds_v1` 的 AP/control/PX4 pins、证据与 setup 路径原样保留，只增加 `control_source=sealed_legacy` 及原有两种公共任务能力声明。旧 control 核验仍检查 manifest/root/package、历史 staged/installed 全 Python 文件集、历史 staged build inputs、build log 与构建脚本；今日仓库的 Python 和构建输入属于新候选的独立 `check_control` 分支。`ap_pv_candidate._sealed_control()` 复用同一 `_control(..., sealed=True)` 实现，避免两套规则漂移。新行仍要求 current/staged/installed 三方一致；旧 installed 或 staged 字节改变仍拒绝。

本次只阅读指定源码与直接引用，无未知结构导航，未运行多余 CBM 刷新。目标文件原索引状态由主代理确认；不把索引就绪当作新逻辑已被索引的证据。

已在 WSL 运行 `python3 -B -m unittest validation.test_joint_profile validation.test_mixed_profile_admission`：13 项通过。新增离线检查覆盖缺证明/越权描述符、错误 manifest-kind/control-source/capabilities、封存旧安装与当前源分离、错误 AP/PX4/Agent/source chain/pin、缺少 capability 参数、摘要篡改与原始路径逃逸。测试中的最小合成 packet 仅隔离检查交叉绑定，不进入 catalog，也不是飞行证明。Windows 原有 symlink 测试受创建符号链接权限限制，故最终在 WSL 原生 Linux 路径复核通过。

## 当前检查点（2026-09-13，#84 前置/映射包）

主会话后续实测：同组合mixed场oxv29042在tick131760以100034744ns累计迟到失败，仍缺整场mixed证明，catalog不提升。后续profile/catalog与joint_profile.py的唯一写入者为主会话。直接核验又发现旧7模块列表不能接纳已封存15模块+2资产的c2；current Control分支现复用完整构建校验器，sealed历史分支逐项核验声明资产，真实两路径及Linux21项定向测试通过。下文“joint_profile.py无需改”是早期缺证据检查的有限结论，已由此实证更正；显式message清单与正式资源overlay的证明接线仍待完整适配。33-final-combo-rate-candidate.md的旧命令已在f6239b7之前标为历史。

**状态**：正式行 `joint_quad_dds_mixed_pv_v1` 仍 `evidence=[]`；纯只读
`check_resources` 复核（无进程、提前返回）确认 `ok=false`，原因
"Missing final mixed/PV capability flight proofs"。行内 workspace 钉仍为历史
0DQQz9/MUlZd0，与已验收三元组（AP mixed fhuf05l9 `1e6250ef…`、Control c2IXOr
`6fe8c0b3…`、message Rzj3Pf `29969da0…`）分叉，待换钉。

**PV 证明行候选**（已落地、逐字核验）：`joint-public-flight-1w6dru32`
（result `10044bf1…`、v2 raw 审计 `8140d80e…`、admission `6178bdbb…`），
status pass / flight_completed / 无 cleanup 错误 / 无 rate_timing_probe /
审计 result_sha 逐字指同场 / outstanding 空。**一行 PV 证明不冒充两份能力。**

**mixed 证明行缺失**：实验工作区全部 `joint-public-flight-*/result.json` 按
task_profile 有界索引（2026-09-13）无 `xy_velocity_z_position_yaw_v1` 运行；
catalog/docs 引用仅历史 mixed `zk5_nukn`（不同组合，被 final-combo 合同排除）。
不据此称全机没有。

**下一场 mixed 命令（无探针，正式证据拒绝 rate_timing_probe 场）**：

```bash
cd /root/wksim-release-acceptance-fe3 && bash tools/run-joint-flight.sh \
  --task-profile xy_velocity_z_position_yaw_v1 \
  --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
  --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
  --control-manifest /root/wksim-joint-control-c2IXOr/build.json \
  --control-sha256 6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e \
  --message-manifest /root/wksim-ros2-Rzj3Pf/message-build.json \
  --message-sha256 29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219
```

**最低必需原始门**：运行完成/源码未变/控制正常关闭/无 cleanup 错误；mixed 原始
审计 pass 且 outstanding 空、result_sha 指同场；admission 保持
ok/experimental/未提升/未飞/children=0/reasons 空；能力描述恰为 mixed schema；
清单钉匹配三元组且留存构建哈希相等；AP control argv 恰好双参数
（pv_profile+mixed_profile）且审计 identity.control_profiles 确认两项。

**待更新文件与唯一写入者交接**：`joint-profiles.json`（换钉+两行证据，归
profile/catalog 所有者，#84 复核）；`33-final-combo-rate-candidate.md`（旧
0DQQz9/OEvS3W 当前命令须降格为历史，归文档所有者）；`joint_profile.py` 与
`audit_mixed_control.py` 本轮未发现需改。正式 launcher 公开入口由主会话消费。

旧默认行与 legacy 证据未动；本节不宣称提升完成。机器可读记录：
`validation/33-formal-promotion/20260913-readiness/readiness.json`。
