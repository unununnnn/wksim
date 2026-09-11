# #59 e0 dynamic budget source map

状态：只读证据盘点；不构成预算批准，也不改变 `e0`、R1 或同源命令合同。

## 范围和计数

当前 `e0` 输出总数为 120。扣除保留槽位和接口/状态元数据后，仍待处理的 dynamic observable 为 56 个：53 个语义数据量和 3 个时间字段。下面九行互斥覆盖这 56 个量。槽位范围为闭区间，并沿用 [numerical-conformance-v1.json](../../Simulator/wksim_core/numerical-conformance-v1.json) 的既有命名。

这里的 `source_mapping` 只用于定位生成 C++、模型端口和已有资料。它不能把 R1 的差值、候选输出或已有阈值转化为新的工程预算。

机器可校验的逐槽展开位于
[`e0-source-to-slot-manifest-20260911.json`](../../validation/e0-source-to-slot-manifest-20260911.json)，
其结构由
[`59-e0-source-to-slot-manifest.schema.json`](59-e0-source-to-slot-manifest.schema.json)
约束。生成器和离线校验器分别是
[`generate_e0_source_to_slot_manifest.py`](../../tools/generate_e0_source_to_slot_manifest.py)
与
[`validate_e0_source_to_slot_manifest.py`](../../tools/validate_e0_source_to_slot_manifest.py)。
私有 ZIP/SLX 不进入 Git；干净 checkout 的严格校验和外部 artifact 根目录约定见
[`59-e0-artifact-portability.md`](59-e0-artifact-portability.md)。
该 manifest 为 schema v2：历史 R1 的 `cpp:` 行号已逐槽解析为精确
`line_ranges`，并绑定到仓库内冻结的 Model 11.0 ZIP 及其成员 SHA-256。校验器直接从
ZIP 成员流式计算哈希，不解压到文件系统；归档路径、归档哈希、成员路径或成员哈希任一漂移都会失败关闭。
当前 SLX 11.8 的路径和哈希只固定来源身份，逐槽同源行号映射保持
`unresolved`，直到从当前生成源码重新推导，不能复用历史 11.0 行号。
其余未绑定的版本、hash、frame 与 datum 保持 `null`，并逐项列入 `unresolved_fields`。

## 分组证据盘点

| 子系统 / 槽位 | source_mapping 和现有来源 | 可用于后续工作的证据 | 明确缺失 | owner 决策与最小工件 |
|---|---|---|---|---|
| 时间字段：`Vehicle[2]`、`Sensor[0]`、`GPS[0]` | `vehicle_time`、`sensor_time`、`gps_time`；生成 C++ 时间赋值位置在 `numerical-conformance-v1.json` 中；[reference sampling contract](../2026-09-09-reference-sampling-contract.md) 固定采样点、端点和保持方式 | 可固定采样相位、时间字段的来源位置和样本顺序；可单独形成调度/时间语义检查 | 权威时钟语义、时间戳生成误差、时间字段是否属于物理准确度比较 | 决定时间字段单独做调度检查还是进入 abs/rel/RMS；生成 `time-field manifest` 和调度检查说明 |
| 刚体状态：`Vehicle[3:11]`、`Vehicle[24:29]` | `velocity_ned`、`position_ned`、`euler_components`、`body_motion_acceleration`、`body_angular_rate`；生成 C++、6DOF MKS、VelE、Abb 位置见 source mapping；[quad parameters report](../2026-09-09-quad-parameters-report.md)、[model parameters](../../Simulator/wksim_core/model_parameters.py)、[model reference provenance](model-reference-provenance.md)、[wksim core README](../../Simulator/wksim_core/README.md) | 名义参数、单位/坐标系、模型方程位置、求解器实现和采样配置；README 明确 Vehicle 加速度是 body-frame velocity derivative，不等同于 IMU specific force | 参数不确定度、状态域、导数/稳定性界、舍入传播、接触/饱和/随机事件域、可追溯参考真值 | 固定适用状态域和事件策略；决定位置/速度/加速度/角速率的度量；生成 `solver-domain manifest` 和逐量推导记录 |
| 姿态度量：`Vehicle[12:15]` | `quaternion_components`；生成 C++ 采用 DCM→Quaternion→`fix_quat_sign`；README 给出 wxyz、NED/FRD 约定 | 可确认输出排列、局部坐标标签和符号修正步骤 | 四元数方向、符号等价类、范数要求、分量误差与姿态角误差之间的关系 | owner 选择分量度量或 invariant angle/geodesic 度量；生成 `quaternion semantics/metric record` |
| 电机/执行器：`Vehicle[16:23]` | `active_motor_speed`、`extra_motor_speed`；电机输入映射、推力/力矩/陀螺项和 Quad X 方向见 [quad parameters report](../2026-09-09-quad-parameters-report.md)；名义参数见 [parameter correspondence](../../validation/model-reference-provenance-20260907/parameter-correspondence.json) | 可确认输入映射、转子方程、参数单位和 active 输出的生成位置 | 电机/转子校准、RPM 参考测量、参数不确定度、真实输入包线；extra/inactive 槽位的独立语义 | 决定 active 与 extra 是否分别比较，以及 inactive 是否应定义为非活动输出；生成 `actuator calibration/source manifest` |
| 车辆地理真值：`Vehicle[30:32]` | `truth_latitude_longitude`、`truth_altitude`；PosGPS 生成位置和初始地理参数见 [parameter correspondence](../../validation/model-reference-provenance-20260907/parameter-correspondence.json) | 可确认经纬度/高度的输出路径、初始名义值和模型端口 | WGS84/其他 datum、椭球高/海拔基准、地理参考不确定度，以及与 GPS 字段的真值关系 | 决定 datum、altitude convention 和与 GNSS 的比较关系；生成 `geodetic reference manifest` |
| IMU 加速度/陀螺：`Sensor[1:6]` | `accelerometer`、`gyroscope`；HILSensor30d、生成 C++ 位置和已有噪声配置见 [numerical contract readiness](2026-09-08-numerical-contract-readiness.md)；通用标定资料索引见 [G6 material index](../g6-material-index.md) | 可确认端口、单位、帧、随机源配置位置和通用校准方法；可用于定义待补证据清单 | 当前 e0 绑定的标定、噪声/延迟模型、随机算法和 reset phase、安装外参、测量不确定度；[ops-08](full-contracts/ops-08.md) 与 [ops-09](full-contracts/ops-09.md) 明确当前模型不足 | 决定比较 noisy/noiseless 输出、seed 对齐、specific-force 语义和适用域；生成 `per-sensor calibration/noise/latency manifest` |
| 磁场：`Sensor[7:9]` | `magnetic_field`；生成 C++ 位置和 nT→Gauss 转换见 `numerical-conformance-v1.json`；噪声配置见 [numerical contract readiness](2026-09-08-numerical-contract-readiness.md) | 可确认转换路径、单位和模型噪声配置位置 | WMM 模型身份、日期、位置、坐标系、磁场参考和误差；磁力计校准与安装外参 | 决定 WMM 版本/日期和 field reference；生成 `WMM provenance + calibration record` |
| 气压/温度：`Sensor[10:13]` | `absolute_pressure`、`differential_pressure`、`pressure_altitude`、`temperature`；Pa/hPa 与 K/°C 转换、生成 C++ 位置和噪声配置见 [numerical contract readiness](2026-09-08-numerical-contract-readiness.md) | 可确认端口、单位转换、模型参数和随机源位置 | 压力/温度传感器规格、校准误差、压力 datum、静压/差压关系、温度适用域和压高定义 | 决定比较 pressure altitude 还是 geodetic truth altitude，并固定 datum/单位；生成 `baro/temp traceability manifest` |
| GNSS：`GPS[1:10]` | `gps_latitude_longitude`、`gps_altitude`、`gps_accuracy_indicators`、`gps_horizontal_speed`、`gps_velocity_ned`、`gps_course_encoded`；生成 C++、初始地理参数、噪声/滤波器配置见 [numerical contract readiness](2026-09-08-numerical-contract-readiness.md) 和 [model reference provenance](model-reference-provenance.md) | 可确认各字段的生成位置、单位/缩放位置、origin 配置、随机源、滤波器配置和待核对的 course 编码 | 接收机或外部参考精度、datum、altitude convention、eph/epv 语义和缩放、course 零点/方向/环绕规则、滤波器初始化与时间对齐 | 决定每个 GNSS 字段的物理语义和 metric；生成 `GNSS reference/noise/filter manifest` |

## 统一缺口判断

以下材料目前只能证明模型实现、名义参数、采样配置或一般标定方法，不能单独产生已批准的工程上界：

- [10-g6-remediation-contract.md](10-g6-remediation-contract.md) 要求预算来自显式误差分析、校准/传感器规格和用途要求；当前尚未完成这些绑定。
- [2026-09-08-numerical-contract-readiness.md](2026-09-08-numerical-contract-readiness.md) 记录了模型噪声、种子和增益配置，但这些是输入/模型配置，不是实现误差或物理准确度预算。
- [model-reference-provenance.md](model-reference-provenance.md) 和 `parameter-correspondence.json` 记录名义方程、端口和参数，不包含参数不确定度或独立物理真值。
- [g6-material-index.md](../g6-material-index.md) 中的传感器标定课程、脚本和样本数据是通用方法资料，不是当前 e0 传感器的序列号绑定、规格、校准证书或适用域证明。
- [ops-08](full-contracts/ops-08.md) 与 [ops-09](full-contracts/ops-09.md) 已将当前传感器 calibration/noise/latency/fault model 标为缺口。

## 明确禁止的推导路径

本工件不从以下内容反推或批准任何 abs、rel 或 RMS 数值：

1. 冻结的 R1 输出差值、R1 容差或任何历史比较结果。
2. 未来候选输出、探针输出、示例日志或未批准的参考运行。
3. 仅凭 RK4 阶数、步长、网格收敛或机器 epsilon 推定误差常数。
4. 仅凭模型噪声幅度、随机种子、增益或传感器课程资料推定最终 observable 的实现预算。

因此 56 项仍保持 `unresolved/blocked`；本文件没有填写或批准任何预算数值。

## Owner 决策清单

1. 固定每个 observable 的参考真值、单位、坐标系、datum、sample phase 和适用状态域。
2. 选择 abs/rel/RMS 的 metric；明确姿态是否使用 invariant metric，course 是否进行角度环绕处理。
3. 决定模型随机噪声、传感器误差、延迟和 reset/seed 是否进入比较，以及如何与数值误差分开归因。
4. 提供并批准模型参数不确定度、传感器规格/校准/外部参考不确定度和适用域。
5. 明确 Vehicle body acceleration 与 IMU specific force 的不同语义，避免跨量比较。
6. 明确 Vehicle 地理真值与 GNSS 的 datum、高度基准、accuracy 字段和 course 编码语义。
7. 明确 active/extra motor 槽位是否都属于对外契约，以及 inactive 槽位的语义。
8. 在证据完整后，逐项批准 bound derivation、执行前预算和版本/hash 绑定。

## 最小后续工件

完成 owner 决策后，按以下顺序生成工件；缺证据的字段必须继续标记为 `unresolved`：

1. `source-to-slot manifest`：slot、source_mapping、源码路径/行号、版本/hash、单位、frame、datum、sample phase。
2. `parameter-noise-domain manifest`：名义参数、噪声配置、随机/reset 语义、状态域、事件条件和证据链接。
3. 每个子系统的 `bound-derivation note`：说明参考量、误差分解、传播方法、适用域和未决项；不允许用 R1 或候选差值补洞。
4. `owner-approval record`：记录 metric、传感器语义、地理基准、时间处理、inactive 输出和批准状态。
