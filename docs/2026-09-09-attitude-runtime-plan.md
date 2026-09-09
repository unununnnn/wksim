# #34 独立双栈姿态/推力运行接缝

2026-09-09。主代理核验当前会话 `01a08407-0ee9-7e11-9b96-b75432014f76`、agent_path、`gpt-6-astra/high` 后 RELEASE。本子代理先做只读调查，后获准只新增本计划、`Simulator/wksim_runtime/attitude_task.py` 和 `validation/test_attitude_task.py`，随后获准小型隔离 ROS 回环验证。没有启动飞控、物理模型或 GCS，没有更改现有 Control、runtime/preflight、正式 profile、pins、旧证据或 Issue。使用 ponytail 技能，无嵌套委派。

## 原票与最短路线

实际读取 [#34](https://github.com/unununnnn/wksim/issues/34)：要求明确四元数/推力契约、AP 候选实际构建/身份/运行、两栈固定姿态阶跃与恢复通过预先预算、非法输入拒绝、能力默认关闭、真实命令与结果及主代理复核。原票未要求同一联合场景或 0.5×。因此分别运行 AP 与 PX4、同一公开任务、各自独立物理时间线可以提供本票运行证据；不把它解释为 #20/G2 或联合倍率通过。

入口应是明确的 `tools` 姿态候选 runner，加一个窄候选准入函数；生产 `independent_quad_dds_v1` 继续保留其旧准入。`runtime.run(task_factory=...)` 只替换任务，`independent_profile.select_config/check_profile` 仍锁定旧资源及历史证据，`runtime.launch_spec` 也不会自动打开姿态开关。不能通过仅替换路径、伪造旧 preflight pass、改历史 catalog、猴子补丁全局 preflight 或假称仓库等于私有安装来放行本候选。

主代理负责新 runner/准入及 `tools/attitude_physics.py` 原始物理观察器；任务实现仅经公开 Prometheus 请求进行 hold/arm/takeoff/position/attitude/land。新 runner 可以复用 `runtime.launch_spec`、`stop_children`、isolation `Reservation/check_isolation`、`evidence.json_identity` 和 `run_joint_flight.record_native_maps` 的实际身份检查方式，但要明确记录其独立候选 scope，不能返回旧正式配置已经飞过的新固件结论。

## 必须绑定的候选身份

| 资源 | 精确候选 / SHA256 |
| --- | --- |
| AP build manifest | `/root/wksim-ap-attitude-hejigg76/attitude-build.json`；`bd8257094e6ab21034e7e6982835d833441d22582c0324b22fe8aa13fa0a4fe4` |
| AP 实际 binary | `build/sitl/bin/arducopter`；`c1a38947d65aafa7a9051a850df46d9fd67c8f0723833bf3508245c81ab7b1c0` |
| 私有 Control manifest | `/root/wksim-attitude-control-x3_2v4wb/attitude-control-build.json`；`95078a02b863b0307832ae9eb8aad6025a6dd0a88b34506983ae5e3cd43cf8d0` |
| 已封存离线验证 manifest | `/root/wksim-attitude-control-x3_2v4wb/attitude-control-verification.json`；SHA `4ed5331deac4a20b2fac59d0545df8e5de10ecf6535b4b6d485f94fea30c662c` |
| AP messages overlay | `/root/wksim-ap-attitude-msgs-qOmnF9fT`；按原生 manifest `overlay_hashes` 全量核验 |
| reviewed Control patch | `27224021ddd7f9f1c6078ff3708af76cb436acece33d9a4fb941955a33e63390` |
| frozen budget | `work/ap-attitude-stage-20260909/flight-budget.json`；`9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f` |

本子代理实际读取两份 WSL manifest 并重算 SHA，匹配上表；没有重新运行写入型 verifier。完整 native source snapshot、generated CDR、hwdef、binary、messages、构建日志/exit 和 Control staged/installed 全包需由 runner 在创建孩子前再次核验。`verify_attitude_control_candidate.py` 的 `main` 会新建 verification 目录并编译 harness，不应直接当只读准入调用；提取已存在的哈希检查思想，保留其 reviewed-patch→完整 OEv 基线的反向证明。

`joint_control_candidate.check/snapshot` 明确要求 repository=staged=installed，且只接受 `/root/wksim-joint-control-*`。本候选属于另一显式 reviewed-patch 证明链；不要放宽该原函数。新的准入须验证本候选整个私有源码包、已安装九个模块、patch、OEv 原基线、消息实际 import path，而不是要求这四个修改文件等于当前仓库。

运行前及落地后各保留 FC `/proc/<pid>/exe`、完整 maps、二进制 SHA；物理 worker 的模型库 maps 和实际库 SHA；绑定 PID/PGID/start_ticks、argv/cwd、namespace、run_id、control_epoch/native_generation、实际导入 Control 和消息路径。静态文件哈希不等于实际加载证明。AP 参数 defaults 文件也应入清单，保留 DDS defaults LAST 的原生动态参数约束。

## 时间与记录

既有独立 launch 默认 AP `--speedup 3`，PX4 `PX4_SIM_SPEED_FACTOR=3` 和 physics `--speedup 3`；新 runner 显式设 1。候选 Control `node.py` 的 `output_rate_hz=40` 通过墙钟节流，tick 是 10ms steady timer，因此它不是原生仿真时间每 25ms 严格输出保证。冻结 JSON 写了 `output_rate_hz:40`，没有最低样本率容差或联合倍率门。本实现不新增 40Hz 最低包率门，不将配置值当测量值；必须记录 native source stamp、接收时间与实际间隔，包括 timer 量化。

Task 使用独立 `truth.jsonl` 的物理秒安排 2s 标定、1s 姿态、0.5s 推力和 8s 恢复，另保留墙钟 watchdog；不使用独立 Task.wait 的墙钟来代替恢复 8 个物理秒。原模型 AP 1ms、PX4 4ms 步进都只约 50Hz 写 truth。主代理新观察器将记录完整每 1ms 输出和 native actuator 输入，并先证明 PX4 step4 与四次 step1 相等。旧降采样 truth 保留其真实格式供 Task 游标，不重标成联合 tick。

## Task 接口与输出

```python
AttitudeTask(directory, health, phase, flight_stack,
             run_id=run_id, protocol='session_v1', uav_id=1,
             use_sim_time=False, budget_path=budget_path)
```

两个栈各自独立 uav1。`report()['attitude_thrust']` 返回 status、budget_sha256、parameter_readback、public_request_graph、phases、calibration、thrust_velocity_increase_mps。阶段含 `physical_cursor(records, final_time, final_height_m)`、native_boot_s、观测 monotonic/Unix、公开状态和公开 command_id；`attitude-progress.json` 原子写入同一结构。`attitude-native.jsonl` 保留原始 DDS CDR（raw subscription，不重新序列化）、source/receive timestamps，以及收到的原始 MAVLink UDP datagram、解码结果和只读观测请求。本机 Humble raw executor 不提供 info；实际用独立、未加入 executor 的 recorder Node 手动 `subscription.handle.take_message(msg_type,True)`，明确每包 `per_message_publisher_gid_available=false`，不能补造packet-GID。publisher端点每0.5墙钟秒另读真实discovery记录，不等同每包归属。

本任务自己的 raw command/setup observer 是第二个 subscriber；就绪检查明确核验两端分别是 `wksim_attitude_raw_recorder` 和 `prometheus_native_control`、唯一非零 GID。不能仍使用原 Task.execute 的 subscription_count==1。原生姿态订阅以实际版本化 topic helper 生成 PX4 topic，AP 固定 `/ap/wksim/attitude_target_v1`；每次姿态命令等待本次公开受理后出现匹配 quaternion/thrust 的真实原生发布，记录物理游标。这个观察明确标为 receiver physical cursor，不是 native acceptance time；目标原生AP header stamp/PX4 timestamp也单独保留。这个观察是发布证据，不是飞控目标 ACK，不能用在线游标代替后续GUA/uORB+完整1ms对齐。

## 原生参数与悬停标定

Task 独占本场私有 namespace 的 14660(AP)/14661(PX4) 遥测接收端口；只接受实际 sysid241/AP 或 sysid22/PX4、component1、回环 peer。它发送 MAVLink `SET_MESSAGE_INTERVAL(ATTITUDE_TARGET,25000us)` 和 PX4 `PARAM_REQUEST_READ`，不发送解锁/模式/位置/姿态原生命令。参数读取只发生在公开/物理地面就绪期间，动作仍完全经 Task 公共入口。

AP `/ap/get_parameters` 使用真实 ROS client future，逐项读 `GUID_OPTIONS`、`GUID_TIMEOUT`、`ATC_ANGLE_BOOST`、`PILOT_THR_FILT`、`MOT_THST_EXPO`、`MOT_THST_HOVER`、`MOT_HOVER_LEARN`、`MOT_PWM_MIN/MAX`、`MOT_BAT_VOLT_MIN/MAX`。保留 request/response 字段及**明确标为本地序列化**的 CDR，不能将其称作抓包。要求读回 GUID_OPTIONS bit3 为真、GUID_TIMEOUT=3。runner 在独立 defaults 中按 baseline GUID_OPTIONS | 8 设置并封存原值/新值，保留其他位；任务不写参数。原 ParameterProtocol 只 allowlist WP_SPD/MPC_XY_CRUISE，故不借它扩大全局参数权限。

PX4 记录 MPC_THR_HOVER、MPC_USE_HTE、MPC_THR_MIN/MAX、THR_MDL_FAC 的真实 PARAM_VALUE 与原生类型；MAVLink 返回中的整数位编码必须由离线审计结合 param_type 解读，不能把 raw float 直接当整数语义。参数不存在或超时会有界失败，不用默认值补造读回。

悬停候选来自稳定位置保持期间连续 3 物理秒的实际 `ATTITUDE_TARGET.thrust` 中位数，两个栈分别计算，范围 0.15..0.8；不会用 PWM 平均或模型理论悬停值替代。固定 AP `GCS_MAVLink_Copter::send_attitude_target` 取 `attitude_control->get_throttle_in()`，与 CTUN.ThI 同源；PX4 `streams/ATTITUDE_TARGET.hpp` 取实际 uORB vehicle_attitude_setpoint 的 q_d 与 thrust_body norm。标定值、对应原始样本、实际 anchor/yaw 在阶跃前封存。

2s 水平直通按冻结 ±0.3m 垂直漂移 / ±0.2m/s 垂直速度检查；失败即整场失败且不进入阶跃。实际 entry yaw 被捕获，roll +5°，0.5s settling 后固定 0.4s 达标，余下 0.1s 保持命令凑满 1s；另做水平 hover+0.03 持续 0.5s，比较最后 0.1s 与阶跃前 0.2s 的上升速度均值。每次恢复使用真实 pre-step anchor 的完整 XYZ_POS+yaw，8 物理秒包含公开受理延迟，连续 1.5s 达到原冻结位置/速度/倾角/yaw门。Task 没有降低门槛或根据结果调 hover。

公开 UAVCommand.XYZ_ATT 的 att_ref 是 roll/pitch/yaw/thrust，并无 quaternion 字段。非单位四元数拒绝属于实际适配器/native入口边界，不能伪造公共 quaternion 工况。已经有 installed adapter 与真实函数体 stub harness 的离线证据；真实运行 guards（错误frame、零/未来/过期stamp、缺GUID_OPTIONS、非单位/非有限/越界）另需有界原生探针和无 GUA/目标时间更新证据。它们不应该夹在正常姿态流中由持续新目标掩盖无副作用判断。

## 复用审计与尚未完成

`audit_independent_velocity.py` 的请求顺序、原始公共事件、50Hz游标及物理时间处理可复用，但它硬编码13个请求、速度工况、旧生产准入和 repository=installed，不能原样给姿态场签 pass。`audit_pv_trajectory.py` 的 CDR解码/float32/angle helper 可复用；其 `audit_timeline` 和 `audit_mixed_control` 的双栈/uav2/联合整数tick/倍率部分不能搬成独立成功声明。新的审计须从每1ms模型原始输入/真值逐段重算预算，并验证 raw DDS公开命令→原生 quaternion/符号/thrust→实际 native日志→电机→真值。

AP `ModeGuided::set_angle` 实際保存 guided_angle_state.use_thrust/thrust/update_time_ms 并调用 `Log_Write_Guided_Attitude_Target`；原生日志含 submode、Euler目标、零body-rate、thrust、climb_rate。保留 BIN 全本和 GUA解码，结合 CTUN、实际PWM/模型输入验证，不把 native publish 当ACK。PX4 保留 ULog 原本、vehicle_attitude_setpoint/actual attitude/actuator轨迹及真实 ATTITUDE_TARGET 遥测。模型质量、旋翼、电池完整身份仍由 runner 提供，单独 Task 不替它认定。

姿态失败时停止发布新的姿态请求，尝试现有公共 LAND，始终保留原失败；飞控/Control失联可能令 LAND 失败，必须记录而不能强称 safe_landing。正常结束也要以公开 disarmed+原始物理地面、已回收子进程和空 cleanup_errors 验证。

本子代理已完成六个无 ROS/FC/model 测试方法：覆盖冻结预算哈希、NED/FRD→ENU/FLU物理读法、悬停需求中位数及缺失/非法数据拒绝、连续稳定重置但不重置deadline、恢复计入ACK延迟、物理时基和最后样本检查、禁止通过观测通道发送原生动作。`python -B -m unittest validation.test_attitude_task` 通过；这不是运行通过。

主代理随后指出现有Humble raw callback限制并释放小型ROS回环。复读 `tools/run_ap_mixed_timeout.py` FinalRecorder 实际代码后改为上述独立unspun记录器。真实私有 net/ipc/mnt namespace 中构造AP/PX4 Task、生成消息和明确fixture publisher，各栈验证两订阅者图、收到CDR与生成序列化逐字节相同、真实source/receive timestamp>0、没有伪造每包GID、四元数回变换正确。只有fixture truth，不启动FC或模型，不能当作真实姿态响应。

最终证据 `/root/wksim-attitude-loopback-trlmqlir/result.json`，SHA256 `7f3e5a684ac4e3679236f9f4f5695c776bc5881eb4c6e4a43ee67b69080fdef7`；内含实际candidate Control/AP messages/PX4 messages导入路径、Task源码 SHA `0d1738a15e4d193f4b9c25508a2c86f8ffd6681c2a316d08dff0fc633ea43efd`、测试源码 SHA `59166d09312acce25eec7468a522ab07d3c01d9f5ac51e2377cff47cd63bdd05` 和原始记录路径。回环进程已正常退出，两Task/两fixture/recorder节点均显式destroy，ROS shutdown，两个观测socket关闭。

初次 shell 环境拼接使 PYTHONPATH 未带 rclpy，在创建ROS前退出。首次实际回环 `/root/wksim-attitude-loopback-m9shapcm` 收到两栈原始记录后在结果JSON写入处发现PX4 numpy.float32不可序列化；原始目录保留，未标成功。改为明确Python float后 `/root/wksim-attitude-loopback-w3m9ry1l` 通过，再补充记录实际导入/source身份并在最终trlmqlir全量重跑。未把失败原始目录或前版成功改写为最终版证据。

发现路径遵守AGENTS：先读已知报告/source，结构未知先实读Codebase Memory status与independent符号导航再读实际源。状态为 ready、50,865 nodes/165,157 edges；非全面覆盖声明。新Task在本轮之后新增，未用旧图对其结构作断言，也没有不必要重索引。真实准入、runtime native guards、完整1ms原始审计、双栈标定及飞行仍由主任务完成；#34不因此关闭。
