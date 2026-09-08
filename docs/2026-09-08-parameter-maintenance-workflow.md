# #43 原生参数维护与两次公开飞行实验入口

2026-09-08初始交付，2026-09-09主代理继续集成。新增 `tools/parameter_maintenance.py` 和 `tools/run-wksim-parameter-mission.sh`，复用现有 WriteProbe 的真实 AP RPC / PX4 UDP 参数通道、正式 runtime.run 与标准 Task。初始交付仅离线验证；主代理真实验收进展另记于本轮报告，本文流程说明不独立宣告 #43 或 Full 完成。初始代理实际 JSONL 的 gpt-6-astra / high 已由主代理核验，没有嵌套委派。

## 明确的用户流程

此命令会执行两次标准公开单航点飞行：设置参数 → 第一次飞行并落地 → 收尾旧 FC/物理/Control/Agent → 同一参数目录启动新 FC/物理/Control/Agent → 拒绝旧命令并独立回读参数 → 显式新任务再次飞行并落地。每次飞行都是现有 Task 的起飞、[2,3,3] ENU 单航点、持续到达核验和降落；参数读操作本身没有隐藏启动飞行的含义。

在 WSL Ubuntu-22.04 项目根目录调用，配置必须是既有 `independent_quad_dds_v1`、`session_v1` 的普通单机配置；不含 mission、display、telemetry、GCS、restart_control 或 promotion 字段：

```sh
bash tools/run-wksim-parameter-mission.sh --config "$CONFIG" \
  --run-id "$RUN_ID" --output-root "/root/wksim-parameter-$RUN_ID" \
  --value 3.1 --restore-original
```

示例 3.1 适用于 AP；PX4 选择 3、4 或5。目标必须显式传 `--value`，工具没有试验值默认值。AP `WP_SPD` 支持 [3,10] m/s、0.1 步；PX4 `MPC_XY_CRUISE` 支持 [3,5] m/s、整数步。也可用位置参数传配置，不能同时给位置参数与 `--config`。输出根必须是不存在、无符号链接的 `/root/wksim-*` 直属目录。省略 `--restore-original` 时，有意保留目标值，同时保留原值和 `pending_restore=true` 的明确说明。

wrapper 创建私有 net/ipc/mount namespace 和 `/dev/shm`，配置 profile 的 setup_files 按原顺序通过 bash 位置参数 source；所有路径都不是拼接的 shell 程序。runtime 继续负责私有 /tmp、资源预约、实际二进制/安装包/模型 pin、正式 preflight、物理耦合、健康与看门狗、任务和子进程清理。没有绕过任何准入，也没有修改 runtime/Task/协议/storage/既有 probe。

## 参数与 FC 生命周期证据

可复用配置为 `Simulator/wksim_runtime/examples/parameter-arducopter.json` 与 `parameter-px4.json`，对应本次实际输入。已完成的完整命令、身份、原始审计和失败样本见[收口报告](2026-09-09-parameter-maintenance-closure-report.md)。

创建新的 UUID ParameterStorage，AP/PX4 FC cwd 均为 lease.path，PX4 同时使用该目录的 `-w`；正常 runtime 让子进程继承 lease.fd。目录只属于这一笔实验，不复制、删除或重置原生参数文件。第一次运行输出在 `before/RUN_ID/`，第二次在 `after/RUN_ID/`，各保留完整 result.json。

第一次任务先等真实新鲜公开状态、原生来源、disarmed 和物理地面。GET 原值，并预先找到能无损映射原 float32 bits 的允许恢复请求；不存在此映射就零 SET 失败。SET 前先持久化 pending_restore 与 unknown，串行发送目标值，另发 GET 精确核对，再关闭全部额外参数客户端/socket，随后执行标准 Task。

只有第一次 result.status=pass、safe_landing=true、children_reaped=true、cleanup_errors=[] 且参数阶段和 Task 完成才继续。记录旧 FC PID/退出码、旧 control_epoch、实际 MOVE 信封与 CDR，关闭父 lease，重新打开同 UUID。重新打开前后核验存储目录、marker inode/hash，以及原生参数文件名称、inode、size、SHA256 完全一致。没有参数文件也失败。新 FC 必须是不同 PID，FC/Agent/模型/消息包/Control及 runtime 源身份必须前后相同；两个 runtime 均独立执行原准入。

after Task 在构造后首次 spin 前把旧 epoch 放入 retired_epochs，不能接受旧 SessionState。它等待新 epoch 的真实定位和地面状态，再取出before第一次实际以Publisher.publish(bytes)发送并保留的唯一MOVE CDR，校验长度/哈希并反序列化核对全部字段，然后原样发布这些字节。原run_id、旧epoch、request_id和payload header均不变，不调用会改写身份的Task.send，也不增加新请求号。初始实现重建后重新序列化，遇到CDR对齐填充差异导致AP第二轮失败；现已保留实际原始序列化出版物，未把字段相同冒充重新编码字节相同。必须观察当前epoch下精确 `wrong_run_or_control_epoch` 拒绝，且requested_run_id/requested_epoch/request_id对应原信封；否则有界失败，没有同义新目标兜底。

拒绝核验同时使用同一个 Task ROS node 的额外只读原生订阅：AP `/ap/cmd_gps_pose`、`/ap/cmd_vel`；PX4 `trajectory_setpoint`、`offboard_control_mode` 的实际版本主题由已安装 frames.topic 决定。每主题必须只有固定 `/prometheus_native_control` 发布者，图中的非零GID固定，RCL实际匹配数为1。等待拒绝后的完整至少1秒，持续核验地面新鲜度、固定发布者以及新的SessionState last_request_id=0，并要求原生样本计数为零。任何原生输出记录原文/CDR并失败，订阅随后销毁。

已直接检查当前已安装 ROS Humble：Subscription 没有 get_publisher_count，Executor._take_subscription 丢弃 MessageInfo，因此回调只接收 message。证据明确将 GID 标为唯一发布者图来源，不能声称逐包原生 GID。首轮真实AP重启未收到liveliness事件，10秒后如实失败；没有发布旧信封或进入第二次飞行。主代理随后接入已安装公共RCL API `rcl_subscription_get_publisher_count`，在受保护的真实subscription handle上读取实际匹配数，要求每主题恰好1，并持续核验唯一发布者图。liveliness仅保留辅助观察，不再作为必需事件。库/头文件/接缝源码哈希随原生窗口保存。真实隔离ROS正反测试证明：不兼容QoS发布者图计数1但匹配0；兼容发布者匹配1且收到实际样本；销毁后回到0。任何查询错误或匹配缺失仍失败，不能退化为只查图或应用事件。[匹配接口证据](2026-09-09-ros-subscription-match.md)。

完成旧信封拒绝后，新建串行参数操作只 GET 本次目标，不重新 SET；该读回与真实 FC 进程/存储重启共同构成此运行的持久性证据。关闭额外参数通道后，用新 epoch 和新信封显式执行第二次标准 Task。若指定恢复，只有第二次 Task 已完成并落地才设置 active=False、生成新 operation_id、重新确认当前 epoch/native_generation 的真实 ground authority，重新创建通道，先 GET 目标仍在，再 SET 原值，再独立 GET 精确确认。

AP SetParameters 的 successful/reason 只记 native_accepted/native_rejected，仍需独立 GET。PX4 PARAM_VALUE 没有 native request_id，仅记 observed；排空、固定 peer/sysid/component/name/type、单在途、关闭跨代通道不能创造强因果关联，也不构成 COMMAND_ACK。读取和持久化不能证明 WP_SPD/MPC_XY_CRUISE 已影响现有公开 Task 的实际速度。

## 结果、失败与验证边界

根 `parameter-maintenance.json` 保存实际配置、CLI值、事务UUID、源码SHA、原值/恢复请求、每阶段参数证据、两次完整运行结果、存储身份、进程退出与新 PID、epochs、原 MOVE、拒绝原文、原生GID/窗口/计数、持久性回读和可选恢复。每阶段另有 `parameter-maintenance.json` 和标准 `prometheus.jsonl`/truth/日志。成功时 current_value 是最近原生 GET 的观测值，附 last_readback 的时间和完整上下文；失败时 current_value=null，保留 last_readback 和 pending_restore，不将旧观测冒充当前已知值。

参数每次实际 RPC/UDP 发送前及回复后均复用 protocol.check_current，权限失效即永久作废该操作。响应上限10秒、无重试。未知写入/回读、epoch变更、地面状态失效、原生静默窗口不成立或未清理完成均停止后续步骤；没有 finally 自动补写、自动恢复默认或继续未落地场景的重启。失败运行保留证据和存储，后续处理要另做显式评估。

离线验证命令：

```sh
python3 -B -m unittest validation.test_wksim_parameter_maintenance -v
bash -n tools/run-wksim-parameter-mission.sh
```

8项离线测试覆盖before/after/restore分离且重启回读阶段零SET、非网格原值零写、unknown不自动补写、真实协议旧epoch永久失效、落地/清理门、FC身份门、真实fcntl lease重新打开和同字节替换inode拒绝、真实RunSession旧MOVE不消耗新请求号、失败before绝不第二次run，以及原生输出/新请求号消耗/缺拒绝/未匹配时失败。另有真实隔离FastDDS匹配与serialized publish测试。标准Task两次真实飞行、旧信封原字节拒绝、双栈FC重启持久性和恢复的主代理验收见[收口报告](2026-09-09-parameter-maintenance-closure-report.md)。
