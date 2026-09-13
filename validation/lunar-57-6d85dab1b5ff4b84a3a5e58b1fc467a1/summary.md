# #57 `9-evidence` ABI 与环境反馈证据摘要

## 票据与边界

- GitHub：#57 `[Astra] 核对模型DLL ABI与反馈合同的具体证据缺口`
- 稳定键：`9-evidence`
- 绑定时状态：`OPEN`，标签含 `ready-for-agent`；本次只交付证据合同，不关闭 #9 决策。
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`117cd58 docs: diagnose final mixed PV rate failures for issue 82`
- 未加载、执行、修改或重新分发厂商 DLL；未修改厂商安装。

## 实际只读命令

```text
rg -n --context 6 "DllInputColls|DllInitPosAngStat|DllInitPosAngState|DllOutCopterData|DlloutVehileInfo60d|DllGetStep0|DllReInitModel|Dllstep|DllInCtrlExt|DllInFromUE" E:\rflysimtools\RflySimAPIs\RflySimSDK\ctrl\DllSimCtrlAPI.py
Get-Content E:\rflysimtools\CopterSim\external\XML\Hexa.xml
Get-Content E:\rflysimtools\CopterSim\external\XML\F450.xml
Get-Content E:\rflysimtools\RflySimAPIs\4.RflySimModel\0.ApiExps\12.DllModelImport\9.ModelLoadCopterSim30100Python\DllSimCtrlAPITest.py
Get-FileHash -Algorithm SHA256 <all listed source files>
```

## 事实结论

- `DllInputColls` 在同一 SDK 包装中发生 `double[20]`→`float[20]` 的声明覆盖；`DllInitPosAngStat` 的存在性检查与实际访问的 `DllInitPosAngState` 不一致。
- `DllOutCopterData`、`DlloutVehileInfo60d`、`Dllstep`、`DllReInitModel`、`DllDestroyModel` 的 Python-side 形状和返回值不足以证明导出端的完整 C ABI、错误码和所有权。
- `Hexa.xml` 与 `F450.xml` 证明可读的 Model/Hover/Frame 元数据存在，但质量、机架和参数与自主候选不同，不能推出 XML/SLX/ZIP/DLL 同源。
- supplied sample 只证明 legacy Python 调用意图；不证明导出符号、许可、同一模型版本或公开分发权。
- `VisionSensorReq` 的 `16H28f` 与字段可作为 SDK 线索，但缺少 wksim 所需 epoch、权威 step、源/接收时间和新鲜度语义。

## 交付

- 合同文档：[9-abi-environment-evidence.md](C:/Users/PC/Documents/odid编译/wksim/docs/plan/9-abi-environment-evidence.md)
- 文档 SHA256：`606cb49eb7f226946793df8a6d0e536c867e00d5e9a431c47595a39cb1e91331`
- 证据事实：[abi-facts.json](C:/Users/PC/Documents/odid编译/wksim/validation/lunar-57-6d85dab1b5ff4b84a3a5e58b1fc467a1/abi-facts.json)
- 只读命令：[read-only-commands.txt](C:/Users/PC/Documents/odid编译/wksim/validation/lunar-57-6d85dab1b5ff4b84a3a5e58b1fc467a1/read-only-commands.txt)
- 未知 ABI/环境策略均明确保持阻塞；静态平面/盒体和一步有效期只是待 #9 决策的候选，不是已批准实现。

## 完成判定与失败边界

本票已交付证据支撑的 ABI 冲突、字段/生命周期缺口和候选环境反馈合同；没有把符号名、ctypes 设置、XML 或静态夹具升级为兼容/运行通过。后续 #27/#28/#29 只能在 ABI/环境决策、可读头或包装源、合法使用依据和隔离生命周期样本齐全后进入实现/运行。
