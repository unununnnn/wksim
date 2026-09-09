# #97 · RC 输入合同 v1

本票冻结设计，实施归 #98 与 #99。依据 #38、2026-09-09 RC 接缝报告和已批准五项决策；用户本次明确授权确定输入合同。C2 真实 RC 执行必须在 C1 速度/混合轴验收之后；#12/#14/#6 及父票原验收继续有效。本合同新增的是 RC 输入服务参数，不改变物理误差、100ms 联合倍率、R1、RateUnmet 或 G0–G6 预算。

## 来源与实际边界

`Modules/uav_control/include/rc_input.h::handle_rc_data` 的执行代码决定通道顺序，不能使用其中 roll/pitch/yaw/thrust 注释替代实际映射。`Modules/uav_control/src/uav_controller.cpp::set_hover_pose_with_rc` 使用公共世界坐标积分，`px4_rc_cb` 保留已解锁/定位/OFFBOARD 前提；原 1.5s 断流检查被 sim_mode 豁免，迁移明确取消这项豁免。

实际 ROS2 文件是 `ros2/src/prometheus_control/prometheus_control/command.py` 与 `node.py`，不在 Simulator/wksim_control。`command.py` 现在提供了受校验 `Desired` 的 `set_rc_desired`/`clear_rc_desired` 共享接缝，RC step 可返回该目标并在解锁清除时归零；`node.py` 仍未接入 String 回调、GID 绑定、显式 RC setup 或原生交接，不能把这段接缝当作 RC 飞行支持。`session.py::RunSession` 负责 run/epoch、递增 setup/command ID 以及原生请求持久身份；RC 不替代或重置这些保护。AP 原生 position_yaw 默认关闭，能力必须由实际安装配置和原生反馈证明。

## 唯一软件来源与信封

选择 `wksim-software-rc-v1`：同一 WSL Linux boot、同一运行用户的单个软件产生进程，输出原始 PWM 微秒整数。产品模块负责归一化和积分；驱动不得发送预积分位置冒充 RC。首版不接键盘、游戏杆、真实接收机或跨主机输入。

拟用 `/uav{uav_id}/prometheus/v2/rc_input`，`std_msgs/String` 严格 JSON，volatile、KEEP_LAST=1、best-effort。此入口尚未实现。最大 UTF-8 4096 bytes；拒绝重复键、未知/缺失字段及 JSON NaN/Infinity。固定字段：

| 字段 | 合同 |
| --- | --- |
| version / source | 整数 1 / 字面量 wksim-software-rc-v1 |
| run_id / control_epoch / uav_id | 精确匹配当前 RunSession 与载具，格式沿用现有 session；epoch 为当前 32 位十六进制字符串 |
| boot_id / stream_id | 当前 Linux boot UUID / 每次启动全新 UUID hex32；废弃的 stream 不得重用 |
| sequence | 严格整数 1..2^64-1，严格递增，允许丢包产生间隙，禁止回绕；布尔值不是整数 |
| produced_monotonic_ns | 同 boot CLOCK_MONOTONIC 的正整数纳秒，严格递增，不接受未来值 |
| channels_us | 恰好八个严格整数，每项在闭区间 [1000,2000]，先全量校验再访问/更新 |

Control 从 callback 的 MessageInfo 绑定唯一发布者 GID，接收时间由 Control 本地采集，不能从载荷采信。启动清单记录 source 脚本/配置 SHA256、PID/starttime/argv、boot_id、run/uav/stream/GID。显式 setup 接管时绑定唯一新鲜候选；多个候选一律拒绝接管。绑定后其他 GID/stream/run/epoch 报文只记拒绝，不刷新当前流寿命、不切换所有者。此为本机所有权/重放隔离，不宣称远端认证。

## 通道与积分

对前四通道令 u=(PWM-1500)/500；|u|≤0.05 时 d=0，否则 d=sign(u)(|u|-0.05)/0.95。边界 1475、1525 均为零；1000/2000 精确得到 -1/+1。不钳位非法 PWM。

| 通道（1起算） | 执行意义 |
| --- | --- |
| 1 | y += -d1 × 1.5 m/s × dt |
| 2 | x += d2 × 1.5 m/s × dt |
| 3 | z = max(0.2m, z + d3 × 1.3 m/s × dt) |
| 4 | yaw += -d4 × 1.5 rad/s × dt |
| 5 | 必须 1000；arm/disarm 不支持，其他值拒绝整帧 |
| 6 | 仅 1000=释放、1500=RC 意图、2000=COMMAND 意图；不移植隐式拨杆沿接管 |
| 7、8 | 必须 1000；kill/LAND 不支持，其他值拒绝整帧 |

原重启手势 ch1<1100、ch2<1100、ch3<1100、ch4>1900 拒绝为 unsupported_reboot_gesture；不触发重启。解锁/上锁/降落继续通过既有显式安全 setup/任务路径处理。其他 RC/手动模式由父来源矩阵跟踪。

积分坐标是 CommandProcessor.local_position 对应的公共局部 ENU，沿用 offset，不随航向旋转 XY。yaw 保留连续积分值，输出适配层负责既有坐标表示转换。进入 RC 捕获一次新鲜实际位置和 yaw，首步 dt=0；首版只允许已在空中、z≥0.2m 的接管，起飞先用既有安全路径。回中维持最后积分目标，重复帧不重新捕获实际位置；物理到达和停止须另证。fence/定位/failsafe 检查继续作用，不借高度下限掩盖越界。

## 时钟、刷新、过期

源标称 50Hz（20ms），Control 沿用配置的输出节奏，不用输入帧数推算位移。单机场景使用现有 operation_time 时基；use_sim_time 场景使用权威 ROS/联合时间。每次有效推进用实际 dt，0<dt≤0.05s；同一时间 dt=0 不积分，时间回退或 dt>0.05s 撤权，禁止拆成补算步或追赶。回调仅缓存最新有效样本，积分使用该样本零阶保持。

独立接收 CLOCK_MONOTONIC 持续检查：接收时 0≤received-produced≤1.5s；每次积分前同时要求 now-produced≤1.5s 且 now-last_valid_receive≤1.5s。恰好 1.5s 有效，超过立即在下一服务 tick 撤权。非法/重复/倒序帧不延长寿命；来自当前绑定源的格式、范围或未来时间错误直接撤权。50Hz/0.05s 是此次输入设计值，1.5s 来自原源码；不以输入预算证明宿主倍率或物理精度。

暂停时不积分；从 running 离开进入 paused/stepping/resuming 即清空 RC 许可、杆量和积分时基。接收墙钟检查没有暂停豁免。单步、恢复时间或新帧均不能自动重启 RC；恢复 running 后需要新的 stream 和显式接管。现有联合暂停的原生保活如适用由其原合同负责，不能把缓存 RC 杆量当保活目标。

## 控制权交接与失效

状态为 UNBOUND → CANDIDATE → ACTIVE_RC，或 REVOKED。候选帧不产生控制输出。新鲜当前 epoch 的 SetupRequest SET_CONTROL_MODE=RC_POS_CONTROL 是唯一接管决定，必须消耗现有递增 request_id；同时要求唯一中位候选（前四 d=0、ch6=1500）、新鲜连接/定位、已解锁、确认 airborne、有效 home、native.ready_external、能力允许及实际 PX4 OFFBOARD/AP GUIDED。不能由模拟 RC 触发解锁、取消检查或暗中切原生模式。

COMMAND→RC 原子清掉旧任务引用、body_reference、shaper 状态和旧命令所有权，再捕获实际 pose/yaw。RC→COMMAND 需要当前流前四回中/ch6=2000 及新的显式 COMMAND_CONTROL setup，原生 external_mode 仍成立；捕获实际位置保持，新任务必须是交接后新 request_id 的命令。ch6 的 1500/2000 单独变化不接管、不重放任务；等待匹配 setup 期间只允许保持目标，不积分。ch6=1000 立即释放，进入 REVOKED。重复 setup 不重新捕获或重置积分；重复 request_id 仍被现有 session 拒绝。

断流、当前源非法帧、定位失效、外部模式切走、原生 generation/坐标原点变化、disarm、reset 或暂停：先撤销 RC 所有权，清空缓存/hover/时基/待交接动作，停止 RC 发布并复用 Node.revoke 的取消请求与事件机制。正常回中保持与输入失效明确不同；失效后不持续发送旧 hover，不自动要求回到 OFFBOARD/GUIDED。停止发送不保证飞控立即停止：AP 可能保留已受理目标，PX4 可能触发其自身失联策略。首次真实运行必须由 #99 的原生失效验证证明各栈最终行为，未证明前不得宣称安全悬停或降落。

重接需要新 stream、当前 epoch、新 setup ID 和全部准入条件；节点重启沿用现有新 epoch/持久原生请求计数规则。保存废弃 stream 与序号高水位到本 epoch 生命周期结束，不能通过 reset 接受旧流；新 epoch 拒绝旧 epoch。普通 RC 交接不重置全局 RunSession.last_request/native counter。

## 下一实现范围及验证交付

#98 仅按现票写 `Simulator/wksim_control/rc_input.py` 与 `validation/test_rc_input.py`：纯信封/流状态/死区/积分，不导入 ROS、不发原生消息。建议 API 为 validate_frame、bind、receive、step、revoke/reset；具体签名在实施测试中冻结，以上语义不得减少。

#99 实际接入前应落实以下至多四文件源码切片的归属：

1. `Simulator/wksim_control/rc_input.py`：复用 #98 纯信封模块。
2. `ros2/src/prometheus_control/prometheus_control/command.py`：RC Desired 与交接引用清理。
3. `ros2/src/prometheus_control/prometheus_control/node.py`：String RC 回调/GID绑定、setup/activate/drive/revoke 与暂停清理。
4. `validation/test_rc_control.py`（新）：假原生链的 host 集成/拒绝/交接测试。

使用已依赖的 std_msgs/String，避免为此修改消息 ABI。若安装包不能导入纯模块，必须在另一个明确归属切片解决安装准入；不能扩大本四文件范围或绕过安装 SHA 检查。两个 native 适配器、session.py、shaping.py 本切片只读；其能力若不足，另立实施前置。#99 现正文仅允许 integration 文档和证据，以上是设计保留范围，不自动授权修改其现票外文件；需要主代理落实实现子票后才可执行。

后续测试命令（尚未交付，不能报告已通过）：`python -m unittest validation.test_rc_input -v`；集成切片交付后 `python -m unittest validation.test_rc_control -v`。需覆盖八通道计数/类型/范围、死区等号及端点、四轴方向/速度、公共世界坐标、回中/高度下限、dt=0/0.05/越界/回退、时间1.5s边界、双新鲜度、重复/倒序/旧epoch/旧stream/错GID/多源、非法帧不续命、所有不支持开关、双向交接、外部模式切走、暂停/重置/原生重启、旧任务不重放和显式重新接管。

原始事件至少含 run/uav/epoch/stream/GID/sequence、source/receive/operation 时间、原始 PWM、归一化杆量、dt、积分前后目标、owner/setup ID、native generation/mode、受理或拒绝 reason。区分 rc_input_rejected、rc_input_expired、rc_takeover_rejected、native_mode_rejected、control_revoked、native publish 和物理反馈；接收/受理不是物理成功。#99 冻结驱动/配置/安装身份后分别交付一次 PX4 和 AP 的真实运行命令、原件及独立审计，验证移动/回中/偏航/断流/切走/新接管；本票无飞行命令或飞行通过结论。
