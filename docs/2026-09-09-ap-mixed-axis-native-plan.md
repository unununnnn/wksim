# AP 原生 XY 速度 / Z 位置：下一切片设计

2026-09-09，#33 / `docs/plan/tickets/23-mixed-trajectory.md`。本轮仅直接读源码并写本文；未构建、测试、索引、枚举完整候选树、启动或停止进程、改补丁/固件/控制代码/准入/pin、提交或发布。主代理读取实际 session JSONL，确认 `/root/ap_mixed_axis_design` 为 `gpt-6-astra/high` 后发出 RELEASE；无嵌套委派。正在进行的完整 P+V 试飞由主代理独占，本文不报告其结果。

**建议新增一个明确的 Guided 子模式 `VelNEPosD`，XY 复用 `VelAccel` 的速度输入及水平避障，Z 复用 `PosVelAccel` 的位置输入、目标围栏检查和原生 D 控制器。DDS 使用现有 GlobalPosition 的严格掩码 `0x9E3`。不新增外部 PID、XY 位置锚点、IDL 或参数技巧。** 首个 profile 明确不提供 Z 速度避障；当前原生 `PosVelAccel` 同样没有这项能力。这个切片不是完整组合矩阵，也不能单独关闭 #33。

## 已实读的原生行为

下列 AP 路径均相对于 `/root/wksim-ap-pv-vn04950x/src`，是本轮实际读取的候选源码；没有修改这个封存候选或固定 clock 基线。仓库控制路径相对于 wksim 根。

| 源码 | 本轮确认的事实及设计影响 |
| --- | --- |
| `ArduCopter/mode_guided.cpp:36,52,255` | `init()` 进入 VelAccel、清 V/A 和 pause；`hold_position()` 切 VelAccel 并清 V/A；`pva_control_start()` 设置 NE/D 速度加速度限制，调用 D/NE init，初始化 yaw，清 terrain 标志。新子模式切入应复用它，不能每个目标包重新初始化。 |
| `libraries/AC_AttitudeControl/AC_PosControl.cpp:544,888` | NE/D init 从当前估计位置、速度和当前姿态/推力重建控制状态；D init 还清 terrain。内部速度轨迹会维护位置状态，这是原生控制器状态，不是调用方制造一个 XY 位置目标。 |
| `ArduCopter/mode_guided.cpp:827` | VelAccel 在 disarmed/landed 时走原安全地面处理；超时清 V/A、停止 rate/angle-rate yaw；调用 `avoid.adjust_velocity_NED_m`，由 `limits_active()` 决定是否允许 GUIDED_OPTIONS 关闭 NE 稳定；NE/D 都使用速度输入。 |
| `ArduCopter/mode_guided.cpp:618,912` | 完整 PVA setter 在改子模式/yaw/时间戳前调用真实 fence；run 用 NE 与 D 的 P/V/A 输入。D 以 `float pz` 传引用，写回 Z；**这条 run 没有 `avoid.adjust_velocity_NED_m`**。 |
| `libraries/AC_AttitudeControl/AC_PosControl.cpp:609,995,1072` | NE 速度输入与 D 位置输入都有原生限加速度/jerk shaping；D update 在内部把位置误差产生的速度与前馈相加，才进入速度 PID。给 wire Vz=0 并调用 avoidance，不会限制后面由 Pz 产生的实际垂直速度。 |
| `libraries/AC_Avoidance/AC_Avoid.h:59`、`AC_Avoid.cpp:224,409` | NED wrapper 转 NEU cm，避障可改变 XYZ；Z limiter 遇零 climb rate 直接返回，proximity/backaway 仍可能产生 Z。不能把避免后的 Z 偷当 mixed Vz 前馈，也不能宣称丢弃它后仍有完整三维避障。 |
| `ArduCopter/mode.cpp:505`、`mode_guided.cpp:138`、`AC_PosControl.cpp:1690,1733` | 每次 update_flight_mode 根据单个布尔值设置一个全轴 EKF reset 方法。VelAccel 要 MoveTarget，PosVelAccel 要 MoveVehicle；NE/D 各自在自己的 update 内消费这个方法。混合模式需要显式分轴选择。 |
| `libraries/AP_Common/Location.cpp:147,269` | `get_alt_m(ABOVE_ORIGIN)` 真正解析 home/origin；缺所需数据返回 false。它不要求先做 XY 向量转换。terrain 转换依赖所处地理位置及 terrain 数据，不能用 wire 中已忽略的 latitude/longitude。SITL 对未初始化 Location 有 panic。 |
| `libraries/AC_Fence/AC_Fence.cpp:984` | `check_destination_within_fence` 检查高度、圆形、polygon，但某个高度转换失败时会跳过该高度检查。Guided `set_destination:470` 自身也注明这个限制。因此不能把“调用了 fence”写成“所有帧转换失败都拒绝”。 |
| `ArduCopter/AP_ExternalControl_Copter.cpp:47,71` | 现有 PV 方法校验 ready 和有限值，经完整 Location→origin NED，然后交 Guided；ready 的真实条件是 `flightmode->in_guided_mode() && motors->armed()`，不是完整 odom/定位检查，也不严格等于 mode number 4。 |
| `ArduCopter/GCS_MAVLink_Copter.cpp:142`、`Log.cpp:363` | Guided 子模式参与目标遥测掩码和 GUID 日志 type；新增枚举不能只改 run。现有 target 遥测不发送 yaw，因此观察掩码与入站 DDS 掩码不同。 |

小范围源 SHA256 本轮读回如下；它们不是完整候选身份准入，也不是运行加载证明。

| 源 | SHA256 |
| --- | --- |
| `ArduCopter/mode_guided.cpp` | `954836c2a3bb1418ed81fd0178abf5521e140a45fc27543896b3ea6d06df0a08` |
| `ArduCopter/mode.h` | `3bde555aca6f4b560a8034349412e9b153b55e1d0a039e57eac236dfe031cec3` |
| `libraries/AP_DDS/AP_DDS_ExternalControl.cpp` | `2e21990fd0662a62a2356819a1f9af9a899031a03dbac6279f98ed59d15349ef` |
| `libraries/AP_Common/Location.cpp` | `038a35efdf42622e1932fb53323dd9a1580d7749413ca778037fd0c27cdda872` |

## 最小 wire 与 API 契约

建议第一版实验 profile 名 `xy_velocity_z_position_yaw_v1`，只允许 map + `FRAME_GLOBAL_REL_ALT=6`、绝对 yaw。此处只推荐名称，不变更现有 `full_xyz_pv_yaw_v1` 的含义。明确拒绝 frame 5/11、yaw-rate、yaw-ignore、单独 X/Y 激活、Pxy+Vz、任何非零 Vz 前馈、A/force；它们不是首个切片的隐含能力。

`GlobalPosition.idl` 已定义全部位：IGNORE_LATITUDE 1 + IGNORE_LONGITUDE 2 + IGNORE_VZ 32 + IGNORE_AFX 64 + IGNORE_AFY 128 + IGNORE_AFZ 256 + IGNORE_YAW_RATE 2048 = **2531 / 0x9E3**。Pz、Vx/Vy、yaw 有效。`0xDE3` 是另加 IGNORE_YAW 的组合，本切片不放行。

在 `AP_DDS_ExternalControl.cpp` 现有完整 P/PV 校验之前增加严格 mixed 分支。先检查 exact mask/frame/map、有限 altitude/yaw/Vx/Vy、double→float 溢出和 cm 整数范围，然后原子转发。ENU `(Ve,Vn)` 转 `Vector2f(Vn,Ve)`，yaw 用原 `wrap_PI(pi/2-yaw)`。lat/lon/Vz/A/angular 等失活 payload 不读、不参与算术、不做位置构造；测试用巨大值/NaN 证明被忽略，但**绝不拿 NaN 选择控制轴**。其余包继续进入原严格分支，保持旧 P/PV 接受与拒绝行为。

建议最窄接线为：

```cpp
// AP_ExternalControl.h：默认 return false；Copter .h/.cpp：override。
bool set_altitude_velocity_xy_and_yaw(int32_t altitude_above_home_cm,
                                    const Vector2f& velocity_ne_ms,
                                    float yaw_rad);

// mode.h / mode_guided.cpp：明确只有 NE velocity、D position 和 yaw。
bool set_vel_NE_pos_D_m(const Vector2f& velocity_ne_ms,
                       float position_d_m, float yaw_rad);
```

ExternalControl 重用 armed/Guided readiness，重复校验有限 V/yaw；通过 `AP::ahrs().get_location(check_loc)` 取得当前有效地理点，`check_loc.set_alt_cm(altitude_above_home_cm, ABOVE_HOME)`，再 `get_alt_m(ABOVE_ORIGIN, up_m)` 得到 `position_d_m=-up_m`。不调用完整 `get_vector_from_origin_NED_m`，不从 wire lat/lon 构造位置，不通过 `home_offset((0,0,z))` 暗造 XY。

围栏由 Guided setter 在改变任何控制状态前检查：重新取**当前实际** Location，只替换 altitude 为目标 ABOVE_ORIGIN，调用现有 `check_destination_within_fence`，失败仍写 NAVIGATION/DEST_OUTSIDE_FENCE。这个当前 XY 只用于有效性/围栏判定，绝不保存为 commanded XY。当前位置已经越过水平 fence 时，新 mixed 命令会被保守拒绝；不能把它描述为允许向内救援的纯速度模式。首个实验必须核验 home/origin 与启用高度 fence 的帧转换全部可用；若要支持转换不可用的配置，需先补显式 fail-closed 检查，不能靠现有 fence 返回 true 放行。frame 11 全包拒绝，避免引入“移动过程中持续 AGL”与“一次采样 terrain”之间未定义的语义。

## Guided 生命周期与逐轴执行

在 `mode.h` 的 SubMode **末尾**追加 `VelNEPosD`（当前末项 Angle，追加值为 7），保留已有日志枚举数值。新增 start/run 与 setter；复用已有 static target 变量，不引入全局 mixed 布尔值或第二套 PID。setter 先完成所有拒绝检查，再仅在跨子模式时调用 `pva_control_start()`；随后清失活目标，保存 Pz、Vxy、yaw、`update_time_ms`。`guided_pos_target_ned_m.xy()` 可以清零作失活存储/日志占位，不能被输入到 NE position API。

run 按以下顺序实现，代码复用来源如上表：

1. 原 disarmed/landed ground handling 和 spool 条件不变。超过 `get_timeout_ms()` 时清 XY 速度与 A，沿用原 yaw 超时规则；**保留目标 Pz**，不宣称 native timeout 是 CURRENT_POS_HOVER。
2. NE 工作速度从已受理 Vxy 取值，构造局部 `(Vn,Ve,0)` 给原 avoidance wrapper。仅使用其 XY 输出，保留原 `do_avoid/limits_active()` 对 NE 稳定选项的优先级；Z 输出明确不进入位置轴。NE 调 `input_vel_accel_NE_m(vxy, zero_accel_xy, false)`，沿用 VelAccel 对 `stabilizing_vel_NE/pos_NE` 的分支。不改 GUIDED_OPTIONS 或 AVOID 参数。
3. D 始终用保存的 `float pz` 和本 tick 的 `float vz=0` 调 `input_pos_vel_accel_D_m(pz, vz, 0, false)`，保留原 PVA float/引用写回模式。这里的零是该原生位置控制 API 的零前馈，不代表 DDS Vz 激活。terrain 状态应为 false，沿用原内部一致性检查。
4. 在 `NE_update_controller()` 前调用已有 `set_reset_handling_method(MoveTarget)`，在 `D_update_controller()` 前设 `MoveVehicle`。无需增加 AC_PosControl 字段或改其算法。`move_vehicle_on_ekf_reset()` 为新子模式返回 false，作为 pause/未进入专用 run 时的默认；正常 mixed run 在各轴 update 前明确覆盖。最后恢复 MoveTarget，避免把 D 的选择留给同 tick 其他调用。必须以真实 reset 测试证明调用顺序；不能只给新枚举选一个全轴 true/false。
5. 原 thrust-vector/auto-yaw 输出不变。每个目标日志用新子模式、Pz 和 Vxy；失活轴零占位必须由新 type 解释，不能作为 active Pxy 的证据。

`run/get_wp/move_vehicle_on_ekf_reset/wp_bearing/crosstrack_error` 的枚举分支都需覆盖新模式。get_wp 返回 false；没有 commanded XY destination，bearing 不伪造指向原点，distance 保持无 XY waypoint 的语义。crosstrack 可以像原 VelAccel 返回控制器值，但不把它称为指定 XY 路径误差。

还需改 `GCS_MAVLink_Copter::send_position_target_local_ned`：新分支报告 Pz/Vxy，忽略 Pxy/Vz/A/yaw/yawrate，即 **0xDE3**，与入站 DDS **0x9E3** 分开解释。这是观察通道修正，不新增 MAVLink 控制路径。`Log.cpp` 本身按 enum type 记录，可原样复用；审计器必须识别新 type=7，禁止把其零占位位置当执行目标。

切入 full P/PV/V/Angle、`hold_position()`、离开再进入 Guided 都应通过现有 start/init 路径重建状态；新 setter 不依赖上一个子模式的 Pxy、Vz、A 或 terrain。特别注意 native `pause()/resume()` 目前只翻 `_paused`，会保留旧目标：若首版要满足 native pause 后不重放 mixed 命令，最小是在新 mixed 子模式的 pause 分支先 `hold_position()` 再置 `_paused=true`，并在 mixed setter 对 `_paused` 返回 false；resume 后保持 VelAccel，必须收到新目标才重进 mixed。该改变只针对新子模式，原模式行为不动。公开暂停/停止不是这个函数的同义词，仍须独立验证。

## 控制层与 oracle：保留哪一层的零

已读 `command.py`、`shaping.py`、两 native adapter、`node.py`、`validation/test_prometheus_control.py`、`tools/validate_prometheus_shaping.py`。

`CommandProcessor.resolve_move` 对两种 mixed 命令输出 `velocity=(*v[:2],0.0)`。BODY 目标在 `step()` 按 command_id 一次解析并缓存；XY 按当时 yaw 旋转，Z 相对当时位置，不应由 adapter 每 tick 再旋转/累加。shaper 在 XY 至少一轴运动时输出 **P=(None,None,z), V=(vx,vy,0.0)**；单独静止 XY 轴用既有捕获锚点修正速度。两 XY 都进入 mixed deadband 后输出 **完整 P=(anchor_x,anchor_y,z)，V 全 None**。yaw-rate 分支不做这些保持，第一切片应在 supports 前置拒绝。

因此最小实现**不改 command/shaping/oracle**。只在 AP 显式 mixed profile 下，将上述严格 mixed 形状中的 Vz 字面零解释为“位置 Z 所需的零前馈”，输出 wire IGNORE_VZ。必须检查 Vz 精确为有限零（可另接受 None，若写入版本契约），非零不可悄悄丢弃。记录 shaped active fields 与 native active mask 两份证据，不能把原 shaper 说成已输出 None，也不能将零改成 None 后仍宣称332组完全同义。

`native_arducopter.py` 的 mixed 分支须放在现有 PV “P 与 V 任意轴均存在”的分支前；否则现有 PV 分支会拿 `(None,None,z)` 调 home_offset 而失败。mixed 只校验 finite Pz、Vx/Vy、零 Vz、A 全 None、finite yaw、yaw_rate None；不把失活 Pxy 送入 home_offset。构造 GlobalPosition 时 wire lat/lon/Vz 可使用消息默认零占位，但由 exact mask 排除。保持状态新鲜、odom、可用订阅者、100 m Z 包络及原子失败。完整 P 的静止分支仍走现有 0x9F8，不硬留在 mixed 模式。新 profile 不应顺便解除原 XYZ_VEL+yaw、yaw-rate mixed 或其他组合的能力拒绝。

`node.py` 新增默认关闭的只读 `arducopter_mixed_profile` 参数，交 adapter；只有验证过新固件身份的实验启动器可注入。支持 `XY_VEL_Z_POS` 和 `XY_VEL_Z_POS_BODY` 且要求 yaw angle；保留现有 pv_profile 的独立能力。现有 `revoke/模式切换/显式接管` 会 reset shaper；失活与 land 也会 reset。不要另造 adapter hold 缓存。若今后要求通用 shaper 把 mixed Vz 改为 None，则应先声明新的有效轴差分类别、保持旧 oracle 固定输入与原输出、增加针对 zero→inactive 的新比较规则；这不是本切片必要改动。

## 实施前测试与有界实飞条件

先在独立新 AP 候选中实施上述约七个原生文件（AP_DDS cpp、ExternalControl 基类 h、Copter ExternalControl h/cpp、mode.h、mode_guided.cpp、GCS_MAVLink_Copter.cpp），控制侧仅 adapter/node 和对应验证/实验准入工具。继承 PV 来源/补丁但不重写封存 PV 候选；生成新 source/build manifests、控制安装候选及显式实验准入。新固件不能冒用旧 PV manifest 或旧实飞 PASS。

最低测试门槛：

- **输入与原子性**：exact 0x9E3/frame6 正例；逐位缺失/新增、部分 XY、force、yaw-ignore/rate、frame5/11、活动非有限/溢出拒绝。失活 lat/lon/Vz/A 改值不改变受理目标；失败前后 mode、target、yaw、timestamp 完全相同。原 full P/PV/V 行为与默认 profile 拒绝回归。
- **实际转换/围栏**：不同 home/origin 高度例（home AMSL 100 m、origin 98 m、relative 3 m 应得到 Down -5 m）；非零当前 XY；缺 home/origin/location 拒绝；目标高度越 fence 拒绝且无状态变化。真实 Location/Fence 测试补足函数切片 stub；明确启用高度 fence 的转换失败边界与 terrain 拒绝。
- **原生轴与生命周期**：记录/断言 NE 只调用 velocity input，D 只调用 position input 且 Vz/A 为零；新鲜进入、连续重发不反复 init、mixed→P→mixed、V/PV/Angle/terrain-position→mixed、超时边界、hold、disarm/rearm、Guided 离开重进、native pause/resume。NE 与 D 单独及同时 EKF reset 验证 MoveTarget/MoveVehicle 语义和控制连续性。仅 enum 或 stub 调用次数不能代替真实状态变化。
- **避障边界**：真实 horizontal fence/proximity 激活时确认 Vxy 确实受限，原 do_avoid 稳定优先级保留；记录实际 AVOID/GUIDED_OPTIONS/GUID_TIMEOUT，不改参数制造支持。单测证明避障产生的 Z 不会变成 Vz 前馈；报告明确 Z 仍是原 PVA 安全范围，不声称 vertical avoidance。
- **公开语义与差分**：原102组命令/332组输出 oracle、既有 native/profile 测试；新增 mixed 活动轴、one-axis hold、all-XY hold、非零共享 offset、BODY once-capture、yaw-rate 原子拒绝。CURRENT_POS_HOVER/ABSOLUTE stop→退出→新接管采用新锚点，拒绝默认权限命令不误发目标；不可只看 stop_control_state Bool。

真实验证先冻结 `xy_velocity_z_position_yaw_v1` 的阶段、持续时间、误差/驻留/停止恢复窗和资源限额，再预约隔离 WSL 资源。第一场宜采用小范围、远离水平与高度 fence margin、已就绪 home/origin、已起飞且实际 GUIDED/OFFBOARD 的双栈相同公开任务：XY 平移同时给**不同于当前高度**的 Z 位置目标；改向；一 XY 静止；两 XY 静止转全 P；再次启动；公开 hold/停止/模式退出后在不同位置重新接管。若只做恒高且 Vz=0，无法充分证明原生 Z 位置控制工作。

用物理真值和原生 GUID/PSC、状态 reset 标记、原始 DDS 目标、公开请求身份共同验收；AP GUID type=7 + 正确 raw DDS mask 是执行语义证据的一部分，发送成功不等于飞控受理/动作完成。XY 运动窗验收 Vx/Vy 和位移方向/量级，Z 位置窗验收高度误差与驻留；全 P 静止窗验收捕获位置，重进窗检查没有回到旧锚点。单独停止目标流超过实际 native timeout，验证 XY 减速而 Pz 仍执行；这与公开 CURRENT_POS_HOVER 的“捕获当前 XYZ”分别审计。真实 fence 拒绝/水平避障/reset 边界可另做隔离有界场，不得用低风险 nominal 场覆盖它们。阈值本报告不擅自冻结，也未执行这些测试。

## 调查边界

已读根 AGENTS/CONTEXT-MAP/domain 指南、wksim AGENTS/CONTEXT、运行边界/项目隔离、本票与指定两份接缝报告。wksim 无 `docs/adr/`。本次所有结构依据均为任务指定或这些文件明确给出的已知源，直接读取；少量文件名/字面量定位后实读目标文件。外部 AP 候选是图外资源，没有使用旧图推断调用关系或为报告触发索引刷新。上文新增接口、profile、测试与试飞均为实施建议，主代理仍需复核；本文不替代候选身份验证，不提供实飞或生产提升结论。
