# #34 原生姿态/推力候选：已暂存，未构建或运行

2026-09-09。交付 `patches/arducopter/0006-dds-attitude-thrust.patch`，以及 `work/ap-attitude-stage-20260909/control.patch` 和对应前后源码。没有改动运行中的 #33 控制源码、原生源码、已安装消息包或正式 profile；没有编译、ROS 节点、SITL、提交或 Issue 状态操作。不能据此关闭 #34。

本子代理由主代理验证实际会话 `01a083d1-53d6-7cc2-9c99-615186249beb` 为 `gpt-6-astra/high`，没有嵌套委派。主代理仅 RELEASE 暂存，未释放重型构建/运行。使用 ponytail 技能，复用现有 Guided 姿态执行器，没有新增控制律、MAVLink 回退或通用框架。

## 实际入口与补丁

AP 只读基线 `/root/wksim-ap-mixed-fhuf05l9/src`，提交 `1511f27194f1dcc3728270883047bdf022b3fd53` 加 0001–0005。`mixed-build.json` SHA256 为 `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`，其二进制记录为 `509c60163b3fceb261d17ceb2d0814c10ec65846e5d8d6689375e3ee05ab731f`。这仅标识继承来源，不是 0006 的构建或加载证明。逐个直接读取已知源；外部 AP/PX4 不在项目图索引内，没有全库刷新。

AP 已有 `ModeGuided::set_angle(const Quaternion&, const Vector3f&, float, bool)`（`ArduCopter/mode.h:1121`），但当前 DDS topic 表没有姿态输入，ExternalControl 也没有该接线。0006 新增明确的 `ardupilot_msgs/msg/WksimAttitudeTarget` 消息和 IDL，ROS topic `/ap/wksim/attitude_target_v1`，DDS topic `rt/ap/wksim/attitude_target_v1`。字段只有 `Header header`、`Quaternion orientation`、`float32 normalized_thrust`，不存在借用 GlobalPosition/Twist 字段的含义替换。DDS type 为 `ardupilot_msgs::msg::dds_::WksimAttitudeTarget_`。

接线是 DDS handler → `AP_ExternalControl::set_attitude_and_thrust` → Copter override → `mode_guided.set_angle(q, Vector3f(0,0,0), u, true)`。其他载具的虚函数默认返回 false。Copter 先检查 armed/Guided、真实 `GUID_OPTIONS` bit 3、单位四元数和有限范围，再改 Guided 子模式与时间戳。零 body rates 表示不加角速度前馈，四元数仍完整控制姿态。现有 native Guided 日志保留目标和实际时间戳；发布成功不是飞控 ACK。

`AP_DDS_WKSIM_ATTITUDE_ENABLED` 默认 **0**，显式打开也只准 SITL。原有 topic 枚举编号保留，新入口追加到末尾。位置/PV/混合轴/速度 handler 和 Guided 控制律无改动。新消息加入 `Tools/ros2/ardupilot_msgs/CMakeLists.txt`；原 `libraries/AP_DDS/wscript:89` 的 IDL glob 已负责生成，无需另造生成器。

## 坐标与推力契约

命令四元数为 Hamilton，ROS 字段 `(x,y,z,w)`，表示 **body FLU → local map ENU**，`header.frame_id` 必须 `map`。内部计算按 WXYZ。设输入 `(w,x,y,z)`、`k=sqrt(1/2)`，NED/FRD 输出是：

```
q_NED_FRD = (k*(w+z), k*(x+y), k*(x-y), k*(w-z))
R_NED_FRD = R_NED_ENU * R_ENU_FLU * R_FLU_FRD
```

此变换自逆；单位姿态 ENU/FLU `(1,0,0,0)` 变为 NED/FRD `(k,0,0,k)`。`q` 与 `-q` 表示同一旋转。不是只翻四元数两个符号，也不是只转换 Euler yaw。AP 在 DDS handler 转换；PX4 复用 `frames.ned_frd_quaternion`。

合法性按 **`abs(sum(q_i*q_i)-1) < 1e-3`**；拒绝等于/超过边界、零、NaN/Inf 和求和溢出。源证据为 `libraries/AP_Math/quaternion.cpp:691–701` 的实际 `length_squared()`；`GCS_MAVLink_Copter.cpp:961–964` 注释写 magnitude，但实现是平方范数，应以实现为准。先校验再归一化，仅清除容差内浮点误差。状态反馈的宽松归一化函数不改；命令新增独立严格校验，避免 PX4 原有 helper 把 `(0,0,0,2)` 悄悄接受。

`u=normalized_thrust` 有限且 `0≤u≤1`，是正升力方向的**无量纲原生 collective demand**，不是 N、m/s、m/s²，也不假定两栈相同输入产生相同加速度：

| 栈 | 原生输入 | 原生后处理 |
| --- | --- | --- |
| PX4 | `VehicleAttitudeSetpoint.q_d` WXYZ NED/FRD；`thrust_body=(0,0,-u)`；OffboardControlMode 仅 attitude 激活 | 原生姿态/速率/混控及电机模型 |
| AP | `set_angle(q_NED_FRD, zero_rates, u, true)`；正 u，不取负号 | `angle_control_run:1163` 调 `set_throttle_out(u,true,throttle_filt)`，含现有倾角补偿/滤波/电机映射 |

PX4 证据：已读 `/root/wksim-px4-state-ONa1Kw/src/msg/versioned/VehicleAttitudeSetpoint.msg`（version 1，负 FRD Z throttle demand）、`dds_topics.yaml:161–162`（实际入口）、`mc_att_control_main.cpp:313–318`（q_d/thrust_body 消费）。AP 倾角补偿见 `AC_AttitudeControl_Multi.cpp:350–363,374–388`。不能把 AP 的标量当作未补偿 body-axis 推力与 PX4 做等效动力学承诺。

AP `GUID_OPTIONS` bit 3（值 8）须在独立实验参数中明确设置并读回，保留其他位；handler 不改参数。实际参数名证据 `ArduCopter/Parameters.cpp:823–828`；`mode.h:1206` 为位定义。`GUID_TIMEOUT` 原生默认 3.0 s，`mode_guided.cpp:1113–1123` 在超时后设水平姿态、零 climb rate，退出 thrust 直通并初始化垂直控制器。0006 不改此恢复逻辑；其发生不等于已回到起点。

消息 header stamp 明确定义为 AP **boot time**，由 `WksimState.time_boot_us` 写入，不能用 Unix/Agent 同步时间。handler 拒绝零、未来、非法纳秒以及超过 250 ms 的时间戳，限制排队旧命令；这不是 epoch/session 机制的替代，#14 的主机隔离仍必需。

## 主机候选与标定/预算

`control.patch` 只涉及 `frames.py`、两适配器、`node.py`，均在私有 `after/control/` 中。新 `native_attitude_profile` 只能为空或 `attitude_thrust_v1`，默认空；既有 `enable_external_attitude` 默认仍 false，两项均需显式打开。AP 消息懒加载，默认 profile 不要求新 overlay。两适配器直接 send 也执行 capability/finite/unit/range 校验，并检查新姿态订阅者；拒绝时不发布 OffboardControlMode 或设定值。现有位置、速度、PV、混合 profile 不会被替换。

这是显式**实验** profile，不是自动固件鉴别；主代理必须先核验构建、消息 overlay、实际加载二进制和运行身份，再把参数交给实验入口。仅设置参数不能证明准入。正式 profile/pins 本轮未更改。

飞行前预算已写 `work/ap-attitude-stage-20260909/flight-budget.json`，状态 `frozen-before-flight-unexecuted`，校验和记录到 `offline-result.json`。两栈分别从稳定位置保持时 3 s 的原生 collective demand 取中位数作为悬停候选；读取并记录模型质量/旋翼/电池、AP angle boost/滤波/电机/hover-learning 参数与 PX4 hover/thrust-model 参数。先做 2 s 水平直通标定，漂移 ≤0.3 m、垂直速度 ≤0.2 m/s；失败标为未标定，不修改验收门槛追着结果调。

预算固定 40 Hz、3 m 初始高度，roll +5° 持续 1 s，0.5 s 后误差 ≤2°（yaw ≤3°）持续 0.4 s；另做水平 `u_hover+0.03`、0.5 s 推力阶跃，末段上升速度相对前段增加 ≥0.05 m/s。每次通过现有 position+yaw 路径恢复到阶跃前 anchor，8 s 内位置误差 ≤0.4 m、速度 ≤0.3 m/s、倾角/yaw ≤3°并持续 1.5 s。越过 4 m 位移、1.5–4.5 m 高度或 15°倾角即按现有 hold/land 失败路径处置并判失败。具体标定数值在每次 run 的阶跃开始前另记，不能将两个栈的 hover 值强行相等。

## 可复现检查与后续执行边界

本轮已通过私有树 `git apply --check --whitespace=error`（native/control 两份）；`python3 -B work/ap-attitude-stage-20260909/check.py` 通过独立旋转矩阵对照、两端默认关闭、40 个非法输入无发布副作用、推力端点与符号、Python AST 检查。这是暂存源的轻量检查；测试录制传输，未创建 ROS 节点。没有声称已编译 C++、验证新消息 CDR 或看到真实飞机响应。

`tools/prepare_ap_attitude_candidate.py` 已提供但**未执行**：核验 mixed 源/二进制清单，在全新 `/root/wksim-ap-attitude-*` 中独立复制、应用 0006，生成 `attitude-source.json` 和独立 `attitude-extra.hwdef`。它不编译、不安装、不准入。取得主代理 RUN RELEASE 后，先运行此工具；候选目录中用已安装 DDS generator 和原 waf 参数构建，额外传 `--extra-hwdef <candidate>/attitude-extra.hwdef`，`--out` 指向新 candidate/build。`--extra-hwdef` 已核对原 `wscript:423–426,516–521`。保留 configure/build 日志及构建前后源码哈希，并把二进制/额外 hwdef 一起封存，不能复用 0005 的身份。

ROS 侧从新候选 `Tools/ros2/ardupilot_msgs` 构建**新的独立 overlay**，另设 build/install/log 目录；不要覆盖 `/root/wksim-dds-VxM6Ni` 或活动控制器安装目录。对 staged `control.patch` 重新 `--check` 后由主代理应用、构建独立控制器 overlay。新 overlay 必须与旧 WksimState/服务保持兼容；需要实际 IDL 生成、CDR roundtrip、native handler 边界（含缺选项/过期/未来/错误 frame）、PV/混合/位置/速度回归，再预约两栈实飞。若基线已变化，按 manifest 拒绝旧补丁/复制，重新审阅差异。

仍未验证：0006 编译与加载身份、新 ROS overlay/CDR、新 native guard 的运行证据、双栈标定与阶跃/恢复、实际电机/姿态/真值，以及主代理最终复核。AP 原生目标日志是执行接线证据，动作完成还需真值与预算评估。
