# Prometheus 输出修整迁移验证

2026-09-05，普通工程报告（flavor=null）。

## 结论与限制

已在 `prometheus_control` 中新增独立的 `SetpointShaper`，移植原Prometheus速度死区、按轴位置保持、偏航保持、混合位置/速度及其他目标的有效字段组织。全新Humble两包构建与40项回归通过；原C++输出方法对照332组，其中286组等价字段通过、46组验证有意修复差异。等价组最大有效字段绝对差 `2.7890144638220704e-8`，低于预先写入脚本的 `abs_tol=2e-5, rel_tol=1e-6`。

**这是控制输出逻辑验证，不是动力学验收、MAVROS线格式联测或真实双飞控任务。** 本阶段未启动飞控、UE或MATLAB。完整PID/UDE/NE、RC、任务节点、原生DDS产品适配、联合场景时钟等仍未完成；不存在“332组全部与旧实现完全一致”的结论。

范围沿用[已确认运行边界](sitl-runtime-proposal.md)与[完整复刻目标](coptersim-reconstruction.md)。仅新增wksim代码/验证材料，保留固定Prometheus原文，不改本机厂商安装，不安装新依赖，不提交或推送。Wayfinder的MATLAB功能范围仍等待用户答复，本阶段没有替用户关闭该决策。

## 来源与实现

上游提交仍为 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`。原 [uav_controller.cpp](../Modules/uav_control/src/uav_controller.cpp) 的754–864行输出分派和1117–1637行输出方法，以及 [math_utils.h](../Modules/common/include/math_utils.h) 的RPY到四元数方法直接参与验证编译。生产实现为 [shaping.py](../ros2/src/prometheus_control/prometheus_control/shaping.py)，只用Python标准库；不引入MAVROS运行依赖。

| 输入工况 | 保留的输出规则 | 激活轴表示 |
| --- | --- | --- |
| XYZ速度全部进入死区 | 固定XYZ位置 | 位置3轴有效、速度不激活 |
| 仅Z速度有效 | 保持XY位置、输出Z速度 | 位置XY与速度Z有效 |
| X/Y至少一轴运动 | 静止平面轴按保持误差修正速度；Z静止时保持高度 | 全速度有效，按需激活位置Z |
| XY速度+Z位置 | 静止平面轴保持/修正，采用指定高度 | 全静止时位置XYZ；否则速度XYZ与位置Z |
| yaw-rate速度输入 | 原样组织速度和偏航角速度 | 不施加yaw角保持 |
| 轨迹/加速度/姿态/全局目标 | 保留各自有效字段；RPY转换FLU四元数，全球高度相对home | 不混用不同类型字段 |

`None`表示某个轴不激活，不表示数值零。TRAJECTORY仍按原输出方法只启用位置/速度，没有把原来未使用的加速度参考擅自变成前馈。详细接口、校准参数及生命周期见[包说明](../ros2/src/prometheus_control/README.md)。

## 显式修复与差分规则

1. 原速度条件和yaw变化可提前 `return`，导致部分步进不发布。本实现当步更新保持状态后输出；43个预先标明的工况复现了旧输出缺失、新输出存在。
2. 原混合模式写 `move_orient`、检查 `move_xy_orient`，读 `prev_vel_sp`、写 `prev_vel_xy_sp`。本实现独立保存模式状态，并在轴由运动转保持时捕获该轴当前位置；1组对照验证不再向旧Y锚点产生修正速度。
3. 原XYZ yaw-rate分支未清理速度保持状态。本实现切入该分支清理历史；1组对照验证回到位置保持时采用新位置，而不是更早的锚点。
4. 原 [uav_estimator.cpp](../Modules/uav_control/src/uav_estimator.cpp) 的610–617行给状态叠加共享平面偏移，1189–1223行说明了本地/共享坐标关系；旧速度保持却直接使用共享位置。本实现要求 `CommandProcessor.local_position()`；1组非零偏移对照验证了本地目标。

其他轴保持不因无关轴速度改变而重置，另有单元检查。旧实现未初始化的Eigen历史缓存由验证壳明确清零，使对照初态可重复；**不声称重现原程序的未定义初态**。稳态规则与有意变化分别计数，比较时检查有效字段集合及数值，不能只挑非零值比较。

## 验证方法与复现

oracle从固定Git对象直接抽取原方法，不把新Python逻辑重写成另一个“参考实现”。输出落到内存记录器，仿照被使用的MAVROS字段宽度、掩码和坐标值；它不包含真实MAVROS序列化、发现或发送。字段定义经官方 [PositionTarget](https://raw.githubusercontent.com/mavlink/mavros/ros2/mavros_msgs/msg/PositionTarget.msg)、[AttitudeTarget](https://raw.githubusercontent.com/mavlink/mavros/ros2/mavros_msgs/msg/AttitudeTarget.msg)、[GlobalPositionTarget](https://raw.githubusercontent.com/mavlink/mavros/ros2/mavros_msgs/msg/GlobalPositionTarget.msg)核对。

使用现有Ubuntu22.04/Humble、Python3.10.12、GNU C++11.4.0、ament1.3.14和Eigen3，C++17/O2/禁用fast-math。固定种子5616生成332组：XYZ轴组合192组、混合轴48组、其他直接输出84组、显式修复序列8组。误差容限只针对这些输出字段的表示/计算差，不是模型精度门槛。

Windows PowerShell构建：

```powershell
wsl.exe -d Ubuntu-22.04 --exec bash /mnt/c/Users/PC/Documents/odid编译/wksim/tools/build-prometheus-ros2.sh
```

WSL Bash运行本次已验证安装（重建后应使用脚本打印的新目录）：

```bash
source /root/wksim-ros2-ByQNy1/install/setup.bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
python3 -m unittest validation.test_wksim_core validation.test_sitl_dds validation.test_ue55_bridge validation.test_prometheus_interfaces validation.test_prometheus_control -v
python3 -m tools.validate_prometheus_commands
python3 -m tools.validate_prometheus_shaping
```

每次生成独立证据和构建目录。构建脚本 `exit-code.txt=0`，差分结果 `status=pass` 才算该链路成功。验证工具拒绝从仓库直接导入或安装模块与源码不同。开发中差分脚本首次启动因列表括号语法错误退出，尚未进入用例；修正后才得到下列实际执行证据，没有通过放宽容差掩盖失败。

## Evidence

路径相对于wksim根目录。每条 `linked_workitem` 为 [Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1) 的已授权实施；`supersedes=none`，旧证据保留。

### E-001 生产源与原始规则

- title: 可校准的保持规则、有效轴和明确的状态修复。
- observed_at: 2026-09-05 UTC。
- source_type: file。
- source_ref / artifact_path: `ros2/src/prometheus_control/prometheus_control/shaping.py`。
- content_hash: `56782d96f9fc6f7df3ddadf80cd8c09f474af81c5c183d20d3d26c2f9e66bc69`。
- repro_command: `sha256sum ros2/src/prometheus_control/prometheus_control/shaping.py`；按上面的固定Git提交只读核对原输出与估计器方法。
- raw_excerpt: `if held[axis] and not self.held[axis]: anchor[axis] = position[axis]`。
- 仓库、`/root/wksim-ros2-ByQNy1/src/prometheus_control/prometheus_control/shaping.py`及其安装文件三者哈希一致。

### E-002 构建与回归

- title: 两包构建、16项命令/修整检查、40项完整回归及原102组命令对照通过。
- observed_at: 2026-09-05 UTC。
- source_type: log。
- source_ref / artifact_path: `validation/prometheus-ros2-LiPsiZ5H/all-tests.log`。
- content_hash: `c33a9f019c1497e5ccd8bcb2dc38a37f8f4d9c33469633a8d3a3ef00ae39f6d6`。
- repro_command: 上述构建、完整unittest与 `python3 -m tools.validate_prometheus_commands`。
- raw_excerpt: `Ran 40 tests in 2.519s; OK`。
- 同目录 `build.log` SHA256 `981b271486779d3c0b6266149da855130983aea03d402e6acf7064e7c2f39fab`；接口RMW/CDR `result.json` SHA256 `2060ea30ef9505b04d1f768707d1bad99bae1bec32ea3126683e24c2c38405ad`，47项/104次通过。新的命令对照 `validation/prometheus-command-hblqqy_3/result.json` SHA256 `594087fdc2f8c7f7ebe56e627870550d3a5110889255c908ff8aa1cf1476ca69`，102组通过。

### E-003 原C++输出对照

- title: 286组等价字段与46组预声明修复差异。
- observed_at: 2026-09-05T07:52:20Z。
- source_type: file。
- source_ref / artifact_path: `validation/prometheus-shaping-l4zugvfp/result.json`。
- content_hash: `4001a04d982d7787dda8af27114d75c01ca04b0eb924af1c1080db830cbb8cbe`。
- repro_command: `python3 -m tools.validate_prometheus_shaping`。
- raw_excerpt: `cases=332; equivalent_cases=286; transition_output_gap=43; held_axis_recapture=1; rate_history_reset=1; offset_normalization=1`。
- `comparisons.json`完整记录每组原始/新输出和差异原因，SHA256 `43c64a077fa4ad0abb65e8f32e1e198540a7a1e9b36b159a9056d4fe2c30f67c`。结果文件另含输入、输出、编译日志、生产/测试/oracle源码哈希与实际安装模块路径。

## Findings 与路径

### F-001 有来源可对照的输出层

- severity: n/a_re；category: other；status: validated；confidence: high。
- evidence_ids: [E-001, E-002, E-003]。
- location: `SetpointShaper.shape`、`SetpointShaper._velocity`。
- impact: 上游输出规则能在无MAVROS的独立库中计算，四类状态/坐标修复有明确证据；不意味着两套飞控已接收这些输出。
- repro_steps: 构建后运行两套差分与完整回归，分别核对等价组和预声明差异组。
- remediation: 接入原生飞控能力转换、控制权/保活/确认与Prometheus任务，再进行真实SITL验证。
- optional_attack: n/a。

### P-001 命令到控制目标

- path_type: callflow。
- start: 生成的Prometheus消息与有效本地状态。
- goal: 得到可交给飞控适配器的、有效轴明确的控制目标。
- steps:
  1. action: `CommandProcessor.step`计算参考量；evidence: E-002；finding: F-001。
  2. action: `local_position`移除共享平面偏移，`SetpointShaper.shape`处理死区、保持和目标类型；evidence: E-001, E-003；finding: F-001。
  3. action: 比较原C++有效字段，单独检查状态转换修复和停止清理；evidence: E-002, E-003；finding: F-001。
- residual_risks: 仍需宿主管理状态新鲜度、运行/epoch和坐标重置；部分飞控可能不支持某些混合激活轴，须显式拒绝或经已验证的语义转换，不能静默降级。控制库本身无网络保活或模式确认。

Codebase Memory已刷新到07:54:03 UTC，45,281节点/146,213边；实际新方法定位与 `metadata_changed` 限制见[索引说明](codebase-memory.md)。这些计数不代表完整Full功能完成比例。
