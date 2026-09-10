# ArUco 联合任务实验入口与当前真实失败

已接通显式候选配置、双栈任务装配、Windows RGB 到 WSL 的原子观测交接和独立原始 DDS 记录。它仍是实验入口，未通过闭环飞行验收，#104/#40 保持开放。

普通联合配置保持原有资源。实验任务必须明确提供当前 Control 与 PX4 land-cadence 清单及 SHA；资源预检在历史环境中核实原基线，再独立检查变更后的真实安装、库与固件。`validation/aruco-tracking-candidate-01/preflight.json` 已实际通过。新 Control 为 `/root/wksim-joint-control-FWBLNX`，清单 SHA `6d82332c80e753ef6d22e8860dda75b3685c39facd7fd3c78da10f26be099586`；PX4 为 `/root/wksim-px4-land-7RjMjQ`，清单 SHA `45c5332cf06a84952189fcf2eabc5d2e15fde9236c704a5c3d6318e7f5dcb3ac`。

两机正常公共起飞并稳定后才允许启用 RGB。协调器绑定实际 run/epoch/instance/generation、新 stream 和首张场景读回，独立相机事件的 generation 与 metadata 文件也逐项核对。当前 12s 候选不支持中途重绑或恢复旧任务；epoch 变化使本次失败。

任务使用原公共消息接口发送 BODY 速度、失效悬停及降落。常驻同一观测只检查过期，不重复喂入；新帧的 step/frame 与 target 必须一致。视觉命令单独使用冻结的受理超时，原生 setup/arm/land 不缩短。相机以外的 peer 只执行起飞、保持、降落。独立 raw 节点不进入执行器，通过原生 RCTake 留存 CDR、GID、源和接收时间；两个请求订阅端点的名称、命名空间和独立 GID 都进入启动检查。写失败、结束写失败或清理失败不能成为通过；排他打开失败不删除已有证据。主审后取消了每条 CDR 的重复 decoded 诊断对象，实际字节及身份保持完整，审计从 CDR 重新解码。

针对性检查包括：44 项 WSL 真实消息类型与编排检查；9 项基于既有真实相机帧的协调器接口检查；9 项物理坐标错位负例；既有空中场景几何审计的 6 项回归。物理审计逐 tick 检查跟踪误差、范围、高度、倾角和最终恢复保持，不能用平均值遮盖单点越界。采集完成仅标为待独立审计，任务返回成功不会自动设置 `flight_completed`。

## 三次真实尝试

| 目录 | run / epoch | 最后 tick | 实际结果 |
| --- | --- | --- | --- |
| `validation/40-aruco-tracking-01` | `aruco-track-afba53e79a` / `d17b518d73844c43ab670adc6845c1e6` | 848 | 累计迟到 107.146683ms，触发原 100ms 保护 |
| `validation/40-aruco-tracking-02` | `aruco-track-0e74873eb6` / `48ab11fb5c4c4c679d55a2ed9d2b71f9` | 12136 | 带既有分阶段 CPU 探针；累计迟到 100.152917ms，真实失败 |
| `validation/40-aruco-tracking-03` | `aruco-track-556a1b0366` / `81f44463c34d476e90b7f44e93e6e2a7` | 13992 | 带 CPU 探针和外部非阻塞 Python 栈采样；再次触发倍率保护 |

三场均在解锁前失败，RGB 未启用；没有把这些场景当作目标跟踪通过。受管进程组均已清理，失败输出及执行源码保留。归档工具逐成员重算哈希，再生成最大 32MiB 的有序分片；重建时先按 `archive.json` 顺序拼接并验证整体 SHA。

第二场的开始时刻漂移可精确分解为：前组工作超过 8ms 所致的 55.913979ms，加上其余释放迟延 40.490203ms，合计 96.404182ms；这不是唯一根因归因。正常节拍等待不算性能缺陷。已记录 GC 最大约 0.42ms，不能单独解释 4–16ms 阶段尖峰。第三场在 `validation/aruco-startup-pyspy-01` 留下 2998 条主线程栈样本；其中 ROS 调度、模型等待及原生等待都有覆盖，采样包含空闲且为非阻塞模式，不能等同精确 CPU 时间或飞行验收。

下一步以隔离 ROS 执行器微基准判断可避免的调度开销，再进行有依据的运行。批准的 1ms 物理步、4ms 屏障、相邻组最小周期、禁止追赶/暗中重锚及累计 100ms 门槛均不变。原始公共命令链与原生目标的完整关联审计还在独立复核中。

复现入口（输出必须是新目录）：

```powershell
& work/dependencies/aruco-python/Scripts/python.exe -B tools/run_aruco_tracking.py --manifest validation/ue55-build-f0409a874ed243cdbad4ac9cb38d886d/candidate-manifest.json --candidate validation/aruco-tracking-candidate-01/candidate.json --output <新目录>
```
