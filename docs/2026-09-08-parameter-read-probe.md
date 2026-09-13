# 参数只读 probe（真实执行待主代理安排）

新增 `tools/probe_parameter_read.py`、`tools/run-parameter-read-probe.sh`。只读取 AP `WP_SPD` 或 PX4 `MPC_XY_CRUISE` 一次，关闭附加客户端后调用标准 `Task.execute()` 完成公开单航点起降。通过 `runtime.run(..., task_factory=ReadProbe)` 保留正式配置校验、资源预约、预检、固定固件及模型核验、进程启动、物理轨迹门槛和收尾。不改产品 runtime、Task、协议模块、配置或 pins，不启动 UE/MATLAB，不构成 #43 参数写入、持久化或飞控重启验收。

## 边界与证据

- 必须 `session_v1`，拒绝 joint、mission、display、telemetry、GCS forwarding、restart-control 和 promotion 配置字段。`--run-id` 与 `--output-root` 必填；现有运行目录由正式运行器拒绝覆盖。
- 读取之前等待 Task 接受的真实 run/epoch/native generation，公开位置有效、disarmed、地面且未开始任务。每次协议核验重新读取本轮 `truth.jsonl`，使用正式运行器的绝对高度 `<0.3m` 和 `2s` 新鲜度门槛。时间取已接受 SessionState 的原生 source_received_monotonic、公开接收时间、公开状态推进时间及物理文件 mtime 映射时间的最旧值；记录时间来源和原始公开状态。mtime 在读文件前取得，不用 UI 自报地面布尔值。
- AP 固定 `/ap/get_parameters`，对应已读固定源码请求主题 `rq/ap/get_parametersRequest`；实际 client ready 与 graph 的同名 GetParameters 类型均必须成功。记录实际 graph，失败不猜另一个服务名。真实 `rcl_interfaces` 单项请求绑定唯一 ROS future，10s 超时，无重试。请求/响应的 CDR 字节及 SHA256 是本地真实对象序列化证据，**不是网络抓包**。
- PX4 使用 `load_dialect('px4')` 核验的生成模块，独立 socket `127.0.0.1:14661`，固定 peer `127.0.0.1:18591`，固定目标 system22/component1。先看到本网络 namespace 中同身份、PX4/quadrotor、未解锁 HEARTBEAT，再有界排空输入，发送唯一 `PARAM_REQUEST_READ(index=-1)`。源 system245/component190；记录真实 UDP 请求/响应原始字节与 SHA256。响应必须 peer/source/name/REAL32 匹配，10s 无回复报告 unknown/timeout。`PARAM_VALUE` 没有 request_id；仅证明本 context 中观察到匹配存储值，不能声称强请求关联。
- `parameter-read.json` 保存原值、context、地面依据、服务图或 heartbeat、协议身份、源码哈希、请求/响应和失败信息；正式 `result.json` 的 `task.parameter_read` 包含同一报告。报告明确零参数写操作和零重启操作；标准 Task 的起降控制命令仍照常执行。读成功并不代表完整运行通过，后者必须正式 `result.json.status=pass` 且真实物理门槛通过。

wrapper 创建 net/ipc/mount namespace 和私有 `/dev/shm`；正式 runtime 在预检通过后建立私有 `/tmp` overlay。profile 配置按 `select_config` 返回的 `setup_files` 原顺序 source；旧 session 示例按正式 runtime 原 overlay 顺序 source。路径均为 bash 位置参数，不拼入 shell 代码。

## 检查与运行命令

仅做了无资源检查：Python AST 解析、`bash -n`、现有 `test_wksim_parameter_protocol.py` 四个测试通过（真实 ROS CDR 和固定 MAVLink 编解码，未创建客户端或启动仿真）。未执行 SITL；没有真实读值或真实服务可用性的成功声明。

以下是项目现有无 mission session 示例的明确命令，每轮使用新的 output-root/run-id；这两个示例仍指向原有资源，不冒充 current profile 候选。若主代理选择 current profile，应提供独立且无上述冲突字段的已审查配置，工具仍执行完整正式预检，禁止为通过预检修改 pins。

```bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
bash tools/run-parameter-read-probe.sh Simulator/wksim_runtime/examples/arducopter-session.json \
  --run-id parameter-read-ap-20260908-01 --output-root /root/wksim-parameter-read-ap-20260908-01
bash tools/run-parameter-read-probe.sh Simulator/wksim_runtime/examples/px4-session.json \
  --run-id parameter-read-px4-20260908-01 --output-root /root/wksim-parameter-read-px4-20260908-01
```

两栈必须由主代理审查后串行执行。预检拒绝、服务未发现、超时或 ground/context 变化均保留失败；不降级、不重试参数操作。上述命令此阶段尚未运行。
