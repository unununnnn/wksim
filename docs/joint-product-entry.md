# 正式联合实验入口

`tools/run-wksim.sh` 接受 `kind: joint_scene` 配置，以一个场景时钟运行 AP/uav1 与 PX4/uav2。当前配置使用经过真实飞行、DDS 恢复和构建身份检查的 `joint_quad_dds_v1`：1ms 物理步、4ms 输入屏障、两个独立模型进程和两套真实 SITL。它与原有单机配置共用正式启动脚本。

首期任务是 Prometheus 公共位置任务：正常预检、解锁、起飞、悬停、航点、降落。启动服务仅运行地面仿真；发送 `start-task` 才启动两个任务。观察程序和操作客户端不发布原生飞行命令。

## 启动与操作

在 WSL Ubuntu-22.04 中执行。配置和运行标识应保存在项目自身目录；每次启动使用新的输出目录，冷重置则保留同一运行目录并产生新 epoch。

```bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/joint-scene.json --preflight
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/joint-scene.json --output-root /root/wksim-joint-operator-001
```

第二个命令保持运行。在另一个 WSL 终端读取状态并提交操作：

```bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
RUN=/root/wksim-joint-operator-001/joint-scene-example
python3 -m json.tool "$RUN/status.json"
EPOCH=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["epoch"])' "$RUN/status.json")
python3 -B -m Simulator.wksim_runtime.joint_actions "$RUN" start-task --epoch "$EPOCH"
```

只执行当前 `allowed_actions` 中列出的动作。客户端提交时校验状态年龄、运行身份和所见 epoch；监督器再次校验操作令牌和递增 command_id。提交结果中的 `result_file` 是该操作的后续结果路径。`submitted`、`accepted` 均不等于动作完成，应读取结果中的 `state` 和 `effect`。任务动作的完成表示已创建新的公共任务，实际飞行完成另见 `task_state`、任务阶段、原生 ACK 和最终物理证据。

| 动作 | 可观察效果 |
|---|---|
| `start-task` | 两侧地面就绪后，经共同开始屏障启动新的公共任务。 |
| `pause` | 当前两侧位置任务已接管时，在完整输入屏障暂停物理及任务时间，等待双侧确认。 |
| `step` | 从已确认暂停推进四个 1ms 物理步，重新暂停。 |
| `resume` | 显式继续，须取得晚于冻结点的新原生状态及双侧确认。 |
| `recover` | 可恢复的 DDS 故障中，旧任务退出后重建失联 Agent，并在批准的 5s 内核验新原生状态。此动作完成后仍需新任务。 |
| `start-recovery-task` | 显式创建新的空中恢复任务，使用新命令身份，原生保持后重新接管、驻留及降落。 |
| `cold-reset` | 退场整个旧场景进程组，再创建新的网络、IPC、挂载隔离及 epoch；新一代地面就绪后完成，不自动启动飞行。 |
| `stop` | 停止权威物理推进并清理本实验进程；清理核验后完成。它是实验退场操作；正常飞行结束先等待任务降落完成。 |

冷重置后重新读取 `EPOCH`。旧代次请求不会在新场景执行，旧代次的操作结果继续保留。`status.json` 中未提供倍率、其他任务或载具的操作入口；配置里的未知字段会被拒绝。

## 身份与证据

启动前核对 AP/PX4 源码及构建产物、安装 Control、实际消息覆盖层、自主模型和已有原始飞行证据。`joint-profiles.json` 记录本机资源的精确路径与哈希，不能仅换一个路径就将其他版本当作已验证候选。原厂安装和旧参考构建保留；此配置不启动原版 CopterSim、Gazebo 或 MATLAB。

运行目录保留 `config.json`、`status.json`、逐操作结果和总 `result.json`。每个 `epochs/<epoch>/` 包含预检、进程身份、原始模型状态、执行器线路、权威时钟、公共 DDS CDR、场景许可/确认、各任务阶段与退出结果。完成公共任务仍需独立模型真值检查；停止或重置本身不能标记飞行完成。

该入口尚不代表 G2/Full 整体验收。正式倍率与全部掉队流程、联合 UI/UE 显示、环境/出生点/碰撞以及 Full 扩展义务继续由原票据承担。真实硬件门槛和未决数值预算没有由本入口代为批准。
