# 单电机效率：双栈真实仿真验收

2026-09-10。继原生接缝提交 `24019d6`，新增显式运行入口、物理所有者事件调度、原始包/ODE4/物理审计和故障收尾。PX4 与 ArduCopter 各完成 baseline、fault、fresh-process repeat，**六场均通过**。

本批采用原生位置保持控制器（PX4 OFFBOARD / AP GUIDED），通过公共命令到达 ENU `[2,3,3]`、yaw 0；没有把它写成外部 PID 测试。物理预算保留原约定，未改变 PID 合同、R1 或联合倍率门。

| 工况 | 扰动窗口峰值位置误差 | 恢复窗口最大位置误差 | 最大速度 | 偏航误差 |
| --- | ---: | ---: | ---: | ---: |
| PX4 baseline | 0.0907 m | 0.0725 m | 0.0305 m/s | 0.00620 rad |
| PX4 fault | 0.0804 m | 0.0850 m | 0.0259 m/s | 0.00540 rad |
| PX4 repeat | 0.0595 m | 0.0851 m | 0.0253 m/s | 0.00387 rad |
| AP baseline | 0.0779 m | 0.0552 m | 0.0122 m/s | 0.01038 rad |
| AP fault | 0.0806 m | 0.0583 m | 0.0140 m/s | 0.01038 rad |
| AP repeat | 0.0823 m | 0.0570 m | 0.0139 m/s | 0.01048 rad |

所有场次均证明：事件起点前连续 6,000 个真实物理步满足稳定条件；fault 恰好在指定 1,000 个 1 ms 区间对 motor0 应用 eta=.97；其余三路为 1，原始 actuator packet 解码与实际输入16一致，未缩放 PWM；16 个 ODE4 旋翼/子阶段逐步读回一致；deadline 前最后连续 1,500 步满足 0.3 m / 0.3 m/s / 0.15 rad 恢复门槛，最大原生状态间隔 32 ms。正常结束有真实落地上锁和原生 eta=1 终态。

六场的模型库均为 `a7325ebf754f6e61ebf25c5382fb67343659454cc176c0a7d50f980b3dcb9199`；17 个初始模型随机状态相同，控制 epoch 各不相同。闭环输入会受飞控调度影响，因此这里证明同种子/同协议在新进程内重复通过，不声称闭环轨迹逐位一致；#46 确定性重新运行仍单独验收。

## 实现与身份

- `efficiency_physics.py` 复用真实 AP servo / PX4 MAVLink 解码捕获，按每 1 ms 调用原生模型。物理进程读取稳定悬停后的不可变请求，使用自身 native tick 作为 origin，再独占、原子发布计划。取消文件出现即撤销，源请求改写/删除会失败。信号在原生区间内延后到完整原始记录写出后处理。
- `efficiency_task.py` 复用原始 DDS 观察器，未发送 RC 帧或执行 RC 场景。稳定窗口重新计时，必须取得连续 6 秒合格数据才会申请事件；失败请求取消并尝试有界 LAND，失败结果不因此改判通过。
- `audit_efficiency_flight.py` 从原始包重解码输入，独立计算 T/M 映射、检查确切区间、物理游标、原生目标/模式数据及逐毫秒预算。缺 terminal、PWM 被缩放、预算修改等负例拒绝。
- `run_efficiency_flight.py` / `run-efficiency-flight.sh` 保留原固件/模型基线的准入结果，另核验新模型构建与库身份；不改默认模型或默认准入。

PX4 本批 Control 为 `/root/wksim-joint-control-WjBuqN/build.json`（`ae5236af5052e81a256566a5e05d1840752fffb4d6f5cc512e0c0a5bb9e88c1d`）；AP 最终为 `/root/wksim-joint-control-8EMCw6/build.json`（`e61239c514c45d6c65222277066a7ca629e6e2638b9877a040bdfc99643e7e2e`）。逐场实际输入、安装源码、进程和原件身份在 [matrix.json](../validation/44-efficiency-flight/matrix.json) 与各自 `result.json` 中。

## 失败与修复

AP baseline-01 在效率事件前发生 takeoff 最终 yaw reset：高度刚过旧交接线时仍以约 0.86 m/s 上升，旧节点提前进入 COMMAND，随后的重置正确触发撤权。新节点保留原生 takeoff 权限，要求速度 ≤0.3 m/s 连续 0.5 秒，并保留 yaw-reset 等待与正常撤权规则；PX4 的原生 warmup 路径保持原行为。50 项相关回归通过。

AP baseline-02 在第一次进入航点容差后仍有减速振荡，速度短暂超过 0.3 m/s。此时没有请求事件；任务改为等待完整连续稳定窗口，而非第一次穿过门槛后立即宣称已稳定。最终 baseline-03 和两场 fault 全部通过原预算。两次失败都完成失败降落，原件保留，未重新标记成功。

## 当前边界与复现

实际可执行入口：

```sh
bash tools/build-joint-control.sh
# 使用上一步输出的新 manifest 和 SHA，并为每次运行选一个新 run-id/output：
bash tools/run-efficiency-flight.sh --stack arducopter --case fault \
  --run-id efficiency-ap-new --output-root /root/wksim-efficiency-flight-ap-new \
  --control-manifest /root/wksim-joint-control-8EMCw6/build.json \
  --control-sha256 e61239c514c45d6c65222277066a7ca629e6e2638b9877a040bdfc99643e7e2e
```

审计在记录的 ROS 消息覆盖层中运行：`python3 -B tools/audit_efficiency_flight.py <run-directory> --output <fresh-external-audit.json>`。默认库/配置是本机明确候选；另一个构建必须完成新身份核验。既有候选的旧源码可由提交/原始归档重演，不把新源码默认为旧安装。

本批没有硬件操作、正式默认模型提升或 G6/Full 改判。可选 DLL ABI、全球航点/GNSS、规划/相机任务、倍率与数值验收仍按各自规格推进。
