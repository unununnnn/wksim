# 固定 ArduCopter JSON 时间与联合 barrier 源码研究

日期：2026-09-06。范围：AP 侧只读源码研究；不分析 PX4 实现、不运行飞控/UE/QGC、不构建、不更改配置。仅此文件为本次写入。结论是源码事实与试验契约建议，不是生产调度或失联策略决策。

## 来源与版本边界

实际读取 WSL Ubuntu-22.04 的 `/root/wksim-ap-dds-yaw-state-4Wr27s/src`，`git rev-parse HEAD` 返回 **1511f27194f1dcc3728270883047bdf022b3fd53**。SIM_JSON、Aircraft、HAL、scheduler 等本文引用文件无本地修改；DDS 文件及 ExternalControl 有本地修改，WksimState.msg/idl 为未跟踪扩展，不能用该 commit 的 GitHub 页面代替其证据。

研究技能已读取；其后台代理建议被用户“不得嵌套代理”覆盖，全程由本代理完成。接口不能读取或修改当前主会话模型/推理配置，故没有虚称验证 gpt-6-astra + low。外部 AP 源码不属于 wksim-prometheus 图覆盖，按 wksim/docs/codebase-memory.md 的外部源规则直接读取；WSL 无 rg，改用 grep/nl。未使用网络二手资料。已读上下文地图、wksim CONTEXT 和父项目 ADR0022；后者属于 AeroTwinSim 参考，不能自动成为 wksim 的验收决定。wksim/docs/adr 不存在。

本地关键文件 SHA256：

| 文件 | SHA256 |
|---|---|
| libraries/SITL/SIM_JSON.cpp | c6383cff7a95cdb3497931a83c2217b19e71607059c408149d8eba78b8118cbc |
| libraries/SITL/SIM_JSON.h | ba8f86c7a6602beff867e37260088a7dc03b6e4b6b67c06837512c877dc25c33 |
| libraries/AP_DDS/AP_DDS_Client.cpp（本地 patch） | e41fd119b40aac34d357b41f9588e04f5ea95b9a88ee0175968ec5341b6401c1 |
| Tools/ros2/ardupilot_msgs/msg/WksimState.msg（本地新增） | 83440d03dfaadca493297d49487a9b4317a2db59d4088d76d794494d36a1a81c |

以下 [代码编号] 对应末尾固定 commit 源码链接；DDS 本地证据另列绝对路径行号。

## 1. 发送、接收与序号事实

- 每次 JSON::update 先 output_servos，再 recv_fdm，再更新磁场/调整 rate。servo 包没有 sensor timestamp、epoch 或传感器序号回显。[JU][JO][H]
- 输出为内存结构直接 UDP sendto：uint16 magic、uint16 frame_rate、uint32 frame_count、16/32 个 uint16 PWM；magic 分别 18458/29569。在目标常规 little-endian ABI 下对应 40/72 字节、小端解码（这是 ABI 推断，源码没有字节序转换）。frame_rate 来自 float rate_hz 到 uint16 的转换；不是实测 FPS，也不是 SCHED_LOOP_RATE 的直接字段。[H][JO][A]
- JSON 自己的 frame_counter 仅在 recv_fdm 处理到末尾递增。Aircraft::sync_frame_time 另有同名父类计数器，不是 servo 包序号。因此 servo C+1 表示前一次 JSON 接收处理完成后又进入 update；不等于“控制主循环完成一次”或“传感器时间增加一次”。[H][JT][JU][A][LOOP][W]
- 等待的单次 socket poll 为 100ms 墙钟；wait_ms >1000 时重新发送当前 input 的 servo，frame_count 不变。注释写“10 second”，实现是约 1.1s 的无包等待累计，调度延迟另计。无最大重试次数。send 失败只打印；不存在可靠传输 ACK。[J][JO][SOCK]
- 默认 lockstep 下无包会一直留在 recv_fdm。收到不完整/无有效记录的正长度包可能提前 return 而不增加 frame_count；下次 update 仍发同序号。重复序号不一定只是超时重传。[J][JU]
- 接收缓冲把换行转 NUL，取最后两个 NUL 之间记录解析；同批多个完整记录只处理最后一条。首包必须具备前后分隔，建议一个 UDP datagram 为 LF + 完整 JSON + LF；不能只依赖末尾 LF。单次 recv 是一个 datagram，不会主动排空整个 UDP 队列；排队的旧 datagram 以后仍可能被处理。[J][SOCK]
- 必需 timestamp、imu.gyro、imu.accel_body、velocity，且必须 attitude/quaternion 至少一个；建议始终给 position。解析是字符串查找/数字转换而非严格 JSON schema 验证，数组失败可返回部分 bitmask；有效性不能只依赖 AP 兜底。[H]（另见 SIM_JSON.cpp:198–296、349–359。）

## 2. timestamp → 模型时间 → FC 时间

源码公式：

```text
if timestamp < last_timestamp: dt = 0, 打印 physics reset
else:                         dt = timestamp - last_timestamp
time_now_us += dt * 1e6
if 0 < dt < 0.1:
    if use_time_sync && !no_lockstep: adjust_frame_time(1 / dt)
    time_advance()
last_timestamp = timestamp
JSON.frame_counter++
```

以上由 [JT] 直接给出。time_now_us 是 uint64；浮点乘法/复合赋值发生整数转换，连续十进制秒差分可能损失微秒，不能未经测量宣称严格每帧 +1000us。time_advance 仅在模型时间没有比其上次调用变化时补 frame_time_us，并按 use_time_sync 做墙钟节流；正常正 1ms 输入已推进模型时间，不会再加第二次。[A][JT]（time_now_us 类型见 SIM_Aircraft.h:279。）

- **相同 timestamp**：dt=0，更新传感器状态并递增 JSON frame_count，但不调用 time_advance、不推进 time_now_us。这不是幂等重传确认：控制/传感器路径仍可被再次触发。[JT][J][S]
- **倒退 timestamp**：不回滚 AP 时间，dt=0，却把 last_timestamp 改成倒退后的值；下一正向包从新值差分。乱序包不能简单当无害丢弃，也不是 AP 自动重启。[JT]
- **大跳变 >=0.1s**：仍直接加时间，但跳过本次 time_advance/速率更新；不能把首包设置为 Unix epoch 或拿大跨度时间跳跃当单步。[JT]
- **首包**：JSON::create 用 NEW_NOTHROW，而该分配器 calloc；last_timestamp、time_now_us、frame_count 等初始为零，use_time_sync 默认 true，no_lockstep 默认 false。[H][NEW]（use_time_sync 见 SIM_Aircraft.h:294。）
- **零首包陷阱**：SITL 初始化 stop_clock(1)，但合法 timestamp=0 会保留模型时间0，fill_fdm 后 stop_clock(0)。AP_HAL::micros64 仅在 stopped clock 非零时返回虚拟时间；零值转用 CLOCK_MONOTONIC 墙钟。因此 timestamp=0 不能作为已冻结的起点。建议有界试验从正的1ms启动，并把启动段与测量段分开；这是推断/试验建议，不是修改源码。[INIT][F][S][HAL][JT]
- 模型返回后 fill_fdm.timestamp_us=time_now_us，SITL_State 再 stop_clock(timestamp_us)，HAL micros64/millis64 从该停止时钟取得时间。[F][S][STOP][HAL]
- **停发是否停 FC 时间**：在已建立非零虚拟时间、no_lockstep=false、没有排队/在途物理包、执行进入 recv_fdm 等待的条件下，当前主线程路径不再到达下一次 stop_clock，因此 AP HAL 虚拟时间停止；墙钟 socket 等待、其他线程/网络不因此停止。若停发时仍有已发 sensor 在队列，可先继续推进；不能把“停止 send 的墙钟瞬间”当冻结时刻。[J][S][W][HAL]
- **no_lockstep=true 明确不满足冻结**：初次 recv 超时/失败后，按 SIM loop_rate_hz（无可用值则10ms）增加 time_now_us 并调用 time_advance 返回；该路径没有增加 JSON frame_count。也就是说同序号甚至可能伴随 FC 时间推进。此模式仍先做100ms recv poll，并非完全非阻塞。[J]
- no_time_sync=true 将 use_time_sync 关闭，影响节流及调 rate，并默认设置 AHRS_EKF_TYPE=10；它与 no_lockstep 是独立开关，不应为了“外部权威时间”随意打开。来源：SIM_JSON.cpp:406–426、499–519；[A]。

## 3. SCHED_LOOP_RATE、--rate 与 --speedup

| 项 | 固定源码事实 | 对试验的含义（推断） |
|---|---|---|
| SCHED_LOOP_RATE | Copter 默认400Hz；启动时钳制50–2000，参数说明称>400高度实验；主循环等 INS 样本。[SCH][SCH2][LOOP][INS] | AP 每1ms JSON不意味着每1ms重新计算一次控制输出；400Hz目标周期2.5ms与4ms barrier也非整周期对齐。 |
| 飞控二进制 --rate | 写 SIM_RATE_HZ；SITL默认1200。[RATE][DEF] | 这是仿真 rate，不是改变主控制率；启动与有效参数须实际记录。这里不对 sim_vehicle.py 包装器同名选项作断言。 |
| frame_rate | 来自 rate_hz；正 dt<0.1 时先设1/dt，update末尾向 SIM_RATE_HZ 在 rate_hz±1 范围调整。[JO][JT][JU] | 1ms JSON且 SIM_RATE_HZ=1000 时应在1000附近；其他配置可出现999/1001等提示值，不能用它重新决定权威 tick。 |
| --speedup | 写 SIM_SPEEDUP；set_speedup→setup_frame_time 设置 target_speedup；墙钟目标间隔1e6/(rate_hz*target_speedup)。[RATE][A]，SIM_Aircraft.cpp:675–678 | 不乘 JSON timestamp 的 dt；改变节流目标，不保证实际实时倍速。模型/通信慢或 barrier 暂停都会拖慢墙钟进度。 |

不建议仅为对齐4ms就改 SCHED_LOOP_RATE；这属于主任务另行决定的控制配置。默认400Hz下1ms驱动物理可以提供时间采样，但不保证每1ms或每4ms都有新的控制计算；具体 IMU采样、主循环相位与控制输出完成需运行证据。[INS][LOOP][W]

## 4. 可读原生 FC 时间字段

| 观测 | 来源 | 限制 |
|---|---|---|
| 本地 WksimState.time_boot_us 与 header.stamp | 本地 AP_DDS_Client.cpp:54–63，直接 AP_HAL::micros64；WksimState.msg:1–5 | 同一 boot 时间、微秒精度表达；不是模型 tick ID。 |
| WksimState 发布 | 本地 AP_DDS_Client.cpp:1860、1962–1966：millis64 间隔>=20ms；Topic_Table.h:409–424：rt/ap/wksim/local_state_v1、BEST_EFFORT、KEEP_LAST depth5 | 最多约50Hz且受线程/传输影响，不能要求每4ms barrier都到一条。停时可能无新样本；沉默本身不能证明冻结。 |
| MAVLink SYSTEM_TIME.time_boot_ms | GCS_Common.cpp:2145–2155 用 AP_HAL::millis。[MAV] | time_unix_usec另取RTC，不能混为boot；毫秒分辨率、32位回绕。 |
| MAVLink ATTITUDE.time_boot_ms | GCS_Common.cpp:6073–6086 用 AP_HAL::millis。[ATT] | 发送时刻，非特定 sensor 包ACK；流频率未在本次运行验证。 |
| MAVLink LOCAL_POSITION_NED.time_boot_ms | GCS_Common.cpp:3039–3058 用 AP_HAL::millis。[POS] | 位置/速度 getter失败就不发；地面初始化阶段可能没有。 |
| DDS通用 Time、Clock | 本地 AP_DDS_Client.cpp:283–290 优先RTC，失败才boot；765–767 Clock复用此函数 | 不能假设 /clock 一直是 boot 或联合场景时间。 |

本地 patch 可读路径（均为 Ubuntu-22.04；GitHub固定commit不含这些修改）：

- `/root/wksim-ap-dds-yaw-state-4Wr27s/src/libraries/AP_DDS/AP_DDS_Client.cpp:54`、`:283`、`:765`、`:1860`、`:1962`。
- `/root/wksim-ap-dds-yaw-state-4Wr27s/src/libraries/AP_DDS/AP_DDS_Topic_Table.h:409`。
- `/root/wksim-ap-dds-yaw-state-4Wr27s/src/libraries/AP_DDS/AP_DDS_config.h:174`（扩展编译条件为 SITL && GPS）。
- `/root/wksim-ap-dds-yaw-state-4Wr27s/src/Tools/ros2/ardupilot_msgs/msg/WksimState.msg:1`。

## 5. 可交给主代理的地面有界接收/发送契约

本节是基于上述事实的**验证协议建议**，不替用户选择生产调度、重传或失联行为。

1. **初始化与身份**：固定源码/二进制/参数证据，记录实际 SCHED_LOOP_RATE、SIM_RATE_HZ、speedup；试验 JSON 明确 no_lockstep=false、no_time_sync=false。模型用整数 tick_us 权威计时；JSON 只在序列化时转秒。用独立会话/端口及源端点约束本地 run_epoch；AP servo 本身没有 epoch，端口复用的陈旧包需要隔离。回复实际收到 servo 的 UDP 源端点，因为 AP sendto/recv 使用同一socket，set_interface_ports不绑定port_in。[H][JO][SOCK]
2. **首握手**：先收到 servo C0，再回首个完整正时间 sensor（建议0.001s），等 C0+1。启动从这一小段建立 AP clock offset；不要把启动阶段的C0和控制就绪等同。物理初态如何映射第一个1ms由主模型定义并记录，不能凭空多积分一次。[JT][INIT][HAL][JU]
3. **每个正常1ms**：收到预期新序号 C，把其PWM记为该区间可用输出；模型只积分一次，到下一整数 tick，再发送对应唯一 sensor JSON。收到 C+1 可以作为上一包“已走完接收处理并进入下一次模型请求”的间接确认，但不是主控制器已完成新输出计算的证明。[JU][JT][S][W][LOOP]
4. **只允许一个待确认 sensor**：不要将4个AP JSON一口气发出；也不要在未来barrier之后预送。禁止使用frame_rate重新计算dt，禁止仅按servo数量增加权威时间。记录映射 `(run_epoch, C, model_tick, sensor_timestamp, wall_send, wall_recv, PWM摘要)`。[J][JT][JO]
5. **重复/丢包路径单列**：同C到来不得再次积分或分配新tick。暂停期间保持不回复该请求，容许AP周期性重发同C。未暂停且等待C+1时，同C可能是sensor丢失后的请求，也可能是迟到重传；直接重发缓存sensor虽能恢复丢失，但其副本若被AP再次处理会产生dt=0并递增序号。因此该原协议不能提供UDP故障下exactly-once。地面正常路径可将歧义记录为“本次验证未通过/无法确定”，重传容错另作有界故障试验；不要暗中把重复sensor当无副作用。[J][JT]
6. **共同4ms边界**：主代理负责PX4侧证据。在AP完成第4个1ms sensor的间接确认后，持有其下一请求，不再回复；同时等待主代理定义的PX4边界证据。只有两侧满足边界条件才允许主模型进入下一4ms窗口。持有的AP servo不增加tick。一次用户单步4ms应放行4次AP物理交换，PX4侧按其已验证4ms契约处理；不要在窗口内每1ms都等待只每4ms提供一次的PX4输出而造成互等。[JU][JT][W]；PX4频率在此仅为用户给定设计假设。
7. **区间执行器选择必须显式**：若PX4只在4ms边界给输出，期间四个1ms模型子步如何使用该输出（例如零阶保持）属于模型调度约定，不能把它叫作每1ms双FC新控制输出屏障。AP也可能在多个请求中保持相同PWM；相同数值不证明重复计算，也不能仅据数值拒收。[LOOP][INS][JO]
8. **暂停验证**：在边界收齐并停发之后，以单调墙钟设置有界观察窗口；记录同序号servo重传、无新model_tick、原生boot时间样本的最后值与新鲜度。对WksimState，4ms内无新样本为预期可能现象，不能为了等遥测而先放行下一tick再宣称停在原边界。恢复后的原生时间增量可佐证整段累计时间，但不能独立证明暂停期间每一瞬间均冻结。[J][HAL]及本地DDS:1962–1966。
9. **结果分层**：分别报告模型tick屏障、AP JSON接收屏障、原生HAL时间观测、控制输出计算完成证据；前两项通过不能自动标记后两项通过。所有等待/重传次数使用试验墙钟上限，不用已冻结的FC虚拟时间作为超时钟。[J][W][LOOP][HAL]

## 6. 成立条件、关键不足与未证实项

**源码支持的有限结论**：非零起点、默认lockstep、严格串行唯一传感器、无排队旧包时，AP可由1ms外部JSON驱动并在4ms边界等待下一包；停止外部推进会阻塞其下一次模型时间发布。这支持地面有界“物理输入/模型时间屏障”验证。[J][JT][S][HAL]

**不能由此推出**：

- 两FC在同一4ms边界都完成了一次新的控制计算：AP序号不是scheduler迭代ACK，400Hz并不整除250Hz。[LOOP][SCH][JU]
- 两FC原生boot时间逐微秒等于模型权威时间：启动偏移、AP浮点到整数转换尚需测量；PX4来源由主代理补齐。[JT][HAL]
- 任意UDP重复/丢失/乱序下仍严格一次推进：AP无sensor ID去重，重复时间递增序号，回退时间重设差分基点。[J][JT][H]
- 停止物理意味着整个进程、DDS/MAVLink墙钟行为停止；本文仅证明常规HAL虚拟时间主路径条件。[W][SOCK][HAL]
- 在不额外推进时间、不改飞控的情况下，现有50Hz WksimState能为每4ms屏障提供独立、即时原生时间ACK；本地发布门限直接不支持这一要求。

**待主代理实验补证**：实际运行二进制是否来自本源码与patch；有效参数/线程配置；首个正包后的clock offset；长序列1ms差分的微秒漂移；servo下一序号与控制计算相位；暂停后遥测缓存排空/可观测性；4ms单步重复多次的累计时间；在途sensor与迟到servo竞态；重复sensor/回退timestamp/丢包各自有界试验；PX4侧传感器ACK及barrier相位。此次没有启动进程或运行测试，以上均未证实。

生产实时倍速、暂停时任务超时处理、失联后保持/终止/重连策略仍留给主任务和用户决定。
 
## 固定源码索引

[J]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.cpp#L303-L381

[JT]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.cpp#L499-L521

[JU]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.cpp#L592-L608

[JO]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.cpp#L89-L136

[H]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.h#L35-L165

[A]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_Aircraft.cpp#L249-L325

[F]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_Aircraft.cpp#L373-L380

[S]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL_SITL/SITL_State.cpp#L207-L254

[W]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL_SITL/SITL_State.cpp#L118-L146

[HAL]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL_SITL/system.cpp#L163-L188

[STOP]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL_SITL/Scheduler.cpp#L301-L307

[INIT]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL_SITL/SITL_State.cpp#L78-L79

[NEW]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_Common/c++.cpp#L36-L46

[RATE]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL_SITL/SITL_cmdline.cpp#L408-L418

[SCH]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_Scheduler/AP_Scheduler.cpp#L43-L68

[SCH2]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_Scheduler/AP_Scheduler.cpp#L109-L121

[LOOP]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_Scheduler/AP_Scheduler.cpp#L348-L379

[INS]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_InertialSensor/AP_InertialSensor.cpp#L2013-L2061

[SOCK]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL/utility/Socket.cpp#L334-L385

[MAV]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/GCS_MAVLink/GCS_Common.cpp#L2145-L2155

[POS]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/GCS_MAVLink/GCS_Common.cpp#L3039-L3058

[ATT]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/GCS_MAVLink/GCS_Common.cpp#L6073-L6086

[DEF]: https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SITL.cpp#L46-L51

补充固定源码：[SIM_JSON 解析器](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.cpp#L198-L296)、[同步开关](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.cpp#L406-L426)、[Aircraft 字段](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_Aircraft.h#L279-L294)、[speedup 设置](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_Aircraft.cpp#L675-L678)。

