# e0 参考模型 normal load/update 预检

2026-09-09。按[下一执行包](2026-09-09-numerical-frontier-next.md)隔离执行；不运行载具 `sim`、代码生成、DLL、厂商启动器、注册或激活操作，不关闭 #23。

**结论：参考预检 ready，仅表示固定 e0 SLX 11.8 在本机 MATLAB R2022b 的 normal 模式 load/update 成功。没有产生数值对照轨迹，也没有给出动力学误差验收或预算。** 原生成 ZIP 11.0 与 SLX 11.8 的版本边界保持不变。

## 身份、隔离与回调

只读来源为 `E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp`。ZIP、SLX、init 的 SHA256 分别是 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`、`c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392`、`9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991`，本次重算符合既有清单。执行前复制进项目独占的验证目录，未复制或执行相邻 DLL、SLXC、P 文件或批处理。

[Python 入口](../tools/probe_model_reference_readiness.py)先解析 SLX XML、init、库引用和 mask；[MATLAB 探针](../tools/probe_model_reference_readiness.m)随后逐阶段记录加载、原 init、参数、update、关闭。所有尝试保留在 [证据目录](../validation/model-reference-readiness-20260909/)。最终执行目录为 `attempt-07/staged-model`，TEMP/TMP、MATLAB_PREFDIR、Simulink cache/codegen 路径均指定在该尝试目录内。代码生成目录设置仅为限制潜在输出位置，未调用生成器。模型保存的 accelerator 模式只在内存中改成 normal，结束 `bdclose` 不保存。

XML 审核发现：PreLoadFcn 只进入模型所在目录；InitFcn 进入同目录并运行同名 `_init.m`，但其 `try/end` 会吞掉异常。因此探针在 update 前另外直接运行未改动的 init，并独立记录结果；文件内容仅为参数/初态赋值。三处 `!start ../html/...` 是帮助按钮 Callback，不调用它们。五处 Stateflow ErrorFcn 为 `Stateflow.Translate.translate`。没有调用厂商帮助按钮、启动或注册逻辑。

23 个直接库引用涉及 11 个库根；保守递归读取库 XML 得到 33 个已安装库文件，全部定位并冻结 SHA256。库的加载回调为加载其他内部库及设置内存中的库位置，mask 初始化为参数与内部块配置；这份保守清单还含未执行的库分支，不能把 33 个文件都称作实际运行依赖。实际块引用路径及其哈希另存于 `effective-dependency-hashes.json`。

## 当前进程的环境与有效配置

MATLAB 为 `9.13.0.2049777 (R2022b)`，可执行路径 `D:/matlab/install date/bin/matlab.exe`。完整 argv、工作目录及环境覆盖在最终尝试的 `command.json`；实际工具版本、初始/重置后搜索路径和产品清单在 `readiness.json`。

`license('test', feature)` 对 `SIMULINK`、`Aerospace_Blockset`、`Aerospace_Toolbox`、`Real-Time_Workshop` 本次均返回 1。这是当前进程的许可可用性测试，**不证明 Coder checkout 或代码生成成功**；它与历史进程中缺 Coder 的盘点不同，本次未改变许可或执行激活。Aerospace 是否足以完成这份模型的预检，由实际 normal update 成功提供进一步证据。

有效求解器为 ODE4、固定步长 `0.001`、normal 模式。22 个历史共同参数/初态的实际块绑定与初始化值逐项记录在 `effective-22-parameters.json`；`ModelParam_uavMotNumbs=4` 另保留于工作区，未混入历史共同 22 项。根 SensorOutput 的 `Param_GlobalNoiseGainSwitch=0`。七组 UniformRandomNumber 的实际 seed、min/max、采样时间在 `readiness.json`，全部 1 ms；差压 SID `12217:1313` 的省略默认值实际解析为 **Minimum=-1、Maximum=1、Seed=25634**。

IMU `i_rand=off`；`i_pow` 为 `ModelParam_noisePowerIMU*[0.0000005 0.0000005 0.0000005 0.000000002 0.000000002 0.000000002]`，mask 的 Enabled=off。探针主动 `slResolve` 此表达式得到 `Simulink:Data:SlResolveNotResolved`，工作区没有该变量，未补值。继承到加速度计/陀螺仪的 `a_pow`/`g_pow` 同样关闭。**实际 normal update 成功，所以这个关闭支路的未解析表达式没有阻断本次预检**；这不保证打开随机支路也可用。通用 `slResolve` 对 `off`、枚举字符串等也会记录解析失败，它们不是 update 的运行失败，原字符串、Evaluate/Enabled 状态及错误均保留。

## 保留的失败与检查界限

| 尝试 | 结果与用途 |
|---|---|
| 根目录 attempt 1 | 探针把 `Real-Time_Workshop` 用作 struct 字段失败，尚未 load 模型；保留完整控制台和退出码 1 |
| attempt-02 | `restoredefaultpath` 脚本与 MATLAB 嵌套函数静态工作区冲突，尚未 load 模型；改为 base workspace 执行，保留退出码 1 |
| attempt-03 | load/update 成功，但保存模式为 accelerator，且目录名 `private` 触发 MATLAB 保留目录警告；不是最终 normal 就绪证据 |
| attempt-04 | staged-model 目录、显式 normal，全部阶段成功、退出码 0；参数采集只覆盖 mask，普通块对话框需补齐 |
| attempt-05 | normal update 成功，新增采集器遇到无 DialogParameters 的块返回 double 而失败；机器结论 blocked，保留两处采集错误 |
| attempt-06 | 修正空对话框采集；完整 normal load/update 与参数预检 |
| attempt-07 | 主代理补齐CLI失败判定与暂存副本执行后哈希；最终完整预检通过 |

启动时现有 MATLAB pathdef 报告历史 `C:/PX4PSP/...` 和旧临时目录不存在；探针保存初始路径并恢复安装默认路径后再访问模型。系统继承的 `C.UTF-8` locale 导致 restoredefaultpath 内 Perl locale 警告，完整原始字节保留在控制台日志；不把警告隐藏成成功输出。最终依赖实际解析到 MATLAB 安装 toolbox。没有修改全局 pathdef 或安装文件。

主代理复核补充：原入口只返回 MATLAB 进程退出码，attempt-05 的参数采集失败仍会让命令返回 0。入口现要求机器 readiness=ready、原文件/暂存副本和全部库哈希不变，才返回 0；进程退出与预检结论分别记录。修改后的最终 **attempt-07** 再次 normal load/update 成功、MATLAB/CLI 均退出 0，22 参数与七随机源复核通过。上文 attempt-06 保留为修正前证据；根 readiness-summary.json 已指向 attempt-07。最终 readiness.json SHA256 为 `d1fb57914f8382673a78548764c3837a259411168653c7d99d91d8ffc19f6f96`。

检查包括 22 项实际参数绑定、七组随机源、normal/ODE4/1 ms、各阶段状态、进程退出码以及原文件/暂存副本/库执行前后哈希。探针早期错误及原始尝试都没有覆盖；最终验证脚本为证据目录下 `verify_effective_07.py`。后续工作仍需参考端输入/日志事件语义、major 记录器合同及有独立来源的逐量预算。这里的 ready 不能作为 #23 数值验收、历史同版本绑定或完整模型物理精度证明。
