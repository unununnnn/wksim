# Prometheus 命令库与原生双飞控节点

从固定 Prometheus 上游迁移命令受理、期望参考量计算与输出修整，现已接入ROS2节点和双原生DDS适配，完成共同位置任务的隔离SITL验证。**它仍不是完整控制器**：RC积分、PID/UDE/NE、全部控制模式及空中失联矩阵尚未完成。AP需要显式候选固件和匹配消息层；不得将 `accepted=True` 当作飞控接受或动作完成。

原始来源为 [AMOVLAB Prometheus 5dcd8cfa764d](https://github.com/amov-lab/Prometheus/blob/5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce/Modules/uav_control/src/uav_controller.cpp)，保留 Apache-2.0 归属。原 ROS1 文件不改写；本包使用实际生成的 ROS2 `prometheus_msgs`，构建方法见[工作区说明](../../README.md)。

## 计算一次参考量

在已 source 本工作区安装目录的 WSL Bash 中运行。示例状态仅用于本地计算，不会连接或操纵飞行器：

```bash
python3 - <<'PY'
from prometheus_msgs.msg import UAVCommand, UAVControlState, UAVState
from geometry_msgs.msg import Quaternion
from prometheus_control.command import CommandProcessor
from prometheus_control.shaping import SetpointShaper

processor = CommandProcessor(takeoff_height=1.0)
processor.update_state(UAVState(
    connected=True, armed=True, odom_valid=True,
    position=[0.0, 0.0, 0.0], attitude_q=Quaternion(w=1.0)))
assert processor.enter_control(UAVControlState.COMMAND_CONTROL).accepted
answer = processor.accept(UAVCommand(
    agent_cmd=UAVCommand.MOVE, move_mode=UAVCommand.XYZ_POS,
    command_id=1, position_ref=[3.0, 2.0, 1.0]))
assert answer.accepted
reference = processor.step()
assert reference.position == (3.0, 2.0, 1.0)
shaper = SetpointShaper()
assert shaper.shape(reference, processor.local_position()).position == (3.0, 2.0, 1.0)
print('Reference and output calculation passed; no flight command was transmitted.')
PY
```

## 输入与输出契约

| 调用 | 含义 | 宿主仍须负责 |
| --- | --- | --- |
| `update_state(UAVState)` | 校验有限位姿/速度与非零四元数；解锁沿捕获起点，解除解锁清除运动状态 | 状态来源、时间戳、新鲜度及估计器可信度 |
| `set_offset(x, y)` | GPS/RTK 的平面位置偏移，单位米 | 在运行配置中固定偏移；本库不重投影已有目标 |
| `enter_control(mode, *, initial_hover=None)` | 本地模式门控；可用一次捕获的 `Desired('position')` 作为空中初始保持目标；重复进入不重捕获 | 原生飞控模式转换、确认、状态新鲜度和控制权管理；初始参考只在显式接管时捕获 |
| `accept(UAVCommand)` | 校验命令与优先级，返回 `Acceptance` | 在调用前校验该飞控的能力，不做静默降级 |
| `step(sim_mode=True, rc_age=0.0)` | 产生不可变 `Desired`，或无输出 `None` | 调度、墙钟看门狗，接入本包输出修整及真实 DDS 发送 |
| `SetpointShaper.shape(reference, local_position)` | 输出按轴标明有效值的 `Setpoint`；停止/降落清理保持状态 | 传入飞控本地ENU位置，处理原生能力、坐标转换与发送 |

参考量使用 Prometheus 的 ENU/FLU 和米、秒、弧度；全局经纬度使用度，`LAT_LON_ALT` 的高度为相对 home 高度。纯计算库不处理传输坐标；PX4 NED/FRD与ArduCopter消息frame由本包原生适配层处理，UE厘米转换仍在包外。混合模式只激活速度 XY 与位置 Z，另外的占位零不可解释为有效目标；其他未激活参考量为 `None`。

`Acceptance.stop_control` 为上游规划控制停止/恢复信号的逻辑值，`None` 表示本次无信号，不是网络确认。`Desired('land')` 仅是降落意图；连接丢失产生 `None`，由宿主/飞控处理失联策略，不能伪造降落成功。围栏、里程计或非仿真 RC 超时按上游优先级触发 LAND。

BODY 命令在受理后的**第一次 `step`** 依据当时的状态锚定，后续步进不随载具转动重新锚定。命令 ID 在受理时即保留高水位，重复或更旧 BODY 命令显式拒绝；即使尚未第一次步进也不会重复受理。高水位在对象生命周期内不回退、不因重新解锁清零；新运行需新建对象，跨运行重放保护仍属于宿主。

## 与上游的有意差异

- 未启用外部姿态控制时拒绝 `XYZ_ATT`，不回退为起飞点悬停。
- 两种 XY 速度/Z 位置模式从当前命令更新 yaw rate，修复上游读取旧值的行为。
- 无效枚举、未实现的 USER_MODE、非有限输入、越界推力/经纬度显式拒绝；拒绝的移动命令不覆盖当前有效参考。
- BODY 命令采用上述严格 ID 高水位；原上游存在旧世界系命令降低后续比较基准的可能，本库不保留它。
- 本地控制进入增加连接/里程计门控，重复进入同一模式不重新捕获悬停，解除解锁清除运动命令；不自动恢复飞控 OFFBOARD。
- 未激活参考量不携带旧值。TRAJECTORY 保留加速度参考，但**下游尚未发送它**；原上游的位置/速度发送路径未使用该加速度。

102 组与原 C++ 方法的对照只证明已覆盖条件下的**有效参考量**，有意差异由独立用例检查，不混称完全等价。测试、哈希、失败记录与未迁移列表见[命令迁移报告](../../../docs/2026-09-05_prometheus-command-report.md)。

原生接入能力须逐字段验证：本机固定ArduCopter原固件的 `GlobalPosition.yaw` 不会执行；仅存在字段不能满足位置＋偏航语义。[可选候选补丁](../../../patches/arducopter/README.md)已接入本包显式SITL配置，但未成为默认固件。未支持的命令在受理前显式拒绝，不能静默删除偏航或回退MAVLink控制。

## 输出修整

每次 `step` 后调用同一个 `SetpointShaper.shape`，即使返回的是 `None` 或 `land`。新运行、epoch或本地坐标原点改变时调用 `reset()`；不要绕过该生命周期而复用旧锚点。必须传入 `processor.local_position()`，不能传带GPS/RTK共享平面偏移的原始 `UAVState.position`。`Setpoint` 的位置/速度/加速度每个分量可以是 `None`（该轴不激活）；这是意图表示，不是直接可发送的ROS消息或MAVLink报文。

保留默认速度死区0.09m/s、混合模式死区0.001m/s、位置保持误差门槛0.04m、保持比例增益1.8/s、偏航门槛0.0349rad，均可通过构造参数校准。四个原float参数按float32解释，以保留边界判断。XYZ速度模式的静止轴采用原位置保持/修正速度规则；yaw-rate模式直接输出，不套用yaw角保持。姿态目标使用FLU的XYZW四元数与归一化推力；全局目标保持home相对高度。

修复变化：速度/偏航变化当步仍输出；只在某一轴由运动转为保持时捕获该轴当前位置，不因另一轴速度改变重置已保持的轴；混合模式与XYZ速度模式分开管理历史；退出yaw-rate时不复用旧锚点。TRAJECTORY输出仍保留上游的位置+速度路径，不擅自启用加速度前馈。

额外8项修整单测和332组原C++输出对照通过：286组等价字段、46组有意修复差异。对照包含带明确初态的内存记录器，不是MAVROS或DDS线格式联测，详见[输出修整报告](../../../docs/2026-09-05_prometheus-shaping-report.md)。

## 运行共同任务

先使用[原生节点报告](../../../docs/2026-09-05_prometheus-native-report.md)中的隔离启动器。它会执行真实仿真解锁与飞行，不用于真机/HIL。构建后可执行入口为 `ros2 run prometheus_control prometheus_control_node`；必须明确 `flight_stack`，PX4还须匹配`native_system_id`与`native_prefix`，AP须匹配WksimState消息层和显式`arducopter_position_yaw`配置。

当前 session_v1 输入在 `/uav{id}/prometheus/v2/setup`、`v2/command`，使用带 run_id/control_epoch/request_id 的包络；旧无身份输入显式拒绝。输出在同前缀的 `state`、`control_state`、`text_info`、`stop_control_state` 和 `v2/state`。命令header使用当前ROS时钟、frame留空或为map/world；默认有效期2秒，MOVE ID严格递增。位置/速度单位米/秒，ENU/FLU；状态header保留飞控boot时间，尚非联合场景统一时钟。模式请求沿用 `SET_PX4_MODE` 字符串字段：AUTO.LOITER 在 PX4 是自主保持，在 ArduCopter 映射到会读取驾驶输入的 LOITER，并非相同的无驾驶输入悬停保证。POSCTL在无遥控输入的PX4上会被原生解锁检查拒绝。

普通解锁后显式请求COMMAND_CONTROL，节点先完成必要的原生起飞/航向对齐，然后才启用目标流；重复请求不会重新起飞。`text_info.message`的JSON事件区分setup_received、native_ack、setup_completed、command_accepted/rejected和control_revoked。离开外部模式、状态超时或活动任务坐标/时钟重置不会自动重获控制。当前共同实测范围为位置、航点和LAND，其他边界与精确复现证据见报告。

空中显式接管现在捕获当时的 ENU 位置和四元数航向；同一个参考贯穿预热和接管后的保持，不回到起飞点、不重放旧 MOVE。地面接管仍保持原起飞语义。新公开命令才能覆盖此保持参考；拒绝的旧包络不能恢复输出。

ArduCopter 另支持明确的 `px4_mode='BRAKE'`（原生模式17），不偷偷替换 AUTO.LOITER。仅在已解锁、确认飞行中且状态有效时受理；PX4和无效/地面状态拒绝。BRAKE 忽略驾驶输入，驾驶者需要再次显式切换模式才能接管；它不是遥控交接已完成的证明。原生 service ACK 与状态观察到 BRAKE 仍分别报告。此节点能力不表示 `MissionTask` 已实现暂停、保持仿真及显式恢复，也不表示实际地面站界面已验收。
