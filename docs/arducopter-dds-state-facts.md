# 固定 ArduCopter 原生 DDS 状态语义事实核对

核对日期：2026-09-05。按 research 技能执行的 AI 辅助只读源码研究；所有事实来自本机一级来源，没有使用公开网页、运行飞控/DDS Agent、调用 ROS 服务或修改 Issue。

结论：这个 pin 的原生 DDS **不足以证明“定位可用于飞行控制”的 `odom_valid=true`**。`pose/filtered` 是相对 **home** 的 ENU 数值，`gps_global_origin/filtered` 是 AHRS 暴露的 EKF origin，两者不能互换。header 时间在 SITL 正常模拟 GPS 路径中是带 UTC 起点的仿真进度；不能直接用宿主墙钟减它判定超时。依据见下文。

## 1. 核对范围与版本

仅检查以下两个授权目录内的源码、消息定义及已有构建头文件：

- A：`/root/wksim-ap-dds-yaw-mVgItN/src`，HEAD = `1511f27194f1dcc3728270883047bdf022b3fd53`。
- B：`/root/wksim-dds-VxM6Ni`；B 本身不是 Git 仓库，`B/src/ardupilot` 的 HEAD 同为上述 pin，检查时工作树干净。
- A 已有四个用户补丁文件：`ArduCopter/AP_ExternalControl_Copter.cpp/.h`、`libraries/AP_DDS/AP_DDS_ExternalControl.cpp`、`libraries/AP_ExternalControl/AP_ExternalControl.h`。读取实际 diff 确认为位置+yaw控制补丁，未改状态发布器。本次保留全部修改。
- 通过 `wsl.exe --distribution Ubuntu-22.04 --exec` 读取；WSL 未安装 `rg`，后续采用 `grep/find/nl/sed`。外部源码不属于 wksim Codebase Memory 覆盖范围，未查询/更新索引。

只读版本检查：`git --no-optional-locks rev-parse HEAD`、`status --short`、`diff`、`sha256sum`。A/B 的 `AP_DDS_Client.cpp` 哈希相同；A、B 源码和 B 安装目录中的 `Status.msg` 哈希也相同：

| 实际文件 | SHA-256 |
| --- | --- |
| A 与 B/src/ardupilot 的 libraries/AP_DDS/AP_DDS_Client.cpp | `16778480542da19bf12a746d755f29217b48f52f43f142bbb89231cb5958c432` |
| 两份源码及 B/ros-install/ardupilot_msgs/share/ardupilot_msgs/msg/Status.msg | `0a1f24b32dc1ca6211767b9ce725f5565c80447cbe8775993a88e9857a93d98b` |

下面链接指向 Ubuntu-22.04 的实际文件，行号均为本次读取版本。B 安装消息可直接查看 [Status.msg:16][installedstatus]。源码结论不等于已证明当前运行二进制、运行参数或 ROS 图的状态。

## 2. 最小可用状态映射

以下“建议映射”是给适配层的语义约束，没有实现适配器。所有历史值都须附带接收新鲜度；未知不等同于已观测故障。

| 适配层状态 | 原生输入及建议映射 | 能证明的范围 / 限制 |
| --- | --- | --- |
| armed、mode、flying | `/ap/status` 对应字段；保留 vehicle_type | 分别取 soft-armed、vehicle mode、get_likely_flying；flying 是飞控报告，不能扩展成定位有效性。[DDS:707][status] |
| EKF failsafe | 新鲜 status 的 `failsafe` 包含 `FS_EKF=24` | 可以报告“已观测到 EKF failsafe”；不包含只能表示此快照未报告该告警。[Status.msg:23][statusmsg]、[DDS:729][status] |
| ekf_healthy、position_valid、odom_valid | `unknown / unsupported_by_native_dds` | 没有直接有效性字段或专用查询服务。若产品接口只能用 bool，建议未证实时置 false 并附 unknown 原因；这是保守适配策略，不能伪称飞控报告了 false。[话题表][topics]、[服务表][services] |
| GPS fix 观测 | 每个接收器分别保存 navsat 的 `status.status`、covariance、接收时间；`fresh && status>=0` 仅表示“最近收到有 fix 的 GPS 报告” | 不能证明 3D fix、RTK fixed、EKF 使用该 GPS 或 EKF GPS-quality-good；见第 3 节。[DDS:211][navsat] |
| pose 数值 | `/ap/pose/filtered`：ENU、米、相对当前 home | 只提供观测数值；有限值、单位四元数、新 stamp 都不能证明对应估计有效。[DDS:413][pose] |
| velocity 数值 | `/ap/twist/filtered`：linear 是地理 ENU，angular 是机体 FLU | linear 读取失败会保留旧值；同一消息的线速度、角速度不是同一坐标表达。[DDS:464][twist] |
| home / EKF origin | home 坐标及 home-valid 保持 unknown；origin 保存为“所报告的 origin 样本” | DDS 没有 home 输出，也没有 origin-valid/reset revision；不能把收到 origin 消息当作初始化成功。[DDS:687][origin]、[话题表][topics] |
| external_control | 不用该字段决定有效性或外部控制准入 | 此 pin 明确赋值 `true`，带待实现注释。[DDS:716][status] |
| prearm_check | 只保留调用时的综合 pre-arm 结果（本次未调用） | 已 armed 直接 true；检查还依赖模式、围栏、检查配置。不能用作飞行中的定位健康查询。[DDS:997][prearmdds]、[Copter arming:17][prearm]、[mandatory position:443][prearmpos] |
| connected / lost | 建议定义为“目标遥测流新鲜 / 超时 / 尚未观测”，使用本机单调接收时间 | 没有发布给 ROS 的 FC connected 布尔值；时间推进及周期报文只能支持可观测流活性，不能证明估计器活性。具体算法见第 5 节。[DDS main loop:1263][ping] |

## 3. 有效性与 GPS 健康的事实边界

**接口覆盖。** 本 pin 的 DDS 话题表和服务表已完整检查。服务包含 arm、mode switch、prearm、takeoff、get/set parameters；没有独立 EKF health、position-valid、home 或 reset 查询。飞控内部有 `ATTITUDE_VALID/HORIZ_VEL/VERT_VEL/HORIZ_POS_REL/HORIZ_POS_ABS/VERT_POS/CONST_POS_MODE/USING_GPS/GPS_GLITCHING/GPS_QUALITY_GOOD/DEAD_RECKONING` 等位，但本 DDS 消息并未输出这些位。参数查询实现使用 AP_Param::find() 并返回参数值，不能等价读取这些运行状态。[话题表:17][topics]、[服务表:4][services]、[NavFilterStatusBit:26][filterbits]、[AHRS get_filter_status:2464][ahrsfilter]、[参数查询:1135][getparams]

**新 pose 不等于新有效估计。** DDS 先更新 stamp，再尝试读取位置；失败时不清除位置、不附 invalid 标志，更新循环仍发送这份消息。四元数读取失败则填单位四元数。twist 的 linear、geopose 的位置和 origin 也会在读取失败时保留原有数据，同时得到新 stamp。即使 AHRS `get_location()` 返回成功，EKF3 的 `getLLH()` 路径也允许回退到 raw GPS，并明确要求飞行控制另查 filter status。[DDS pose:413][pose]、[twist:464][twist]、[geopose:569][geopose]、[origin:687][origin]、[发布循环:1802][update]、[AHRS LLA:871][ahrslla]、[EKF3 LLA:330][ekflla]

**FS_EKF 不是健康位的反值。** DDS 读取的是 `AP_Notify::flags.failsafe_ekf`。Copter 在 origin 未就绪、EKF 检查关闭、检查从未通过时有提前返回；失败还经过计数门槛。触发函数先设置内部 `failsafe.ekf`，未解锁时返回，之后才置通知位。因此“没有 FS_EKF”甚至不等价于“内部 failsafe.ekf=false”，更不能等价于 position-valid。Copter 的 `position_ok()` 会另外检查内部 failsafe 及绝对/相对位置能力。[DDS:729][status]、[EKF check:30][ekfcheck]、[failsafe event:165][ekfnotify]、[position_ok:220][positionok]

status 的变化检测比较 `failsafe_size`，没有比较数组元素；若告警替换但数量相同、其他字段不变，可能等到周期刷新才发布新内容。源码意图是无变化约 2 Hz 刷新，不是完整告警事件日志。[DDS:735][status]

**GPS 可用字段与退化。**

- `/ap/navsat` 发布每个实例，`header.frame_id` 写入十进制实例号；不是“主 GPS”标志。DDS 先要求 `gps.is_healthy(instance)`，再要求该实例的 `last_fix_time_ms` 改变。内部 healthy 检查时序和驱动状态；该 bool 本身没有被序列化。[DDS:218][navsat]、[GPS healthy:1789][gpshealthy]
- unhealthy 分支虽然给内存中的 status 写 -1，却返回 false；外层只在返回 true 时发送，所以消费者未必收到 NO_FIX。GPS 的 last-fix 时间仅在 status>=2D 且未 force-disable 时更新；实际丢 fix 后可能表现为停更。必须按实例判 stale，不能无限保留最后一次 FIX。[DDS:220][navsat]、[DDS publish:1784][update]、[GPS fix timing:940][gpsfix]
- 数值映射是 2D/3D→0，DGPS→1，RTK float/fixed→2。IDL 定义 0=FIX、1=SBAS、2=GBAS；代码值 2 旁的 SBAS 注释不正确，不能沿用。该压缩映射丢失了 2D/3D、float/fixed 区别；`service=1` 也是当前固定 GPS 值，源码留有其他星座的 TODO。[DDS:238][navsat]、[NavSatStatus.idl:8][navsatstatus]
- covariance 与 covariance_type 来自 GPS 接口，不是 EKF 位置协方差；UNKNOWN 或零值不能解释为误差为零。NavSatFix schema 不含卫星数、HDOP、EKF fusion/quality 位。[DDS:281][navsat]、[NavSatFix.idl:23][navsatidl]

## 4. ENU 原点、高度与变更可见性

**pose 的准确参照。** 调用链为：

`DDS PoseStamped → ahrs.get_relative_position_NED_home() → home.get_distance_NED(ahrs.get_location()) → (E,N,-D)`。

只有 home 已设置且 get_location 成功才更新位置。`Location::get_distance_NED()` 使用经纬度差的局部距离近似，并直接相减两个 `Location.alt`，没有在该函数中转换高度 frame。因此本消息是以 home 为参照的地理位置结果，并非直接搬运 EKF 相对 origin 的内部 position 状态。[DDS:433][pose]、[AHRS:1839][ahrsposition]、[Location:425][locationmath]

在该次成功调用中：

```text
pose.x = 从 home 到当前 AHRS Location 的 East 距离（米）
pose.y = 从 home 到当前 AHRS Location 的 North 距离（米）
pose.z = (当前 Location.alt - home.alt) × 0.01
```

home setter 将 home 转为 ABSOLUTE；EKF3 正常 LLA 路径也构造 ABSOLUTE altitude。不过 DDS pose、geopose、origin 的 `header.frame_id` 均写 `base_link`，这个字符串与上述地理 ENU 数值参照不一致；适配层不可据此把位置当成机体坐标或用机体 yaw 再旋转。[AHRS home:3041][ahrshome]、[EKF3 LLA:334][ekflla]、[DDS pose][pose]、[geopose][geopose]、[origin][origin]、[Frames:3][frames]

**home 与 gps_global_origin 不保证相等。** DDS origin 来自 `ahrs.get_origin()`，不调用 `get_home()`。home 的首次初始化通常取当前估计位置；未锁定 home 在 arming 时会重新设置。飞行中首次建立 home 的特殊分支取当前水平位置、复制 EKF origin 的高度——该分支只对齐高度，不能推出经纬度也一致。[DDS origin:695][origin]、[Copter home:4][commands]、[arming home:724][armhome]

因此不能用 `origin.altitude + pose.z` 一般性恢复绝对高度，也不能把 pose 的 ENU 偏移直接叠加到 EKF origin 经纬度。即使某次 home 与 origin 恰好相等，经纬度量化/局部距离转换也不保证与 EKF 内部 NED 数值逐位一致。用 geopose 与 pose 反算 home 只能作为条件推导：要求两份数据都成功更新、同一状态时刻及相同高度基准；当前消息未提供这组联合保证。[Location:425][locationmath]、[DDS 各话题独立读取][pose]、[geopose][geopose]、[update][update]

**高度 datum 不能仅凭消息名称确定。** GeoPoint/NavSatFix 的 IDL 写的是 WGS84 椭球高；DDS 实际复制 `Location.alt`（navsat 仅转换到 ABSOLUTE），geopose 源码还留有高度 frame 假设 TODO。GPS 后端的 canonical altitude 默认 AMSL；启用 HeightEllipsoid 且有 undulation 时才改用椭球高。此调查没有读取运行中的参数，不能证明实际高度基准已符合 ROS 椭球高约定，也不能把 local z 当海拔或 AGL。[GeoPoint.idl:24][geopointidl]、[NavSatFix.idl:49][navsatidl]、[DDS navsat:272][navsat]、[DDS geopose:577][geopose]、[GPS altitude:450][gpsalt]、[GPS option:248][gpsaltparam]

**飞行中 home 变更。** mission 的 DO_SET_HOME 与 GCS home handler 都能调用 setter；Copter setter 本身没有“已 armed 禁止变更”的条件。AHRS 成功设置 home 后安排的是 MAVLink HOME/ORIGIN 报告及本地日志/存储；DDS 表没有对应 home/变更事件。下一次 pose 成功更新会使用新的 home，可能平移/改变 z，而 gps_global_origin 可以完全不变。[Mission:2012][missionhome]、[GCS:5501][gcshome]、[Copter setter:58][commands]、[AHRS setter:3041][ahrshome]、[DDS 表][topics]

**估计器 reset。** AHRS 内部确有返回最近 reset 时间和 delta 的 `getLastYawResetAngle`、`getLastPosNorthEastReset`、`getLastPosDownReset`。原生 DDS 没有输出这些时间/delta，也没有 reset counter 或重定位事件；Header 只有 stamp/frame_id。不能从一次 pose/orientation 跳变区分真实运动、home 改变、GPS 回退、估计器 reset，也不能从“没跳变”证明没 reset。[AHRS yaw reset:2804][yawreset]、[NE reset:2837][nereset]、[D reset:2904][dreset]、[DDS 表][topics]、[Header:13][header]

origin 也不是 reset 序号：EKF3 的公开 origin 高度可受 `_originHgtMode` 与 `ekfGpsRefHgt` 修正影响；AHRS 更新缓存 origin，DDS 约每秒复制其数值。高度变化可被观察，但没有事件原因/版本，未必与某次 reset 一一对应。单独的 `resetHeightDatum()` 路径只允许在地面、非 rangefinder 高度源时执行，会改变高度状态及 origin；不要把这个地面 datum 操作泛化成飞行中所有 reset。[EKF3 origin:413][ekforigin]、[高度修正:831][heightcorrect]、[AHRS origin cache:427][originstate]、[cached getter:3735][originget]、[DDS origin][origin]、[height datum reset:365][heightreset]

此外，`AP_DDS_External_Odom.cpp` 的 `reset_counter=0` 是接收外部 TF 后传给视觉里程计的输入处理，不是原生 EKF reset 状态输出。[External Odom:11][extodom]

## 5. 时间戳与连接/丢失判据

**实际时间公式。** 所有上述 outgoing header stamp 通过同一个 `update_topic(Time&)` 填充：

```text
RTC 已建立：stamp_us = AP_HAL::micros64() + rtc_shift
RTC 未建立：stamp_us = AP_HAL::micros64()
sec = stamp_us / 1_000_000
nanosec = (stamp_us % 1_000_000) × 1_000
```

RTC shift 来自获准时间源；源码拒绝使 shift 倒退的更新时间，首次 RTC 建立或时间校正仍可产生向前跳变。`/ap/time` 与 `/ap/clock` 使用同一取时实现；后者只是把该 Time 放入 Clock，并不额外输出“时间源/epoch 已同步”标志。[DDS time:197][time]、[RTC:47][rtc]、[Clock:679][clock]、[DDS topic names:280][qosclock]

SITL 启动时设置非零 stopped clock，后续将其更新为仿真 `state.timestamp_us`；HAL micros64 优先返回它，只在未设置 stopped clock 时回退到宿主单调计时。模拟 GPS 用 `start_time_UTC + HAL 仿真进度` 构造时间；3D GPS 时间可设置 RTC。默认 start_time_UTC 取启动时宿主墙钟，也允许启动参数覆盖。因此正常 SITL/GPS 路径具有 **UTC epoch 外形、仿真推进速率**；既非持续宿主墙钟，也非保证从零开始的仿真秒数。[SITL start:78][simstart]、[SITL step:249][simclock]、[HAL clock:173][halclock]、[GPS time:252][gpstime]、[GPS→RTC:997][rtcfeed]、[UTC 起点:263][startutc]、[起点覆盖:529][startoverride]

这些 stamp 是 DDS 填充消息时取的时间，不能替代传感器原始采样时间或 EKF 最后一次有效更新时间；尤其失败后重发旧位置仍有新 stamp。源码也不能证明它与自主仿真核心/UE/ROS 消费者使用同一权威时间线。[DDS pose][pose]、[navsat][navsat]、[geopose][geopose]、[origin][origin]

**源码默认发布门槛与 QoS。** 下表是宏默认值和实现逻辑，不是实测频率；循环使用严格 `>`，还受调度、编译覆写、仿真速率影响。

| 流 | 默认门槛/更新方式 | DDS writer QoS |
| --- | --- | --- |
| pose / twist / geopose | 间隔 >33 ms 后填充并发送，约 30 Hz 量级 | best effort、volatile、keep-last 5 |
| gps_global_origin | 间隔 >1000 ms | best effort、volatile、keep-last 5 |
| status | 每 >100 ms 检查；有检测到的变化发送，否则距上次发送 >500 ms 才发送 | reliable、transient-local、keep-last 1 |
| time / clock | 各自间隔 >10 ms | reliable、volatile、keep-last 20 |
| navsat | healthy 且该实例 last_fix_time_ms 改变 | best effort、volatile、keep-last 5 |

依据：[DDS 默认配置:37][config]、[status/clock 默认配置:109][statusconfig]、[更新循环:1772][update]、[status 比较:735][status]、[topic QoS 全表][topics]。

**飞控内部连接检测。** 建立 XRCE session 和 DDS entities 后置私有 `connected=true`。循环按 HAL 时间每 >500 ms 检查 pong，并发送 ping；累计 missed 计数 >2 时置 false 并进入重连流程。该变量和 `status_ok` 没有出现在 DDS 状态消息中。这是 FC→Agent 的内部会话检测，不是 ROS 消费者可直接读取的端到端连接证据；也不是严格的 1.5 秒宿主墙钟 SLA。[ping 间隔:88][pingperiod]、[DDS loop:1263][ping]、[私有连接状态:258][linkvars]、[Status.msg:16][statusmsg]

适配层最小接收策略（推导建议，非现有实现）：

1. 针对已配置的目标流，用本机 steady/monotonic 时钟记录接收时刻，分别维护 link、pose、status、各 GPS 实例的新鲜度。超过各自可配置 TTL 记为 stale；首次未收到为 unknown。源码没有给 ROS 消费者定义 TTL，不能把默认发送间隔当超时保证。
2. 启动/重连后要求观察到连续推进的源时间及新接收流量；可优先用 volatile 的 pose 或 time/clock 辅助判断。status 是 transient-local，单个历史样本不能证明飞控当前在线；静止时数值不变也不能判掉线。
3. 时间跳变/回退、重新发现数据源时重新建立 epoch/freshness 基线。不要直接算 `host_wall_now - header.stamp`，也不要让受仿真时间控制的计时器独自承担链路超时。仿真暂停时超时只意味着“没有新遥测”，不能据此区分暂停、进程停止、Agent 故障或网络丢失。
4. 将连接/流新鲜度与定位有效性分别报告；连续更新的 DDS stamp 只说明该发布路径有推进，不说明 EKF 数据有效。GPS 单流停更也不能直接断言整条 DDS 链路断开。

上述区分来自时间实现、独立发布门槛与消息缺失的状态语义。[DDS time][time]、[HAL time][halclock]、[update][update]、[status QoS:316][qosstatus]、[GPS gate][navsat]。另外，`/ap/rc.is_connected` 判断的是无线电接收机 failsafe/有效通道，不是 DDS 连接。[DDS RC:537][rc]

## 6. 仍不可证明、不得填成 true 的项目

- **严格 odom/EKF/position/GPS-for-navigation 有效性**：缺直接有效位、原始估计 freshness、主 GPS/融合来源；absence of failsafe、prearm true、finite pose 都不足以补齐。
- **当前 home 及固定坐标参照**：缺 home 坐标/有效位/版本；不能证明 home==EKF origin、整个飞行中不变，或 absolute altitude 一定采用椭球高。
- **reset 事件的完整性**：缺 delta、counter、事件时间、原因，无法无歧义恢复 reset 或证明没有发生 reset。
- **具体运行事实**：本次不启动程序、不读取实时 ROS 图、不调用服务；没有证明实际二进制与源码一致、宏覆写/参数取值、当前 EKF backend/GPS 类型、实际 QoS 匹配、发布频率、故障超时或某次服务调用成功。
- **时间线统一**：源码只证明上述 HAL/RTC 机制，不能证明与外部自主仿真核心的 epoch、速率、暂停/重启策略已对齐。

前三项的接口证据见第 2–4 节，时间与运行边界见第 5 节。当前原生接口足以构建“状态/故障观测 + 带新鲜度的遥测”，不能据此伪造完整的定位有效性契约。本次唯一新增产物是本笔记，不包含 Prometheus 上游控制节点或 PX4 adapter 迁移。

[topics]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Topic_Table.h:17
[services]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Service_Table.h:4
[status]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:707
[statusmsg]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/Tools/ros2/ardupilot_msgs/msg/Status.msg:16
[pose]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:413
[twist]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:464
[geopose]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:569
[origin]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:687
[update]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:1772
[navsat]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:211
[navsatstatus]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/Idl/sensor_msgs/msg/NavSatStatus.idl:8
[navsatidl]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/Idl/sensor_msgs/msg/NavSatFix.idl:23
[gpsfix]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_GPS/AP_GPS.cpp:940
[gpshealthy]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_GPS/AP_GPS.cpp:1789
[prearmdds]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:997
[prearm]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/AP_Arming_Copter.cpp:8
[prearmpos]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/AP_Arming_Copter.cpp:443
[ekfcheck]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/ekf_check.cpp:30
[ekfnotify]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/ekf_check.cpp:165
[filterbits]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_NavEKF/AP_Nav_Common.h:26
[positionok]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/system.cpp:220
[ahrsfilter]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:2463
[ahrsposition]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:1839
[locationmath]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_Common/Location.cpp:425
[ahrshome]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:3041
[frames]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Frames.h:3
[ahrslla]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:871
[ekflla]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_NavEKF3/AP_NavEKF3_Outputs.cpp:330
[commands]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/commands.cpp:4
[armhome]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/AP_Arming_Copter.cpp:724
[missionhome]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/ArduCopter/mode_auto.cpp:2012
[gcshome]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/GCS_MAVLink/GCS_Common.cpp:5501
[yawreset]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:2804
[nereset]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:2837
[dreset]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:2904
[heightreset]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_NavEKF3/AP_NavEKF3_PosVelFusion.cpp:365
[ekforigin]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_NavEKF3/AP_NavEKF3_Outputs.cpp:413
[heightcorrect]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_NavEKF3/AP_NavEKF3_Measurements.cpp:831
[originstate]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:427
[originget]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_AHRS/AP_AHRS.cpp:3735
[gpsalt]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_GPS/GPS_Backend.cpp:450
[gpsaltparam]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_GPS/AP_GPS.cpp:248
[geopointidl]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/Idl/geographic_msgs/msg/GeoPoint.idl:24
[time]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:197
[clock]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:679
[rtc]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_RTC/AP_RTC.cpp:47
[halclock]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_HAL_SITL/system.cpp:173
[simclock]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_HAL_SITL/SITL_State.cpp:249
[simstart]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_HAL_SITL/SITL_State.cpp:78
[gpstime]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/SITL/SIM_GPS.cpp:252
[rtcfeed]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_GPS/AP_GPS.cpp:997
[startutc]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_HAL_SITL/SITL_cmdline.cpp:263
[startoverride]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_HAL_SITL/SITL_cmdline.cpp:529
[config]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_config.h:37
[statusconfig]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_config.h:109
[ping]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:1263
[pingperiod]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:88
[linkvars]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.h:258
[getparams]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:1135
[qosclock]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Topic_Table.h:280
[qosstatus]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Topic_Table.h:316
[rc]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_Client.cpp:537
[extodom]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/AP_DDS_External_Odom.cpp:11
[header]: //wsl.localhost/Ubuntu-22.04/root/wksim-ap-dds-yaw-mVgItN/src/libraries/AP_DDS/Idl/std_msgs/msg/Header.idl:13
[installedstatus]: //wsl.localhost/Ubuntu-22.04/root/wksim-dds-VxM6Ni/ros-install/ardupilot_msgs/share/ardupilot_msgs/msg/Status.msg:16
