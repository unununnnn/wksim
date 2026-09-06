# 控制节点重启与旧输入隔离

推荐使用 `session_v1` 配置和 `/root/wksim-ros2-2egljG` 已飞候选。新节点**不受理旧的无身份 setup/command 输入**，没有静默兼容或自动补 epoch。原 47 个 Prometheus schema 未改；新增包 `wksim_msgs` 包装它们。历史 `legacy_v1` 安装与例子保留，只用于旧流程，不能据此声称具有重启隔离能力。

## 运行与显式地面重启

在 WSL Ubuntu-22.04 的仓库根目录执行，使用新的 run_id 或尚不存在的输出目录：

```bash
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/arducopter-session.json --output-root /tmp/wksim-session-runs
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/px4-session.json --output-root /tmp/wksim-session-runs
```

两者是独立实验，不是联合场景。创建私有 network/IPC/mount namespace 和 `/dev/shm`，预约规则见[独立隔离](wksim-isolation.md)。旧的 `arducopter.json` / `px4.json` 不改变含义；缺少 `control_protocol` 仍选择历史 `legacy_v1`。候选匹配和覆盖层检查见[只读准入](wksim-control-profile.md)。

要在本次任务解锁前重启控制进程，在复制的 session 配置中显式添加 `"restart_control_on_ground": true`。它必须是布尔值，且只能配合 session 协议。运行器先完成地面 AUTO.LOITER，核对新鲜的公开 disarmed 状态和物理地面真值，再回收自己拥有的 control 进程组、启动同一安装代码的新进程。Agent、飞控与物理进程不重启，物理时间持续前进。任务收到新 epoch 后才发出新的 AUTO.LOITER、ARM 和接管请求。

这不是异常恢复开关。意外控制进程退出、时钟回退、超时或状态失效仍失败退出；没有空中重启、自动重试或抢回控制。未来用户界面的运行中任意时刻 restart 操作不在本切片内。

## 接口与身份

| 接缝 | 类型/路径 | 约束 |
| --- | --- | --- |
| setup 输入 | `wksim_msgs/SetupRequest`，`/uav1/prometheus/v2/setup` | `version=1`、run_id、control_epoch、request_id、原 UAVSetup |
| command 输入 | `wksim_msgs/CommandRequest`，`/uav1/prometheus/v2/command` | 同样的外层身份、原 UAVCommand；MOVE command_id 仍须递增 |
| 状态输出 | `wksim_msgs/SessionState`，`/uav1/prometheus/v2/state` | run/epoch、序号、最后消费的请求号、native_generation、原状态与控制状态、源接收和发布时刻 |
| 事件 | 原 TextInfo，`/uav1/prometheus/text_info` | JSON 包含 version/run/epoch/request_id；异步 ACK、完成和撤销沿用发起操作的请求号 |
| 旧状态输出 | 原 `/state`、`/control_state` | 只读过渡输出；没有外层 run/epoch，不作为新任务的权威输入 |

run_id 是显式 1–64 位 ASCII 标识，vehicle_id 当前固定1。每个 ControlNode 进程产生32位不透明 epoch；客户端必须从当前状态获取，不得猜测。请求号是 uint64，从1开始，在同一 epoch 的 setup/command 两入口共同递增；后续语义拒绝也消费该号，重试须新号。错误版本、run 或 epoch 不会污染新会话的请求水位。

原 payload 的 header 使用 ROS 请求时钟并继续检查年龄、坐标 frame 和 command_id；它不是 FC 启动时间。收到包、原生接受、模式/动作完成分别报告。本地撤销仅停止后续输出并放弃本地等待，**不能撤回飞控已经接受的动作**。

任务只将本次等待请求的拒绝视为任务失败；旧请求、其他 run 和未由本任务发起的拒绝仍记录，但不能让新任务误判自身操作失败。真正的 `control_revoked` 始终会中止活动任务。计划重启时先保留地面证据供运行器核验，再清空旧状态并拒绝 retired epoch；观察到未计划的新 epoch 不会自动接管。

## 原生回执和时间

`RunSession` 在 `/tmp/wksim-control-<uid>/<run_id>--<vehicle_id>` 持有 Linux `flock`，目录0700、锁0600。同一身份不能有第二个控制节点。PX4每次原生命令发送前，将 source system/component 分配计数原子写入并 fsync；跨进程重启不复用。范围200–254 × 1–255，共14,025次原生操作；设定值流不计数，耗尽时拒绝，不循环。保留计数文件是正常行为，不能为重试删除它。

PX4回执必须匹配当前 source identity、command 和源时间，并满足 ACK 序号时间/进度不回退；IN_PROGRESS不算完成。ArduCopter服务保存精确 Future/client，取消时移除 pending request 并取消 Future；迟到旧回复不能完成新操作。真实字段与本地固件来源见[原生适配器契约](wksim-native-request-identity.md)。

源时间保留在 `state.header`，`source_clock=fc_boot`。`source_received_monotonic_s` 是该原生位置样本首次被接受时的 WSL 单调时钟；`published_monotonic_s` 是包装消息发布时刻。重复数据不能刷新接收年龄；源/样本/本地时钟回退会清空原生缓存并锁存失效，后来时间追上也不恢复旧缓存。源无效时不输出伪造姿态。PX4启动时可能先收到位置、尚无姿态；此时 assembled state 明确 connected=false、odom_valid=false、header为0，不能当作有效源样本。

这些机制是本机协作和重放隔离，不是网络认证或防恶意本机写入。原生状态没有应用 UUID，无法单靠首包证明全新适配器收到数据的历史来源；私有网络、同一持续运行的FC、公开会话身份和新鲜度共同限定本次实测边界。乱序包会保守触发失效，这不是任意网络条件下的恢复承诺。

## 验证入口

以下命令由协调者在隔离资源可用时执行。前两条使用正式 runtime、真实FC与物理；Task测试接缝仅注入明确标记的错误公共输入和一次记录过的PX4回执，观察器不代发原生飞行控制命令。

```bash
bash tools/run-control-restart-validation.sh arducopter /root/wksim-ros2-2egljG
bash tools/run-control-restart-validation.sh px4 /root/wksim-ros2-2egljG
bash tools/check-session-product.sh
```

结果保存在新建的 `validation/product-epoch-*` 与 `validation/session-product-checks-*`。ArduCopter的迟到服务回复测试使用真实本地RMW延迟服务器，不是改写真实FC的回复时间；实际飞行和进程重启另有证据。PX4已记录旧ACK在实际进程重启后被拒绝；旧ACK与新 pending 同命令的关联另由边界测试验证。完整命令、失败记录、清理和范围见[第二批报告](2026-09-05_product-second-wave-report.md)。
