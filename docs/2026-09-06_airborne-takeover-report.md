# 空中显式接管的前置安全修复

2026-09-06 JST。双栈真实节点验证通过：让出位置输出后物理继续推进，旧请求不能恢复输出，新的显式接管保持当前位姿而非回到起飞点。此轮完成的是 #42 的节点前置修复，**不是 MissionTask 暂停/恢复或实际地面站交接的完整交付**。#42、#18 和 Full Goal 仍开放。

Prometheus P450 真实机体/旋翼资产及 UE5.5 配置保持不变，仍在 `Simulator/ue55/Content/Wksim/P450/`；本轮未启动 UE、地面站或浏览器。资产来源和真实原生画面见 [P450 报告](2026-09-06_p450-view-report.md)。

## 修复与明确语义

- 原节点空中 `COMMAND_CONTROL` 接管也使用 home 上方3米、yaw=0；修复为在新请求受理时一次捕获当前本地 ENU 位置和四元数航向，同一个参考贯穿 PX4 预热与双栈激活后的保持。
- 地面接管仍走原来的正常起飞/航向对齐流程。相同模式的重复 setup 不重新捕获；新公开命令才覆盖保持目标；旧 MOVE、旧 request_id、错误 epoch 不产生恢复。
- `CommandProcessor.enter_control(mode, initial_hover=...)` 是现有 module 的一个可选 interface 输入，不增加一套任务控制器。使用 codebase-design 的 interface 测试原则：真实生成消息穿过 `on_request`/`tick`，由记录型 native adapter 验证输出；此类测试不是实际飞行证明。
- 新增明确的 AP-only `px4_mode='BRAKE'`，原生模式17。需要已解锁、确认飞行中和有效状态；PX4或无效状态拒绝。原生 service ACK 和实际状态观察到 BRAKE 仍分开报告。**没有把 AUTO.LOITER 偷换成 BRAKE**，也没有自动选择掉线/返航/降落策略。

公开包络/原生转换/位置与偏航门槛不变。新增 `takeover_reference` 事件记录捕获参考、原生代次和源 boot 时间；不是伪造的动作完成反馈。

## ArduCopter 真实失败与原因

初次空中场景 `airborne-takeover-_bz_8fk1` 失败，原始文件保留。在请求 AUTO.LOITER（原生 LOITER=5）后，58.76→65.00秒物理时间内，机体由约2.02米下降到地面；之后新的接管被正确识别为地面起飞，不能算空中恢复。原验证器只检验“仍解锁/LOITER/无输出/时间推进”的一项局部检查曾标 pass；独立真值审计揭示这不证明仍在空中，现已加上物理高度检查，不改写旧报告。

按 diagnosing-bugs 保留最小、可重复的只读红色反馈环：

```powershell
& 'D:/date/miniconda/python.exe' -B tools/audit_airborne_takeover.py validation/airborne-takeover-_bz_8fk1/runs/takeover-arducopter-6983075f29/result.json --release-only
```

实际返回1：`Released aircraft landed/descended below 2m`；313条真值，最低-0.012733米。此复查读取旧实飞记录，不修改记录也不发送飞行命令。

排查区分 LOITER 驾驶输入、飞行状态误报和物理输出中断三种原因。独立真值与公开高度共同排除“只误报落地”。原生 BIN 日志在该窗口内62条 RCIN 的 C3 全为1000；原来的默认 SITL 输入未被新建、覆盖或伪造。固定 ArduCopter `1511f27194f1dcc3728270883047bdf022b3fd53` 的 `ModeLoiter::run` 使用驾驶爬升率；`get_pilot_desired_climb_rate_ms` 对低于中位死区的有效油门产生下降率。`ModeBrake::run` 设零爬升率，初始化不设自动退出超时。相同模型/固件/参数改为显式 BRAKE 后真实保持成功。

官方 [LOITER 文档](https://ardupilot.org/copter/docs/loiter-mode.html)同样说明油门控制高度；[BRAKE 文档](https://ardupilot.org/copter/docs/brake-mode.html)说明该模式不接受驾驶输入，驾驶者需显式切出模式。因此 BRAKE 只是这里无驾驶输入的原生保持选择，不能称为已完成 RC 或 QGC 操作权交接。没有关闭健康检查或设置遥控中位来掩盖差异。

## 构建、版本与所有尝试

两次使用 `tools/build-prometheus-ros2.sh` 创建全新安装工作区，不覆盖历史安装：

| 构建 | 工作区 | 用途 |
| --- | --- | --- |
| `prometheus-ros2-SiMdzIxm` | `/root/wksim-ros2-LxCffT` | 初始当前位置接管修复；发现 AP LOITER 问题 |
| `prometheus-ros2-WHapQlFu` | `/root/wksim-ros2-MUlZd0` | 最终明确 BRAKE 支持；正式 session 配置现固定此安装 |

每次均47接口、52消息类型、104序列化往返通过。最终 colcon 三包构建40.5秒。两栈各完成原有六公开输入基线后才更新配置与能力索引；legacy_v1 历史基线完全不改。变更前及初始候选的能力索引分别保存在 `validation/airborne-takeover-integration-20260906/capability-index-before.json` 和 `capability-index-initial-candidate.json`。

最终六输入基线：PX4 `px4-dds-hxgna8aa`（结果 SHA256 `e106cb9b266baf290f23b517cb63404269f07a6bda1968eba1a35dd43ac7189a`）；AP `arducopter-dds-xuvva567`（`c3e0098eba16ff2e77cb50f55e3bfac81255c03d6a48d92662d72ed36e267899`）。这些基线的 ground DDS 重连不等于空中 DDS 失联验收。

最终完整安装快照 SHA256：prometheus_msgs `fc5f25cd3bd19b3dae4c1c58ea303cd85c484dbf6e9c065ec082058ff987b806`，wksim_msgs `fa5fadcb39d83bd1d2412b3b1d58955423a698236f19d9cf208956c120fdabe3`，prometheus_control `e4c44ad9a1797f043669bbae9bc2e9b82d5f109979e1300d1f29e7cc98368da8`。当前能力索引 SHA256 `31e004cfabeda0b1020c430061022b80dc671bda2ced3c60a00d36dfc0bb282e`。预检继续检查两栈证据、消息/源码/安装文件及 overlay，未跳过准入。

8次真实尝试：

| 尝试目录 | 结果 |
| --- | --- |
| `px4-dds-f3iw239c` / `arducopter-dds-y_u4_i23` | 初始候选六输入基线均通过 |
| `airborne-takeover-kgv_f2hf` | 初始 PX4 空中场景通过 |
| `airborne-takeover-_bz_8fk1` | AP LOITER 下降/落地，空中场景失败；原样保留 |
| `px4-dds-hxgna8aa` / `arducopter-dds-xuvva567` | 最终候选六输入基线均通过 |
| `airborne-takeover-ya_15jdl` / `airborne-takeover-mhao0sx_` | 最终双栈空中场景均通过 |

另有两次初始 Windows→bash 参数传递错误，在启动测试/飞控之前返回1；随后使用保存的私有 namespace 启动脚本，未改全局 shell 或网络。所有8次实飞均在私有 net/ipc/mount 与独立 `/dev/shm` 内。

## 最终真实结果与独立审计

使用正式 runtime 的公开 Task 输入 seam，标签为模拟操作员；没有在观察器中发送原生飞行命令。实际顺序为正常解锁起飞、[2,3,3]米/-0.9弧度、释放、旧 setup/MOVE/epoch 拒绝、新接管、另一新航点、正常降落。它**没有运行 MissionTask 的暂停/恢复分支**。

| 独立物理指标 | PX4 | ArduCopter |
| --- | --- | --- |
| run_id | `takeover-px4-41c0753f35` | `takeover-arducopter-b9d0192303` |
| 释放时原生模式 | AUTO.LOITER | BRAKE |
| 释放物理窗口 | 26.54→32.72秒 | 58.86→65.12秒 |
| 窗口最小高度 | 2.962184米 | 2.974944米 |
| 窗口新位置输出 | 0 | 0 |
| 接管最大位置误差 | 0.078803米 | 0.084674米 |
| 接管最大航向误差 | 0.003211弧度 | 0.009307弧度 |
| 捕获参考的原生样本 | 53 | 21 |
| 最终物理高度 | -0.000000797米 | -0.000023839米 |

误差门槛仍为位置0.5米、航向0.15弧度；释放保持沿用3米目标±0.6米，额外要求一直在2米以上。PX4 原生 NED/yaw 转换和 AP E7 经度纬度截断分别检查，不混为动力学等价验收。独立原始真值审计同时核对当前 runtime 与安装源代码 SHA256。

审计：`validation/airborne-takeover-integration-20260906/audit-px4.json`（SHA256 `96ae253dbb7a03f74b3ed7021627972c0a04facbe50345081f1d9d7408e3f268`）、`audit-arducopter.json`（`86cb345c464a0aab9590b8930dd30d993e616aaf8c843ddbef065b28086dec42`）。`cleanup.json` 检查8次尝试的36个 Linux 进程组，无残留；原 PID828/start_ticks19268/命令行不变。用户 UE PID35256 创建时间 `2026-09-06T02:20:00.42221+09:00` 不变，未操作该编辑器。

复现会启动真实隔离 SITL，非真机/HIL：

```bash
bash tools/run-takeover-validation.sh px4 /root/wksim-ros2-MUlZd0
bash tools/run-takeover-validation.sh arducopter /root/wksim-ros2-MUlZd0
```

末尾添加 `baseline` 则复跑原六输入基线。新运行创建新证据目录；审计命令对新结果执行 `python3 -B tools/audit_airborne_takeover.py <实际result.json>`。

## 回归、记忆与下一接缝

最终 WSL **204+10** 和 Windows **88** 项通过，无跳过，共302项；日志为 `validation/session-product-checks-LPXo5hFy/`、`validation/airborne-takeover-integration-20260906/windows-console.log`。最初201项矩阵有1项失败：篡改注入还指向旧基线证据，现改为从活动索引选择目标后仍验证篡改必须拒绝；未删除或削弱该检查，红色日志保留在 `session-product-checks-n6ibd0c6`。

一个子代理独占新增测试文件；首次因自己未看到配置暂停，主代理核对实际 session 的三次 turn_context 均 `gpt-6-astra/low` 后继续，最终已关闭。主代理复核代码并运行上述完整矩阵和真实测试；未嵌套或换用模型。

Codebase Memory 在新结构审查前刷新成功：2026-09-05 19:44:17 UTC，86,159节点/194,794边；artifact19:44:29。原生刷新日志和精确入口核对见 [记忆说明](codebase-memory.md)。图只导航，构建与真值不由节点数量推导。

下一项仍是任务/仿真生命周期：目前 `MissionTask` 检测控制权丢失仍报错并由 runtime 清理隔离运行；尚未提供让出后保持运行、带新操作身份的显式恢复与航点处置 interface。本轮没有掩盖该缺口。QGC 安全隔离启动、实际界面、空中 DDS 失联策略及其他 HITL 门槛保持未完成；不得用此公开输入场景将 #42 关闭。
