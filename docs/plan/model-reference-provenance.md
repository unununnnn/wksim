# G6 模型参考来源核对

2026-09-07；只读文本及 ZIP/SLX XML，未加载 DLL、执行 MATLAB/厂商程序、逆向二进制或修改厂商文件。Full 范围和既有 #5/#8 批准保持有效。本报告不关闭 G6/#23，也不提出未经依据的误差预算。

**结论：init 的主要数值与生成源码相符，但相邻 SLX 版本较新，DLL 的构建来源及实际 ABI 仍无证据。当前四个文件不能组成已证明的独立数值参考链。**

## 可复核证据

模板目录为 `E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp`。12 个文件的大小和 SHA256 见 [资源清单](../../validation/model-reference-provenance-20260907/resource-hashes.json)；两个档案的全部成员、原始字节 SHA256 和 ZIP 时间字段见 [档案清单](../../validation/model-reference-provenance-20260907/archive-manifest.json)。ZIP 时间字段不等于可信构建证明。

| 关系 | 已证明 | 未证明 |
| --- | --- | --- |
| ZIP → 生成模型 | `Exp1_MinModelTemp.cpp/.h/ert_main.cpp` 头均标记模型 `Exp1_MinModelTemp`、版本 **11.0**、Coder 9.8 R2022b、生成时间 **2025-12-08 17:36:13**、ert.tlc、Windows64；Validation result 为 Not run | 尚无独立物理精度验证 |
| SLX → init | `simulink/blockdiagram.xml:8–13` 的 InitFcn 按自身文件名构造 `_init.m` 并 run；因此现有 SLX 明确引用相邻 init | 文本回调不能证明历史生成时实际使用的 init 哈希 |
| SLX ↔ ZIP | 两者模型名称、ODE4、0.001 秒步长和根 I/O 名称/尺寸一致 | SLX `metadata/coreProperties.xml` revision 为 **11.8**、修改时间 **2025-12-10T09:38:45Z**；blockdiagram ModelVersionFormat 同为 11.8。它不是已证明的 ZIP 11.0 原始生成版本 |
| init ↔ ZIP 参数 | 22 项具名参数/初态逐项数值相等，见下表和 JSON | `ModelParam_uavMotNumbs=int8(4)` 无同名生成参数；`FaultParamAPI.FaultInParams` 初始化也未建立到生成参数的映射。名称消失可能是优化或未使用，不能推断具体原因 |
| DLL ↔ ZIP/SLX/init | DLL 存在，SHA256 `30747a8d47ca76ed3a2c751eac212102dde6a3ab4b29ba8eaae5926d416ca91b`。SITL 批处理声明 `DLLModel=Exp1_MinModelTemp` 并将同名 DLL 复制至 CopterSim 模型目录；这证明预期使用关系 | 没有构建清单、源码哈希、链接日志或导出实现将该 DLL 绑定到 ZIP 11.0 或 SLX 11.8；没有加载测试，不能认定实际导出函数、参数、种子或输出一致 |

[文本证据](../../validation/model-reference-provenance-20260907/text-evidence.json) 使用 CRCRLF 规范化后的逻辑行号；哈希始终对原始字节计算。init 的赋值按 GB18030 解码，结论仅引用可无歧义读取的数值表达式。

## 参数与接口对应

[逐项参数表](../../validation/model-reference-provenance-20260907/parameter-correspondence.json) 保留 init 表达式和源码 initializer。22 项共同数值：初始 Euler/位置/机体系速度/角速度均为三维零，RPM=0；GPS=[40.1540302,116.2593683]、海拔参数=-50；质量=1.515，惯量=diag(0.0211,0.0219,0.0366)；motorCr=842.1、motorWb=22.83、motorT=0.0214、motorJm=0.0001287、motorMinThr=0.05；rotorCm=2.783e-7、rotorCt=1.681e-5；uavR=0.225、uavCd=0.055、uavCCm=[0.0035,0.0039,0.0034]、uavDearo=0.12；3DType/uavType 均为 3。质量及动力学参数相同不能证明整个模型方程或传感器版本相同。

生成头 `Exp1_MinModelTemp.h:349–358` 的根输入是 real_T inPWMs[16]、TerrainIn15d[15]；输出为 HILSensor30d[30]、HILGPS30d[30]、VehileInfo60d[60]。SLX `simulink/graphicalInterface.xml` 完整列出同名同维端口，输出及 terrain 声明 double。SLX 6DOF mask 将初始位置标为 NED、初始速度标为 FRD。这里证明端口和局部坐标标签相符，**未完成 120 个输出元素的逐量单位/顺序及 DLL 导出映射**。

生成 cpp:8493–8495 设置 ODE4 和 0.001 秒。其初始化部分存在多组 RandSeed 的赋值逻辑，已留文本证据；init 不提供统一随机种子合同，SLX 与 DLL 的逐组种子/噪声配置相等尚未证明。

## DLL 可读包装边界

模板目录没有可读 `.h/.c/.cpp` DLL 导出包装实现；ZIP 仅有生成模型、示例 `ert_main.cpp`、类型/求解器头和 `buildInfo.mat`。`ert_main.cpp` 提供 C++ 类 initialize→step→terminate 示例，不提供 Dll* 导出包装。`GenerateModelDLLFile.p` 仅记录文件哈希，未解析或执行；buildInfo.mat、SLXC 与 DLL 也未作为文本解析。

唯一已知的相邻 SDK 消费端 `RflySimSDK/ctrl/DllSimCtrlAPI.py` 已定点只读核对，[证据](../../validation/model-reference-provenance-20260907/sdk-wrapper-evidence.json)记录 SHA 和行号。它既把 DllInputColls 声明为 double[20] 又重设为 float[20]；检查 DllInitPosAngStat 却访问 DllInitPosAngState。它不能替代样本 DLL 的头文件或真实 ABI 清单。SLX configSet 的 CustomSource/CustomInclude/CustomLibrary 和 PostCodeGenCommand 为空，也没有提供可继续追踪的导出包装路径。未做 SDK 全盘搜索。

## 下一步

先以已固定哈希向模型供应来源取得 **ZIP 11.0 对应的原 SLX/init、该 DLL 的构建清单和导出包装头/源**；所需清单须明确输入/输出逐元素、单位、初始化、step、reset、terminate、步长和种子。若无历史材料，可在隔离副本中从一份固定版本 SLX/init 重新生成并保存源码和构建证据，形成新的成对参考；这属于后续模型执行步骤，本轮未运行。新生成的 DLL 与同份源码对照只证明实现/接口一致性，独立精度仍需可信的 Simulink 执行或其他独立参考。收到可核对材料后再冻结工况、采样和有工程来源的逐量预算，然后运行 G6 对照，不能倒用实测差异制定预算。
