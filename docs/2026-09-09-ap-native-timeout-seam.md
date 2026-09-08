# #33 AP mixed 原生停流 / timeout / 后续接管接缝

2026-09-09。本文是有界实施设计，未执行新试飞、构建、测试、索引、固件/ROS修改、提交或工单操作。主代理核实实际子任务 session 为 `gpt-6-astra/high` 后 RELEASE；无嵌套代理。主代理的 mixed nominal 运行仍在原始逐 1ms 审计中，已发现短窗 tracking 越界，本文不将其称为完整审计 PASS。

建议新增**独立、显式标注为原生边界的实验 runner**：复用当前双模型 SceneClock / JointPhysics / 0.5×调度及固定资源核验，让 AP 由一个诊断 DDS 发布者完成 mixed 运动，再停止其目标发布；AP/PX4 物理、DDS Agent、原生状态和 `/clock` 持续推进。窗口结束后销毁诊断目标发布者，启动同一已封存控制安装的一个新 ControlNode 和新公共 Task，显式接管当前位置再降落。PX4 本实验保持 disarmed，只作为现有双模型时间基础设施的参与者；不报告本实验为双栈公共 mixed 任务验收。

这个选择省去新的单 AP 权威时钟/步进协议，也不要求旧 Task 在公共状态停流时忽略错误。若资源目标改成单 AP，必须另做单栈时钟/每 tick 证据接缝；不能把当前 JointPhysics 或 SceneClock 的双参与者合同改成可缺一方。

## 当前源码实际允许什么

仓库路径以 wksim 根为基准；AP 路径以 `/root/wksim-ap-mixed-fhuf05l9/src` 为基准。以下来自指定文件实读及少量接口字面量定位，不依赖旧图推断新代码；wksim 没有 `docs/adr/`。

| 实际入口 | 已确认的行为 / 复用界限 |
| --- | --- |
| `ArduCopter/mode_guided.cpp:668` | `set_vel_NE_pos_D_m` 完成有限值、home/origin/location/fence检查后才切模式、保存 Pz/Vxy/yaw，`update_time_ms=millis()`，并写 GUIP type 7；暂停时拒绝。 |
| 同文件 `:1049` | `vel_NE_pos_D_control_run` 在 `millis()-update_time_ms > get_timeout_ms()` 后清 V/A，保留 Pz；NE 走 velocity input，D 始终走 position input。yaw 是 ANGLE_RATE 时会切 HOLD，故 timeout 后不把原绝对 yaw 继续跟踪作为隐含合同。 |
| 同文件 `:1330`；`ArduCopter/Parameters.cpp:869` | timeout 为 `MAX(guided_timeout,0.1)*1000`，返回 uint32 毫秒；参数名 `GUID_TIMEOUT`，源码默认 3.0s。真实运行值必须从本场原生日志/参数证据确认，不能以默认代替。 |
| 同文件 `:54,961,1336` | `hold_position()` 改成 VelAccel 并清 V/A；native pause 在 mixed 时先调用它，再置 `_paused`。pause run 对 NE/D 都使用零速度；resume 只清 `_paused`。所以 timeout 保留 Pz 与 native pause/hold 的 Z 行为不同。 |
| `libraries/AP_DDS/AP_DDS_ExternalControl.cpp:13` | mixed 输入严格 `map`、frame 6、mask `0x9E3`；`velocity.linear.x/y` 是 ENU，转 NE 为 `(y,x)`；altitude 是 ABOVE_HOME，yaw ENU 转 `wrap_PI(pi/2-yaw)`。lat/lon/Vz/A失活。 |
| `ArduCopter/AP_ExternalControl_Copter.cpp:71` | `set_altitude_velocity_xy_and_yaw` 要求 armed+Guided，真实 ABOVE_HOME→ABOVE_ORIGIN 转换，再给 Guided `-altitude_above_origin_m`。Pz不是直接的负 home-relative高度。 |
| `libraries/AP_DDS/AP_DDS_Service_Table.h`、`AP_DDS_Client.cpp:975` | 实际服务表只有 arm、mode、prearm、takeoff、可选参数服务，**没有 DDS pause/resume 服务**。不可创造 `/ap/pause`、pause Bool 或给 ModeSwitch 添加 pause 字段。 |
| `tools/sitl_dds.py:51` | NativeDDS 已提供状态/原点订阅、arm/mode/takeoff服务客户端、异步 response检查、position/yaw发送、单节点pump。现有 pump 只构造完整位置目标，不能直接发送 mixed；其 `setpoint=None` 会停止目标发送并继续spin，但没有 mixed发送契约或原始CDR/GID证明。 |
| `tools/validate_sitl_physics.py:29` | 旧 runner 的 `--ap-dds-candidate` 只接受旧 yaw候选前缀；实验 manifest路径使用 clock候选且要求公共 session回归。不存在 mixed native-timeout选项；不能把mixed目录硬传入或关闭准入检查。其独立ap_json trace默认20tick采样，也不是逐1ms审计。 |
| `Simulator/wksim_core/joint.py:32`、`Simulator/wksim_runtime/scene_clock.py:13` | JointPhysics等待两个真实FC输入；SceneClock提交要求恰好AP/PX4两份同tick模型响应。复用这条实际物理时钟，不能冻结SceneClock后靠墙钟等待假称native timeout。 |
| `tools/run_joint_flight.py:291,510,578` | 已有物理健康检查、JointRate、ClockPublisher、模型/FC/Agent创建、每tick原始wire/truth和清理骨架。其默认健康检查把Control/Task意外退出视为失败，mixed CLI还明确排斥pause/dds-loss组合；不直接套现有参数制造停流。 |
| `Simulator/wksim_runtime/task.py:142,253,260,273` | 同一Task收到新ControlEpoch会锁错误；active状态超过2墙钟秒不新鲜或control_revoked也失败。Task关闭自身不会停止ControlNode持续发送已缓存mixed命令。不能仅关闭公共命令发布者来触发native timeout。 |
| `ros2/src/prometheus_control/prometheus_control/node.py:351,631` | revoke清processor/shaper和本地pending观察；destroy_node取消pending并关闭session。没有在shutdown强制发送hold。因此正常结束旧Control进程可以停止其目标流，但其最后原生目标仍在FC内。 |
| `Simulator/wksim_runtime/task.py:417` | `recover_then_land()` 要求从未发送过请求的新的session_v1 Task、use_sim_time、fresh状态、完整接管门槛；获取当前request高水位后公开SET_CONTROL_MODE，等待新鲜GUIDED/COMMAND_CONTROL，保持2s，再LAND、落地、地面LOITER。AP不享受PX4专用allow_native_hold路径。 |

服务调用应直接按实际ROS类型表达：`/ap/mode_switch` 为 `ardupilot_msgs/srv/ModeSwitch`，request `{mode:4}`进入GUIDED，`{mode:9}`为LAND；response的`status`和`curr_mode`同时记录，另以持续状态确认。`/ap/arm_motors` 的 `ArmMotors.Request(arm=True)` 使用正常checks，response为`result`。`/ap/experimental/takeoff` 的 `Takeoff.Request(alt=3.0)` response为`status`。诊断前半程可使用这些真实DDS服务，不称为公共Prometheus输入。后半程必须是公共Task经产品ControlNode执行。

目标为 `/ap/cmd_gps_pose` 的 `ardupilot_msgs/msg/GlobalPosition`：header.frame_id=`map`、当前共享ROS stamp、coordinate_frame=6、type_mask=2531、altitude有限、velocity.linear.x/y有限、yaw有限。完整 P 保持使用原adapter产生的 `0x9F8`。零目标、LAND、切模式或发送完整P都改变原生边界，不能出现在timeout观测窗口。

## 最小新增工作与既有资源复用

新增名称建议 `tools/run_ap_mixed_native_boundary.py` 与独立 `tools/audit_ap_mixed_native_boundary.py`，不是现有参数。runner/phase合同范围写为 `ap_mixed_native_timeout_v1`，原mixed profile仍为 `xy_velocity_z_position_yaw_v1`。不改生产profile/pin、公共Task、控制节点或封存飞控。

- 复用 `ap_mixed_candidate.admit`、`joint_control_candidate.check/control_environment`、runtime的 `launch_spec/digest/stop_children`，和运行器现有的源副本、manifest、加载映射、命名空间与owned process身份做法。`admit`会完整检查现有AP候选、控制安装和固定资源；本文只读manifest，没有执行这套验证。新runner还须把自己的源码/合同/审计器hash纳入运行清单。
- AP候选当前manifest记录binary SHA256 `509c60163b3fceb261d17ceb2d0814c10ec65846e5d8d6689375e3ee05ab731f`、source manifest SHA256 `347750d7fff400dda47e671597c1a34c031f71c06c9917dc214f7d16dd533fc9`、patch SHA256 `6a19feb1261a31cc9a3670a9bde9e26da9eb961f1ef92e1a7b54f504513a952f`。它仍是built-not-admitted/production_admitted=false的构建记录；不改其中历史flown字段，不把本次读取当作当前binary哈希或运行加载证明。
- 控制尾段复用主代理本轮最终核验的**同一显式control manifest与安装目录**，不重新构建、不回退默认安装；启动时再次检查实际import路径、Python文件哈希、消息覆盖层及启动参数。本文未获该最终manifest路径/hash，不替主代理猜测。
- 原生诊断节点宜窄封装NativeDDS现有服务/状态逻辑，并新增严格mixed target构造、显式停发/销毁publisher、状态源stamp进展、GID记录及错误门槛。不要实例化一个默默同时创建position publisher的“只读”NativeDDS再另建第二发布者。其现有ready只检测最近存在并不完整验证odom；起飞/切入条件还需WksimState有效性、home/origin和真实状态连续新鲜检查。
- 复用SceneClock、JointPhysics、worker、ClockPublisher、JointRate的原合同；两个FC、两个模型、两个Agent持续服务，仅AP在诊断前半程飞行。保留0.5×、900墙钟秒/180000tick总界及原倍率界；有限次数phase，任何异常失败留档。
- 原始记录器借用PVProbe的raw CDR做法，新增精确MessageInfo publisher GID/接收时间/原生源时间，并记录publisher发现集合。原PVProbe固定订阅两个公共请求，直接挂在标准Task旁会使其“恰好1个subscriber”门槛失败。最小方案：本诊断记录器持续录native/session/event，不订阅公共v2/setup和v2/command，公共尾段请求由Task.envelopes和Control事件留证。若要求公共请求也有独立raw CDR，则须单独实现严格两个具名endpoint检查的实验tail，完整保留原Task的freshness/revocation/身份门槛；不要放宽为subscriber_count>=1，也不要声称原recover_then_land可原样用PVProbe。
- `audit_joint_flight.audit_timeline(..., require_flight=False, require_ground=True)` 可复用时间线/真实模型输入校验；双公共任务成功及两机飞行门槛不适用于这个AP-only诊断。新增审计器负责AP高度/速度/timeout、目标静默/控制源交接、参数/GUIP/ORGN和公共尾段检查，明确列出未复用的验收。

## 拟冻结阶段

以下数字为实施前建议合同，未运行，不可在观察结果后悄悄调界。timeout时基以本场**最后原生受理目标的AP时间**为准，墙钟用于watchdog，共同tick用于物理审计。

1. **准入和预检**：独立net/ipc/mnt资源，固定二进制/安装/模型，原生时钟和home/origin有效，GUID_TIMEOUT、GUID_OPTIONS及AVOID/FENCE相关实际值留档。GUID_OPTIONS必须确认没有关闭所需NE稳定行为；不改参数制造停止能力。所有publisher和服务身份冻结。PX4始终disarmed。
2. **真实DDS起飞与mixed基线**：AP normal arm、GUIDED/takeoff到3m，原生状态和真值达到高度/速度界。发mixed Vxy=(0.8,0.4) ENU、Z=3m、yaw=0，按原mixed速度逐轴0.3m/s、高度0.5m、yaw0.15rad界连续3s。首段只是诊断准备，不复用nominal PASS。
3. **最终Z阶跃并停发**：保持已稳定Vxy，把最后目标Z改为6m，在有界短串（建议0.2仿真秒）后停发。以实际raw消息和GUIP type7确认新Pz至少受理一次；没有目标ACK不能把publish成功当受理。记录最后publish、最后raw接收、最后GUIP受理时间及对应tick。不继续发送mixed、零V、完整P、cmd_vel、mode/land请求。
4. **原生timeout观测**：两FC物理和原生DDS继续，SceneClock phase一直running。覆盖严格`>`边界及其后最多10仿真秒的停止准备；随后连续3s要求XY速度模长≤0.25m/s，Z目标误差≤0.5m，XY相对停止驻留起点漂移≤1m。timeout前速度必须显著非零；timeout后出现减速并最终满足上述界。**区别于当前位置Z保持的关键充分性条件**：进入timeout时真值高度距最后Z目标仍>0.75m，且之后向该目标继续移动并达界；如果已经到位，本场只能证明保高，不能证明停流后Z位置纠偏，应记为该子项inconclusive而不是PASS，也不事后拉远目标或改timeout。native期不要求原absolute yaw在timeout后保持同一角度，但始终有姿态/位置包络与时钟健康检查。
5. **明确交接**：确认diagnostic target publisher销毁、无未完成service、AP原生target stream保持静默后启动产品ControlNode；新ControlEpoch和session有独立记录。保持同一run_id/scene_epoch及不断前进的物理时间。新Task先接收启动后新鲜公开状态和新的epoch，记录一次性、匹配run/scene/epoch的显式start offer，然后调用未改动 `Task.recover_then_land()`。其公共接管重新捕获实际XYZ/yaw，发完整P保持，再公共LAND落地；不重播诊断mixed/旧任务命令。
6. **收尾与独立判定**：公共尾段和真值确认disarmed+ground；收口后才停止模型/FC/Agent。正常退出要求、剩余owned进程组、未拥有AP身份、源/构建hash复核沿用现有运行器。失败也收owned资源并保留所有证据，强制退出不能改判正常着陆或完整PASS。

Z=6m阶跃配默认3s timeout是否满足“timeout时仍>0.75m误差”是尚未验证的物理可辨识性风险，应在首次真实结果中明确检验。首次若不足，只能保留结果并预先另立后续参数合同；不得用相同恒高轨迹宣称证明了持续Z纠偏。围栏/模型包络需在开飞前确认6m目标安全且可受理。

原生日志必须用本场实际GUIP名称/字段，不预设GUID别名。GUIP在setter写入，不是每tick执行日志；timeout run未写新的GUIP零速度记录，故“没有timeout后的GUIP零值”不直接判失败。以最后type7+Pz、没有新target、原生时间跨越阈值、实际速度下降和Z继续闭环组成证据。若使用PSC或只读`POSITION_TARGET_LOCAL_NED`观察内部目标，需要固定原生日志schema/采样与模式，不能把估计位置当期望目标。type7的pX/pY/Vz/A零仅为失活占位；Pz结合ORGN与本场home高度核算，origin/home改变或reset须失败或另列边界。

## 若必须从公共mixed阶段退出旧控制

可在另一个明确scope的runner中，用原公共Task完成mixed准备，然后通过**新增实验协议**先让旧Task保存`retired_for_native_timeout`结果并正常关闭，再正常TERM本场旧ControlNode并验证退出0；只把这两个精准PID标为expected exit，其他process-health门槛不动。最后一个已受理原生目标以GUIP时间为准，不能用发送TERM的墙钟为timeout起点。物理、Agent和被动记录器始终继续。旧Task退出不应记录task PASS/mission complete，旧Control关闭不应记录native hold完成。

随后启动同一控制安装的新进程并确认ControlEpoch与旧epoch不同，再创建新Task按上述显式offer接管/降落。不要调用`restart_on_ground()`（仅地面允许），不要让旧Task清error/清epoch重新接收，不要改on_control_revoked，不要添加“native timeout期间fresh=True”，不要借scene pause/SceneLease宽限冻结物理。此选项比纯native前半程多一套Task退休协议和父supervisor预期退出处理；当前runner没有此接口，不能直接靠现有task_mode=recover复用（它绑定scene_lifecycle/recovery-go许可）。

这个变体能证明“公共控制进程终止后原生mixed timeout，以及新的公共接管”，仍不等于产品支持任意空中Control热重启或完整恢复流程。建议先做前述独立native边界，再决定是否需要这一额外公开链证据。

## native pause的单独边界

实际 `ArduCopter/GCS_MAVLink_Copter.cpp:523,854` 有 `MAV_CMD_DO_PAUSE_CONTINUE` 的 `mavlink_command_int_t` handler：`(uint8_t)param1==0`调用当前flightmode.pause，`==1`调用resume，成功返回ACCEPTED，失败FAILED，其他值DENIED。这是已实读的原生MAVLink控制入口，**不是DDS服务**。本文没有验证端到端序列化、所有公共参数检查或可用遥测link，也未调用它。

若另做native pause实飞，必须单列“原生DDS目标+显式MAVLink pause命令”诊断scope，先核对该版本command-int wire与ACK来源，保留command/ACK原始字节；不要把现有telemetry-only link静默升级成控制fallback。停流timeout实验不需要也不应加入pause命令。pause/resume应验证mixed转VelAccel、paused中mixed拒绝、resume后无旧目标重播、新目标才重入type7；pause时Z零速度与timeout时保留Pz必须分别报告。没有DDS pause服务是当前可用接口边界，不必为了首个timeout场新增固件/IDL。

## 未完成与限制

本报告未读取主代理仍在更新的整场日志或其最终控制manifest，不提供真实参数值、GUIP/ORGN解析结果或native timeout成功结论。新runner、新审计器、phase metadata、publisher归属检查、公共尾段身份offer均尚未实现；原生pause的端到端调用另有接口验证前置。nominal逐1ms tracking失败必须独立解决或保留失败，native-only成功不能覆盖它，也不能关闭#33的全部组合/异常/正式准入要求。
