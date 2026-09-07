# G6 模型参考来源核对补充（e1 一致链与能力盘点）

2026-09-07 二轮；只读文本/ZIP XML/DLL 字符串与本机 MATLAB 许可查询（任务私有 startup 目录，未改厂商/用户文件）。承接 [来源核对](model-reference-provenance.md)；不关闭 G6/#23，不提出未经依据的误差预算。

## 新事实

1. **e1_MinModelTempLib 是版本一致链**：SLX `metadata/coreProperties.xml` revision **1.1183** 与 ZIP 生成头 `Model version 1.1183` 一致（e0 为 SLX 11.8 vs ZIP 11.0 不一致）。e1 生成标记：R2024b Coder 24.2、ert.tlc、ODE4、0.001s；根 I/O 与 e0 完全相同（inPWMs[16]、TerrainIn15d[15]、HILSensor30d/HILGPS30d[30]、VehileInfo60d[60]）。
2. **e1 init 与 e0 同动力学**（部分变量改名）：GPS [40.1540302, 116.2593683]、海拔 -50、uavMass 1.515、motorCr 842.1、motorWb 22.83、motorT 0.0214、motorJm 0.0001287、rotorCm 2.783e-7、rotorCt 1.681e-5、uavR 0.225、uavCd 0.055、uavMotNumbs int8(4)、uavType 3。
3. **e0 与 e1 生成源码数值不恒等**：唯一常量 557 项相同；e1 独有 `a_sath/a_satl=±160.0`（<S277> 加速度饱和）、`4.36` 三向量、`850000.0` 及版本标记 24.2/1.1183/2017.838…；e0 独有仅版本标记（2019.838…、9.8、9.81）。**e1 是更新的不同动力学变体**，不是 e0 的同源替代品。
4. **e1 DLL 导出包装 ABI 由二进制字符串实证**：`DllCreatModel/DllDestroyModel/Dllstep/DllGetStep0/DllReInitModel/DllInitGpsPos/DllInitPosAngState/DllInputPWMs/DllTerrainIn15d/DlloutHILSensor30d/DlloutHILGPS30d/DlloutVehileInfo60d`，逐一对应生成根 I/O；`DllInitPosAngState` 为正确名（SDK 消费者 DllSimCtrlAPI.py 的 `DllInitPosAngStat` 检查确属其自身缺陷）。DLL 内无版本文本，**DLL↔ZIP 1.1183 构建绑定仍未证明**；两个模板目录及 E:/rflysimtools 全树均无 Dll* 导出包装的 .h/.c/.cpp 源（仅 .p 构建助手与 ctypes 消费者）。
5. **e0 SLX 11.8 由 R2022b 保存**（coreProperties 含 R2022b），与本机 MATLAB R2022b 兼容可打开/仿真；e1 SLX 无本地可运行版本（其链为 R2024b）。
6. **本机 MATLAB 能力盘点**（任务私有 `-sd`+私有 startup.m，未执行原 RflySim 自动注册）：Simulink 10.6 可用；Simulink Coder 9.8 已安装但**许可不存在**（`license('checkout','Simulink_Coder')` 错误 -5,357）；RTW_Embedded_Coder 许可可用（1）但无 Simulink Coder 不能独立生成。**本机可执行 SLX 仿真，不可从 SLX 重新生成代码。**

## 对 G6/#23 的含义（不代为决定）

- **参考执行可行路径**：本机 Simulink 运行 e0 SLX 11.8 作为参考；实现侧为当前 wksim 物理（e0 ZIP 11.0 源码构建）。前置子步骤是 11.0↔11.8 漂移刻画（SLX 11.8 块参数 XML vs ZIP 11.0 常量的文本级核对），且误差预算必须按工程来源在运行前冻结，**不能倒用实测差异制定预算**；若漂移具模型影响，则须改走供应商原始材料/e1(R2024b 环境)/其他来源路径。
- **不可行项**：本机无法从 SLX 重新生成代码（Simulink Coder 无许可）；e1 链需 R2024b 环境；DLL 作参考需 #27 宿主且其↔源码绑定只能由差异对照本身实证（循环但不自洽为空话：对照通过即互为佐证，不通过即证不对应）。
- e0 DLL（旧+新命名导出并存，见重建文档）与 e1 DLL 的实际 ABI 仍以二进制/加载核验为准，ctypes 消费者不作 ABI 权威。

所有哈希/行号级证据：本文件只读结论可经相同命令重放核对；[首轮核对](model-reference-provenance.md) 的资源清单继续有效。#23 仍待 #6 批次决策与 G6 预算批准。
