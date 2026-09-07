# 联合场景真实 DDS 中断、显式恢复与最终回归

承接提交 `6d2e371d918f202acd64e822dee4300e86942bcd`。真实 AP/PX4 Agent 中断后，联合物理冻结、显式恢复、新公共任务接管并降落的两个案例已通过加强后的离线审计。本轮又完成当前源码的健康暂停/单步/继续飞行，并修复了恢复审计漏核对实际授权文件的缺口。**这是已批准生命周期的限定证据，G2、#8/#19/#20/#22 和完整 Goal 继续开放。**

规格与38张初始切片早已批准并发布；本轮不重复请求批准，不改写或关闭原 Wayfinder，不改变原生阻塞关系。授权依据仍是[联合原则](2026-09-06_recommended-decisions-accepted.md)及[分别批准的任务语义与监督数值](2026-09-06_joint-wall-supervision-accepted.md)。

## 实现和运行身份

此前提交已经实现：完整输入确认后的1ms微步故障冻结；版本2许可中的故障载具范围；显式恢复时只退休已退出 Agent 的原生 DDS 发布者；链路/导航就绪与任务控制资格分开报告；旧 Task 自行失败，新 Task 使用新请求身份保持2秒后降落。PX4 被动重连未满足5秒窗口后，采用本实验内明确授权的原生 DDS 客户端 stop/start，先以私有 `/tmp` 和 `SO_PEERCRED` 核验目标 PX4 PID。它不是飞行命令旁路。

| 项目 | 封存身份 |
|---|---|
| AP 候选 | `/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json` |
| AP 清单 SHA256 | `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a` |
| AP 固件 SHA256 | `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de` |
| Control 候选 | `/root/wksim-joint-control-JlC29M/build.json` |
| Control 清单 SHA256 | `9bcdf892f57ee56486fc5732f96aa4666e1f7ab3bd6c8a84ab1825d253791201` |
| PX4 | 项目独立目录 `/root/wksim-dependencies/px4-d6f12ad1`；提交 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` |
| PX4 固件 SHA256 | `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd` |

保留 Prometheus 上游基线、原 ROS1、原固定飞控和默认生产准入。实际模型仍由自主 C++ 模型构建；这些联合运行不启动 CopterSim、闭源模型 DLL、Gazebo、MATLAB 或 UE。具体模型构建、参数、子进程 argv、安装包及源文件哈希均在每场 `result.json`、`*-build.json` 和源快照中；这证明这些实验的依赖边界，不替代 G6 全模式独立构建验收。

## 两个真实中断恢复案例

这两场是在上一检查点已经结束的真实实验，本轮使用其原始数据再次审计，没有重复启动它们。

| 检查 | AP Agent 中断 | PX4 Agent 中断 |
|---|---:|---:|
| 证据目录 | `joint-public-flight-gjoiiu49` | `joint-public-flight-39f4dlru` |
| 请求中断 tick → 观测退出并冻结 tick | 51460 → 51461 | 51428 → 51429 |
| 请求退出至观测退出的墙钟间隔 | 约1.94ms | 约1.55ms |
| 显式物理恢复就绪耗时 | 2.483852s | 0.510124s |
| 故障/Agent重新连接、显式恢复前的额外物理步 | 0 | 0 |
| 最终共同 tick | 64228 | 62956 |
| AP 新公共请求 | 4/5/6 | 4/5/6 |
| PX4 新公共请求 | 4/5/6 | 4/5/6/7 |
| AP 2秒保持最大位置误差 / 速度 | 0.05614m / 0.04167m/s | 0.03778m / 0.03062m/s |
| PX4 2秒保持最大位置误差 / 速度 | 0.08028m / 0.03629m/s | 0.26487m / 0.29522m/s |
| 模型、FC、Control、新 Task 退出码 | 均0 | 均0 |
| 自建进程组无残留 | 13 | 15 |

约1.94/1.55ms 是本次自有 Agent 进程退出的观测间隔，不是任意网络丢包的检测预算。故障可在完整的1ms微步输入确认后冻结；不要求伪装成尚未完成的4ms屏障。重新启动 Agent 没有推进冻结物理，也没有恢复旧任务。两个旧 Task 均自然失败并退出1；物理恢复确认后才另行授权新任务。

PX4 Agent 中断案例中，原生 failsafe 真实存在。新任务经过公开 `AUTO.LOITER` 请求及原生 ACK 恢复健康，再请求 `COMMAND_CONTROL`，因此比 AP 中断案例多一个新请求。没有伪造定位/RC、关闭健康检查或自动抢回控制。能力受理、原生 ACK、控制接管和2秒物理保持/落地分别核对，不以 ACK 代替动作完成。

**源码适用范围明确区分：**AP 案例通过 `--verify-current-sources`。PX4 案例的封存运行器早于当前进程身份保护增强，当前源码核验按预期拒绝 `tools/run_joint_flight.py`，失败日志已保留；随后按封存源码通过。唯一差异是注入前增加 PID/PGID/start_ticks、`/proc/exe` 核验及完整观测记录，见[差分](../validation/joint-dds-recovery-final-20260906/px4-runner-source.diff)。两场均使用相同 JlC29M Control，但不能把 PX4 旧运行说成验证当前全部运行器代码。

最终审计：[AP 当前源码](../validation/joint-public-flight-gjoiiu49/dds-recovery-audit.json)、[PX4 封存源码](../validation/joint-public-flight-39f4dlru/dds-recovery-audit.json)。两机仍使用同一参考出生原点、无机间碰撞耦合；这些位置任务门槛不是 G6 动力学等价预算。

## 本轮健康生命周期回归

新运行 `joint-public-flight-u46hqids` 使用当前源码和相同候选，124.947墙钟秒内完成：tick51452暂停4.00271s，严格单步至51456，再暂停4.00198s；显式继续后在51952取得双 Control 的新原生样本确认，随后完成原公共任务的航点和降落。

最终69068个共同tick，两机同时高于1m共14013个tick，即 **14.013仿真秒**。AP/PX4航点驻留最大物理误差分别0.19064/0.45817m，原0.5m门槛保持。10个模型/飞控/Agent/Control/Task自建进程组均无残留，模型、飞控、Control和Task全部正常退出0。原始许可CDR、控制确认、Task时基、逐步模型和执行器/传感器记录、当前源码审计通过，见[生命周期审计](../validation/joint-public-flight-u46hqids/lifecycle-audit.json)。

## 审计缺口、修复和负向检查

本轮使用原始证据的临时副本，把 `recovery-go.json` 的运行身份改为另一运行；旧审计仍通过。该[红色结果](../validation/joint-dds-recovery-final-20260906/audit-negative-red.json)说明旧审计漏查授权文件，不能解释为飞行本身收到过错误授权。原始证据保持不变。

`tools/audit_joint_dds_recovery.py` 现核对：预声明门槛/最终权威时间；授权文件、生命周期授权记录和新 Task 就绪身份；新请求与实际发送日志的一致性；每个请求对应的原生 ACK 事件与原始 DDS `TextInfo` CDR、公开受理/接管确认；请求的运行/控制代次、map坐标及共同时间网格。物理完成仍由独立模型真值验证。

新增 `tools/check_joint_dds_recovery_audit.py` 只构造临时审计输入副本。以下6个负例全部在对应门拒绝：外来授权、放宽门槛、ACK借用错误请求号、改写实际发送日志、旧请求重放、冻结模型发生位移。各原始文件哈希前后相同，见[负向结果](../validation/joint-dds-recovery-final-20260906/audit-negatives.json)。这些是证据审计测试，不是模拟出来的飞控验证。

AP恢复、PX4恢复和健康生命周期的最终审计分别再次完整执行，输出 SHA256 均逐字节一致，见[重复审计](../validation/joint-dds-recovery-final-20260906/audit-repeatability.json)。

## 回归和残留检查

| 检查 | 结果 | 证据 |
|---|---|---|
| 当前源接缝 | 61项：55通过、6跳过 | `scene-lifecycle-checks-LSXs2qKw/tests.log` |
| 默认产品矩阵 | 304项：279通过、25跳过 | `session-product-checks-tyy6AUPg/session-tests.log` |
| 旧版准入 | 11/11通过 | 同目录 `legacy-preflight-tests.log` |
| JlC29M安装候选 | 历史73项通过，本轮未重跑 | `joint-control-checks-M8r02V99/tests.log` |
| 审计负向 | 6/6正确拒绝 | `joint-dds-recovery-final-20260906/audit-negatives.json` |

完整跳过名单、实际命令及96项源码指纹在[回归摘要](../validation/joint-dds-recovery-final-20260906/regression-summary.json)。跳过项不计入通过，历史候选检查不冒称本轮重新执行。主代理另检查实际源码、审计差异和真实运行。

本次汇总全部10个 DDS 尝试及1个健康回归，**138个自建进程组**按当前 `/proc` 重新核查均无残留；失败样本仍按失败保存。原 AP PID828/start_ticks19268及argv在各场前后和本轮核查时一致。清单、退出码、现场内核身份和结果摘要见[集成记录](../validation/joint-dds-recovery-final-20260906/integration.json)。没有停止原AP、操作真实硬件或修改厂商安装。

## 保留失败和剩余门槛

| 样本后缀 | 保留结果 |
|---|---|
| `5y5s1fat`、`6j56sh3u` | 旧DDS发布者仍在发现缓存中，5秒恢复门拒绝；随后只允许明确退出Agent的GID退休。 |
| `yuk0rgxx` | 独立PX4资源缺少alias启动文件，飞控退出255；修复私有资源并补准入检查。 |
| `9eeyzgyj` | PX4被动重连未满足5秒窗口。 |
| `eglc5bjf` | DDS客户端已恢复，但原生failsafe仍存在；后来分开报告传输/导航与任务资格。 |
| `kj284sh1` | PX4临近触地短暂 `odom_valid=false`，任务按规则失败；重复性问题未通过过滤或放宽阈值消除，继续追查原始字段。 |
| `sn40rz3y` | 原注入身份保护拒绝，旧版未保留第二次观测细节；没有对身份不符的进程发信号。 |
| `svzk81sz` | 较早Control候选AP恢复通过，只保留其历史范围，不充作当前源码证明。 |

对 `kj284sh1` 的只读追查已进一步完成：[精确解码与源码证据](../validation/joint-dds-recovery-final-20260906/px4-landing-diagnosis.json)把原始 SessionState CDR 送入实际 `Task.receive_session`，重现同一失败。序号9744/9745无效，9746恢复，窗口21.747ms；位置有效位、dead_reckoning和generation未发生对应异常。封存原生ULog在60.840/61.840仿真秒的estimator flags均保持tilt/yaw有效，两个时刻在场景观察记录中相距2.026墙钟秒；固定PX4每1仿真秒或标志变化发布一次该消息，而适配器要求2墙钟秒内收到。主线复读两侧源码、核验ULog归档哈希并重复解码通过。

这使 **estimator消息新鲜度越界** 成为最强假设，但旧观察器没有记录Control的实际DDS接收时刻，尚不能宣称精确根因已证实。下一步只补充Control评估瞬间各原生源的接收时间/年龄、有效性原因及estimator/GPS/attitude原始CDR与发布者身份，再做有界实测；保留2s批准值和失效即失败语义，不以过滤无效样本处理重复性问题。

本轮未完成：任意网络黑洞/丢包、输入迟到和模型/飞控掉队矩阵、倍率合同与实测、完整cold-reset旧公共/原生队列隔离、正式联合配置/CLI/UI/UE、环境/分离出生点/碰撞、G3控制与demo、G4公开Full全部模式/机型、G5真实MATLAB及G6正式预算和逐行证据。#22目前仍原生阻塞于开放的#8，不能借本轮关闭更广义策略或项目。

## 复现

Ubuntu-22.04/root，项目目录 `/mnt/c/Users/PC/Documents/odid编译/wksim`：

```bash
bash tools/run-joint-flight.sh \
  --ap-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a \
  --control-manifest /root/wksim-joint-control-JlC29M/build.json \
  --control-sha256 9bcdf892f57ee56486fc5732f96aa4666e1f7ab3bd6c8a84ab1825d253791201 \
  --scene-lifecycle
# 单独真实中断实验再指定 --dds-loss arducopter 或 --dds-loss px4。

bash tools/check-scene-lifecycle-source.sh
bash tools/check-session-product.sh

source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
python3 -B tools/audit_joint_dds_recovery.py validation/joint-public-flight-gjoiiu49 --verify-current-sources
python3 -B tools/audit_joint_dds_recovery.py validation/joint-public-flight-39f4dlru
python3 -B tools/audit_joint_lifecycle.py validation/joint-public-flight-u46hqids --verify-current-sources
python3 -B tools/check_joint_dds_recovery_audit.py validation/joint-public-flight-gjoiiu49 \
  --output validation/joint-dds-recovery-final-20260906/audit-negatives.json
python3 -B validation/joint-dds-recovery-final-20260906/repeat-audits.py
python3 -B validation/joint-dds-recovery-final-20260906/verify-integration.py
```

Codebase Memory 实读仍600527节点/712312边；`joint_lifecycle.py`为not_tracked，两个审计工具按tools排除，见[精确覆盖](../validation/joint-dds-recovery-final-20260906/index-coverage.json)。本轮直接读取已知源码，无依赖新结构的图查询；不把ready当作此前持久化失败已修复。后续依赖新结构的查询仍须先检查/刷新。

两名侧线代理分别只做隔离回归和保留失败的只读诊断，实际turn_context的 `gpt-6-astra / low` 由代理及主线核验。主线独占真实飞控测试，未嵌套委派；未推送工作区或发布厂商资源。
