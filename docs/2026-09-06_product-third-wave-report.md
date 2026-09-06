# 第三批：多航点任务与取消

2026-09-06 JST（验收记录为2026-09-05 UTC），#15“单机多航点任务与取消闭环”完成主代理源码复核、10次真实产品/场景运行以及185项无跳过回归。[机器审计](../validation/product-third-wave-20260906/audit.json)、[证据清单](../validation/product-third-wave-20260906/manifest.json)及[进程检查](../validation/product-third-wave-20260906/cleanup.json)保留完整身份与哈希。它是一个已验收切片，不是完整项目交付。

#15已于2026-09-05 15:14:40 UTC按completed关闭并读回，[远端验收记录](https://github.com/unununnnn/wksim/issues/15#issuecomment-5552742286)。原父图#1及规格#10更新时间不变。

## 交付

同一严格任务配置分别选择PX4、ArduCopter，完成ENU位置、转向、BODY FLU相对移动、逐点连续驻留及降落。公共请求和命令身份递增；受理、接管、运行、完成、失败、取消分别报告。本地取消CLI明确指定run_id/mission_id，不必进入隔离DDS网络。任务被取消后不派发后续航点；所选降落处置需要实际反馈和独立物理真值，不能将“已取消”当成“已停住”。详见[操作与契约](wksim-missions.md)。

按 codebase-design 的模块原则，任务状态、取消与驻留编排集中在 MissionTask，复用已有 Task 的公共请求/反馈接口；纯配置和取消文件通道可独立测试。没有添加新的飞控消息类型、修改已验证控制安装包或更换物理模型。

来源是固定Prometheus基线 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce` 的基本ENU/BODY与waypoint任务流程。仍保留ROS1源码，未提交/推送混合工作区。运行继续复用 `wksim-dds-VxM6Ni`、`wksim-ros2-2egljG`、`wksim-ap-dds-yaw-state-4Wr27s`、PX4 `d6f12ad1` 及现有自主模型库；每次运行的源码、原生固件、Agent、模型哈希都在各自result中。

## 实际结果

| 场景 | PX4证据目录 | ArduCopter证据目录 | 预期与实际 |
|---|---|---|---|
| 正式三航点 | `mission-third-flight-20260905/example-px4-mission-001` | `mission-third-flight-20260905/example-arducopter-mission-001` | 各3次MOVE，全部驻留，LAND及真实落地，pass |
| 第二点受理后取消 | `product-mission-cancel-m5fsgzq_` | `product-mission-cancel-05w2mjvt` | 各2次MOVE，第三点未发；第一点完成，取消并落地，cancelled |
| 解锁前地面取消 | `product-mission-cancel_ground-bo564kf8` | `product-mission-cancel_ground-m7tbil07` | 0次公共控制请求、没有解锁，cancelled |
| 外部模式切换 | `product-mission-external_mode-1g7sj4_j` | `product-mission-external_mode-ybb7hiy7` | 操作者通过公共Setup请求hold；实际模式完成，任务failed、仅2点、未抢回 |
| 解算后BODY越界 | `product-mission-invalid_body-8w9svt1d` | `product-mission-invalid_body-13fkbis4` | 前2点完成，第三点解算越界而未发送，任务failed |

以上路径均位于`validation/`。正常运行直接使用正式 `run-wksim.sh`，没有任务替身。负向场景使用同一runtime与真实MissionTask的明确输入测试接缝：取消调用真实CLI；模式切换由标记为simulated_operator的公共SetupRequest发起。观察器没有原生控制发布者。外部接管失败后仅作最多3s只读观察，记录实际模式完成；不清除失败、不恢复任务。

失败场景的测试通过不等于任务飞行成功：外部接管及无效目标结果明确为 `failed`、`safe_landing=false`、`unsuccessful_isolated_teardown`，没有伪报安全降落。

三点物理窗口最大位置误差分别为PX4 **0.44664m**、ArduCopter **0.23881m**；最大速度 **0.41742 / 0.28451m/s**，最大偏航误差 **0.12771 / 0.10136rad**。门槛始终为0.5m、0.5m/s、0.15rad。反馈驻留各满2个原始boot秒；物理窗口保留独立游标和时长，范围为1.94–2.04s，不将其修饰为与飞控钟完全相等。它们是控制集成验收，不是正式动力学等价预算。

## 可复现命令

从wksim目录在Ubuntu-22.04执行：

```bash
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/px4-mission.json --output-root validation/NEW_OUTPUT
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/arducopter-mission.json --output-root validation/NEW_OUTPUT
bash tools/run-mission-validation.sh px4 cancel
bash tools/run-mission-validation.sh arducopter cancel
bash tools/run-mission-validation.sh px4 external_mode
bash tools/run-mission-validation.sh arducopter external_mode
bash tools/run-mission-validation.sh px4 invalid_body
bash tools/run-mission-validation.sh arducopter invalid_body
bash tools/run-mission-validation.sh px4 cancel_ground
bash tools/run-mission-validation.sh arducopter cancel_ground
bash tools/check-session-product.sh
```

每个实验用未占用的run_id/输出路径；场景工具自动生成新身份。只读审计 `audit_mission_product.py` 要求两个`--normal RESULT`和八个`--case ACCEPTANCE`，输出必须新建。`check_mission_cleanup.py`读取审计中列明的进程组，不进行任何进程终止。

回归日志在 `validation/session-product-checks-oq6Hthkv/`：session-tests.log为177项/12.779s，legacy-preflight-tests.log为8项/0.361s，均无skip。新增55项包括严格配置、取消文件原子性及Linux链接/FIFO边界、真实numpy.float32序列化、完整连续驻留计时、外部接管、取消ACK等待和独立物理审核。Windows先测时的4项平台skip不被混算成通过；它们已在Linux最终矩阵实际执行。

归档能力/工单状态后，再次运行177+8项检查无skip，日志为 `session-product-checks-btaX6d0C`（13.085s/0.322s），重新审计10个运行所得哈希相同。审计SHA256：`3cd5a524a0dcbaa2c93b62241add639ec955ddd0a161bf1ac78e335885a8e9ce`。48个自建进程组（10个最终运行及第二轮2个失败运行）均无残留；用户原有ArduCopter PID828、start_ticks19268及命令行未变。

## 失败样本与限制

首次两栈运行遇到numpy.float32位置快照无法JSON序列化，连最终result写入也失败；原始任务、公共消息、控制和物理日志保留在 `mission-first-flight-20260905`，不补造result。已把位置快照显式转成内建float，并在写入进度前校验JSON；真实类型回归和后续完整result验证均通过。首轮清理后另以只读进程查询核对无对应产品进程，原PID828仍在。

第二轮两栈在90°转向后短暂进入容差、随后超调而失败，保留 `mission-second-flight-20260905` 的完整result。修正为完整连续驻留窗口，越界从头计时并保留reset事件；没有放宽门槛、调低目标或改造飞控参数。

两名实际执行子代理均核验gpt-6-astra/low：Avicenna有4个turn_context（含初始与继续），Kepler有1个，全部关闭。第三个同配置代理请求遇到容量不足，该工作由主代理完成，没有替换模型。主代理负责任务执行、独立物理审计、真实运行和集成门。

本批没有重新启动UE；第二批UE5.5证据只对应当时源码/运行，不冒充本批视觉回归。日志磁盘写满/崩溃持久化、空中DDS失联、共享时钟、控制重启续飞、RC/实机、全球任务、动态规划、MATLAB和正式数值预算仍未由本票验收。

Codebase Memory已刷新至15:04:04 UTC、61,826 nodes / 167,560 edges，新任务入口、驻留、取消、物理审计四个精确查询完整返回。节点数量不等于迁移完成率；覆盖限制见[代码记忆说明](codebase-memory.md)。

下一执行前沿为[#18 wksim界面配置到任务结果的完整流程](https://github.com/unununnnn/wksim/issues/18)。原父图#1和规格#10保持开放不改写，未决HITL门槛及Full扩展义务不删除，Goal保持active。
