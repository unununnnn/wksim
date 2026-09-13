# #86 `35-px4-flight` PX4 外部 PID 校正尝试交接

## 运行身份

- 本次为原 #86 输出目录前缀失败后的命令校正尝试；旧失败原件仍在 `validation/lunar-86-5321a4b394e94d4fb20e232d70e1e915/`。
- run ID：`pid-px4-20260909-02-7e3ce147`
- 输出根：`/root/wksim-pid-flight-pid-px4-20260909-02-7e3ce147`
- 实际命令：

```text
bash tools/run-pid-flight.sh --stack px4 --run-id pid-px4-20260909-02-7e3ce147 --config Simulator/wksim_runtime/pid-flight-v1.json --output-root /root/wksim-pid-flight-pid-px4-20260909-02-7e3ce147
```

- 配置 SHA256：`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`
- runner SHA256：`695e59e92700045e4d7ce297f9b11127939bf833855195edac27dc961d4c430f`
- wrapper SHA256：`c772423deea8dde33914f05edef5777cf116c06cbae4c008f9accaea09ae8302`

## 实际结果

- 新命令的 `--preflight` 真实通过：`ok=true`、`reasons=[]`、退出码 `0`，无 FC/model/ROS 子进程。
- 完整运行真实进入 `physics_listening`、`agent_listening`、`physics_fc_coupled`、姿态/参数准备、arming 和 PID calibration 阶段。
- 最终失败：`ValueError: position_enu must be a finite number`。
- run/result：`status=failed`、`safe_landing=false`、`stop_kind=unsuccessful_isolated_teardown`；`children_reaped=true`、`cleanup_errors=[]`、`source_unchanged=true`、`candidate_unchanged=true`。
- 失败后 WSL 无该 run、PX4、模型、Agent、PID physics 或 control 残留；完整 raw 物理流、PID trace、native log 和 result 保留在输出根。
- 未满足外部 PID 的物理/native 完成条件；不能把部分 calibration 或 `online_ok` 当作 PASS。

## 独立审计

准确命令：

```text
source /opt/ros/humble/setup.bash; source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash; source /root/wksim-ros2-MUlZd0/install/local_setup.bash; source /root/wksim-ap-attitude-msgs-qOmnF9fT/install/local_setup.bash; source /root/wksim-attitude-control-x3_2v4wb/install/local_setup.bash; /usr/bin/python3 -B tools/audit_pid_flight.py --run-dir /root/wksim-pid-flight-pid-px4-20260909-02-7e3ce147/pid-px4-20260909-02-7e3ce147 --output /mnt/c/Users/PC/Documents/odid编译/wksim/validation/lunar-86-20260909-px4-02/pid-audit.json
```

- 审计退出码：`1`，`status=rejected`。
- 具体拒绝：缺少 `disturbance-event.json`；运行在扰动事件之前已失败，因此不能生成或补造该事件。
- 审计输出绑定实际 run/source/config 身份，并保留已通过的身份检查和第一失败。

## 证据哈希

- `flight.stdout.log`：`d4d6b0fabd3fcd7307069f16c9f499a22ed5fbc6ae5fe76072af3c22a2a1925c`
- 输出 `result.json`：`1774c73f6f787dd87eb1db22423ecf1bd5d2c6c4a3b0fa9132da81145c9b8745`
- `physics-1ms.jsonl`：`34ac6142c3c309b4c1c8e5b9e9e6dc988444a2e6a85aed92c54962936b0b9904`
- `pid-resolved-config.json`：`7045442006f0db6048826c7ef72bada10d9427197ca71be88abdd0833ee5e4fe`
- `pid-audit.json`：`b4beb0c87ac4fc099d2bf63a977803a1f8a5e2015b3db19e2ab95b220db668c1`
- 活动目录：`validation/lunar-86-20260909-px4-02/`

## 处理判定

本次校正尝试仍未满足 #86 完成条件。#86 保持 `OPEN + needs-triage`；具体缺口为 `position_enu` 非有限值导致的 PID 运行失败，以及独立审计所需 disturbance event 缺失。不要再次重试，须由 Astra 先定位/修复并冻结新的运行合同；#87 继续阻塞。
