# 正式联合 P+V / mixed 任务入口

本接缝复用已经冻结的两段 P+V 与 mixed 任务语义。源码和纯协议测试通过不表示正式实飞已通过；正式 profile 仍必须拥有最终组合的有效准入证据。本文不修改历史实验结果，也不把实验 admission 改成正式身份。

在项目的 Ubuntu 22.04 / ROS Humble 环境中，从 wksim 仓库根运行。两个例子分别为 `Simulator/wksim_runtime/examples/joint-pv.json` 和 `Simulator/wksim_runtime/examples/joint-mixed.json`；每次运行使用新的 `run_id`。以下以 P+V 为例：

```bash
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/joint-pv.json --preflight
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/joint-pv.json --output-root /tmp/wksim-formal
```

运行器完成严格资源核验与 DDS 初始化后保持任务待启动。第二个终端读取 `/tmp/wksim-formal/joint-pv-example/status.json`，确认 `allowed_actions` 已含 `start-task`，再执行：

```bash
python3 -B -m Simulator.wksim_runtime.joint_actions /tmp/wksim-formal/joint-pv-example start-task
```

提交回复是命令受理链的一部分，不是飞行完成。等待两个 worker 完成降落，`status.json` 中的 `task_state` 为 `completed`，再正常停止并审计：

```bash
python3 -B -m Simulator.wksim_runtime.joint_actions /tmp/wksim-formal/joint-pv-example stop
# 等待启动终端返回。以下是该 profile 当前明确选择的 overlays。
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-OEvS3W/install/local_setup.bash
python3 -B tools/audit_joint_trajectory.py /tmp/wksim-formal/joint-pv-example --output /tmp/joint-pv-formal-audit.json
```

mixed 用 `joint-mixed.json` 和 `joint-mixed-example` 替换相应名称。正式运行器从已准入的 capability 列表派生 AP 的两个只读开关；JSON 没有允许任意开启原生分支的布尔字段。新任务冻结为 0.5×、初始 hold 5 秒、waypoint 2 秒，其余轨迹、停止、新锚、BODY 捕获和降落语义沿用原任务。

两类新任务在提交端和 supervisor mailbox 的受理前均排除 `pause`、`step`、`resume`、`recover`、`start-recovery-task`、`set-rate`。`stop` 与 `cold-reset` 保留真实进程/场景退休语义；cold-reset 创建新 epoch 并需要再次显式 start-task，不能视为轨迹恢复。中断或 fault 保留真实失败，不能回落 position 后声称轨迹完成。正常完成证明要求完成后 `stop`；cold-reset 不出具被退休任务的完成证明。

新任务和正式 JointTask 使用同一 SceneLease/control epoch。被动原始 CDR recorder 使用现有 `wksim_joint_supervisor` 节点；setup/command 各自必须恰好有该节点与命名 Control 两个非零且不同 GID 的端点。旧 position/velocity 仍要求一个端点。P+V 每一腿的 ready/go 使用实际 task identity，在四 tick 边界发出 `start_ns=(issued_tick+1000)*1000000`；初始正式 go 只由显式 start-task 产生。

停止后的 `physical_task_proof` 与独立离线复算均使用真实正式 result/preflight、`tasks/<id>/<stack>` 和原始 `pv-dds.jsonl` / `wire.jsonl` / `clock.jsonl` / 每 1ms truth。只给共享数值函数传递实际 epoch/authority/tasks 字段别名和明确的 `task_root`、`recorder_name`、`wire_name`；不存在合成的 experimental admission。decoder 的实际 overlay 与消息包摘要必须匹配正式预检。mixed 同时审计原始 AP DataFlash GUIP submode 7，原生日志 schema 与已准入 source manifest 绑定。

执行时封存正式 runtime/core、实际任务/审计/verifier 工具、控制安装源码、build manifests、native Log.cpp 及其原始 source manifest。原始逐包、1ms、误差、停止与倍率门槛不变：连续倍率仍核验累计 100ms、全部完整 10 秒 ±2% 和 60 秒 ±1% 滑窗。

本范围仅覆盖固定正常 home/origin 与环境的任务。加速度参考被保留但不执行；yaw-rate、terrain、native timeout/fence/home-or-origin-reset/avoidance 边界以及空中恢复不由 nominal PASS 代验。更高倍率与全功能验收仍是各自的义务。
