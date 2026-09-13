# G6 当前逐量误差预算证据链（只读审计）

- `audit_id`: `ds-g6-budget-evidence-20260913-01`
- 日期：2026-09-13
- 工作类别：new-development / 只读证据审计（不构建、不运行 native/MATLAB/ROS/飞控/模型/UE）
- 实际 cwd：`C:/Users/PC/Documents/odid编译/wksim`，分支 `main`，HEAD `abf1ac3934e3ad8dcfbcb5c7b4dc49712d407c18`
- 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 检查退出码 **0**
- 冻结 R1 合同 SHA256 `23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0`

> 本审计**不发明、不放宽、不批准**任何 epsilon。所有预算字段保持原状（R1 全 0；同源新合同不存在）。
> `tools/run_e0_same_source_conformance.py`（同源入口）**已存在且已实现**；缺失的是有依据、已 approved 的逐量预算与执行身份，不是入口。

## 1. 结论摘要

| 项 | 值 |
| --- | --- |
| 输出槽总数 | 120 |
| 计入本审计的 dynamic/物理量槽 | 56 |
| 保留槽/接口元数据槽 | 64 |
| **有 approved epsilon 的槽** | **0** |
| slot manifest 已绑定 frame 的槽 | 0 |
| slot manifest 已绑定 datum 的槽 | 0 |
| slot manifest 仍未解析（56/56） | 56 |
| 当前 11.8 RHS 解析为 `terminal` 的槽 | 26 |
| R1 跨版本失败值 / case-轴 / 比较数 | 5684 / 49 / 180360 |
| 同源 C0 整时序离线比较 | 60120 值，2 处不同 |
| 首步映射态 / 总状态 | 13 / 36 |
| 首步 stage+末态差异条目 | 7 |
| 同源入口状态 | blocked (no approved per-quantity budget, no execution block) |
| `physical_accuracy` / `g6_acceptance` | `False` / `False` |

## 2. 三个必须区分的层次

**结构 aligned（结构对齐）** — Slot parse + exact array/index ownership under the frozen R1 observables, plus the same-source entry's structural layer (501 rows, 1 ms grid, 120 values/sample, complete terminal record, embedded source identity). The word "aligned" in the retained comparator outputs means this level only and is NOT a numerical or G6 verdict.

**首步对齐** — k=0->1 intra-step ODE4 trace comparison over 13 of 36 mapped rigid-body states plus five mrdivide operand/result rows. Retained result: 5 stage/final differences on Vehicle60 and 1 ULP earliest divergence at p,q,r stage-2 derivatives[1]. This is one step, one case, one component, one value.

**完整时序数值验收** — The contract-declared rule over all 501 samples of all 120 slots under pre-approved abs_i/rel_i/rms_i budgets. THIS LEVEL HAS NEVER BEEN REACHED, because no budget is approved and no same-source contract with an execution block exists. It is NOT substituted by the same-source C0 offline diagnostic, which has zero approved budget and reports g6_acceptance=false.

结论：现有全部"aligned"字样只到第一、第二层。**第三层从未到达**：没有任何槽拥有已批准的 `abs_budget`/`rel_budget`/`rms_budget`，也没有带 `execution` 块的同源合同文件存在。

## 3. 权威来源与约定

- `route_contract`：docs/plan/10-g6-remediation-contract.md
- `command_seam`：docs/plan/59-e0-same-source-command.md
- `budget_source_map`：docs/plan/59-e0-dynamic-budget-source-map.md
- `material_index`：docs/g6-material-index.md
- `frozen_r1_contract`：Simulator/wksim_core/numerical-conformance-v1.json (sha256 23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0)
- `slot_manifest`：validation/e0-source-to-slot-manifest-20260911.json (status=unresolved)
- `current_source_mapping`：validation/e0-current-source-mapping-20260912.json (status=bound, generated_source sha256 2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274)
- `current_rhs_references`：validation/e0-current-rhs-references-20260912.json (status=bound)
- `time_field_authority`：validation/coordination/major-time-acceptance-20260913-01/verification.json

| 约定 | 值 |
| --- | --- |
| 时间网格 | k * 0.001 s, k = 0..500 inclusive (501 rows), tolerance 1e-12 s |
| 采样相位 | major_root_output (major step, before the subsequent explicit Update/ODE) |
| native 时间字段 | Vehicle60[2] s = k*0.001; Sensor30[0] us = (k*0.001)*1e6; GPS30[0] us = (k*0.001)*1e6 |
| 数组 | {'Vehicle60': 60, 'Sensor30': 30, 'GPS30': 30} |
| 输出端口 | {'Vehicle60': 'VehileInfo60d', 'Sensor30': 'HILSensor30d', 'GPS30': 'HILGPS30d'} |
| 冻结 metric 标识 | `abs_le_a_plus_r_absref_with_rms_cap_v1` |
| frame 状态 | all 56/56 dynamic slots carry frame=null in the slot manifest; conventions exist only as project prose in Simulator/wksim_core/README.md:52,54 and are not slot bindings |
| datum 状态 | all 56/56 dynamic slots carry datum=null in the slot manifest; no WGS84/ellipsoid binding exists for truth_altitude, gps_altitude or pressure_altitude |

## 4. 逐量证据表

单位来自冻结 R1 `observables[].native_unit`；历史来源是 11.0 ZIP 已绑定行号；当前 11.8 行号来自 `e0-current-source-mapping-20260912.json`（生成源 SHA `2c25b3fa…`，与本次 C0 native 记录 `original_cpp_sha256` 相同）。`frame`/`datum` 在 slot manifest 中 56/56 全为 `null`。

### 4.1 状态量（`Vehicle60`）

| 槽位 | 观测量 | 单位 | 权威来源（历史11.0 / 当前11.8） | frame | datum | 相位 | 首步13态覆盖 | 同源C0整时序 | R1失败值 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Vehicle60[2]` | vehicle_time | s | `cpp:3917,7822` / 当前11.8行 7864 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[3]` | velocity_ned | m/s | `cpp:7823-7827; SLX:system_12218_1328 VelE` / 当前11.8行 7865 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 154（C2G 7,C3G 147） |
| `Vehicle60[4]` | velocity_ned | m/s | `cpp:7823-7827; SLX:system_12218_1328 VelE` / 当前11.8行 7867 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 481（C2G 204,C3G 277） |
| `Vehicle60[5]` | velocity_ned | m/s | `cpp:7823-7827; SLX:system_12218_1328 VelE` / 当前11.8行 7869 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 7（C3G 7） |
| `Vehicle60[6]` | position_ned | m | `cpp:7824-7828; 6DOF MKS` / 当前11.8行 7866 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 75（C2G 6,C3G 69） |
| `Vehicle60[7]` | position_ned | m | `cpp:7824-7828; 6DOF MKS` / 当前11.8行 7868 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 574（C2G 194,C3G 380） |
| `Vehicle60[8]` | position_ned | m | `cpp:7824-7828; 6DOF MKS` / 当前11.8行 7870 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 0 |
| `Vehicle60[9]` | euler_components | rad | `cpp:4301,7845-7846` / 当前11.8行 [[4306, 4309]] | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 437（C2G 199,C3G 238） |
| `Vehicle60[10]` | euler_components | rad | `cpp:4301,7845-7846` / 当前11.8行 7887 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 23（C2G 6,C3G 17） |
| `Vehicle60[11]` | euler_components | rad | `cpp:4301,7845-7846` / 当前11.8行 7888 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 499（C2G 210,C3G 289） |
| `Vehicle60[12]` | quaternion_components | 1 | `cpp:7847-7850; SLX DCM->Quaternion->fix_quat_sign` / 当前11.8行 7889 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 0 |
| `Vehicle60[13]` | quaternion_components | 1 | `cpp:7847-7850; SLX DCM->Quaternion->fix_quat_sign` / 当前11.8行 7890 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 425（C2G 199,C3G 226） |
| `Vehicle60[14]` | quaternion_components | 1 | `cpp:7847-7850; SLX DCM->Quaternion->fix_quat_sign` / 当前11.8行 7891 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 19（C2G 6,C3G 13） |
| `Vehicle60[15]` | quaternion_components | 1 | `cpp:7847-7850; SLX DCM->Quaternion->fix_quat_sign` / 当前11.8行 7892 | **null** | **null** | major_root_output | 是 | 501/501比，差异0 | 243（C2G 62,C3G 181） |
| `Vehicle60[16]` | active_motor_speed | rpm | `cpp:7851-7858; h:1398` / 当前11.8行 [[7893, 7894]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[17]` | active_motor_speed | rpm | `cpp:7851-7858; h:1398` / 当前11.8行 [[7895, 7896]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[18]` | active_motor_speed | rpm | `cpp:7851-7858; h:1398` / 当前11.8行 [[7897, 7898]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[19]` | active_motor_speed | rpm | `cpp:7851-7858; h:1398` / 当前11.8行 [[7899, 7900]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[20]` | extra_motor_speed | rpm | `cpp:7859-7866; h:1398` / 当前11.8行 [[7901, 7902]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[21]` | extra_motor_speed | rpm | `cpp:7859-7866; h:1398` / 当前11.8行 [[7903, 7904]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[22]` | extra_motor_speed | rpm | `cpp:7859-7866; h:1398` / 当前11.8行 [[7905, 7906]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[23]` | extra_motor_speed | rpm | `cpp:7859-7866; h:1398` / 当前11.8行 [[7907, 7908]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[24]` | body_motion_acceleration | m/s^2 | `cpp:7867-7871; SLX Abb` / 当前11.8行 7909 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 147（C2G 1,C3G 146） |
| `Vehicle60[25]` | body_motion_acceleration | m/s^2 | `cpp:7867-7871; SLX Abb` / 当前11.8行 7911 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 394（C2G 186,C3G 208） |
| `Vehicle60[26]` | body_motion_acceleration | m/s^2 | `cpp:7867-7871; SLX Abb` / 当前11.8行 7913 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 5（C3G 5） |
| `Vehicle60[27]` | body_angular_rate | rad/s | `cpp:7868-7872` / 当前11.8行 7910 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 272（C2G 175,C3G 97） |
| `Vehicle60[28]` | body_angular_rate | rad/s | `cpp:7868-7872` / 当前11.8行 7912 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 157（C3G 157） |
| `Vehicle60[29]` | body_angular_rate | rad/s | `cpp:7868-7872` / 当前11.8行 7914 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 333（C2G 290,C3G 43） |
| `Vehicle60[30]` | truth_latitude_longitude | degree | `cpp:7873-7874; SLX PosGPS` / 当前11.8行 7915 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[31]` | truth_latitude_longitude | degree | `cpp:7873-7874; SLX PosGPS` / 当前11.8行 7916 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Vehicle60[32]` | truth_altitude | m | `cpp:7875; same rtb_Add as GPS30[3]` / 当前11.8行 7917 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |

### 4.2 传感器量（`Sensor30`）

| 槽位 | 观测量 | 单位 | 权威来源（历史11.0 / 当前11.8） | frame | datum | 相位 | 首步13态覆盖 | 同源C0整时序 | R1失败值 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Sensor30[0]` | sensor_time | us | `cpp:3922,7437` / 当前11.8行 7442 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Sensor30[1]` | accelerometer | m/s^2 | `cpp:7457-7512; h S262 Three-axis Accelerometer` / 当前11.8行 [[7466, 7467]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 65（C3G 65） |
| `Sensor30[2]` | accelerometer | m/s^2 | `cpp:7457-7512; h S262 Three-axis Accelerometer` / 当前11.8行 [[7491, 7492]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 185（C3G 185） |
| `Sensor30[3]` | accelerometer | m/s^2 | `cpp:7457-7512; h S262 Three-axis Accelerometer` / 当前11.8行 [[7516, 7517]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Sensor30[4]` | gyroscope | rad/s | `cpp:7532-7607; h S263 Three-axis Gyroscope` / 当前11.8行 [[7541, 7542]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 108（C3G 108） |
| `Sensor30[5]` | gyroscope | rad/s | `cpp:7532-7607; h S263 Three-axis Gyroscope` / 当前11.8行 [[7566, 7567]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 125（C3G 125） |
| `Sensor30[6]` | gyroscope | rad/s | `cpp:7532-7607; h S263 Three-axis Gyroscope` / 当前11.8行 [[7611, 7612]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Sensor30[7]` | magnetic_field | gauss | `cpp:7608-7616; h:1194 nT2Gauss=1e-5` / 当前11.8行 [[7613, 7615]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 119（C2G 39,C3G 80） |
| `Sensor30[8]` | magnetic_field | gauss | `cpp:7608-7616; h:1194 nT2Gauss=1e-5` / 当前11.8行 [[7616, 7618]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 279（C2G 114,C3G 165） |
| `Sensor30[9]` | magnetic_field | gauss | `cpp:7608-7616; h:1194 nT2Gauss=1e-5` / 当前11.8行 [[7619, 7621]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 120（C2G 44,C3G 76） |
| `Sensor30[10]` | absolute_pressure | hPa | `cpp:7617-7618; h:1272 Pa*0.01` / 当前11.8行 [[7622, 7623]] | **null** | **null** | major_root_output | 否 | 501/501比，差异2 | 4（C0 2,C2G 1,C3G 1） |
| `Sensor30[11]` | differential_pressure | hPa | `cpp:7619-7623; h:1299 Pa*0.01` / 当前11.8行 [[7624, 7628]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 4（C3G 4） |
| `Sensor30[12]` | pressure_altitude | m | `cpp:7624` / 当前11.8行 7629 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `Sensor30[13]` | temperature | degC | `cpp:7625-7626 subtract 273.15000000000003` / 当前11.8行 [[7630, 7631]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |

### 4.3 GPS 量（`GPS30`）

| 槽位 | 观测量 | 单位 | 权威来源（历史11.0 / 当前11.8） | frame | datum | 相位 | 首步13态覆盖 | 同源C0整时序 | R1失败值 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GPS30[0]` | gps_time | us | `cpp:3922,7727` / 当前11.8行 7732 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `GPS30[1]` | gps_latitude_longitude | 1e-7 degree per native unit | `cpp:7728-7731; h:1323-1326` / 当前11.8行 [[7733, 7734]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `GPS30[2]` | gps_latitude_longitude | 1e-7 degree per native unit | `cpp:7728-7731; h:1323-1326` / 当前11.8行 [[7735, 7736]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `GPS30[3]` | gps_altitude | 1e-3 m per native unit | `cpp:7732-7733; h:1329` / 当前11.8行 [[7737, 7738]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `GPS30[4]` | gps_accuracy_indicators | native scaled double | `cpp:7653-7660,7734-7735; h:1332-1341 values .3/.4 scale100` / 当前11.8行 7739 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `GPS30[5]` | gps_accuracy_indicators | native scaled double | `cpp:7653-7660,7734-7735; h:1332-1341 values .3/.4 scale100` / 当前11.8行 7740 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |
| `GPS30[6]` | gps_horizontal_speed | 1e-2 m/s per native unit | `cpp:7683-7689; h:1362` / 当前11.8行 [[7693, 7694]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 136（C3G 136） |
| `GPS30[7]` | gps_velocity_ned | 1e-2 m/s per native unit | `cpp:7736-7739; h:1365` / 当前11.8行 7741 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 89（C3G 89） |
| `GPS30[8]` | gps_velocity_ned | 1e-2 m/s per native unit | `cpp:7736-7739; h:1365` / 当前11.8行 7742 | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 199（C3G 199） |
| `GPS30[9]` | gps_velocity_ned | 1e-2 m/s per native unit | `cpp:7736-7739; h:1365` / 当前11.8行 [[7743, 7744]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 6（C3G 6） |
| `GPS30[10]` | gps_course_encoded | native angle code | `cpp:7695-7708,7725-7726; h:1374,1380` / 当前11.8行 [[7730, 7731]] | **null** | **null** | major_root_output | 否 | 501/501比，差异0 | 0 |

### 4.4 导数量（显式分组）

| 槽位 | 观测量 | 单位 | 语义 | 当前11.8行 | 当前11.8 RHS解析 | R1失败值 |
| --- | --- | --- | --- | --- | --- | --- |
| `Sensor30[1]` | accelerometer | m/s^2 | mapped_physical_observable | [[7466, 7467]] | `unresolved`/compound_expression | 65 |
| `Sensor30[2]` | accelerometer | m/s^2 | mapped_physical_observable | [[7491, 7492]] | `unresolved`/compound_expression | 185 |
| `Sensor30[3]` | accelerometer | m/s^2 | mapped_physical_observable | [[7516, 7517]] | `unresolved`/compound_expression | 0 |
| `Sensor30[4]` | gyroscope | rad/s | mapped_physical_observable | [[7541, 7542]] | `unresolved`/compound_expression | 108 |
| `Sensor30[5]` | gyroscope | rad/s | mapped_physical_observable | [[7566, 7567]] | `unresolved`/compound_expression | 125 |
| `Sensor30[6]` | gyroscope | rad/s | mapped_physical_observable | [[7611, 7612]] | `unresolved`/compound_expression | 0 |
| `Vehicle60[24]` | body_motion_acceleration | m/s^2 | mapped_physical_observable | 7909 | `terminal` | 147 |
| `Vehicle60[25]` | body_motion_acceleration | m/s^2 | mapped_physical_observable | 7911 | `terminal` | 394 |
| `Vehicle60[26]` | body_motion_acceleration | m/s^2 | mapped_physical_observable | 7913 | `terminal` | 5 |
| `Vehicle60[27]` | body_angular_rate | rad/s | mapped_physical_observable | 7910 | `terminal` | 272 |
| `Vehicle60[28]` | body_angular_rate | rad/s | mapped_physical_observable | 7912 | `terminal` | 157 |
| `Vehicle60[29]` | body_angular_rate | rad/s | mapped_physical_observable | 7914 | `terminal` | 333 |

导数量补充事实：

- `Vehicle60[24:26]` 是**机体系速度导数**，按 `Simulator/wksim_core/README.md:52` **不是**加速度计比力；`Sensor30[1:3]` 才是 IMU 比力通道。两者不可跨量比较。
- 首步分歧被定位到 `p,q,r` 导数 index 1（stage 2, t=0.0005），参考 `bc56d4db33a987b8` vs 目标 `bc56d4db33a987b9`，**1 ULP**；上游（`rtb_IntegratorSecondOrderLimi_d`、`Selector2`、`M1/Fd/Sum1_a/TT0gLR/Sum4_f`）**尚未**双引擎逐位捕获，根因未证明。
- 对角快路径候选在 13 个映射态与 5 次 mrdivide 结果上与参考一致，但 guard review 证明该分支在其中一个分量上比正确舍入除法**低 1 ULP 精度**；参考求解器是否为"乘以倒数"仍未定。
- `L5`：通用求解体在 `d = 5e-324` 且分子非零时算得 `0 - 0*inf = NaN`，快速路径守卫会正确落回，但通用体本身不是修复；对保留惯量不可达。

### 4.5 时间字段

- 权威：`validation/coordination/major-time-acceptance-20260913-01/verification.json`
- 三参考文件时间首列：product 形式匹配 **501/501**，division 形式匹配 **429/501**。
- 与"先除法再缩放"的差异行数：Vehicle60 **72**，Sensor30 **61**，GPS30 **61**。
- `budget_approved=False`，`g6_acceptance=False`。
- 四条时间/相位前置记录**全部** `acceptance=false`：
  - `vehicle_time_premise`：status `evidence_for_review_only`，acceptance `False`，budget_approved `False`
  - `identity_rule_v3`：status `prospective_rule_for_review`，acceptance `False`
  - `major_microtime_binding_v4`：status `prospective_binding_for_review`，acceptance `False`
  - `major_time_binding_v3`：status `prospective_binding_for_review`，acceptance `False`
- 结论：no time/phase rule is approved; all four retained records are prospective_for_review with acceptance=false

## 5. 现有比较覆盖与失败数量

| 层次 | 覆盖 | 差异/失败 | 是否数值验收 |
| --- | --- | --- | --- |
| 结构 aligned | 120/120 槽解析、501 行、1 ms 网格、120 值/样本、终态记录、内嵌 source identity | 0（结构） | 否 |
| 首步对齐 | 13/36 状态 + 5 次 mrdivide 操作数/结果，单一工况 C3G，k=0→1 | stage+末态 7 条；最早 1 ULP | 否 |
| 同源 C0 整时序（离线诊断） | 60120 值 = 501×120 | 2 处不同（`Sensor30[10]` k=153/k=181），零 approved 预算 | 否（`g6_acceptance=false`） |
| R1 跨版本三工况 | 180360 值 | **5684** 失败值，**49** 个 case/轴，C0/C2G/C3G = 2/1943/3739 | 否（`numerical_failed`，`physical_accuracy=unverified`） |
| 完整时序数值验收 | **0 槽** | — | **从未到达** |

### 5.1 R1 失败按观测量聚合

| 观测量 | 槽 | 失败值 | C0 | C2G | C3G | 最大绝对误差 |
| --- | --- | --- | --- | --- | --- | --- |
| euler_components | 3 | 959 | 0 | 415 | 544 | 5.55112e-17 |
| body_angular_rate | 3 | 762 | 0 | 465 | 297 | 1.11022e-16 |
| quaternion_components | 4 | 687 | 0 | 267 | 420 | 2.08167e-17 |
| position_ned | 3 | 649 | 0 | 200 | 449 | 1.38778e-17 |
| velocity_ned | 3 | 642 | 0 | 211 | 431 | 2.22045e-16 |
| body_motion_acceleration | 3 | 546 | 0 | 187 | 359 | 8.88178e-16 |
| magnetic_field | 3 | 518 | 0 | 197 | 321 | 5.55112e-16 |
| gps_velocity_ned | 3 | 294 | 0 | 0 | 294 | 2.84217e-14 |
| accelerometer | 3 | 250 | 0 | 0 | 250 | 3.46945e-17 |
| gyroscope | 3 | 233 | 0 | 0 | 233 | 2.22045e-16 |
| gps_horizontal_speed | 1 | 136 | 0 | 0 | 136 | 2.84217e-14 |
| absolute_pressure | 1 | 4 | 2 | 1 | 1 | 2.27374e-13 |
| differential_pressure | 1 | 4 | 0 | 0 | 4 | 1.73472e-18 |
| gps_time | 1 | 0 | 0 | 0 | 0 | — |
| gps_latitude_longitude | 2 | 0 | 0 | 0 | 0 | — |
| gps_altitude | 1 | 0 | 0 | 0 | 0 | — |
| gps_accuracy_indicators | 2 | 0 | 0 | 0 | 0 | — |
| gps_course_encoded | 1 | 0 | 0 | 0 | 0 | — |
| sensor_time | 1 | 0 | 0 | 0 | 0 | — |
| pressure_altitude | 1 | 0 | 0 | 0 | 0 | — |
| temperature | 1 | 0 | 0 | 0 | 0 | — |
| vehicle_time | 1 | 0 | 0 | 0 | 0 | — |
| active_motor_speed | 4 | 0 | 0 | 0 | 0 | — |
| extra_motor_speed | 4 | 0 | 0 | 0 | 0 | — |
| truth_latitude_longitude | 2 | 0 | 0 | 0 | 0 | — |
| truth_altitude | 1 | 0 | 0 | 0 | 0 | — |

R1 聚合：最大 ULP 距离 **8192**，最大相对误差 **1.57605e-12**，符号翻转 **0**，比值落在 [0.5,2] 之外 **0**，参考恰为 0 的失败 **0**。

### 5.2 同源 C0 与 R1 的关系（不得混用）

- 同源 C0 使用**保留的 11.8 生成源** native 记录（`2c25b3fa…`）+ normal 参考，零预算、诊断标签；它证明"同源入口可离线重跑并复现 2 处差异"，**不**证明 G6。
- R1 是 **ZIP 11.0 native vs SLX 11.8 normal** 的跨版本零容差保留规则，是比 Full 更强的特定条件，其 5684 失败值**原样保留**，不得用同源 C0 结果覆盖或改判。

## 6. 缺失的批准依据

| 缺口 | 现状 | 谁能解除 |
| --- | --- | --- |
| `B1-no-approved-per-quantity-budget` No abs_budget / rel_budget / rms_budget basis exists for any of the 120 slots. | 需要：error analysis or calibration/sensor specification per observable；需要：state domain and event policy；需要：derivation note and owner-approval record | project owner / delegated engineering authority named in the #59 route contract |
| `B2-frame-and-datum-unbound` frame and datum are null for all 56/56 dynamic slots. | 需要：slot-level frame binding；需要：WGS84/ellipsoid and altitude-datum binding；需要：GPS course angle wrapping convention；需要：eph/epv physical semantics | project owner |
| `B3-time-phase-rule-unapproved` All four retained time/premise records are prospective_for_review with acceptance=false. | 需要：a decision that the three time fields are schedule metadata (excluded) or a bound schedule budget | project owner (separate from B1; time fields may be excluded by a scoped decision) |
| `B4-no-same-source-execution-identity` No same-source contract with an execution block (matlab, export script, stage files, native manifest, WSL executable) exists. | 需要：a frozen same-source contract file with all 120 approved budgets；需要：the full execution block with live hashes | main session (sole writer of native/official profile) |
| `B5-derivative-path-only-partially-observed` The first divergence is localised to one component of one step; the pqr(q) derivative operand chain is only partially observed. | 需要：mrdivide numerator and Selector2 captured on both engines；需要：all 36 states mapped, not 13；需要：a second discriminating solve component | main session (deeper instrumentation is second-level, not delegable offline) |

逐槽的共同缺项（56/56）：`abs_budget` / `rel_budget` / `rms_budget` 无任何有依据的数值；`frame=null`；`datum=null`；slot manifest 的 `version`/`hash` 未绑定当前 11.8 生成源；没有指明 metric、语义、datum 与适用域的 owner-approval record。

已存在的、**不能**当作预算的东西（`docs/plan/59-e0-dynamic-budget-source-map.md` 明确禁止反推）：R1 差值、候选/探针差值、RK4 阶数或网格收敛、模型噪声幅值/种子/增益、传感器教学资料、SITL 航点门槛、`double` epsilon。

## 7. 同源入口的实际行为（已实跑，非推断）

- 工具：`tools/run_e0_same_source_conformance.py`（SHA256 `8398100b7fb6b839e279afd6e8f8708e57e415450dbb6621acdc9ea9ecc46517`）
- 对冻结 R1 合同的真实调用：`python tools/run_e0_same_source_conformance.py Simulator/wksim_core/numerical-conformance-v1.json`
  - 观测结果：`status=blocked`，退出码 **2**，`matlab_launched=False`，`native_launched=False`
  - 阻塞原因：`Reject: refusing to treat the frozen R1 contract as the new same-source contract`
- 次序探针：validate_contract() on a synthetic in-memory-shaped contract containing all 120 R1 slots with approved zero budgets, then validate_execution() on the same object
  - `validate_contract` 阻塞原因：`空`
  - `validate_execution`：`Reject: execution block missing`
- 结论：the same-source entry EXISTS and is implemented; the missing item is the approved per-quantity budget and the execution identity, not the entry. No epsilon was invented, relaxed or approved by this audit.

## 8. 稳定 SHA 与可执行的下一次重核

交付物（本目录独占写入，交付后停止写入）：

| 文件 | 角色 |
| --- | --- |
| `audit.md` | 本报告 |
| `audit.json` | 机器可读逐量台账与阻断项 |
| `build_audit.py` | 只读生成器（重跑即重建 audit.json） |
| `verify_inputs.py` | 只读重核脚本（身份 + 失败数 + 同源 C0 复算） |
| `.gitattributes` | 固定本目录文本行尾，避免 CRLF 混入哈希 |
| `write_manifest.py` | 生成 `manifest.json` 与 `SHA256SUMS` |
| `manifest.json` | 交付范围、checkout 身份与非声明 |
| `SHA256SUMS` | **交付物自身的权威 SHA256 清单（内容寻址终点，不反向被引用）** |

交付物自身的稳定 SHA256 记录在 `SHA256SUMS`（由 `write_manifest.py` 最后生成，该文件不再引用任何清单，因此不存在自引用）。

被本审计引用的全部原件身份（生成时刻实测，`verify_inputs.py` 可复现）：

| 原件 | SHA256 |
| --- | --- |
| `docs/plan/10-g6-remediation-contract.md` | `48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0` |
| `docs/plan/59-e0-same-source-command.md` | `345caff0fd354717a64ed1dfac2c3ad33f87c72713cf3362483c395fb66b197e` |
| `docs/plan/59-e0-dynamic-budget-source-map.md` | `35a56084105409329131add7d4b9e35be6d1a145c6e18268c96324805313cd42` |
| `docs/plan/59-e0-artifact-portability.md` | `8d3e70b12fc7d6851fc2a6fa96afeb8e4810540864b020075d54656a274737f3` |
| `docs/g6-material-index.md` | `3201a69f3c9c41e55ed327fcc766fbd59910066151caff3257ea9bc969cf1fca` |
| `docs/2026-09-13-major-time-conventions.md` | `c67439a614d105a627befd9d0d18596b2dcfebe349c5181e88c4bf8fd8c18897` |
| `docs/2026-09-13-diagonal-solve-experiment.md` | `70bee119d14d615236da620f8491fb07433561dea263c1f5a018995eadb1079b` |
| `docs/coordination/short-cycle-goal.md` | `d6339f23b61e3b1fee4e5d729b283bf1378da2622d9538a8ce29affaa606c71c` |
| `docs/coordination/module-delivery-policy-20260912.md` | `9299afa7cfbfc9ca3cdb0ce9ddfa8fc749f9397da0da36b2c82ebe3b35c9a968` |
| `docs/coordination/architecture-continuation-20260913.md` | `665890489b087085d1bf143143b8ae7ddfa0a37af4d3506f3525c31372c1295d` |
| `tools/run_e0_same_source_conformance.py` | `8398100b7fb6b839e279afd6e8f8708e57e415450dbb6621acdc9ea9ecc46517` |
| `tools/validate_e0_source_to_slot_manifest.py` | `676829e44e95c714fa921b1b94d05e4741a989b0b75f90c5e244641a14cca642` |
| `tools/compare_first_step_trace.py` | `7f7be184e2e31c6dbb9a4a198b4c313f7cef5b72f8f18abd958606c144eefc9f` |
| `tools/probe_reference_first_step.m` | `eb485804023c5310ea436af5d14f862e3aa5e75f3342fd057d6f313f00649603` |
| `validation/e0-source-to-slot-manifest-20260911.json` | `e48982b4732e4fd84ea26390eb516b7e35aea93267aa741ef3c32538cefa6867` |
| `validation/e0-current-source-mapping-20260912.json` | `28684e66cd6e49c90907dacdabf219608a3e3ba808e07e3bd9068233268489f8` |
| `validation/e0-current-rhs-references-20260912.json` | `fa068cc78f8f93e695417d6e315002c799f1bd4d7ef03641a5b236be9cddc188` |
| `validation/numerical-conformance-gxxh6xhr/run-index.json` | `2a964b731d585ca11c26ec2cc01f9d2b653942c8fc94b347b826c4280e605a94` |
| `validation/numerical-conformance-gxxh6xhr/all-failures.jsonl` | `1dfdbb84cef0010d0ed376b2c6bf10cd752c549616bedf38711e2c619bb6aee3` |
| `validation/numerical-conformance-gxxh6xhr/all-360-scalars.csv` | `0fab134db75f75fc20142c0d5251364224e2c70a7980a280235a19a93ba34e7a` |
| `validation/coordination/g6-solve-same-source-20260913/existing-c0-observation.json` | `45e64ca36fad78c1ff167e2a7370cbfcb77d8ed0c23ac46b7ae9e05740d9805f` |
| `validation/e0-major-recorder-parent-final-01/record.jsonl` | `8ce61b3338d42f964dbb704bcebe25a7c0b728926eae974970fe3cb6a58ff354` |
| `validation/e0-major-recorder-parent-final-01/build-manifest.json` | `ac6dbccf16c0842c8d7e0632eacff42a4657215fb2fe13fd0e7c6d1caafdf997` |
| `validation/coordination/g6-target-first-step-20260913/comparison-v2.json` | `2a6b8fe9338224d64f0cc91fd4c66139b3422ca23c3032049cd529d6387ea3c9` |
| `validation/coordination/g6-reference-probe-20260913/run-03/reference-first-step.json` | `99fc1ec84a110bea1e5998a97b4f9c66231966474268ba74bfc343b584e03f85` |
| `validation/coordination/g6-reference-probe-20260913/run-05/reference-first-step.json` | `72ff7d8eaeee7854bf026d19a7ee37f38c061764ce5369d0dd5845b1aa084c62` |
| `validation/coordination/g6-target-first-step-20260913/first-step-trace.jsonl` | `343509972eb3233cd8b4c32c8f0747c2e959cefeb2dab57ea747930c40e3fb86` |
| `validation/coordination/g6-diagonal-solve-candidate-20260913/first-step-trace.jsonl` | `5e89b720dac275a4980df1881aae2dfde76d223ad9a0bc8dbeba15edaa1e1d09` |
| `validation/coordination/g6-diagonal-solve-candidate-20260913/comparator-result-v2.json` | `0a09b86111bc0f8b7c24c2456551729ee2d5377edb3b6888122905a369b09178` |
| `validation/coordination/g6-guard-review-20260913-01/sha-receipt-20260913-02.json` | `e2890e094e6e5acfe11111b54a48d9e194110799cc3036a38ccbe414cd543b27` |
| `validation/coordination/g6-guard-review-20260913-01/findings-g6-diagonal-guard-20260913.md` | `1b29a64b1709e6c0f236b401790b464c43893a7cad5cceea2257f7384af51838` |
| `validation/coordination/major-time-acceptance-20260913-01/verification.json` | `edf6a755f7e3b5b2b71e7c9064311653b689210b43884ed93e9c6d5659cd6f70` |
| `validation/coordination/g6-time-premise-acceptance-20260913-01/prospective-rule.json` | `5e069ef03257f4c78d731675387363e9595e13ff057718ecfc3e2f16238bf178` |
| `validation/coordination/ds-g6-identity-rule-20260913-01/g6-identity-rule-v3.json` | `7779d7a37fe1ce75638fc4eafd59886d3ae74ac5e3af8c4503f0a2adacafbc30` |
| `validation/coordination/ds-g6-major-microtime-binding-20260913-01/g6-major-microtime-binding-v4.json` | `b2c6aa7467c918d73c877930fce9478d9db089667df1294a336948dcc36aea65` |
| `validation/coordination/ds-g6-major-time-binding-20260913-01/g6-major-time-binding-v3.json` | `248b4910ec3380e0754845d3e22493a754fa5bb682d1c02c701fa3faaf4497b5` |
| `validation/coordination/g6-first-divergence-20260913/diagnosis.json` | `33b04b76046b9a2f12ff1bc24c41d582419ad63ddfde7b4ad6483febb7757133` |
| `docs/plan/59-e0-dynamic-budget-source-map.md` | `35a56084105409329131add7d4b9e35be6d1a145c6e18268c96324805313cd42` |

重核命令：

1. re-verify the frozen R1 identity and the retained 5684 failures

   ```
   $i = Get-Content validation/10-g6-remediation/review-20260909/inspection.json -Raw | ConvertFrom-Json; foreach ($h in $i.hashes) { if ((Get-FileHash -LiteralPath $h.path -Algorithm SHA256).Hash.ToLower() -ne $h.sha256) { throw ("Hash changed: " + $h.path) } }; if (($i.results | Measure-Object -Property failed_values -Sum).Sum -ne 5684) { throw "Failure total changed" }
   ```

   期望：exit 0; 15 identities unchanged; 5684 failures retained

2. prove the same-source entry still refuses R1 and still blocks before any launch

   ```
   python tools/run_e0_same_source_conformance.py Simulator/wksim_core/numerical-conformance-v1.json
   ```

   期望：status=blocked, exit 2, matlab_launched=false, native_launched=false

3. re-validate the unresolved slot manifest offline

   ```
   python -B tools/validate_e0_source_to_slot_manifest.py
   ```

   期望：status=pass with 56 slots, 0 errors (the pass is provenance-only)

4. re-derive the same-source C0 full-series diagnostic read-only

   ```
   python -B -c "import sys; sys.path.insert(0,'.'); from tools.run_e0_same_source_conformance import ARRAY_LENGTHS, parse_native_record, parse_reference_f64; import json; from pathlib import Path; r=Path('.'); b=json.loads((r/'validation/e0-major-recorder-parent-final-01/build-manifest.json').read_bytes()); n=parse_native_record(r/'validation/e0-major-recorder-parent-final-01/record.jsonl', b['source_identity']); t=d=0; for a,w in ARRAY_LENGTHS.items():
    e=parse_reference_f64(r/'validation/numerical-conformance-u56ce17a/C0'/(a+'.f64'),a,w)
    for i in range(w):
     t+=501; d+=sum(1 for k in range(501) if e[k][i]!=n[a][k][i])
   print(t,d)"
   ```

   期望：comparisons 60120, different_values 2 (Sensor30[10] at k=153 and k=181)

5. re-hash every input this audit cites

   ```
   python -B validation/coordination/ds-g6-budget-evidence-20260913-01/verify_inputs.py
   ```

   期望：exit 0, all identities match audit.json

## 9. 非声明与阻断项

- This audit approves NO epsilon and relaxes NO budget.
- The same-source entry tools/run_e0_same_source_conformance.py EXISTS; it is not missing. Only the approved budget and the execution identity are missing.
- The same-source entry exists and is implemented; structural alignment is not a numerical or G6 verdict.
- No first-step alignment (13 states, 1 case, 1 step, 1 component) substitutes for full time-series acceptance.
- No MATLAB, native, ROS, flight-controller, model, UE, or MATLAB build was started; no epsilon was invented.
- R1 remains numerical_failed; G6 and physical accuracy remain unverified; issue #59 remains OPEN/needs-triage.

只有表 6 中列出的授权方能解除对应阻断项；本审计不自批准、不代批准、不放宽任何门槛。
