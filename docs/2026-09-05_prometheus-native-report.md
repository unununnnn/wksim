# Prometheus 原生双飞控控制节点验证

2026-09-05。**同一组 Prometheus 输入已在 PX4 和 ArduCopter 上完成隔离 SITL 任务，51 项自动检查通过。** 这次运行使用安装后的 `prometheus_control` 节点，不再由诊断脚本直接发送飞行控制命令。原始 Prometheus ROS1 文件保持不变；复用已迁移的命令处理和输出修整。

范围为用户授权的本机软件在环实现，普通工程报告，无安全报告 flavor。它不是完整 CopterSim 复刻、联合场景或真机/HIL验收；MATLAB TCP/JSON 传输选择不变，客户端/桥尚未实现，其首期功能范围仍待用户答复。未修改原厂安装、原DDS构建或用户飞控进程。关联 [Wayfinder 移植图](https://github.com/unununnnn/wksim/issues/1)。

## 复现当前通过的任务

在本仓库的 WSL Ubuntu22.04 Bash 中执行；沿用已安装 Humble 和 `/root/wksim-dds-VxM6Ni`。以下工作区均已存在，原生节点来自 `/root/wksim-ros2-0viK3f/install`：

```bash
bash tools/run-prometheus-validation.sh arducopter /root/wksim-dds-VxM6Ni \
  /root/wksim-ros2-0viK3f /root/wksim-ap-dds-yaw-state-4Wr27s
bash tools/run-prometheus-validation.sh px4 /root/wksim-dds-VxM6Ni \
  /root/wksim-ros2-0viK3f
```

启动器强制独立网络命名空间、ROS domain77、回环地址和独立端口；只收尾自己创建的子进程。两次运行是独立实验，不共享场景或权威时间。仿真模型、Agent、飞控、产品节点均有独立日志。

重新构建时执行下列命令，并将打印的新工作区路径代入上面的验证命令。两个脚本均新建工作区，不覆盖旧构建。

```bash
bash tools/build-prometheus-ros2.sh
bash tools/build-ap-dds-yaw.sh /root/wksim-dds-VxM6Ni --with-state
```

已额外实际执行第二条脚本，生成 `/root/wksim-ap-dds-yaw-fJUTtb`，固件和 `ardupilot_msgs` 均构建成功。其固定基线为 `1511f27194f1dcc3728270883047bdf022b3fd53`，两个补丁涉及的11个源码文件与飞行候选 `4Wr27s` 逐文件哈希一致；新二进制SHA256为 `6e666bd73e5add95d3279fbfc08d0b4a47773cc2befaf14a49e70fb8d21c23b2`。新候选尚未执行飞行验证，不能用它替换下文已验证二进制的身份。该目录 `build.log` SHA256为 `525fadff143778e84091a057d7ec59479206f3ea40b0b338efa7456a723b629c`，`ros-build.log` 为 `4ab1f5cc7e285c5d310f2eb8b1493921124d2e233afc5aadf6ee8257fd9a518d`，分别记录固件成功和1个ROS包完成。

全量自动检查必须带真实消息覆盖层并进入隔离网络；不在用户飞控所在的网络中实例化控制节点：

```bash
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-0viK3f/install/local_setup.bash
unshare --net bash -c 'ip link set lo up; ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=78 python3 -m unittest discover -s validation -p "test_*.py" -v'
python3 tools/validate_ap_dds_yaw_boundary.py /root/wksim-ap-dds-yaw-state-4Wr27s
python3 tools/validate_prometheus_evidence.py \
  validation/arducopter-dds-urq9hofr/result.json \
  validation/px4-dds-epf9gukj/result.json \
  validation/prometheus-native-checks-33tTFL70/unit-tests.log
```

最后一个只读核验器检查飞控二进制、仓库/构建副本/安装包七个Python文件及运行工具的哈希；检查两个任务的六条公开输入除时间戳外完全相同，诊断层没有发送原生控制命令，也没有发送设定值；检查产品 `UAVState` 实际经历飞行、降落、失联及恢复。

## 已实现的边界

统一入口为 `/uav{id}/prometheus/setup`、`command`，反馈为 `state`、`control_state`、`text_info` 和 `stop_control_state`。仍使用原 Prometheus 枚举和字段映射。`SET_PX4_MODE` 保留旧字段名，但通过适配器解释；`AUTO.LOITER` 分别映射 PX4自主悬停与 ArduCopter LOITER。本次六条输入依次为自主悬停、普通解锁、COMMAND_CONTROL、ENU `[2,3,3]` 航点、LAND、重连后自主悬停。

| 层次 | 本次实现 | 不能混称 |
| --- | --- | --- |
| 命令受理 | 非零时间戳、最大2秒输入年龄、坐标frame、递增MOVE ID、优先级和能力校验 | 飞控已接受或动作完成 |
| 原生请求 | PX4精确关联命令/时间戳/目标身份ACK；AP异步服务、模式返回值及超时 | 已到达目标 |
| 动作反馈 | 真实模式/解锁反馈；高度、航点驻留、落地与物理真值验证 | 仅消息已发布 |
| 控制生命周期 | 稳态时钟看门狗；失联、重置、离开外部模式不重放旧运动 | 空中失联策略全部验证 |

原生模式切换和任务控制权是不同状态。地面定位可用不代表最终磁航向对齐已完成：PX4先使用原生AUTO.TAKEOFF，完成离地对齐后再预热1墙钟秒并进入OFFBOARD；AP在GUIDED原生起飞期间不发送位置流。两者在原生起飞阶段仅允许单独的偏航对齐重置，延后至少0.5墙钟秒再接管；位置、home或时钟混合重置不能被后来的偏航事件掩盖。进入COMMAND_CONTROL后的任何上述重置仍撤销控制，模式被外部切走也不会自动抢回。

目前默认40Hz输出、2墙钟秒状态超时；计时不依赖ROS `/clock` 是否暂停。`UAVState.header` 为对应飞控boot时间，任务输入header为当前ROS时钟。两者没有被冒充为同一联合场景时间；短时SITL boot时间上限检查、跨运行epoch、统一`/clock`仍属于后续工作。

### ArduCopter 状态扩展

新增独立 `ardupilot_msgs/WksimState` 话题 `/ap/wksim/local_state_v1`，不改变原Status/Pose/GeoPoint的schema或既有topic序号。仅在隔离SITL候选中启用，配套 [0002-dds-local-state.patch](../patches/arducopter/0002-dds-local-state.patch) 和消息覆盖层必须匹配；位置＋偏航还要求补丁0001以及显式 `arducopter_position_yaw=true`。这不是凭版本名或topic发现自动识别能力。

消息同时提供boot微秒、32位滤波器状态、AHRS健康、位姿/速度/home有效标志、home经纬度/原生绝对高度、最后偏航/NE/Down重置时间。AHRS字段在同一次信号量保护下采样；GPS字段另取主GPS快照，不宣称与AHRS严格同采样时刻。位置ENU相对home、线速度ENU、角速度FLU，单位米/秒/弧度。无效字段清零并置无效标志，适配器以NaN和`odom_valid=false`对外表达未知；不会刷新旧坐标冒充有效。

home并非EKF origin；原生高度不冒称WGS84椭球高。地方坐标到全球目标转换使用固定AP的纬度比例和中点经度缩放，限定100m局部范围和绝对纬度≤85°。该状态包不取代完整定位质量/重置事件协议；所有异常尚未做真实传感器故障注入。

## 运行证据

| 指标 | ArduCopter | PX4 |
| --- | --- | --- |
| 最终证据目录 | [urq9hofr](../validation/arducopter-dds-urq9hofr/result.json) | [epf9gukj](../validation/px4-dds-epf9gukj/result.json) |
| 物理最大高度 | 3.0016m | 3.1799m |
| 5秒高度保持窗最大估计误差 | 0.0547m | 0.4974m |
| 物理轨迹最小航点误差 | 0.0215m | 0.0402m |
| 物理最终高度 | 约0m | 约0m |
| 产品状态样本 / 原生接受ACK | 2674 / 6 | 3367 / 6 |
| 地面断流后产品失联状态样本 | 199 | 136 |
| Agent断开3墙钟秒时飞控继续推进 | 9.0仿真秒 | 8.8仿真秒 |
| 恢复到新鲜状态并确认新模式 | 0.933墙钟秒 | 0.368墙钟秒 |
| 子进程全部回收 | 是 | 是 |

沿用已有集成门槛：起飞≥2.5m、高度误差≤0.6m、姿态倾角≤0.35rad、航点误差≤0.5m且速度≤0.5m/s并保持2飞控秒、降落高度绝对值≤0.3m且解除解锁。独立模型真值另检查起飞/航点/落地。本次没有重做三方向偏航驻留测试，也没有把这些控制集成门槛当作CopterSim动力学等价容差。

51项自动检查包含原41项及新增10项，使用真实ROS生成消息；新检查覆盖坐标、四元数、状态有效标志、CDR、home/重置集合、能力拒绝、服务超时、ACK身份、原生起飞与接管分离、优先级停止信号及禁止自动重获控制。它们的记录器不是真实故障注入。偏航C++接入层111条断言在新候选上回归通过。

### 失败记录与修复依据

- [首次AP任务](../validation/arducopter-dds-qd3_uo_v/result.json)在初始起飞偏航对齐时撤销控制；后续原生快照证实是单独yaw重置，改为上述原生起飞阶段等待，未取消活动任务重置保护。
- [首次PX4任务](../validation/px4-dds-38d5b4b6/result.json)在地面等待最终航向对齐而超时。固定源 `EKF2.cpp` / `Ekf::isYawFinalAlignComplete` 明确包含离地磁对齐条件；以`EstimatorStatusFlags`的初始yaw/tilt有效性作为定位门槛，最终对齐仍用于外部控制准入。
- [PX4 POSCTL任务](../validation/px4-dds-zhjmxehu/result.json)普通解锁被原生健康检查拒绝。原生`FailsafeFlags.manual_control_signal_lost=true`，`modeCheck.cpp`要求该模式有手动输入；共同任务明确改用AUTO.LOITER，未发送伪遥控、强制解锁或关闭检查。
- 首次单元测试发现ROS固定数组元素为NumPy标量，不能直接赋给要求Python float的`rel_alt`；在适配边界显式转换后通过。最初网络守卫也曾因未引用shell字符串而拒绝启动，在创建飞控前终止，已修复并保留Python侧二次隔离检查。

## Evidence → Finding → Path

- **E1（file/command）**：[完整检查日志](../validation/prometheus-native-checks-33tTFL70/unit-tests.log)，51 tests / OK，SHA256 `1a22cec8bde3657df4fd52a98a8af09f85d7f38ab5b1fea30cfa129c025ca527`；复现见上方unittest命令。
- **E2（file/log）**：AP最终result SHA256 `49708ddf16724b1fcbc6caaea74f668df0ebc813c356f6e9390b3c280f08fa06`；PX4最终result SHA256 `11ba0b41d11a20894995fae34eb9305b8138acd5a6f47d4d6b3f446284c95832`。完整原生、Prometheus、物理与飞控日志在各结果同目录，复现见两条隔离启动命令。
- **E3（file/source）**：[只读证据审计](../validation/prometheus-native-checks-33tTFL70/manifest.json)核对同输入、静默诊断控制层、产品状态失联/恢复和三份产品源码哈希；源码对照及所有artifact hash保存在manifest。
- **E4（command/build）**：[Humble新工作区构建](../validation/prometheus-ros2-R5Iv5lEh/result.json)47接口/52类型/104次CDR；[候选C++接入层](../validation/ap-dds-yaw-boundary-hjj1ld0x/result.json)111 assertions。AP候选源码固定1511f271，二进制SHA256 `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5`；PX4二进制仍为 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`。
- **F1（validated / high / other）**：在上述固定SITL条件下，Prometheus统一入口可驱动两套原生DDS闭环。依据E1–E4；不推广为所有控制模式兼容。
- **F2（validated / high / design）**：定位就绪、飞控ACK、初始航向对齐和任务接管不可合并为同一布尔成功。依据源码、三次失败日志及E1/E2修复后运行；后续继续用分阶段事件验收。
- **P1（callflow）**：`UAVSetup/UAVCommand → ControlNode → CommandProcessor/SetpointShaper → PX4Link/ArduCopterLink → native ACK + UAVState → independent truth checks`。前三段由E1/E3源代码及单元检查覆盖，后两段由E2/E4覆盖；保留空中失联、运行epoch、多机和未实现能力的风险边界。

## 未完成范围

RC、PID/UDE/NE、reboot、任务/规划/感知demo、完整RflySim工具组织和wksim界面尚未迁移。AP适配首批只开放位置/机体系位置/经纬度位置＋偏航；速度、混合、轨迹和姿态显式拒绝。PX4具备相关输出代码，但本次真实飞行只验收共同位置流程，全球位置转换仍拒绝。命令身份认证、跨运行重放、完整控制权租约、空中DDS失联/故障矩阵、正式ROS2 launch编排、联合场景权威时间、UE产品级状态分发/环境反馈、模型DLL导入、MATLAB桥均未因此完成。原厂及既有固件哈希保持不变，用户ArduCopter PID828仍运行。

Codebase Memory已刷新并查询新节点，实际覆盖和低置信度边在[索引说明](codebase-memory.md)中限定；图节点数不是功能交付量。所有新增源码和证据当前仍为本地未提交文件，未提交或推送混合工作区。
