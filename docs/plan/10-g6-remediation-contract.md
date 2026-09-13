# #59 G6 来源一致数值验收路线

2026-09-13 状态核对：固定 e0 SLX 11.8 已生成、独立构建并具有 major 采集与同源比较入口。`tools/run_e0_same_source_conformance.py` 已实现合同检查、执行身份核验、normal/native 编排及严格逐量比较；当前缺少有依据且 approved 的完整逐量预算，入口在启动模型前返回 blocked。来源、入口和预算是不同的完成条件，不重新派发已完成的生成/入口工作。

主任务材料补充：[G6材料索引](../g6-material-index.md)已定位本机厂家开发/生成说明和传感器标定教材、MWLOG/MAT示例数据。它们是继续实现和误差分析的输入，尚未建立与当前e0模型全部验收量的计量/工况绑定，不能直接改填本合同缺失的精度预算；R1旧结果保持不变。

历史记录（2026-09-09）：当时状态为 `blocked_budget_and_same_source_entry`。截至2026-09-13，同源入口已经实现，当前缺口是完整、有依据且获批的误差预算；不能把历史状态当成入口仍缺失。本文件尚未冻结新的物理精度合同。#59、父 #10、G6、Full 仍开放；R1 继续 `numerical_failed`。

## 要求与已有证据

[Full规格](full-migration-spec.md)要求固定模型、初态、输入、随机种子与预先误差包络，不要求跨平台浮点逐位一致。[G6目标](goal-objective.md)还要求完整功能账本、硬件实测、来源许可和交接；本数值路线不能替代这些义务。[扩展账本](full-scope-expansion.md)中未完成项继续保留。

[R1合同](../../Simulator/wksim_core/numerical-conformance-v1.json) SHA256 为 `23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0`，120槽预算均为绝对0、相对0。它检验跨版本原生值保留，是比Full要求更强的特定条件，不是物理精度预算。C0/C2G/C3G 原结果分别有2/1943/3739个不等值，共180360次比较、5684个失败值、49个失败case/轴；全部执行有效。没有将微小差值归因为已证实的编译器误差，没有重试或改判。

本次重新计算15份来源、配置、工具和结果身份，见[证据](../../validation/10-g6-remediation/review-20260909/inspection.json)。原记录、阈值和厂商材料未修改。

## 来源决策

选择 **固定 e0 SLX 11.8 + 原 init + 实际有效库依赖，normal 执行作参考；由同一冻结副本新生成并独立编译的 native 模型作候选**。该来源一致路线已有生成候选与采集实现；尚未完成新合同下的数值验收，也未据此替换正式模型。

| 材料 | 身份/证据 | 决策 |
| --- | --- | --- |
| e0 SLX 11.8 | c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392 | 选定可编辑参考来源；已有R2022b normal有效运行 |
| e0 init | 9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991 | 与SLX、22项有效参数及17份依赖一起冻结 |
| e0 ZIP 11.0 | d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed | 保留历史目标；没有11.0历史SLX绑定，不能改称11.8产物 |
| e1 SLX/ZIP 1.1183 | [修正后的来源核对](2026-09-08-numerical-contract-readiness.md) | revision相等不证明外链pixhawk库同源；有不同动力学，不替代e0 |
| e0/e1 DLL或ZIP再编译 | [来源报告](model-reference-provenance.md) | 缺完整DLL构建绑定；目标自比只证明包装/重复性 |

若取得ZIP11.0实际生成时SLX/init/库/生成清单，可另审同源11.0路线；当前未找到该成套材料，不据目录相邻推定。normal与新native的独立执行引擎能验实现一致性，但两者共享模型方程，不能单独证明实机准确性。

[#70合同](26-generation-contract.md)中的权限和入口缺口应按其历史时间理解。2026-09-13主会话通过GitHub CLI核实：[#70](https://github.com/unununnnn/wksim/issues/70)已CLOSED（最后更新2026-09-11），[#26](https://github.com/unununnnn/wksim/issues/26)仍OPEN；当前同源11.8已生成并有采集/比较入口。#70关闭不等于#26、G6或Full通过。历史normal参考使用已获本机授权；不把缺少再分发权解释成禁止所有本地使用，也不以旧许可失败或license test=1代替实际生成证据。厂商字节保持本地。

## 采样、随机数和工况

沿用[已验证采样机制](../2026-09-09-reference-sampling-contract.md)：ODE4、1ms；两根输入宽16/15，SampleTime=.001、Interpolate=off，左端输入整步保持；major样本k=0..500共501行。native需501次完整step，终态引擎时间.501s，与比较末时刻.500s分开记录。新生成源必须重新定位major采样点，禁止直接套用11.0行号、平移post输出、补样或额外step刷新输出。

保留原22项参数、初态、四电机、FaultInParams、滤波/Memory状态、七组seed及min/max/1ms采样。G=0仍有噪声；i_rand=off，不补造i_pow。七组seed相符不证明随机算法、首次取样和reset相位相符；需在新源逐组绑定状态初始化、更新顺序与输出支路。按步记录随机源可见量或可审查的状态证据；不可见则列为未验证。无噪声只能另立派生配置逐源清零，不能把它计为原默认传感器通过。

首批沿用R1三份输入的精确CSV身份：C0全零；C2G k100起四路.6；C3G初始四路.6，k100起第一路.65；其他12路和Terrain15为零。每例新进程、独立epoch、原地面初态。这些工况的依据是源码电机关系Wb+Cr*u和Ct*omega²：.6理想总推力约18.75N，大于1.515kg的约14.86N重量；用于激发响应，不是容差依据或离地保证。

后续G6还需自由落体、其余三电机逐路扰动、冷重建、长轨迹、非零地形及Full约定构型/故障。各自需先固定有效初态、接触/环境语义、时长与输入表；本票不把未定义条件写成可立即运行的测试。三短工况通过也不覆盖这些范围。

## 新误差合同的实施切缝

新合同另用ID和文件，不能修改R1。至少逐量包含 `observable, source_mapping, unit, frame, datum, sample_phase, metric, abs_budget, rel_budget, derivation, domain, approval, contract_sha256`。字段未知或无预算依据时状态必须为blocked，不以null/缺省值通过。

位置、速度、加速度、角速率、电机转速按原生SI/已核对rpm逐轴报告峰值与RMS。接口ID、mask、样本数与步号保持精确验证。四元数方向、GPS航向编码、海拔基准、eph/epv语义先核实；未核实槽仍完整记录原编码，不能计作物理覆盖。保留槽和未使用电机槽单列。

对已定义连续量，可采用逐样本 `abs(x-r) <= A_i + R_i*abs(r)`，并独立设置RMS上限；A_i/R_i目前**未赋值、未批准**。每项必须从明确工况上的误差分析或校准/传感器规格及用途需求得到。平滑区RK4全局误差阶为O(h^4)，但仅知道阶数不能确定误差常数；需状态域内导数/稳定性界及舍入传播界，接触/饱和/随机事件不得套用平滑界。独立网格收敛只能支持分析，不能拿本次候选差值乘系数反推验收预算。

实机准确性另需可追溯物理参考、测量不确定度、标定和适用域；模型参数值、噪声幅值、double epsilon、R1差值、SITL航点门槛均不足以给出该预算。当前缺少这些依据，不能诚实冻结非零物理预算。

## 执行入口与拒绝边界

现有可执行检查（项目根PowerShell，本次已执行）：

```powershell
python validation/test_numerical_conformance.py
Get-FileHash -Algorithm SHA256 Simulator/wksim_core/numerical-conformance-v1.json
```

第一条只检查比较器正负例，不执行载具。现有 `python tools/run_numerical_conformance.py --run --cases C0 C2G C3G` 是**旧R1跨版本重跑入口**，本票未运行；它固定旧合同、构建及目标hash，不能作为新同源G6命令。

同源入口现在为 `python tools/run_e0_same_source_conformance.py <新合同路径> --output <新结果路径> --evidence-dir <新证据目录>`；这是参数格式，当前没有完整获批预算合同可用来启动比较。实际字段、校验顺序和命令见[同源命令接缝](59-e0-same-source-command.md)。入口在预算和执行身份通过后才可到达模型启动，不修改旧入口 pin，不填造预算，不把参数示例当成可运行的已批准合同。

入口交付时须给出实际可运行的argv、cwd、工具版本/hash、输入与新合同hash、独立输出目录、超时和进程收尾；不能发布占位CLI供Luna执行。结果schema须含case/epoch、source/config/contract身份、两侧原始binary64输出与全部major/post输入、实际退出/终态、逐量峰值/RMS/首失败及全部失败。状态分为blocked、invalid_run、numerical_failed、declared_cases_pass；physical_accuracy与G6状态独立。

缺身份、错输入/格点、少样、非有限值、bool伪数值、缺terminal、随机相位未证或预算未冻结均不得通过。即使新比较通过也不改写R1结果。

## #59 当前交接

已完成来源选择、历史证据复核、采样/随机数约束、生成采集及同源比较入口；有依据的逐量预算仍缺失，保持 #59/G6 开放。复用既有 11.8 C0 major 与 normal 原件的离线检查覆盖 60,120 值，Sensor30[10] 在 k153/k181 仍有两处差异；另一个对角求解候选只验证了 C3G 首步 240 major 与 13 映射态等有限范围，不能代替本合同的完整比较。细节见[对角求解实验](../2026-09-13-diagonal-solve-experiment.md)。下一步聚焦预算所需的模型误差分析/校准依据与尚未证明的工况，不重建已完成入口，不重跑旧 R1。

实际会话 `01a085ae-8e74-7431-aa16-113eac9436f4` 最新turn_context已核验 `model=gpt-6-astra, effort=low`；没有子代理。证据只发布项目文档、哈希与既有结果摘要。
