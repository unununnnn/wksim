# #23 独立 major 输出记录器：实现与准备检查

2026-09-09。根据[参考采样合同](2026-09-09-reference-sampling-contract.md)、[生成输出相位](plan/2026-09-08-generated-output-phase.md)和[独立复核](plan/2026-09-08-output-phase-review.md)，已实现独立生成侧记录器，并完成构建及输入拒绝检查。**本轮没有构造、initialize 或 step 载具模型，没有采集载具输出或进行数值比较；#23/G6 保持开放。**

实现文件为 `tools/build_major_model_recorder.py`、`tools/major_model_recorder.cpp` 和 `validation/test_major_model_recorder.py`。不改生产 `Simulator/wksim_core/model.py/.cpp`、默认库、ABI、准入 pins、MATLAB、codegen 或只读供应商材料。

## 材料与观测插入

构建器先对整个 ZIP 验证 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`，再只读取与当前 wrapper 相同的五个成员：

- `e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp`
- `e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.h`
- `e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/rtwtypes.h`
- `R2022b/simulink/include/rtw_continuous.h`
- `R2022b/simulink/include/rtw_solver.h`

原始 CPP SHA256 固定为 `a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019`。不解码重写源文件：保留非 UTF-8 注释、所有原始字节和换行；本轮直接读取的固定成员含 9403 个 CRLF、0 个 CRCRLF。逻辑行检查能识别两种换行，但实际插入上下文严格匹配此固定来源，不接受换行转换后的替代文件。

仅增加两处文本：头文件 include 后的 callback 声明，以及原逻辑行 7877 最后一段 Vehicle 输出 memcpy 后、7878 现有 major 分支前的 major guard/callback。同时要求全文哈希、唯一前后上下文、逻辑行位置成立；去掉这两段新增字节必须完全还原原 CPP。四份头文件原字节不变。派生 CPP SHA256 为 `a3eba68e1a4a5cefc772fb502a63eac1e7475548688adebb83cbc9390086a073`。

callback 接受 `const ExtY_Exp1_MinModelTemp_T&`，只按类型复制 Vehicle60、Sensor30、GPS30，并增加记录器自己的调用计数。它不写 Y/X/B/DW/参数/随机种子、不再求值、不调用 step/update、不分配内存、不做 I/O。计数每个外层调用前清零，完整 step 返回后必须恰好为1；minor 回调不得混入。该位置依然是完整 Y 快照，并非可恢复状态检查点，也不声称之前没有初始化或其他状态更新。

## 输入与输出协议

可执行文件接受 `--validate-input INPUT.csv` 或 `--record INPUT.csv`。无参数或未知模式拒绝。所有输入在构造模型之前一次性读取、校验；`--validate-input` 到此返回，绝不构造模型。

CSV 首行严格为 `k,time_s`，接着 `inPWMs0` 至 `inPWMs15`、`TerrainIn15d0` 至 `TerrainIn15d14`，共33列。必须正好501行，k严格为0至500，time_s位于对应1ms格点，每行16个有限归一化PWM值在[0,1]内、15个地形值有限；拒绝空行、缺列、缺样、额外样本、错序、非有限值及大于1MiB的文件。时间检查的1e-12秒仅是固定步长调度的浮点舍入检查，不是载具数值误差预算。输入 fixtures 的数值仅用于解析检查，不是批准的载具工况。

未来获准 `--record` 时，一个进程拥有一个 `MulticopterModelClass`。每行在一次完整外层 step 之前提交全部31项输入；major回调复制完成后继续原有Update/ODE。仅在step正常返回、模型无errorStatus、major计数为1、引擎时间正确且两组输出全有限之后，才发出这一行JSONL。

JSONL使用小型 `schema_version=1` 记录，按顺序保存：

- `major_recorder_start`：ZIP/五成员/原CPP/派生CPP/driver/builder哈希、观测相位、数组顺序、实际解析的完整原始CSV文本、501次调用和两个结束时刻。原始CSV与逐行实际输入共同绑定输入，不接受调用者自报哈希代替真实内容。
- `major_recorder_sample`：整数k、完整调用编号、输入时间、引擎前/后时间、major计数、实际提交的16/15项输入、`major_root_outputs` 与 `post_step_api` 两组具名 Vehicle60/Sensor30/GPS30，以及 `step_status=complete`。不按结构体内存顺序序列化；不改写任何数组内时间槽，也不平移post-step输出。
- `major_recorder_end`：完成状态、attempted/returned调用数、已写样本数、比较终点0.500s及实际引擎结束时间。完整501份major输出要求501次完整调用，引擎结束应为0.501s。

异常路径向stderr写失败原因和三个调用/样本计数并以非零状态退出；异常退出、进程中止、缺终止记录、缺样或非法JSON均不能被当作成功运行。未来运行监督器还须将case/epoch、冻结预算、输入文件与哈希、精确命令、构建清单/可执行文件哈希、stdout/stderr和实际退出码归档，核验原始CSV与逐行输入一致，并严格检查501个样本、终止记录和各通道时间。该监督/数值验收步骤尚未执行，此工具自身不宣布物理等价。

## 本轮完成的准备检查

在没有活动飞控/模型的保留窗口中，Ubuntu-22.04构建目录为 `/root/wksim-major-recorder-j_3guvtn/`。仅该全新私有目录保存供应商源副本、原始CPP、派生CPP及可执行文件；仓库内证据不包含生成供应商源码。

实际编译器为 `g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0`，选项 `-std=c++17 -O2 -fno-fast-math -Wl,--no-undefined`。构建退出0、stderr为空，可执行文件SHA256为 `c685817a974471113793fde3c78eeed26f7c7b56eef1194f9df1fd2ecf7e8d49`。完整命令与源/产物哈希见私有目录 `build.json` 及 `validation/major-recorder-l1kb845j/build.json`。

`validation/major-recorder-l1kb845j/result.json` 为pass：五成员哈希、原始源还原、派生CPP匹配、拒绝未固定ZIP/CPP和不唯一/变化的插入上下文全部通过。14次进程调用包含1次合法CSV的纯预检，以及缺行、额外行、错序k、错时刻、PWM上下越界/NaN、地形Inf、非数字、空字段、缺列、非法参数、缺文件的拒绝检查。所有拒绝的attempted/returned/emitted计数为0；合法CSV仅使用 `--validate-input`。执行命令、输入SHA256、各进程输出、退出码和执行前脚本快照均已保留，源与可执行文件前后未变。

可重复的构建/准备检查命令（不执行载具模型）：

```text
python3 tools/build_major_model_recorder.py
python3 validation/test_major_model_recorder.py --manifest /root/wksim-major-recorder-<new>/build.json
```

没有进行有效输入的 `--record` smoke。后续载具major/post记录及与SLX11.8的跨版本比较仍等待具体工况、字段/单位、冻结逐量预算和独立运行窗口；已通过的输入机制小模型检查与此构建结果不能替代它们。
