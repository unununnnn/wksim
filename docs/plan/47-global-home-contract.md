# 47 全球坐标与权威 home 合同 v1

2026-09-09；#116，父票 #47。本文冻结 #117 的纯转换边界与 #118 的接入设计，不证明全球飞行已通过。证据在 `validation/lunar-116-home-20260909-01/`。源码身份以该目录 identity.txt 为准。

## 已读取的事实

项目基线 `e5b877cafd06e97ffe21a2911b85436e72fa106d`。控制源码实际在 `ros2/src/prometheus_control/prometheus_control/`，不是 Simulator 下的同名文件。

| 依据 | 实际语义与限制 |
| --- | --- |
| native_arducopter.py: home_offset、receive、navigation_valid、send | home 为 WksimState 的 e7/cm 字段；home tuple 变化使 generation 增加。local ENU 相对 home；global 发布 GlobalPosition，FRAME_GLOBAL_REL_ALT、mask 0x9F8、map。当前位置/yaw 候选必须显式启用。 |
| patches/arducopter/0002-dds-local-state.patch | home 来自 AHRS.get_home、home_is_set 和 ABSOLUTE 高度解析；位置来自 get_relative_position_NED_home，转换为 ENU。GPS 数值是原始 GPS，不是 home 或融合位置。 |
| AP 1511f27194f1dcc3728270883047bdf022b3fd53，libraries/AP_AHRS/AP_AHRS.cpp:1839 | 先要求 _home_is_set 和 get_location 成功，再计算 _home.get_distance_NED(loc)。 |
| 同版本 libraries/AP_Common/Location.cpp:426 | get_distance_NED 使用经纬度差、经度中纬度缩放和高度差；明确不处理高度 frame 转换。其两个输入高度基准必须一致，不能由函数名推定。 |
| patches/arducopter/0001-dds-global-position-yaw.patch | DDS 检查字段、有限数和范围；度转 e7、米转 cm；通过 convert_alt_frame 选择 Location frame；yaw 从 ENU 转 NED 后交 Guided.set_destination。 |
| native_px4.py: supports、state、request | LAT_LON_ALT 当前拒绝；位置为 VehicleLocalPosition 的 NED 转 ENU，ref_alt 是 EKF 原点 AMSL，不能替代 home。当前 state.altitude 来自 SensorGps.altitude_msl_m。 |
| PX4 d6f12ad1c4f70ad3230afd7d86e971421e02fef4，msg/versioned/HomePosition.msg | MESSAGE_VERSION=1，lat/lon 度，alt 米 AMSL，valid_hpos/valid_alt/valid_lpos、manual_home、update_count。 |
| 同版本 msg/versioned/VehicleGlobalPosition.msg | 融合 WGS84 lat/lon、alt AMSL 与独立 alt_ellipsoid；有效位、时间和全球位置 reset counters。不是 SensorGps。 |
| 同版本 msg/versioned/VehicleLocalPosition.msg | xy_global/z_global、ref_lat/ref_lon/ref_alt、ref_timestamp 定义局部投影原点。 |
| 同版本 src/modules/uxrce_dds_client/dds_topics.yaml | 输出 home_position（5 Hz 上限）、vehicle_global_position（50 Hz 上限），输入 trajectory_setpoint。上限不证明真实发布频率。 |
| command.py、shaping.py、frames.py、Simulator/wksim_runtime/config.py | 公共全球高度已有 home-relative 语义；ENU/NED=(N,E,-U)；配置拒绝未知字段，目前没有本合同的 home/全球 profile。 |

外部 PX4 只读根 `/root/wksim-px4-state-ONa1Kw/src`，AP 根 `/root/wksim-dependencies/ardupilot-1511f271`。它们用于固定源码分析，不据此宣称当前安装产物匹配或已飞行。

## 公共数据、单位与基准

`global-home-v1` 输入由 latitude_deg、longitude_deg、height_m、height_reference、identity、command_id、issued_monotonic、expires_monotonic 构成。禁止布尔冒充数值、NaN、Infinity、缺失字段或隐式单位。角度为 WGS84 大地纬度/经度（度）；yaw 是公共 ENU 弧度。局部长度米，速度米/秒，NED 转 ENU 严格交换前两轴并反转第三轴。

height_reference 只接受 `home_relative` 或 `amsl`；前者 H_target=H_home+height_m，后者 h_rel=height_m-H_home。公共 UAVCommand.altitude 仍只表示 home_relative；AMSL 输入必须经过显式转换接口并保存原输入。ellipsoid、AGL、terrain、未知 datum 全部拒绝；不得把 WGS84 水平坐标标签当作椭球高标签，也不得假设海拔零点或添加猜测的 geoid 偏移。

AP ABSOLUTE 是原生绝对高度标记。进入双栈 AMSL profile 前，实际 AP 固件/传感器输入/模型 origin 配置必须证明其绝对高与场景 AMSL 一致；仅有该枚举不构成实证。无法证明时返回 `datum_unverified`。不准借 raw GPS 修补 home。场景 origin、EKF origin、home 分别记录，即使数值恰好相等也保留三个身份。

## 权威 home 与失效

HomeSnapshot 必须包含 schema、stack、run_id、instance_id、vehicle_id、control_epoch、native boot/session identity、发布者 GID、source timestamp、received monotonic、home_generation、lat/lon、alt_amsl_m、datum proof identity、valid flags。PX4 另保存 update_count/manual_home；AP 保存原始 e7/cm tuple。同一原生有效更新在比较之后才能进入缓存。

PX4 使用版本匹配的 HomePosition（topic() 构造 `/fmu/out/home_position_v1`）且 valid_hpos、valid_alt 为真；绝不从 VehicleLocalPosition.ref_* 合成 home。valid_lpos 只标记原生 home 的局部字段，不拿它代替独立 EKF origin 检查。融合全球位置须 lat_lon_valid、alt_valid、非 dead_reckoning，且满足现有导航门控。订阅版本/固件发布表不匹配则拒绝。

AP 使用同一已绑定 WksimState 的 home_valid 和原始 home 字段；保留 filter_status_valid、ahrs_healthy、attitude/position/velocity_valid、GPS fix>=3、非 failsafe 等现有门控。GPS 数值或 EKF origin 不能赋值给 HomeSnapshot。

冻结 freshness 为墙钟单调时间 2.0s（有效区间 0<=age<=2.0），每次受理和每次原生发布都检查；重复 source stamp 不刷新租期，回退时间使会话失效。home 虽可能变化很少，仍要求原生新鲜观测；若实际发布稀疏，后继必须建立显式原生查询/保活证据，不能默默延长 TTL。暂停期间禁止受理和发布新的全球运动；恢复后必须取得新的有效状态，不靠冻结时间延长旧全球目标。

home_generation 是运行内单调整数：首次有效 home 建立一代；有效位变化、坐标/高度变化、PX4 update_count 变化（含回绕）、源身份变化均撤销已绑定目标。数值比较采用原生精度，不设会吞掉真实 home 变化的 epsilon。AP 当前消息没有 home 更新计数，同值重设无法被 tuple 检测：该能力明确未覆盖，#118 要么补原生更新身份并归档，要么拒绝要求检测同值重设的 profile；不得声称已检测。

EKF 原点/ref_timestamp、全球 reset counters、局部 reset counters、控制 epoch、FC 重启、DDS 发布者换代也撤销旧目标。home_generation 与 local_origin_generation 分开，不把 EKF reset 命名为 home 更新。失效时清空目标及缓存转换，停止旧设定值发布，进入现有控制失效路径；不自动重投影、重放、重新接管或猜测降落行为。

ResolvedTarget 保留原始全球输入、home snapshot identity、origin identity、两种高度、量化后目标与算法版本。命令 identity 必须与当前快照全部匹配，command_id 单调去重；命令 TTL 最大 2s。运动期间即使 TTL 尚未耗尽也不能绕过 home 换代。所有拒绝有稳定 reason 和关联原始证据，不以 publish/ACK 代表动作完成。

## 冻结的转换算法与数值门槛

这是原生坐标兼容算法，不宣称全球椭球测地距离精度。

PX4：采用固定源码 src/lib/geo/geo.cpp MapProjection::project 的球面方位等距投影，R=6371000m。参考点为当前有效 EKF ref_lat/ref_lon；纬经度先转弧度。c=acos(clamp(sin(phi0)sin(phi)+cos(phi0)cos(phi)cos(dlon),-1,1))；c=0 时 k=1，否则 k=c/sin(c)。N=kR[cos(phi0)sin(phi)-sin(phi0)cos(phi)cos(dlon)]，E=kR cos(phi)sin(dlon)。z_NED=ref_alt-H_target；公开 ENU=(E,N,H_target-ref_alt)。输出按原生 float32 量化。不得用 home 的局部 x/y/z 或简单高度差替代投影原点。

AP：全球控制保持经纬度目标，显式 FRAME_GLOBAL_REL_ALT 与 h_rel；度到 e7、米到 cm 按原生截断及实际 float 字段量化。local home ENU 数值对照采用固定 Location 比例 0.011131884502145034 m/e7 和中纬度 cos，经度差跨日期线归一化。该算法仅用于有界坐标核验，不能把 AP global 命令悄悄改成 local 命令。原生高度解析失败即拒绝。

共同运行 envelope：home、target、PX4 origin 的 |latitude|<=85 度，经度输入 [-180,180]；内部统一 [-180,180)，零经纬合法。home 投影水平距离与 PX4 origin 投影水平距离分别<=100m；|h_rel|<=100m；原生量化前后均检查。实际试飞仅使用预先冻结的正高度，负高度边界只做拒绝/转换测试，不授权地下飞行。此 envelope 是本候选的支持边界，不能泛称全球远距离支持。

#117 数值验收：同一输入对固定 PX4 C++ project 的 N/E/z 最大绝对误差<=0.001m；AP 量化后 e7/cm 完全一致，Location float 计算误差<=0.001m；不量化的坐标回算误差<=1e-9度，量化往返<=2e-7度、高度<=0.02m。将量化误差与飞行误差分别报告。必须包括零坐标、南西半球、日期线两侧、85度边界、100m边界前后、非零且互不相同的 home/origin 高度、NaN/Inf/布尔、AMSL与椭球混淆、过期、重复/回退时间、旧run/epoch/home/origin。固定 C++ oracle 未运行前不得声称这些门槛已经通过。

## 原生接入计划与文件预约

#117 仅写 `Simulator/wksim_control/global_reference.py` 与 `validation/test_global_reference.py`，提供纯 resolve/validate_current 边界；参数显式携带 now/home/origin，不读取系统时间或发 ROS。

#118 需要单写入者预约以下实际文件：`ros2/src/prometheus_control/prometheus_control/native_px4.py`、`native_arducopter.py`、`node.py`、`command.py`、`shaping.py`、`session.py`（均同目录），`Simulator/wksim_runtime/config.py`；以及新的 `validation/test_global_native.py`、`tools/run-global-flight.sh`、`tools/audit_global_flight.py`。本合同是具体预约清单，不覆盖别票的并行写入，也不改变 #118 当前仅有文档/证据的票据写入范围；开工前须由主代理将具体范围写入 #118 并核对所有权。若需要 AP 同值 home 更新计数，另预约固件补丁/消息 overlay，不能在这些文件中伪造。

PX4 明确启用 `global-home-v1` 才允许 LAT_LON_ALT；经上述校验后的显式 global-to-native projection 输出 TrajectorySetpoint 与 OffboardControlMode(position=true)。保留全球原意及转换记录，不在 supports 中直接放行再走普通 local fallback。AP 保留 GlobalPosition、map、0x9F8、FRAME_GLOBAL_REL_ALT 与 yaw 语义；每次发送前复核 home identity。安装包、消息类型、固件、DDS yaml、模型和 profile SHA 必须与运行 evidence 匹配。

未来工具 CLI 建议形状 `bash tools/run-global-flight.sh --stack <px4|arducopter> --run-id <new> --config <frozen-json> --output-root <new-root>`，审计 `python tools/audit_global_flight.py <result.json> --output <new-audit.json>`。这些入口尚未创建，不能作为本票已运行命令。后继交付准确可执行版本后才派发 #119/#120。

运行必须从真实原生 home 和有身份的场景 origin 构造固定目标并在发命令前封存：例如 home 附近 E=5m、N=3m、h_rel=3m 的有界工况；实际经纬度由该栈冻结算法产生并记录，不猜测地理位置。另外保存 home 与 EKF origin 不同的工况、越界目标及 home 变化后的旧目标拒绝。不得为了测试修改厂商资源或直接操纵未预约进程。

沿用规格物理门槛：起飞>=2.5m，保持5飞控秒且高度误差<=0.6m、倾角<=0.35rad；目标误差<=0.5m、速度<=0.5m/s 持续2飞控秒；落地 |高度|<=0.3m 且 disarmed。global target 的原始经纬度/home/AMSL、独立物理真值与同一场景基准共同证明目标误差，不能只审计转换后的 local 设定值。越界/身份错误必须零原生目标发布；失效后零旧目标发布且不自动接管。真值坐标到全球的基准缺失则验收失败。

## 证据与未验证项

本票为静态设计：固定源码、哈希、消息与配置边界支持合同；没有新飞行、没有原生安装准入、没有全局转换实现/数值 oracle 成绩。AP ABSOLUTE 与实际传感器 AMSL 一致性、同值 home 重设计数、PX4 消息安装/真实周期、#118 写入范围和原生接入仍需后继实证。父票 #47、Full、R1、RateUnmet 结论均不随本合同变化。
