# CopterSim 完整功能重建：已确认方向与资源证据

更新：2026-09-05。对应 [RflySim 模块组织与 UE5.5 SITL 运行边界决策](https://github.com/unununnnn/wksim/issues/4)。本页是会话决策与证据的本地副本，不是完成声明。

## 用户已经确认

- 终态要求完整功能与操作流程复刻，不缩减成只满足首个SITL实验的子集。
- 参考范围确定为2026-09-05冻结的当前公开完整版全部功能；定制版专属能力单列扩展，不自动进入基线。
- 移植主体仍为Prometheus；UE5.5显示，WSL Ubuntu22.04与ROS2/DDS，PX4及ArduCopter支持不变。
- 自主核心确定取代Gazebo。保留本机Gazebo安装不代表保留其为目标依赖；不执行卸载。
- 核心必须能够独立构建运行，不要求原版CopterSim.exe或闭源模型DLL存在；原版DLL仅可选导入。
- 保留完整功能与流程，界面按wksim重做，不要求品牌或像素级布局复制。
- MATLAB/Simulink允许作为构建期工具生成C/C++，日常仿真不依赖MATLAB；原先的轻量MATLAB接口仍需保留。
- 充分使用本地模型、SDK、模板、参数和脚本；对本地二进制开展兼容性分析。当前离线范围不包括修改原程序、授权绕过或再发布厂商代码。

用户已确认数值验收方法：协议与操作行为兼容，动力学/传感器按固定工况和明确误差阈值对照，不要求跨平台浮点结果逐位一致。具体工况与阈值数值仍须在对照测试前锁定，不得用试验结果事后放宽，也不得给出无依据的复现百分比。

参考文档快照与哈希见 `validation/reference-full-20260905/manifest.json`。它冻结文档功能范围，不代表已获得或核实某个完整版可执行文件的精确应用版本。本地原程序哈希仍作为独立对照证据，不把安装包V5.00标签等同于CopterSim组件版本。

## 本地材料不止2019年公开模型

[公开CopterSim仓库](https://github.com/RflySim/CopterSim)的核查基线为 `0d14487f8dc3086ad29387ed40e068e301905343`，提交日期2019-07-25。它是模型工程，不是当前完整应用源码。

本地另发现：`E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip`。

- SHA256：`d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`。
- 7个成员，包括实际模型 `.cpp/.h`、`ert_main.cpp`、`rtwtypes.h`、`buildInfo.mat` 及 `rtw_continuous.h`、`rtw_solver.h`。
- 生成标记：Simulink Coder R2022b，模型版本11.0，2025-12-08，Windows x86-64，`ert.tlc`；此模型版本不是CopterSim应用版本。
- 入口 `MulticopterModelClass::initialize/step/terminate`；源码设置基本步长0.001秒。
- 输入：16维PWM、15维地形；输出：30维HIL传感器、30维GPS、60维载具状态。
- 示例main是无实时节拍的连续循环；还缺经过验证的构建配方、调度、飞控接口、插件包装及完整工具程序。
- 生成注释保留 `Validation result: Not run`；这是厂商生成时的标记。后续本机独立构建与冒烟检查已通过，见下节，但不代表原版完整数值验证通过。

因此首个自主模型验证可优先评估这份本地生成代码，不能据此宣称全部机型都有可构建源码，也不能据此推断可再发布。模型旁的 `.p` 构建助手是MATLAB P-code，不等于可读 `.m` 源码。

## 独立构建与有界模型检查（已通过）

2026-09-05 04:28:36 UTC，在WSL Ubuntu22.04.5、GCC11.4上执行 `tools/probe_generated_model.py`：

- 仅将已核查的5个模型源/头文件解包到WSL临时目录，未修改原ZIP，未将厂商源文件复制进仓库。
- 使用 `g++ -std=c++17 -O2 -fno-fast-math` 编译成功。未运行MATLAB、CopterSim、Gazebo、ROS、飞控或UE；未安装新软件。
- 动态依赖仅列出标准Linux C/C++/数学运行库与加载器，没有MATLAB或CopterSim运行库。
- 3个工况各2000步、基本步长0.001秒；每步检查120维输出全部有限、模型时钟递增正确、无模型错误。
- 零输入与0.65输入产生不同位置/旋翼输出；0.65输入重复运行的120维最终输出最大绝对差为0（仅同一构建的重复性，非跨平台承诺）。
- 原ZIP哈希不变。编译、依赖、运行日志和完整输出保存在 `validation/generated-model-inco3l9z/`。

上述证明一个保留模型可在WSL独立构建、运行并响应输入，不证明所有机型、真实物理精度、DLL兼容、实时性能、原版数值等价或双飞控SITL。诊断用容差（时钟与同构建重复性1e-9）不是最终动力学验收阈值。

## 双飞控物理实现（首个机型已通过）

2026-09-05新增 `Simulator/wksim_core`，实现本地模型构建、C ABI、独立调度、AP JSON与PX4 MAVLink物理接口。两套真实飞控均已通过正常解锁、3米起飞、5秒保持、NED航点、2秒航点保持、降落和上锁；无需原CopterSim、Gazebo或MATLAB。12项自动化检查及原模型回归通过，Codebase Memory已刷新。详见[可复现报告](2026-09-05_sitl-physics-report.md)和[运行说明](../Simulator/wksim_core/README.md)。

这仍只有一个四旋翼模型和物理链路；该阶段的MAVLink测试命令不等于DDS任务接口。后续已通过[双原生DDS验证](2026-09-05_native-dds-report.md)和[UE5.5真实显示验证](2026-09-05_ue55-report.md)，并迁移[完整ROS2接口包](2026-09-05_prometheus-ros2-report.md)。Prometheus控制/任务、MATLAB接口、可选原DLL、其他模型/模式及完整数值验收仍未完成。

用户随后确认WSL核心/双DDS/Prometheus与Windows UE/可选DLL宿主分工、联合场景共享权威时间，详见[运行边界决议](https://github.com/unununnnn/wksim/issues/4#issuecomment-5550138622)。目前双独立计时实验不等于同场景联合仿真；原DLL导入、环境反馈和全部Full工作流保留为后续实现要求。

## 本轮静态盘点

可复现脚本：`work/coptersim-compat-20260905/inspect_pe.py`；原始结果：`work/coptersim-compat-20260905/evidence/pe-inventory.json`。

- 只读解析2个EXE与16个模型DLL，全部是AMD64 PE，无CLR目录；解析器没有报告警告。这不是“无壳”或“所有依赖已知”的结论。
- CopterSim.exe导入Qt5界面、网络、串口等库，并保留部分 `ModelCalc` 修饰导出名；NoUI程序没有导出表。导出名只是后续定位线索，不是完整函数恢复。
- 模型DLL同时有旧命名接口（`DlloutputSensors`、`DlloutModel3DInfo`）与新命名接口（`DlloutHILSensor30d`、`DlloutVehileInfo60d`）；加载器必须核查版本、签名和布局，不能仅凭名字替换。
- SDK `DllSimCtrlAPI.ModelLoad` 已包含加载、重置、步进及输出调用。其碰撞数组类型声明存在前后差异，初始化函数存在名称检查差异；调用方源码可用于交叉核查，不应无条件当成准确ABI规范。
- 静态导入只见KERNEL32的模型也可能动态加载其他能力，不能据此断言其运行时完全独立。

## 完整功能清单草案

公开完整版范围已冻结；下表仍是需要细化成逐项测试的验收目录，不是已实现功能。终态覆盖与首期SITL分开管理。

| 功能域 | 需要覆盖/验证的内容 |
| --- | --- |
| 模型 | 内置多旋翼、XML参数、可选DLL、其他载具模型与构型 |
| 动力学与传感器 | 六自由度、电机/动力、环境、IMU/GPS等、噪声、地形/碰撞反馈 |
| 运行调度 | 初始化、重置、暂停/步进/倍速、时间戳、确定性、多实例隔离，按参考版本逐项核对 |
| 飞控接口 | PX4标准/定制SITL、ArduCopter、后续HIL/SIH等参考版本模式，不以DDS代替物理闭环 |
| 外部接口 | SDK报文、控制/真值、参数/故障注入、地面站转发、MATLAB轻量接口 |
| 工具操作 | 模型配置、数据库/导入导出、启动CLI/NoUI、wksim界面、日志、错误与运行状态 |
| 多机与网络 | 载具编号、端口、命名空间、分布式运行和适用版本中的通信模式 |
| UE5.5 | 位姿/旋翼、场景与地形/碰撞、必要视觉传感器接口，按工具链边界逐项映射 |

依据：[CopterSim功能手册](https://rflysim.com/doc/zh/3.Soft/coptersim.html)、[协议目录](https://rflysim.com/doc/zh/4.DevRef/protocol.html)、[模型SDK](https://rflysim.com/doc/zh/4.DevRef/pysdk/ctrl/dllsim.html)及本地资源。暂停/步进/确定性等也包括自主实现所需验收项，不声称参考产品都已公开支持。定制版专属功能不可默认为当前可观察行为。

## 后续验证

1. 在已冻结的公开完整版范围内建立每项功能的“文档/源码/参考观测/实现/测试”记录，无法观测的项明确标注。
2. 独立构建与时间/有限数值/重复性/输入响应冒烟已通过；继续固定初态、参数、随机种子、工况和误差预算，完成物理数值对照。禁止把冒烟成功当作精度验证。
3. 对齐旧/新模型ABI，再对模型宿主执行输入输出对照；必要时只围绕缺口定位二进制调用和状态行为。
4. 自主模型、双原生DDS与UE5.5已分别验证；继续迁移Prometheus控制/任务、正式状态分发和联合场景时钟，才能验收完整目标SITL工作流。不得以诊断节点、原程序或Gazebo成功代替此项。
5. 后续扩展全部目标功能、界面、机型、故障、多机及其他仿真模式；阶段交付不改变完整终态。

当前没有反编译全部应用、恢复原源码或完成完整自主仿真产品。双飞控物理联调已通过一个机型，DDS与UE诊断边界已验证，但Prometheus任务端到端仍未完成；运行边界决策票已关闭，验收与后续实施票继续开放。
