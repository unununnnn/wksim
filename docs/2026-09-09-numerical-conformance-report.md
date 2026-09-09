# #23 冻结原生数值对照执行报告

2026-09-09。三个固定工况均完成有效运行，但均未通过冻结 R1 的零误差判据。六个模型进程（3 MATLAB、3 native recorder）全部正常退出 0；不存在运行无效或需要重试的工况。三例共比较 180,360 个值，严格不等 5,684 个值，涉及 49 个 case/轴。#23/G6 不关闭，物理准确性仍未验证。

| 工况 | 每轴样本 | 轴数 | 失败轴数 | 不等值数 | 执行 | 数值结果 |
|---|---:|---:|---:|---:|---|---|
| C0 | 501 | 120 | 1 | 2 | valid / 两进程退出0 | numerical_failed |
| C2G | 501 | 120 | 18 | 1943 | valid / 两进程退出0 | numerical_failed |
| C3G | 501 | 120 | 30 | 3739 | valid / 两进程退出0 | numerical_failed |

## 冻结身份和执行边界

执行前主代理已冻结 [契约](../Simulator/wksim_core/numerical-conformance-v1.json)，SHA256 `23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0`，基线提交 `a7e20b3`。每例独立 epoch，在任何模型初始化/仿真前复制契约、CSV、SLX、原 init 和绑定/依赖清单，核验并记录源材料、工具源、暂存副本、目标源码/构建/可执行文件 SHA256 及完整 argv。运行后逐项复验全部身份不变。

参考为 SLX 11.8、MATLAB `9.13.0.2049777 (R2022b)`、Simulink normal、ODE4、固定1 ms。三个工况分别使用新的 MATLAB 进程及私有 TEMP/TMP/PREF/cache/codegen 目录。未调用代码生成、DLL、厂商启动器或 SITL；未修改生产运行时、旧模型、冻结契约和CSV。执行原 init 后、update 后及 sim 后复核22项参数与实际绑定、4电机配置、FaultInParams、七组随机种子、关闭的 IMU 支路和实际库路径；未制造 i_pow 值。17份实际依赖文件在进程前后均符合冻结哈希。

两个根输入实际端口1/2、宽16/15，SampleTime=`0.001`、Interpolate=`off`，501行原CSV以 Dataset/timeseries 输入并逐行核验解析的binary64输入与目标实际提交值。派生配置在 sim 前记录，其SHA256为 `b07b62928417e35fc38c7b43845362f7419f7df42f00798bbe4b494a5527dd1c`。

根输出 Dataset 名称实际为空；导出器从模型根 Outport 实际编号确定1=Sensor30、2=GPS30、3=Vehicle60，再读取对应Dataset元素。三个通道独立校验501个严格递增时间、0..0.500 s网格和30/30/60宽度，通过getdatasamples逐样本展开，每行按`time + values`写little-endian binary64。JSON仅存元数据，未用于导出参考数组。

目标使用已有 `/root/wksim-major-recorder-j_3guvtn/build.json`（SHA256 `6e16102ae1197a899eef554b9c938f5ca32220516fdd8630c7b8b1b19267cce3`）和可执行文件（SHA256 `c685817a974471113793fde3c78eeed26f7c7b56eef1194f9df1fd2ecf7e8d49`），没有重建。Ubuntu-22.04 / g++11.4.0 / `-O2 -fno-fast-math`。每例新的WSL进程执行501次step，每次完整返回且major回调数1；保留全部major及原post-step数组，实际引擎结束0.501 s，比较终点0.500 s。核验start源码/完整CSV、逐行输入/编号/时钟、全部有限输出、end计数和退出码。

比较直接使用有限binary64数值`x == r`，正负零相等。全部120槽的绝对和相对预算均0；没有缩放、量化、时间平移、四元数符号对齐或根据结果修改阈值。1e-12 s只用于调度网格检查，不用于输出值验收。ZIP11.0与SLX11.8的历史同版本绑定仍未证实。

## 实际响应与差异

C0仅Sensor30[10]绝对气压有两个差异：k153参考1007.2510342146562、目标1007.2510342146564 hPa；k181参考1007.2490164986876、目标1007.2490164986878 hPa。其余119轴每轴501样本精确相等。

C2G的18失败轴包括微小横向运动/姿态分量及磁场、气压差异；垂向位置/速度和四电机转速全程精确相等。C3G的30失败轴覆盖更多运动、传感器与GPS速度分量。差值量级见下面完整逐轴表；不按大小把严格失败改成通过，也不将差异归因于尚未隔离验证的编译器或库。

| 工况 | 末参考 NED位置(m) | 末参考 NED速度(m/s) | 末参考 Euler(rad) | 末参考电机(rpm) | 参考z_NED范围(m) |
|---|---|---|---|---|---|
| C0 | [0.0, 0.0, 0.0] | [0.0, 0.0, 0.0] | [0.0, -0.0, 0.0] | [0.0, 0.0, 0.0, 0.0] | [0.0, 0.0] |
| C2G | [1.1052691390253961e-16, 5.1739196970458826e-17, -0.14680537794073828] | [1.2015857889206827e-15, 5.783739386220189e-16, -0.8631236986454804] | [3.9371883303069126e-16, -7.921734233840312e-16, -1.5014794117499814e-31] | [5042.887995382479, 5042.887995382479, 5042.887995382479, 5042.887995382479] | [-0.14680537794073828, 3.8837314376321776e-05] |
| C3G | [-0.05998614513714806, -0.06559720344127806, -0.2721302591307612] | [-0.6123998704083278, -0.6814120095210602, -1.148842834692707] | [-0.44093124825042834, 0.37456416394250414, -0.05639419140525022] | [5444.961163151008, 5042.888033484514, 5042.888033484514, 5042.888033484514] | [-0.2721302591307612, 3.8837314376321776e-05] |

上述为直接观测的原生响应，不宣称记录了地面接触事件本身。零地形、固定初态和0.5 s窗口只覆盖这三份输入；自由落体、其他电机通道排列、非零地形、长轨迹、其他配置及真实物理准确性未测。四元数方向/分量约定、GPS航向角和高度基准、eph/epv物理意义、WMM物理正确性依然未验证。

## 可重放证据与检查

[执行器](../tools/run_numerical_conformance.py)、[参考导出器](../tools/export_model_reference.m)、[比较器负向检查](../validation/test_numerical_conformance.py)。本次命令为：

```text
python validation/test_numerical_conformance.py
python tools/run_numerical_conformance.py --run --cases C0
python tools/run_numerical_conformance.py --run --cases C2G C3G
```

两次执行器调用均退出1，原因是严格数值失败；MATLAB/target各自仍全部退出0。负向检查通过：精确相等、正负零、最小1 ULP差异失败、不有限/缺end/错输入/错时钟判运行无效。未进行模型重试或覆盖原始尝试。

[汇总索引与证据SHA256](../validation/numerical-conformance-gxxh6xhr/run-index.json)、[全部360轴CSV](../validation/numerical-conformance-gxxh6xhr/all-360-scalars.csv)、[所有5684失败值JSONL](../validation/numerical-conformance-gxxh6xhr/all-failures.jsonl)、[实际响应摘要](../validation/numerical-conformance-gxxh6xhr/response-summary.json)。失败行保留case/epoch/契约哈希/k/数组/索引、参考和目标十进制及hex binary64值；不是只保留最坏样本。

- C0 epoch `904e8d0a14354b4697556f88f13c1d82`：[执行前清单](../validation/numerical-conformance-u56ce17a/C0/manifest.json)、[结果](../validation/numerical-conformance-u56ce17a/C0/result.json)、[参考元数据](../validation/numerical-conformance-u56ce17a/C0/reference.json)、[目标完整major/post记录](../validation/numerical-conformance-u56ce17a/C0/target.stdout.log)、[逐轴统计](../validation/numerical-conformance-u56ce17a/C0/per-scalar.json)、[全部失败](../validation/numerical-conformance-u56ce17a/C0/failures.jsonl)。同目录保存三个f64输出、输入f64、原始stdout/stderr、进程PID/起止/退出码和执行后身份清单。
- C2G epoch `fa6030ef2c8545cca7cdd806e7d7f62c`：[执行前清单](../validation/numerical-conformance-gxxh6xhr/C2G/manifest.json)、[结果](../validation/numerical-conformance-gxxh6xhr/C2G/result.json)、[参考元数据](../validation/numerical-conformance-gxxh6xhr/C2G/reference.json)、[目标完整major/post记录](../validation/numerical-conformance-gxxh6xhr/C2G/target.stdout.log)、[逐轴统计](../validation/numerical-conformance-gxxh6xhr/C2G/per-scalar.json)、[全部失败](../validation/numerical-conformance-gxxh6xhr/C2G/failures.jsonl)。同目录保存三个f64输出、输入f64、原始stdout/stderr、进程PID/起止/退出码和执行后身份清单。
- C3G epoch `bfc32bfdf4c74490a02a91c84b8ecf4d`：[执行前清单](../validation/numerical-conformance-gxxh6xhr/C3G/manifest.json)、[结果](../validation/numerical-conformance-gxxh6xhr/C3G/result.json)、[参考元数据](../validation/numerical-conformance-gxxh6xhr/C3G/reference.json)、[目标完整major/post记录](../validation/numerical-conformance-gxxh6xhr/C3G/target.stdout.log)、[逐轴统计](../validation/numerical-conformance-gxxh6xhr/C3G/per-scalar.json)、[全部失败](../validation/numerical-conformance-gxxh6xhr/C3G/failures.jsonl)。同目录保存三个f64输出、输入f64、原始stdout/stderr、进程PID/起止/退出码和执行后身份清单。

三例最后模型进程退出后，Windows MATLAB进程清单与WSL `pgrep -af major_model_recorder`均为空，已通知主代理释放独占计算窗口。工具目录按Codebase Memory约定排除；本工作直接读取已知源和固定证据，没有作新的结构图查询或无必要重索引。

## 执行后的比较器边界修正与离线复核

模型执行时的工具源仍保存在各例目录，并由原始manifest固定。执行完成后仅在比较器中把JSON整数token显式转换为float，使整数形式的不等目标值也能输出binary64 hex；此边界没有触发本次三例。增加整数token负向检查后，仅重放三份封存的原始数据，没有重新运行任何模型，也没有改变预算、输入或时间。三例逐轴JSON与所有失败JSONL均与原结果SHA256相同（字节一致）；[离线复核清单](../validation/numerical-conformance-audit-yfepeud6/summary.json)记录新比较器源、原始数据哈希和测试退出0。执行后身份不变描述指各模型进程完成时的检查；这一后续比较器修正另外保留，不冒称当前源与执行时源字节相同。

主代理复核要求在转换前排除bool。最终比较器已对major/post全部数组先要求JSON数值类型int/float且有限，拒绝bool，并补充布尔负例。[最终离线复核](../validation/numerical-conformance-audit-g44e4j8r/summary.json)再次记录全部负例通过、三例统计与失败清单仍逐字节一致，总失败仍5684；前一次离线复核保持原样。

## 全部360个case/轴统计

索引从0开始。每行N=501；最大绝对误差及RMS均使用该轴的原生单位，不跨单位合并。空首失败值表示该轴全部相等，全部保留字段也见机器CSV/JSON。RMS以501样本为分母。

| 工况 | 数组[索引] | 原生单位 | 语义状态 | N | 失败数 | 最大绝对误差 | RMS | 首失败k | 首参考值 | 首目标值 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| C0 | Vehicle60[0] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[1] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[2] | s | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[3] | m/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[4] | m/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[5] | m/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[6] | m | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[7] | m | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[8] | m | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[9] | rad | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[10] | rad | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[11] | rad | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[12] | 1 | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[13] | 1 | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[14] | 1 | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[15] | 1 | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[16] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[17] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[18] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[19] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[20] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[21] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[22] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[23] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[24] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[25] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[26] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[27] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[28] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[29] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[30] | degree | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[31] | degree | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[32] | m | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[33] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[34] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[35] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[36] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[37] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[38] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[39] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[40] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[41] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[42] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[43] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[44] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[45] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[46] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[47] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[48] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[49] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[50] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[51] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[52] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[53] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[54] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[55] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[56] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[57] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[58] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Vehicle60[59] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[0] | us | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[1] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[2] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[3] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[4] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[5] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[6] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[7] | gauss | wmm_physical_fidelity_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[8] | gauss | wmm_physical_fidelity_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[9] | gauss | wmm_physical_fidelity_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[10] | hPa | mapped_physical_observable | 501 | 2 | 2.2737367544323206e-13 | 1.135733211304304e-14 | 153 | 1007.2510342146562 | 1007.2510342146564 |
| C0 | Sensor30[11] | hPa | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[12] | m | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[13] | degC | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[14] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[15] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[16] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[17] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[18] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[19] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[20] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[21] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[22] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[23] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[24] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[25] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[26] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[27] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[28] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | Sensor30[29] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[0] | us | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[1] | 1e-7 degree per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[2] | 1e-7 degree per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[3] | 1e-3 m per native unit | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[4] | native scaled double | physical_accuracy_meaning_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[5] | native scaled double | physical_accuracy_meaning_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[6] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[7] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[8] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[9] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[10] | native angle code | angular_units_and_convention_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[11] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[12] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[13] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[14] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[15] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[16] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[17] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[18] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[19] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[20] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[21] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[22] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[23] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[24] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[25] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[26] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[27] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[28] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C0 | GPS30[29] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[0] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[1] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[2] | s | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[3] | m/s | mapped_physical_observable | 501 | 7 | 8.816207631167156e-39 | 4.379937708815388e-40 | 101 | 6.254852369965466e-30 | 6.2548523699654644e-30 |
| C2G | Vehicle60[4] | m/s | mapped_physical_observable | 501 | 204 | 1.9721522630525295e-31 | 2.6406097147660504e-32 | 102 | 3.7062960365027813e-28 | 3.7062960365025517e-28 |
| C2G | Vehicle60[5] | m/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[6] | m | mapped_physical_observable | 501 | 6 | 5.739718509874451e-42 | 3.0720963345483116e-43 | 104 | 5.028804167469239e-29 | 5.028804167469211e-29 |
| C2G | Vehicle60[7] | m | mapped_physical_observable | 501 | 194 | 3.851859888774472e-33 | 1.549986916322939e-33 | 103 | 9.470144788103625e-31 | 9.470144788103436e-31 |
| C2G | Vehicle60[8] | m | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[9] | rad | encoded_orientation_components_only | 501 | 199 | 2.465190328815662e-32 | 1.2193286513458563e-32 | 180 | 5.788838661472879e-18 | 5.7888386614728786e-18 |
| C2G | Vehicle60[10] | rad | encoded_orientation_components_only | 501 | 6 | 7.52316384526264e-37 | 5.89784920550624e-38 | 103 | -1.597461820221506e-22 | -1.5974618202215062e-22 |
| C2G | Vehicle60[11] | rad | encoded_orientation_components_only | 501 | 210 | 2.1895288505075267e-47 | 3.498810871353901e-48 | 101 | -6.950736882419855e-49 | -6.950736882419856e-49 |
| C2G | Vehicle60[12] | 1 | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[13] | 1 | encoded_orientation_components_only | 501 | 199 | 1.232595164407831e-32 | 6.0966432567292813e-33 | 180 | 2.8944193307364397e-18 | 2.8944193307364393e-18 |
| C2G | Vehicle60[14] | 1 | encoded_orientation_components_only | 501 | 6 | 3.76158192263132e-37 | 2.94892460275312e-38 | 103 | -7.98730910110753e-23 | -7.987309101107531e-23 |
| C2G | Vehicle60[15] | 1 | encoded_orientation_components_only | 501 | 62 | 1.0947644252537633e-47 | 1.3573076247612088e-48 | 101 | 5.768406825694697e-51 | 5.76840682569462e-51 |
| C2G | Vehicle60[16] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[17] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[18] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[19] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[20] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[21] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[22] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[23] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[24] | m/s^2 | mapped_physical_observable | 501 | 1 | 7.52316384526264e-37 | 3.361101729917689e-38 | 104 | 2.545351135395025e-21 | 2.545351135395024e-21 |
| C2G | Vehicle60[25] | m/s^2 | mapped_physical_observable | 501 | 186 | 3.944304526105059e-31 | 1.1750017088127267e-31 | 176 | 3.901423655148012e-17 | 3.9014236551480124e-17 |
| C2G | Vehicle60[26] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[27] | rad/s | mapped_physical_observable | 501 | 175 | 1.9721522630525295e-31 | 9.149294479811463e-32 | 174 | 1.8718735762208645e-16 | 1.8718735762208643e-16 |
| C2G | Vehicle60[28] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[29] | rad/s | mapped_physical_observable | 501 | 290 | 5.473822126268817e-48 | 1.9613497623562838e-48 | 102 | 1.5821737222835028e-44 | 1.582173722283498e-44 |
| C2G | Vehicle60[30] | degree | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[31] | degree | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[32] | m | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[33] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[34] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[35] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[36] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[37] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[38] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[39] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[40] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[41] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[42] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[43] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[44] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[45] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[46] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[47] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[48] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[49] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[50] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[51] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[52] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[53] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[54] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[55] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[56] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[57] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[58] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Vehicle60[59] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[0] | us | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[1] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[2] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[3] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[4] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[5] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[6] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[7] | gauss | wmm_physical_fidelity_unverified | 501 | 39 | 1.6653345369377348e-16 | 2.849366649710549e-17 | 105 | 0.2731008007865005 | 0.27310080078650056 |
| C2G | Sensor30[8] | gauss | wmm_physical_fidelity_unverified | 501 | 114 | 2.7755575615628914e-17 | 4.802606508355503e-18 | 103 | -0.03648431144603924 | -0.03648431144603923 |
| C2G | Sensor30[9] | gauss | wmm_physical_fidelity_unverified | 501 | 44 | 1.1102230246251565e-16 | 2.339679525288184e-17 | 105 | 0.4757685858594119 | 0.47576858585941184 |
| C2G | Sensor30[10] | hPa | mapped_physical_observable | 501 | 1 | 1.1368683772161603e-13 | 5.0791533295611124e-15 | 454 | 1007.254162541956 | 1007.2541625419559 |
| C2G | Sensor30[11] | hPa | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[12] | m | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[13] | degC | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[14] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[15] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[16] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[17] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[18] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[19] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[20] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[21] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[22] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[23] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[24] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[25] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[26] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[27] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[28] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | Sensor30[29] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[0] | us | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[1] | 1e-7 degree per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[2] | 1e-7 degree per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[3] | 1e-3 m per native unit | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[4] | native scaled double | physical_accuracy_meaning_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[5] | native scaled double | physical_accuracy_meaning_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[6] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[7] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[8] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[9] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[10] | native angle code | angular_units_and_convention_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[11] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[12] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[13] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[14] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[15] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[16] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[17] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[18] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[19] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[20] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[21] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[22] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[23] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[24] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[25] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[26] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[27] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[28] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C2G | GPS30[29] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[0] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[1] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[2] | s | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[3] | m/s | mapped_physical_observable | 501 | 147 | 1.1102230246251565e-16 | 1.1812663380805638e-17 | 1 | 6.254852369965466e-30 | 6.2548523699654644e-30 |
| C3G | Vehicle60[4] | m/s | mapped_physical_observable | 501 | 277 | 1.1102230246251565e-16 | 2.4646595029350217e-17 | 2 | 3.7062960365027813e-28 | 3.7062960365025517e-28 |
| C3G | Vehicle60[5] | m/s | mapped_physical_observable | 501 | 7 | 2.220446049250313e-16 | 2.1620621174126005e-17 | 332 | -0.7884325625874159 | -0.7884325625874158 |
| C3G | Vehicle60[6] | m | mapped_physical_observable | 501 | 69 | 2.710505431213761e-20 | 6.7014650420133024e-21 | 4 | 5.028804167469239e-29 | 5.028804167469211e-29 |
| C3G | Vehicle60[7] | m | mapped_physical_observable | 501 | 380 | 1.3877787807814457e-17 | 4.782939154563286e-18 | 3 | 9.470144788103625e-31 | 9.470144788103436e-31 |
| C3G | Vehicle60[8] | m | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[9] | rad | encoded_orientation_components_only | 501 | 238 | 5.551115123125783e-17 | 1.504656954389587e-17 | 80 | 5.788838661472879e-18 | 5.7888386614728786e-18 |
| C3G | Vehicle60[10] | rad | encoded_orientation_components_only | 501 | 17 | 5.551115123125783e-17 | 3.921312611662815e-18 | 3 | -1.597461820221506e-22 | -1.5974618202215062e-22 |
| C3G | Vehicle60[11] | rad | encoded_orientation_components_only | 501 | 289 | 1.3877787807814457e-17 | 2.5996098188234747e-18 | 1 | -6.950736882419855e-49 | -6.950736882419856e-49 |
| C3G | Vehicle60[12] | 1 | encoded_orientation_components_only | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[13] | 1 | encoded_orientation_components_only | 501 | 226 | 2.0816681711721685e-17 | 5.210837042785272e-18 | 80 | 2.8944193307364397e-18 | 2.8944193307364393e-18 |
| C3G | Vehicle60[14] | 1 | encoded_orientation_components_only | 501 | 13 | 1.3552527156068805e-20 | 1.2664570091608876e-21 | 3 | -7.98730910110753e-23 | -7.987309101107531e-23 |
| C3G | Vehicle60[15] | 1 | encoded_orientation_components_only | 501 | 181 | 5.204170427930421e-18 | 1.2663516355540011e-18 | 1 | 5.768406825694697e-51 | 5.76840682569462e-51 |
| C3G | Vehicle60[16] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[17] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[18] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[19] | rpm | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[20] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[21] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[22] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[23] | rpm | inactive_channels_not_aircraft_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[24] | m/s^2 | mapped_physical_observable | 501 | 146 | 8.881784197001252e-16 | 5.908378467799313e-17 | 4 | 2.545351135395025e-21 | 2.545351135395024e-21 |
| C3G | Vehicle60[25] | m/s^2 | mapped_physical_observable | 501 | 208 | 4.440892098500626e-16 | 1.0426022311258004e-16 | 76 | 3.901423655148012e-17 | 3.9014236551480124e-17 |
| C3G | Vehicle60[26] | m/s^2 | mapped_physical_observable | 501 | 5 | 8.881784197001252e-16 | 6.58033040892131e-17 | 392 | -3.584480258787728 | -3.5844802587877282 |
| C3G | Vehicle60[27] | rad/s | mapped_physical_observable | 501 | 97 | 1.1102230246251565e-16 | 2.5921576926108995e-17 | 74 | 1.8718735762208645e-16 | 1.8718735762208643e-16 |
| C3G | Vehicle60[28] | rad/s | mapped_physical_observable | 501 | 157 | 1.1102230246251565e-16 | 5.1127856143961794e-17 | 107 | 0.00559115402194978 | 0.005591154021949779 |
| C3G | Vehicle60[29] | rad/s | mapped_physical_observable | 501 | 43 | 2.1382117680737565e-50 | 2.4819874904185702e-51 | 2 | 1.5821737222835028e-44 | 1.582173722283498e-44 |
| C3G | Vehicle60[30] | degree | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[31] | degree | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[32] | m | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[33] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[34] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[35] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[36] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[37] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[38] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[39] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[40] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[41] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[42] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[43] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[44] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[45] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[46] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[47] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[48] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[49] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[50] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[51] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[52] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[53] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[54] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[55] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[56] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[57] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[58] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Vehicle60[59] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[0] | us | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[1] | m/s^2 | mapped_physical_observable | 501 | 65 | 2.7755575615628914e-17 | 4.3198334560285154e-18 | 164 | -0.0026674330623334902 | -0.0026674330623334907 |
| C3G | Sensor30[2] | m/s^2 | mapped_physical_observable | 501 | 185 | 3.469446951953614e-17 | 8.555356262420717e-18 | 146 | -0.008187674962513006 | -0.008187674962513004 |
| C3G | Sensor30[3] | m/s^2 | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[4] | rad/s | mapped_physical_observable | 501 | 108 | 1.1102230246251565e-16 | 2.45072355955392e-17 | 108 | 0.0016664500812948145 | 0.0016664500812948147 |
| C3G | Sensor30[5] | rad/s | mapped_physical_observable | 501 | 125 | 2.220446049250313e-16 | 8.24408684718765e-17 | 112 | 0.006573640971549386 | 0.006573640971549385 |
| C3G | Sensor30[6] | rad/s | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[7] | gauss | wmm_physical_fidelity_unverified | 501 | 80 | 2.7755575615628914e-16 | 4.071371722771768e-17 | 5 | 0.27281580257063287 | 0.2728158025706329 |
| C3G | Sensor30[8] | gauss | wmm_physical_fidelity_unverified | 501 | 165 | 1.6653345369377348e-16 | 1.523456126938408e-17 | 3 | -0.03580951227537994 | -0.035809512275379936 |
| C3G | Sensor30[9] | gauss | wmm_physical_fidelity_unverified | 501 | 76 | 5.551115123125783e-16 | 4.5595262603755485e-17 | 5 | 0.47250932606398677 | 0.4725093260639867 |
| C3G | Sensor30[10] | hPa | mapped_physical_observable | 501 | 1 | 2.2737367544323206e-13 | 1.0158306659122225e-14 | 309 | 1007.2382360972755 | 1007.2382360972757 |
| C3G | Sensor30[11] | hPa | mapped_physical_observable | 501 | 4 | 1.734723475976807e-18 | 9.541293887399028e-20 | 185 | -0.0018776835099400056 | -0.0018776835099400054 |
| C3G | Sensor30[12] | m | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[13] | degC | mapped_physical_observable | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[14] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[15] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[16] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[17] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[18] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[19] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[20] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[21] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[22] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[23] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[24] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[25] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[26] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[27] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[28] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | Sensor30[29] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[0] | us | schedule_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[1] | 1e-7 degree per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[2] | 1e-7 degree per native unit | mapped_physical_observable_unquantized_double | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[3] | 1e-3 m per native unit | height_datum_semantics_not_fully_verified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[4] | native scaled double | physical_accuracy_meaning_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[5] | native scaled double | physical_accuracy_meaning_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[6] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 136 | 2.842170943040401e-14 | 2.997059719762453e-15 | 144 | 0.21101260687437653 | 0.21101260687437645 |
| C3G | GPS30[7] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 89 | 1.4210854715202004e-14 | 1.3104581656537307e-15 | 169 | -0.22938571275123382 | -0.2293857127512338 |
| C3G | GPS30[8] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 199 | 1.4210854715202004e-14 | 2.625495796137511e-15 | 144 | -0.2041539865355749 | -0.20415398653557487 |
| C3G | GPS30[9] | 1e-2 m/s per native unit | mapped_physical_observable_unquantized_double | 501 | 6 | 2.842170943040401e-14 | 1.904682498585417e-15 | 332 | -76.44747655820791 | -76.4474765582079 |
| C3G | GPS30[10] | native angle code | angular_units_and_convention_unverified | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[11] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[12] | dimensionless integer-valued double | interface_metadata | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[13] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[14] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[15] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[16] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[17] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[18] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[19] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[20] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[21] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[22] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[23] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[24] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[25] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[26] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[27] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[28] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
| C3G | GPS30[29] | native double | reserved_not_physical_coverage | 501 | 0 | 0.0 | 0.0 |  |  |  |
