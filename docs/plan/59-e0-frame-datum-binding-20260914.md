# #59 e0 动态槽 frame/datum 绑定补充（G6/B2）

2026-09-14（含 2026-09-14 独立复核后的修正）。这是**纯离线补充工件**：只把已提交文本里**逐字存在**的坐标系与基准绑定到 56 个 dynamic 槽上。它不产生、不推导、不批准任何 `abs_budget`、`rel_budget`、`rms_budget`、单位、frame、datum 或 owner 决策。

对应阻塞项见 [g6-c3g-stage2-boundary.md](g6-c3g-stage2-boundary.md)：本切片只处理 **B2**，不触碰 B1（预算）、B3（时间规则裁定）、B4（新同源合同冻结）、B5（首步求解边界）。#59、#60、G6、Full 仍开放，R1 仍 `numerical_failed`。

机器可校验文件：[`e0-frame-datum-binding-20260914.json`](../../validation/e0-frame-datum-binding-20260914.json)；离线校验器：[`test_e0_frame_datum_binding.py`](../../validation/test_e0_frame_datum_binding.py)；独立复核产物：[`deepseek-g6-frame-datum-review-20260914-01/`](../../validation/coordination/deepseek-g6-frame-datum-review-20260914-01/)。复核目录只含离线读验证脚本与报告：本切片**不保留生成器**，payload 由校验器逐项重算，而不是由脚本重写。

## 保守绑定原则

复核后收紧的硬规则：**不允许把互不相干的坐标标签组合成方向、标量坐标系或原点结论。**

1. 只有提交文本**明确标注该量本身**为 NED / 机体系 / 比力 / 角速度时，才绑定 `NED` 或 `FRD`。
2. **标量不得**获得 `FRD` / `NED`：电机转速是标量 rpm，`gps_horizontal_speed` 是标量幅值；旋翼安装位置写作 `position_FRD` 不构成标量输出的坐标系。
3. 姿态**方向**不绑定：欧拉与四元数的"机体相对 NED"方向没有提交文本直接陈述；源映射明确把"四元数方向"列为缺失，R1 `unverified_boundaries` 同样列出。`Simulator/ue55/README.md:37` 描述的是 UE 显示字段，仅作 EV-18 上下文保留。
4. 机体角速度的 datum **不称**为模型局部 NED 原点；无提交文本支持。
5. 提交文本只写 `latitude,longitude` / `degree` 时，不自称 geodetic；token 定名 `lat_lon_deg`。

## 范围与槽位集合

沿用 [numerical-conformance-v1.json](../../Simulator/wksim_core/numerical-conformance-v1.json)（`contract_id` `wksim-e0-fixed-reference-native-preservation-v1`）的既有命名：

| 集合 | 数量 | 判定 |
| --- | --- | --- |
| 全部槽位 | 120 | `Vehicle60 + Sensor30 + GPS30` |
| dynamic 槽位 | **56** | `semantic_status` 不属于 `interface_metadata` / `reserved_not_physical_coverage` |
| — 语义量 | **53** | 非 `schedule_metadata` |
| — 时间字段 | **3** | `vehicle_time` `sensor_time` `gps_time`（`schedule_metadata`） |
| excluded 槽位 | **64** | `interface_metadata`（5 槽）+ `reserved_not_physical_coverage`（59 槽） |

56/64 由校验器从**冻结合同在 HEAD 的 blob** 重算并逐项比对；缺、重、多、或混入保留槽一律失败关闭。

## 受控词表（只允许这些取值）

frame 与 datum 只能取下列 token；token 集合与每 observable 的绑定都被校验器**独立冻结**，JSON 不能自行扩表。

### frame（3 个）

| token | 含义 | 已提交原文 |
| --- | --- | --- |
| `NED` | 模型局部北-东-地；仅用于提交文本标注为该坐标系的**矢量** | `Simulator/wksim_core/README.md:52` 位置/速度为 NED；`Simulator/wksim_core/state_stream.py:10` `position_frame="NED"`；`Simulator/wksim_core/model.py:110` coordinates NED / FRD；`model_parameters.py:33` `"m; NED"`；readiness `:105` Ve，m/s，NED；readiness `:106` Xe，m，NED |
| `FRD` | 机体前-右-下；仅用于提交文本标注为机体系 / 比力 / 角速度的**矢量** | `README.md:52` 角速度和比力为 FRD；`state_stream.py:11` `body_frame="FRD"`；`model.py:110` coordinates NED / FRD；readiness `:110` 机体系运动加速度；readiness `:111` wb，rad/s，机体系 |
| `lat_lon_deg` | 以度为单位的经纬度对；不称 geodetic | `model_parameters.py:37` `"degree; latitude,longitude"`；合同 native_unit `1e-7 degree per native unit`；`gnss_event.py:64` lat, lon |

### datum（2 个）

| token | 含义 | 已提交原文 |
| --- | --- | --- |
| `model_local_NED_frame_reference` | NED 位置的原点；NED 速度的静止基准（不用于机体角速度） | `model_parameters.py:33` `"m; NED"`；readiness **`:88`** `ModelInit_PosE=[0,0,-10] m` |
| `degC_zero_at_273.15000000000003_K` | 摄氏标度，零点为生成源码减去的 `273.15000000000003` | 合同 `subtract 273.15000000000003`；`e0-current-rhs-references-20260912.json` `273.15000000000003` |

`model_local_NED_frame_reference` **不表示**任何大地基准、椭球或海拔零点，也不是机体角速度的零位（OD-24）。

## 逐量绑定结果

`—` 表示**显式未绑定**，每个都带精确 owner 决策编号，不是通过。

| observable | 索引 | 合同 native_unit | frame | datum | 未决 owner 项 |
| --- | --- | --- | --- | --- | --- |
| `vehicle_time` | 2 | s | — | — | OD-01, OD-02 |
| `velocity_ned` | 3,4,5 | m/s | NED | model_local_NED_frame_reference | OD-22 |
| `position_ned` | 6,7,8 | m | NED | model_local_NED_frame_reference | OD-22 |
| `euler_components` | 9,10,11 | rad | — | — | OD-16 |
| `quaternion_components` | 12,13,14,15 | 1 | — | — | OD-15 |
| `active_motor_speed` | 16,17,18,19 | rpm | — | — | OD-19 |
| `extra_motor_speed` | 20,21,22,23 | rpm | — | — | OD-19, OD-20 |
| `body_motion_acceleration` | 24,25,26 | m/s^2 | FRD | — | OD-21 |
| `body_angular_rate` | 27,28,29 | rad/s | FRD | — | OD-24 |
| `truth_latitude_longitude` | 30,31 | degree | lat_lon_deg | — | OD-03 |
| `truth_altitude` | 32 | m | — | — | OD-04, OD-05 |
| `sensor_time` | 0 | us | — | — | OD-01, OD-02 |
| `accelerometer` | 1,2,3 | m/s^2 | FRD | — | OD-17, OD-18 |
| `gyroscope` | 4,5,6 | rad/s | FRD | — | OD-17, OD-18 |
| `magnetic_field` | 7,8,9 | gauss | — | — | OD-06, OD-07 |
| `absolute_pressure` | 10 | hPa | — | — | OD-08, OD-09 |
| `differential_pressure` | 11 | hPa | — | — | OD-08, OD-09 |
| `pressure_altitude` | 12 | m | — | — | OD-04, OD-05 |
| `temperature` | 13 | degC | — | degC_zero_at_273.15000000000003_K | OD-10 |
| `gps_time` | 0 | us | — | — | OD-01, OD-02 |
| `gps_latitude_longitude` | 1,2 | 1e-7 degree per native unit | lat_lon_deg | — | OD-03 |
| `gps_altitude` | 3 | 1e-3 m per native unit | — | — | OD-04, OD-05 |
| `gps_accuracy_indicators` | 4,5 | native scaled double | — | — | OD-11, OD-12 |
| `gps_horizontal_speed` | 6 | 1e-2 m/s per native unit | — | — | OD-23 |
| `gps_velocity_ned` | 7,8,9 | 1e-2 m/s per native unit | NED | model_local_NED_frame_reference | OD-22 |
| `gps_course_encoded` | 10 | native angle code | — | — | OD-13, OD-14 |

统计：`frame` 绑定 **25** / 未绑定 **31**；`datum` 绑定 **10** / 未绑定 **46**；owner 决策 **24** 个。

GPS 速度槽的 NED 依据：`Simulator/wksim_core/px4_mavlink.py:31` "derive COG from the already-scaled NED velocity"；`Simulator/wksim_core/gnss_event.py:64` 顺序注释 `# time, fix, lat, lon, alt, eph, epv, vel, vn, ve, vd, cog, satellites`。

`extra_motor_speed` 属非活动通道（`Simulator/wksim_core/model_parameters.py:55-57` `"motor_count": 4`、`"16 normalized commands [0,1]; indices 4..15 must be zero"`）；是否进入对外合同由 OD-20 决定。

## 未决 owner 决策（全部 `not_made`）

| id | 主题 | 问题 | 涉及槽 |
| --- | --- | --- | --- |
| OD-01 | time_field_scope | 三个 `schedule_metadata` 时间字段是被排除在物理准确度比较之外（B3），还是各自取得绑定的时间预算？ | Vehicle60[2], Sensor30[0], GPS30[0] |
| OD-02 | time_field_epoch | 三个时间字段的绝对零点/epoch 是什么，微秒与秒的换算如何锚定？ | 同上 |
| OD-03 | lat_lon_horizontal_datum | truth/GPS 经纬度属于哪个水平基准，可否称为 geodetic？ | Vehicle60[30,31], GPS30[1,2] |
| OD-04 | altitude_axis_sign | truth/gps/pressure 高度的垂直轴符号与朝向（上正还是 NED 下正）？ | Vehicle60[32], Sensor30[12], GPS30[3] |
| OD-05 | altitude_height_datum | 这三个高度量的高度基准（椭球高 / AMSL / AGL / 局部）；pressure_altitude 是否与地理真值高度比较？ | 同上 |
| OD-06 | magnetic_field_frame | 磁场三分量在哪个坐标系表达？ | Sensor30[7,8,9] |
| OD-07 | magnetic_field_reference | WMM 模型身份、日期/epoch、计算位置与磁场参考？ | Sensor30[7,8,9] |
| OD-08 | pressure_frame | 绝对压/差压对应哪个仪表系与取压位置？ | Sensor30[10,11] |
| OD-09 | pressure_datum | 压力 datum（绝对/真空 或 海平面/QNH），静压与差压关系？ | Sensor30[10,11] |
| OD-10 | temperature_frame_and_domain | 温度的测量位置、坐标系与适用域？ | Sensor30[13] |
| OD-11 | accuracy_indicator_frame | eph/epv 是否带水平/垂直轴含义，属于哪个系？ | GPS30[4,5] |
| OD-12 | accuracy_indicator_semantics | eph/epv 的物理含义与缩放？ | GPS30[4,5] |
| OD-13 | course_reference_frame | 编码航向使用哪个参考轴/系？ | GPS30[10] |
| OD-14 | course_wrap_convention | 航向零点、方向（从北顺时针？）与环绕规则？ | GPS30[10] |
| OD-15 | quaternion_direction_and_metric | e0 四元数输出的旋转方向（FRD→NED 还是 NED→FRD）是什么；符号/范数等价类与比较度量？ | Vehicle60[12..15] |
| OD-16 | euler_frame_sequence_and_order | 欧拉输出的参考方向、旋转顺序，以及各索引对应的 roll/pitch/yaw？ | Vehicle60[9,10,11] |
| OD-17 | imu_mounting_extrinsics | 加速度计/陀螺相对机体 FRD 的安装外参？ | Sensor30[1..6] |
| OD-18 | imu_zero_reference | 比力与角速度的标定/零位基准，以及比力语义？ | Sensor30[1..6] |
| OD-19 | rotor_speed_frame_and_reference | 标量旋翼转速是否带任何 frame/轴约定；rpm 零位与校准基准？ | Vehicle60[16..23] |
| OD-20 | inactive_channel_scope | `extra_motor_speed` 非活动通道是否属于对外比较合同？ | Vehicle60[20..23] |
| OD-21 | body_acceleration_reference | `body_motion_acceleration` 的零位/参考（它是机体系速度导数，不是比力）？ | Vehicle60[24..26] |
| OD-22 | ned_earth_model | 模型局部 NED 系是平坦/惯性还是考虑地球自转，适用域？ | Vehicle60[3..8], GPS30[7..9] |
| OD-23 | horizontal_speed_frame | `GPS30[6]` 是否为 NED 水平速度幅值；若是，水平面与基准由谁定义？ | GPS30[6] |
| OD-24 | angular_rate_zero_reference | 机体角速度的零位/参考是什么，可否描述为模型局部 NED 原点？ | Vehicle60[27..29] |

OD-14 的边界：`Simulator/wksim_core/px4_mavlink.py:30-31` 只说明模板 COG 公式，且该适配器**绕过** `GPS30[10]`、改由 NED 速度重算 COG，因此不能绑定模型自身的编码。

## 明确不做的推导

1. 不把已绑定 frame/datum 当作精度、标定或测量结果；它们只是约定陈述。
2. 不用 R1 差值、首步 trace、对角求解候选或任何运行/探针结果反推 frame、datum 或预算。
3. 不因某槽绑定了 frame 就宣称该量获得物理覆盖。
4. **不把互不相干的坐标标签组合成方向、标量坐标系或原点结论**（见"保守绑定原则"）。
5. 不改动 `numerical-conformance-v1.json`、`e0-source-to-slot-manifest-20260911.json`、当前 source mapping / RHS 工件、`10-g6-remediation-contract.md` 或任何 #26/#33/#9 文件。
6. `null` 永不等于批准：每个 `null` 都带 `status="unresolved_owner_decision"`、精确原因和一个 `state="not_made"` 的 owner 决策 id。

## 输入钉定（pin）

`pins` 的 id→path 表由校验器**硬编码**并逐项比对；每个 pin 的 `sha256` 必须等于 `sha256(HEAD:<path>)`，且 `git diff HEAD -- <path>` 必须无内容漂移。**不哈希工作树原始字节**，因此 checkout 的 EOL 转换不改变判定。`evidence_policy.require_tracked_at_head` 必须与该表一致、无重复、无多余项。

## 命令与身份

```text
python -B -m pytest validation/test_e0_frame_datum_binding.py -q -p no:cacheprovider
python -B -m unittest validation.test_e0_frame_datum_binding -v
python -B -m pytest validation/test_e0_source_to_slot_manifest.py validation/test_derive_e0_current_source_mapping.py -q -p no:cacheprovider
python -B tools/validate_e0_source_to_slot_manifest.py
python -B validation/coordination/deepseek-g6-frame-datum-review-20260914-01/verify_citations.py
python -B validation/coordination/deepseek-g6-frame-datum-review-20260914-01/verify_independent.py
python -B validation/coordination/deepseek-g6-frame-datum-review-20260914-01/attack_replay.py
```

Windows 10（本机）与 WSL `Ubuntu-22.04`（`python3` 3.10.12 / pytest 9.1.1）都跑同一组命令；`verify_citations.py` 逐条把本文件、payload 的 `evidence_refs`/`committed_text` 的 locator+片段解析到 `HEAD:<path>` 的提交字节上，`attack_replay.py` 重放四个已知攻击并要求全部 reject。

校验器逐项重算：pin 表一致性与 HEAD blob 摘要、冻结合同 ID/摘要、56/64 槽集合、每槽 `observable`/`native_unit`/`source_label`/`semantic_status`/`sample_phase`/`current_generated_rhs`（后者必须等于该槽被钉定的完整 RHS 身份：`rhs.text` 或 `references[].name` / `references[].path`，例如 `Exp1_MinModelTemp_B.Product[2]`；`Product` 一类真子串、未加下标的基符号、前缀/后缀、邻近符号均失败关闭）、冻结 token 集合、冻结每 observable 绑定、证据 id→path/supports/locator/quote 身份、`observables[]` 定位器按合同 JSON 的 **observables 元素字符串字段精确相等** 解析（不是整份 blob 子串）、**frame 与 datum 双方**的证据支持、每条 `committed_text` 与每个 `quote` 在 `HEAD:<path>` 提交字节中的落点、owner 决策 id/topic/slots 是否仍为 `not_made` 且**双向被槽引用**（无孤儿、无未被回指的 slots）、payload `counts` 的全部键与数值必须与槽列表/owner 列表实测结构一致，以及 `budget_approved` / `g6_acceptance` / `physical_accuracy` / `issues_closed` / `effective` 全为 false、`r1_status` 仍为 `numerical_failed`。payload 以**拒绝重复 JSON 键**的方式载入（`json.loads` 会静默保留最后一个值，可能藏住被替换的 pin）。manifest 缺失槽的失败关闭可通过向校验函数注入临时 manifest 副本走活动路径，不得改写 HEAD。

负例由同一校验函数覆盖：缺/重/多槽、伪造 frame/datum、null 被当成通过、owner 决策被标记已作出、owner 决策成为孤儿、删除或替换 pin、pin 摘要与 HEAD blob 不符、pin 路径不在 HEAD、策略列表重复/多余、重复 JSON 键、篡改 `quote` 或 `locator`、篡改 `committed_text`、伪造或截断 `current_generated_rhs` 身份、`counts` 谎报/缺键/多键、`observables[]` 非精确字段引用、任一验收位翻转、写入 `abs_budget`、写入 `g6_accepted` 一类验收键、篡改 `native_unit`、篡改 owner 决策 slots。

本切片没有运行模型、MATLAB、ROS、飞控、UE、native 或构建；没有 `git add`/commit/push，没有改动议题。#83 未被重跑。被复核取代的 CodeBuddy 探针与生成器（`codebuddy-g6-frame-datum-review-20260914-01/**`）已删除，避免留下可重写 payload 的脚本。
