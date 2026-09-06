# 共同时间下的双飞控 Prometheus 公共任务验证

状态：核心联合物理入口、双载具 Task 身份与显式 ROS 操作时基已实现，取得真实连续联合飞行证据。**不是完整 G2/Full 交付**：本轮不验证空中物理暂停/恢复、倍速、掉队恢复、碰撞/分离出生点或正式联合 UI。此前原则与时钟基础见[批准记录](2026-09-06_recommended-decisions-accepted.md)、[时钟/冷重建报告](2026-09-06_scene-clock-lifecycle-report.md)。

## 实现

- [JointPhysics](../Simulator/wksim_core/joint.py)复用既有 AP JSON、PX4 HIL 编解码和 epoch 模型进程，使用同一 `SceneClock`。每机1ms真实模型子步，AP每步传感器/下一请求握手，PX4每4ms传感器/严格原生时间输入屏障；零阶保持实际执行器输入，不发送模式、解锁或位置任务命令。AP下一请求仍不是新控制计算完成ACK。
- [Task](../Simulator/wksim_runtime/task.py)新增严格 `uav_id=1, use_sim_time=False` 参数。默认行为保持原墙钟等待/FC启动时间驻留；显式 ROS 模式下等待与驻留使用真实节点 ROS 时间。AP映射 `/uav1/prometheus`、PX4映射 `/uav2/prometheus`；嵌套 state/control 身份校验先于 epoch、请求高水位和代次绑定。旧 epoch/时钟倒退不自动恢复。MissionTask只同步身份相关调用，其专用驻留/暂停语义没有冒称一并迁移。
- [ControlNode](../ros2/src/prometheus_control/prometheus_control/node.py)在 `use_sim_time=true` 时让起飞、预热和操作完成截止使用 ROS 时间；原10/25/35秒等数值未放宽。通信新鲜度、原生ACK等待、输出服务仍使用原单调墙钟。时钟校验放在原生副作用及持续输出之前；不增加健康检查豁免。
- 控制进程停止改为 SIGINT/TERM 只置停止标志，当前回调返回后再销毁节点/ROS context；不让异步信号先使正在发布的context失效。没有吞掉正常运行中的ROS错误。
- [受控验证入口](../tools/run_joint_flight.py)调用同一个现有 `Task.execute`；两个独立安装的控制节点实际承担原生DDS命令。ROS消息接口继续用固定原overlay；没有重编消息来冒充兼容，也没有用诊断器代发控制。

## 独立构建与准入

复用CMake/colcon，只构建控制包到新目录；原固定AP、PX4、消息包和控制安装不覆盖。[构建工具](../tools/build-joint-control.sh)与[显式候选校验](../tools/joint_control_candidate.py)记录仓库/暂存/安装Python文件集合与SHA、CMake/package/入口、构建日志、脚本和清单哈希。实际启动前仍要求固定环境/AP候选预检通过；新控制安装须另给清单SHA，子进程验证导入的确切安装路径。默认生产capability/候选哈希未放宽。

最终控制候选 `/root/wksim-joint-control-I4sbJN`，清单SHA256 `3b0bca977f9d2775a5f9ddbacd8c29e76e8ebf63b2c9682f339ea8f458bfe4d3`。前序 `BZx0RO`（时基初版）、`zKvX4e`（前置时钟校验）保留作版本/负向对照，不混称最终候选。

AP仍用 `/root/wksim-ap-clock-stop-OXQqdR`，清单SHA256 `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a`；AP固件 `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de`，PX4固件 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`。

## 实测与独立审计

预先固定验证上界：180000个1ms tick、900墙钟秒。任务仍是既有六条公共输入：自主保持、普通解锁、COMMAND_CONTROL、ENU `[2,3,3]` 航点、LAND、落地保持；无强制解锁/RC伪造/关闭预检。每次包括两个真实FC、两个Agent、两个真实模型进程、两个公共Task、两个安装控制节点，一个主时钟所有者。各在私有net/ipc/mount与 `/dev/shm` 中运行。

记录先写WSL自有目录，结束后复制到仓库证据目录。它减少跨盘记录开销，不是硬实时倍率保证；显示和日志没有被当作时间来源。

| 证据目录 | 控制候选 | 飞行结果及限制 |
|---|---|---|
| `joint-public-flight-onnyn2l_` | BZx0RO | failed；启动数据含非有限字段，结果保存再次报错，最初异常未完整落盘。保留失败，不追溯编造原因。 |
| `joint-public-flight-i66_ezp_` | BZx0RO | 飞行/原始数据审计通过；清理时AP控制节点退出1，不称正常停止完成。 |
| `joint-public-flight-bhdnhf4e` | BZx0RO | 飞行/审计通过，控制节点正常退出。 |
| `joint-public-flight-mej8no3_` | zKvX4e | 前置时钟校验后飞行/审计通过；清理时PX4控制节点退出1，退出竞态保留。 |
| `joint-public-flight-mn8zqmos` | I4sbJN | 最终飞行、原始数据、当前源码和正常控制退出审计均通过。 |

[最终审计](../validation/joint-public-flight-mn8zqmos/audit.json)核对源快照、当前实际执行源、控制安装/暂存集合、原生输入字节、两个模型每步输入/输出、公共请求与原生接受ACK、任务ROS时段及独立物理真值。旧版本只使用其留存源码/安装身份，不把新版本校验倒填成旧版当时已具备的能力。

| 最终实测 | AP / uav1 | PX4 / uav2 |
|---|---:|---:|
| 模型总tick | 69144 | 69144 |
| 公共请求 / 原生接受ACK | 6 / 6 | 6 / 6 |
| 独立物理最大高度 m | 2.99016 | 3.04843 |
| 独立物理最小航点误差 m | 0.02270 | 0.06403 |
| 任务驻留时段内物理航点最大误差 m | 0.18202 | 0.46279 |
| 任务悬停时段内物理高度最大误差 m | 0.10937 | 0.17412 |
| 最后Task ROS时间 s | 64.864 | 68.999 |
| 模型、FC、Task、Control退出码 | 均0 | 均0 |

共享scene epoch `5cf3311ff7c945e0bf2bf301263e14cf`；两个控制epoch各自独立。公共输入序列去除时间戳后完全一致，但话题/载具身份不同。模型逐步记录有 **13814个同tick两机均高于1m的样本（13.814仿真秒）**，不是两个独立实验的墙钟重叠。全程69145次ROS时钟发布（含0）、17286个4ms屏障、69144条AP传感器输入、17286条PX4 IMU及691条GPS输入。

审计按传感器发送前实际缓存的原生执行器输出逐步核对模型输入，允许但不赋予步进权限的同值AP重复请求单独计数。初版审计把启动时排队的frame0重复误当非法，随后改为只接受相同内容的当前/上一帧，并仍要求每一步都取得下一帧确认；没有放行跳帧或多推进模型。

两机当前使用模板的同一参考原点和无机间碰撞耦合模型；这证明共同时间与公共任务路径，不证明分离出生点、编队避碰或环境交互已完成。高度/位置任务门槛也不是G6动力学等价预算。

## 失败回归与退出验证

- 结果保存现在把非有限启动字段明确记录为 `{"nonfinite_number":"nan"}` 等，而非填零或当作有效定位；实际有效性判断不改变。回归执行保留的旧save代码可复现失败，再验证新保存不会丢掉错误或改写有限坐标。
- [无效时钟负对照](../validation/joint-flight-integration-20260906/invalid-clock-negative.log)：旧控制候选在记录器测试中先调用普通arm请求再拒绝时钟，持续输出路径也未拒绝。前置校验后两项通过；记录器不是实际飞控命令证据。
- 12次普通真实ROS节点SIGTERM未复现退出竞态；随后在真实发布回调前加入仅测试用200ms延迟并发送SIGTERM，旧zKvX4e稳定复现 `publisher context is invalid`。证据 `/tmp/wksim-control-stop-window-gej8bk71`。这是定点扩大已知竞态窗口，不是替换状态或飞控。
- 最终候选在[73项专用检查](../validation/joint-control-checks-urksKorY/tests.log)中通过身份、真实ROS时基、时钟副作用门、默认兼容、同窗口退出及12次普通退出；测试进程记录在日志给出的自有临时目录。最终联合运行还强制要求控制节点正常退出，否则整体判失败，原先的异常退出样本不改写。
- [旧默认矩阵](../validation/session-product-checks-tfBI35cP/session-tests.log)270项、跳过13项，其余通过；[旧版准入10项](../validation/session-product-checks-tfBI35cP/legacy-preflight-tests.log)通过。候选的8项新条件测试在专用环境补跑，前轮4项场景/真实模型条件测试另有证据；原有1项跳过保留。不把跳过算成通过或Full覆盖率。

五次场景涉及50个自建进程组，最终清理需以[集成记录](../validation/joint-flight-integration-20260906/integration.json)中的实际内核检查为准。成功最终运行两个Agent经受控TERM退出-15，其余八个子进程均0；原AP PID828/start_ticks19268保持不变。未操作原UE、P450资产、真实硬件或原厂安装。

Nietzsche侧线只处理Task/MissionTask身份与相应测试，显式gpt-6-astra/low并核验实际turn_context；主线修正了旧测试夹具缺少control.uav_id的问题，未降低实际消息身份校验。无嵌套代理。

## 复现与剩余工作

在Ubuntu-22.04/root、仓库目录执行，使用已封存的最终候选：

```bash
bash tools/run-joint-flight.sh \
  --ap-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a \
  --control-manifest /root/wksim-joint-control-I4sbJN/build.json \
  --control-sha256 3b0bca977f9d2775a5f9ddbacd8c29e76e8ebf63b2c9682f339ea8f458bfe4d3
python3 tools/audit_joint_flight.py validation/joint-public-flight-mn8zqmos --verify-current-sources
```

新构建用 `bash tools/build-joint-control.sh`，必须采用那次输出的新目录/清单SHA，不覆盖旧候选。实际停止竞态与无效时钟的修正均在最终安装候选实测，不借旧版飞行证明新代码。

下一集成门仍包括正式联合配置/UI、任务与物理暂停衔接、暂停时新鲜度与保活、倍速、迟到/掉队/重连策略、完整冷重置旧队列隔离、环境/出生点/碰撞、UE同步查看及Full余项。现有MissionTask的“任务暂停但物理继续”不等于物理暂停。#8详细策略/#19/#20/G2与Full保持开放。

Codebase Memory仍返回可读数据库600527节点/712312边；本轮新JointPhysics为not_tracked，Task/Control源为metadata_changed，tools按子树排除。此前总体刷新/持久化错误未被宣布解决；本轮使用精确源码与运行快照，不进行依赖未验证新增结构的图查询，也不为报告归档重复全库索引。
