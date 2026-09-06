# MissionTask 暂停、显式恢复与取消保活

2026-09-06 JST。正式 MissionTask 已接入本地 CLI 暂停/恢复；固定 PX4 与 ArduCopter 分别通过暂停恢复、外部公共模式交接、暂停中取消后显式接管降落，共6个成功场景。另保留1个验证脚本退出码断言错误的失败样本。#42仍 OPEN：这不是实际 QGC 交互、RC 驾驶或空中 DDS 失联策略验收；#18和 Full Goal 不关闭。

## 实现与接口

操作契约、命令和状态详见 [任务使用说明](wksim-missions.md)。按 codebase-design，将请求文件校验/幂等封装在 ActionMailbox 小接口内，复用取消模块的文件安全实现；Task/MissionTask 保留唯一公开 Prometheus 发送接口，没有新增诊断原生飞行发送器或通用控制框架。

- 新增 `mission_actions.py`、`control-wksim-mission.py`：明确 run/mission/control_epoch/native_generation/action_token/request_id；同一令牌消费一次，状态转换轮换令牌。原子独占文件发布，提交不等于实际完成；保留请求文件审计。提交与消费之间的状态竞争由运行器再核对，不假设跨 Windows/WSL 单调时钟相同。
- MissionTask 增加 pausing/paused/resuming/landing 状态。明确暂停使用 PX4 AUTO.LOITER / AP BRAKE，观察 ACK 与实际撤销任务控制后才 paused。已发生外部模式切换则只观察，不再发模式命令。原 AUTO.LOITER→AP LOITER 映射没有变。
- paused 中继续检查进程、状态新鲜度、原生代次；不自动接管。恢复需要新的令牌与 COMMAND_CONTROL 请求，先按现有节点保持当前位姿，再发新身份的 MOVE。BODY 首次仍是 XYZ_POS_BODY；恢复使用原记录的 ENU 目标，不能重新锚定。停留计时和物理游标重新开始，保留中断窗口和每次尝试身份。
- 取消在其他操作者仍持权时等待，不自动抢回控制；显式 resume 授权接管后发 LAND，不再重发被中断的航点，或由外部操作者先落地。取消/控制释放先后顺序和起飞阶段连续两次暂停的异常路由竞态均已修复并加测试。
- Task 从新鲜 SessionState 跟随 request_id 高水位；ACK 匹配冻结的本次请求 ID，避免外部请求抬高计数后等错 ACK。新命令 ID 同时考虑已观察的受理记录。
- Mission 物理 argv 改为 `--run-until-stopped`，有界诊断仍保留 `--duration`。动力学方程、1ms模型子步和原执行器握手未改。运行器只扣除 paused 等待的墙钟时间；各命令/健康/执行器超时不冻结。不是联合场景时钟暂停。

这仍有明确失败分支：显式暂停在实际发保持前已无法确认任务所有权、接管/模式确认超时、数据/代次失效，都会停止进一步任务请求并记录失败，而非承诺任意并发操作者输入都能续飞。尚未做超过原315墙钟秒或3600仿真秒上限的长时空中验收；本次长寿命改变有启动契约与计时单测，不把约2秒墙钟等待说成长时飞行证据。

## 环境与版本

Prometheus 原基线 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce` 不改。当前安装 `/root/wksim-ros2-MUlZd0` 及能力预检基线不改，仍由正式 preflight 核对后启动；本轮没有向安装目录直接写源文件。

| 依赖 | 固定身份 |
| --- | --- |
| ROS2 / DDS | Ubuntu-22.04，Humble，`/root/wksim-dds-VxM6Ni`；私有 net/ipc/mount、独立 /dev/shm、domain77/localhost/FastDDS |
| PX4 | `/opt/aerotwinsim/src/px4-d6f12ad1`，commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，binary SHA256 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd` |
| ArduCopter | `/root/wksim-ap-dds-yaw-state-4Wr27s`，commit `1511f27194f1dcc3728270883047bdf022b3fd53`，binary SHA256 `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5` |
| 安装控制包 | prometheus_control SHA256 `e4c44ad9a1797f043669bbae9bc2e9b82d5f109979e1300d1f29e7cc98368da8`；上轮实际节点接管证据见[报告](2026-09-06_airborne-takeover-report.md) |

每个 result.json 保存确切 argv、PID/PGID、配置、源码/模型/二进制哈希及进程回收结果；独立审计逐项重新计算6个成功运行的 runtime 输入哈希，均与当前源码相符，并复核实际 FC 二进制。

## 实际命令与结果

在 Ubuntu-22.04 的 wksim 目录执行（每次运行器自动使用新 run_id）：

```bash
bash tools/run-mission-lifecycle.sh px4 pause_resume
bash tools/run-mission-lifecycle.sh arducopter pause_resume
bash tools/run-mission-lifecycle.sh px4 external_resume
bash tools/run-mission-lifecycle.sh arducopter external_resume
bash tools/run-mission-lifecycle.sh px4 pause_cancel
bash tools/run-mission-lifecycle.sh arducopter pause_cancel
```

测试只通过定时操作者输入调用真实 CLI，或发送一条标注身份的公共模式 SetupRequest；没有替换 MissionTask.execute/pump/send/pause/visit，不代发原生 DDS 命令。选择示例第3个 BODY 航点首次驻留至少0.7个 boot 秒后中断，paused 至少6个 boot 秒才提交新 resume。外部交接使用高于当前1000的 request_id，恢复的公开请求实际超过该高水位。

| 场景 | PX4证据目录 / 物理继续秒 / 最低高度m | ArduCopter证据目录 / 物理继续秒 / 最低高度m |
| --- | --- | --- |
| 暂停后恢复航点 | `mission-lifecycle-39qt5r3x` / 6.340 / 2.912683 | `mission-lifecycle-6wpgh5_n` / 6.380 / 2.969667 |
| 外部模式交接后显式恢复 | `mission-lifecycle-3ta8azx8` / 6.400 / 2.910543 | `mission-lifecycle-yq3m8y9u` / 6.400 / 2.969291 |
| 暂停中取消、显式恢复后降落 | `mission-lifecycle-f30u3z08` / 6.340 / 2.921865 | `mission-lifecycle-6e6kpqy9` / 6.460 / 2.969735 |

以上目录均在 `validation/`，各含 acceptance.json 和 runs/<run_id>/result.json。6次 paused 中公共任务请求计数均不增加；保留全部原生位置输出观察记录，以0.5墙钟秒队列排空保护段之后的窗口统计，新增观察均为0，不把保护段隐藏。各旧令牌 resume 提交实际返回1、submitted=false、offer/action不匹配。

4次恢复航点的首次尝试记录为 interrupted，第二次使用新身份完成；新目标与原记录 ENU/偏航匹配。停留仍按原位置≤0.5m、速度≤0.5m/s、偏航≤0.15rad、完整2个 FC boot 秒验收，物理窗口独立复核，未改变数值门槛。物理记录窗口实际1.96–2.04s等原始差异保留，不拿公共时间重标物理时间。

2次取消结果均是 `cancelled` 且 safe_landing=true，只完成前2点；第三点不再发第二次 MOVE，显式接管后直接 LAND。它们不是完成完整航线的 pass。

失败 `mission-lifecycle-v8n9f1rn`：产品正确拒绝旧令牌；验证脚本错误地预期 CLI 返回2，实际契约是1，因而诊断异常导致隔离运行失败收尾。修正的是退出码断言并核对 JSON 拒绝原因，不是接受旧令牌、放宽飞行阈值或删除失败样本。实际飞控已启动，该尝试计入7次/28进程组审计，不计安全降落。

## 回归、审计与保留

- 最终 WSL `bash tools/check-session-product.sh`：`validation/session-product-checks-FKNMvePk/`，234项 session 检查（跳过1项 Windows专属junction）及10项旧预检均通过。初轮231项日志 `session-product-checks-TWkXgTZW` 保留。
- Windows Python `D:/date/miniconda/python.exe -X utf8 -B -m unittest discover -s validation -p 'test_wksim_console_*.py' -v`：88项通过，`validation/mission-lifecycle-integration-20260906/windows-console.log`。
- MissionTask Windows 最终31项通过；ActionMailbox Windows19项中16通过、3符号链接权限不足跳过；真实 Windows junction 拒绝通过，3符号链接用例已在WSL通过。因此不能把任意单平台日志说成“全部无跳过”。
- 最终合并 Windows 任务/动作入口日志为同整合目录 `windows-mission-final.log`（50项、3项权限跳过）；中间误选Linux平台用例、新测试fixture及失败脚本的说明保留在 `integration-notes.md`。
- 独立磁盘回读、物理重算、输入哈希和进程组审计：`tools/audit_mission_lifecycle.py` → `validation/mission-lifecycle-integration-20260906/independent-audit.json`，7次尝试、28个自建组、0残留。未拥有 ArduCopter PID828/start_ticks19268 前后身份不变。
- 两个子代理实际持久化 turn_context 共2/3条均为 gpt-6-astra/low；分别仅写请求模块/测试/CLI和只读审查，两者已关闭，未嵌套。证据见同目录 agent-settings.json。
- Codebase Memory 最新87,512节点/196,679边，20:17:24UTC；精确导航/覆盖记录见[代码记忆](codebase-memory.md)。图只用于导航，实际源码/运行哈希另行核对，不把图大小当完成度。
- UE P450机体、CW/CCW旋翼、材质共5个真实资产和上游许可仍在 `Simulator/ue55/Content/Wksim/P450/`；来源、原生导入、显示证据见[P450报告](2026-09-06_p450-view-report.md)。本轮未重新下载或修改资产，没有把P450显示网格说成已校准的P450动力学。
- 用户原UE编辑器 PID35256、创建时间 `2026-09-06T02:20:00.4222100+09:00` 不变；没有连接其远程执行入口。源配置保留 bRemoteExecution=True、127.0.0.1绑定和TTL=0。未推送混合工作区、未发布厂商资源。

实际 QGC/浏览器交互、工作台暂停恢复按钮、UE冷启动稳定性、空中DDS失联、联合时钟、其他Full模式/机型、MATLAB范围、插件ABI和正式数值预算仍须推进。既有候选/仿真身份不能替代这些验收；本报告只是一次可复现的任务生命周期进展。

已发布并读回[#42进度评论](https://github.com/unununnnn/wksim/issues/42#issuecomment-5554578255)，创建时间2026-09-05 20:29:20 UTC；issue状态仍OPEN。未修改或关闭Wayfinder父图/正式规格。
