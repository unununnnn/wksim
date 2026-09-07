# G6 下一条参考证据接缝

2026-09-07。只复用既有文本/元数据证据；未重新展开 ZIP/SLX、读取或执行 DLL、运行 MATLAB/厂商程序或占用主线运行资源。

**下一步是取得并只读核对指定 DLL 的可读导出包装及构建来源清单，不是再次核对相邻模型参数。** [既有来源报告](model-reference-provenance.md)已经完成本轮允许范围内的元数据核对：ZIP 模型 11.0、相邻 SLX 11.8，22 项参数一致，未建立 DLL 构建来源。当前没有找到可引用的开源 DLL 包装头/源位置；不能将消费端 Python 或生成模型头称为它。

## 一个可执行工作单元

输入是模型供应来源交付的文本材料，必须明确绑定 `Exp1_MinModelTemp.dll` SHA256 `30747a8d47ca76ed3a2c751eac212102dde6a3ab4b29ba8eaae5926d416ca91b`：导出包装 `.h/.c/.cpp`、构建清单及其引用的模型/初始化文件哈希。收到后只做文本核对，输出一份“导出调用 → 生成模型调用/根端口”交叉表；缺任一必要字段则保持该行 unresolved，不加载样本。

最小可审阅行必须包含：导出符号与调用约定、返回/参数类型与数组长度、底层模型方法或根端口、每元素单位/坐标/次序、输入在 step 前还是后提交、输出对应的采样时刻。生命周期还需标明初始化、step、reset 和 terminate 的真实实现，以及 reset 是否恢复全部随机状态。它须解释当前消费端 `DllInputColls` 的 double[20]/float[20] 冲突，不能任选一项。

完成条件是能够从该 DLL 哈希追到固定生成源码/SLX/init 版本，并为计划比较的每一个可观测量填写有来源的交叉表。可以先只完成一个可观测量以验证映射链条，但那不覆盖剩余 120 维，也不构成 G6 通过。若供应来源不能提供历史材料，本工作单元记录“来源链无法建立”后停止；隔离重新生成成对参考应另立执行步骤。

## 为什么这是实际缺口

| 已固定证据 | 能证明的边界 |
| --- | --- |
| `MulticopterModel.zip` 内 `e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.h:349–358` | C++ 根输入 16 PWM/15 terrain，根输出 30/30/60；不是 C DLL 导出签名，也没有全部元素的单位合同 |
| 同目录生成 cpp:8493–8495 | 生成模型 ODE4、0.001 秒；不能外推 DLL step 调用次数或输出采样相位 |
| SLX `metadata/coreProperties.xml:7–8` 与生成 cpp:6–8 | SLX revision 11.8 与 ZIP 11.0 的版本关系未闭合 |
| SLX `simulink/configSet0.xml:399,410–413` | PostCodeGenCommand、CustomSource/Include/Library 为空，不能从这里获得包装路径 |
| `RflySimSDK/ctrl/DllSimCtrlAPI.py:1237–1239,1294–1296` | 同一消费端将 DllInputColls 声明成两种元素宽度；其 SHA 为 `0a2a30e91fe55590aec198f1e852a6d45d6aa34c029557de62880d0b81cf5420`，不是指定 DLL ABI 的权威证明 |

上述逻辑行及原始摘录见 [text-evidence.json](../../validation/model-reference-provenance-20260907/text-evidence.json)、[sdk-wrapper-evidence.json](../../validation/model-reference-provenance-20260907/sdk-wrapper-evidence.json)。文件哈希沿用 [resource-hashes.json](../../validation/model-reference-provenance-20260907/resource-hashes.json)，本轮未重新散列厂商文件。[机器摘要](../../validation/remaining-gates-20260907/next-seam.json)保存工作单元状态。

这条接缝只解决参考身份及可观测量映射的前置缺口；同份源码与 DLL 一致仍不等于独立物理精度。G6 后续还需要可信独立参考、固定工况/初态/逐组种子/采样及事前有工程依据的逐量误差预算。本轮没有提出容差；G6/#23、Full 保持 open。#9 环境/RGB 已批准不改变 DLL ABI、数值预算和硬件审批边界。


主代理范围说明：以上是本次“只读既有文本”的有界子任务建议，不是整个项目的阻塞判定，也不新增用户许可门槛。未找到供应方包装不妨碍继续其他已批准切片；后续可独立核对本机合法样本的导出/调用实现或准备有来源的成对生成构建，再形成可审阅的真实 ABI/数值合同。
