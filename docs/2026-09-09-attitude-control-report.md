# #34 独立主机姿态候选：构建与离线 guard 通过

2026-09-09。最终候选 `/root/wksim-attitude-control-x3_2v4wb` 已实际 colcon 构建，21 个已安装适配器/生成消息/既有回归方法通过；原生函数体的独立 C++ harness 通过 36 个无副作用拒绝检查。这是明确的 reviewed-patch 实验候选，**不是当前仓库源码等于候选源码的声明，不是运行准入或飞行验收**。

主代理核验会话 `01a083f3-3c70-7ad0-8933-fe7c669ce91b` 实际为 `gpt-6-astra/high`，先收到流水线说明，再发出 RELEASE + RUN RELEASE。使用 ponytail 技能；无嵌套代理。

## 身份与来源

| 项目 | 值 / SHA256 |
| --- | --- |
| sealed OEv 基线 | `/root/wksim-joint-control-OEvS3W/build.json` |
| OEv 清单 | `d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e` |
| 精确 reviewed control.patch | `27224021ddd7f9f1c6078ff3708af76cb436acece33d9a4fb941955a33e63390` |
| 对应原生 attitude-build.json | `bd8257094e6ab21034e7e6982835d833441d22582c0324b22fe8aa13fa0a4fe4` |
| 最终主机构建清单 | `95078a02b863b0307832ae9eb8aad6025a6dd0a88b34506983ae5e3cd43cf8d0` |
| 最终主机验证清单 | `4ed5331deac4a20b2fac59d0545df8e5de10ecf6535b4b6d485f94fea30c662c` |

可审阅副本在 `validation/attitude-control-x3_2v4wb/`。`attitude-control-build.json` 逐项保存基线与修改后完整包哈希、9 个 Python 文件安装哈希、CMakeLists/package.xml/入口脚本等输入、原仓库完整包哈希、构建脚本/日志、消息覆盖层及 patch 身份。验证清单封存测试代码、已有回归来源、生成 harness、编译日志、运行结果和反向补丁证明。

构建器先验证 OEv 源码、安装源码、构建输入和原日志均匹配 sealed manifest；完整复制其 `src/prometheus_control` 到新候选的 `tree/ros2/src/prometheus_control`，之后才应用精确补丁。4 个改动文件的前后哈希匹配 staging manifest，其余文件逐字节不变。构建前及独立验证时均对私有副本执行 `git apply --reverse`，恢复后的**整个包**与 sealed OEv 完全一致。

原仓库控制包、OEv 源码/安装包/清单/日志在构建及验证后重新核验未变。没有修改 FVM、现有 profile、原生补丁或任何旧安装 prefix。没有调用通用 `joint_control_candidate` 的“仓库=安装”准入来放行此补丁候选，也没有放宽它的检查。

## 实际构建与安装来源

`tools/build_attitude_control_candidate.py` 在全新 `/root/wksim-attitude-control-*` 下写入私有 build/install/colcon-log，以 sequential colcon 和两个编译工作线程的上限构建 `prometheus_control`；最终 build.exit 为 0。只 source Humble、本项目既有 PX4 消息、common messages，以及新的 AP attitude messages；没有全局安装。

实际测试进程记录的导入位置为：

- control：`/root/wksim-attitude-control-x3_2v4wb/install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control`；测试显式核验全部 9 个模块来自该位置。
- AP messages：`/root/wksim-ap-attitude-msgs-qOmnF9fT/install/ardupilot_msgs/local/lib/python3.10/dist-packages/ardupilot_msgs`；显式核验来自该新 overlay，并检查此前原生构建清单封存的 overlay 内容。
- PX4 messages：`/root/wksim-dds-VxM6Ni/ros-install/px4_msgs/local/lib/python3.10/dist-packages/px4_msgs`。
- prometheus_msgs / wksim_msgs：`/root/wksim-ros2-MUlZd0/install/` 中各自 package。

初次私有候选 `qsttx4bb` 已通过同样构建与 21 个测试。补充实际消息模块 import-path 记录后重新生成最终 `x3_2v4wb` 候选和 seal；两次均成功，没有失败构建或失败测试。旧私有证据保留。

## 离线验证覆盖

`validation/test_attitude_control_candidate.py` 导入完整的**已安装适配器模块**和实际生成 ROS 消息，使用已有 recording transport；不初始化 ROS 节点。

- 两栈适配器默认拒绝姿态，AP 默认不创建新姿态 publisher；非法 profile 被拒。单独的 CommandProcessor external-control 开关默认拒绝，明确打开两个开关后接受并生成可发送目标。
- 四元数长度/零值/非单位值/非有限值/溢出、推力非有限值及 `[0,1]` 外输入、上下平方范数阈值相邻浮点数均检查；所有拒绝逐次对照先前已发布消息，PX4 OffboardControlMode 也不能出现部分发布。
- 检查缺订阅者、过期/失效时钟、AP 缺状态及无效 odometry 的无发布拒绝。
- 生成 ROS codec roundtrip 检查推力 0、0.375、1，以及正负等价四元数。AP 保持 map ENU/FLU、正 collective demand 和 boot stamp；PX4 只激活 attitude，输出 FRD 负 Z demand；用独立旋转矩阵核验基变换。
- 10 个既有 NativeTests 与 7 个 PV/mixed 方法原样复用，覆盖位置、速度、完整 PV、混合 XY velocity/Z position、body capture、输入/就绪拒绝、state codec、ACK 与超时等。两个启动真实 ROS 节点的方法未选入；源代码专用测试 wrapper 不适用于安装候选，因此只提取指定回归方法原体，并先核验本次 installed import path。没有修改其断言。

`tools/verify_attitude_control_candidate.py` 另核验原生完整 source snapshot，再从该候选提取 `handle_attitude_control`、`set_attitude_and_thrust`、`ready_for_external_control` 原函数体，以 `g++ -std=c++17 -Wall -Wextra -Werror` 编译。使用实际生成消息 struct，覆盖缺 external-control、未 Guided/armed、缺 thrust option、错误 frame、负/零/非法/未来/过期时间戳、非单位/NaN/Inf/溢出、推力越界，以及直达 Copter setter 的独立拒绝；检查 250 ms 恰好边界可接受、端点推力、变换和零 body-rate 参数。36 个拒绝均未调用 recording set_angle。

这个 C++ harness 的 Quaternion 运算、时钟、Guided option accessor、motors 与 set_angle 是明确的 stub。它验证真实函数体分支，**不验证 AP_Math 本体、GUID_OPTIONS 参数存储、Guided 调度、日志时间戳、电机或实际飞控执行**。之前原生构建/跨 ROS-native CDR 的证据仍见 `2026-09-09-attitude-build-report.md`。

## 重现与剩余边界

在 WSL Ubuntu-22.04 项目目录运行：

```sh
python3 -B tools/build_attitude_control_candidate.py
python3 -B tools/verify_attitude_control_candidate.py <printed-candidate-root> <printed-build-manifest-sha256>
```

构建器始终新建私有 prefix；验证器只接受显式 build manifest SHA，并拒绝覆盖已有 verification 目录。工具中的 sealed OEv、reviewed patch 和原生 manifest pins 是本次实验的具体来源，不是通用绕过入口。

没有启动 SITL、FC、GCS、模型或 ROS 节点，没有改生产准入、提交或 Issue。运行身份、真实 GUID_OPTIONS 读回、原生 runtime guard、双栈标定/姿态与推力阶跃/恢复/真值验收仍需主任务完成；本结果不能关闭 #34。
