# #24 四旋翼质量配置与真实静态响应

2026-09-09 JST。实现完成，等待主代理复核；没有修改工单、提交、生产模型或默认准入 pin。#23 的关闭仍仅表示严格数值对照交付完成：R1 numerical_failed，G6/物理精度未获通过。

用户现在可以用 [命令工具](../tools/quad_model_parameters.py) 创建具名 Quad X 配置、修改质量、保存、导出、导入，并从该配置构建和运行独立本地模型。示例为 [quad-parameters-example.json](quad-parameters-example.json)。[实现](../Simulator/wksim_core/model_parameters.py) 仅允许质量在 **0.5–5.0 kg** 内编辑，默认 **1.515 kg**；此范围是有限输入合同，不能理解为该构型经过验证的完整飞行包线。质量变化不自动改变惯量或旋翼，适用于本票的受控单参数比较。

## 保存、构建与运行

以下在本仓库的 Ubuntu-22.04 WSL 根目录执行。每个输出采用新文件，已有配置不会被覆盖；每次运行使用新进程。Python 标准库足够，无新增包依赖。

```bash
out=$(mktemp -d /tmp/wksim-quad-user-XXXXXX)
python3 tools/quad_model_parameters.py new "$out/default.json"
python3 tools/quad_model_parameters.py edit "$out/default.json" "$out/payload.json" --name payload --mass-kg 1.818
python3 tools/quad_model_parameters.py export "$out/payload.json" "$out/export.json"
python3 tools/quad_model_parameters.py import "$out/export.json" "$out/imported.json"
python3 tools/quad_model_parameters.py inspect "$out/imported.json"
library=$(python3 tools/quad_model_parameters.py build "$out/imported.json")
python3 tools/quad_model_parameters.py run "$out/imported.json" "$library" "$out/response.jsonl" --commands .8 .8 .8 .8 --ticks 500
```

`build --archive <path>` 可显式提供本机 ZIP；必须匹配原默认源 SHA256。Windows 上可创建/保存/导入 JSON；构建及 native 运行要求 Linux。JSON 不接受漏字段、未知字段、错误单位、布尔/字符串/非有限质量、超范围质量、重复键、固定组件改写或未随参数更新的身份。应使用 `edit` 生成新身份。

每次构建在独立 `/tmp/wksim-model-*` 保留原始生成 cpp、参数化 cpp、原始头文件、包装副本、配置、编译命令/版本、日志和 `build.json`。运行前核对配置、文件哈希、原始 source pin、参数化内容和运行库导出的模型身份/实际质量；第一步前记录 `applied_mass_kg_before_step`。输出逐 tick 保存全部 120 个 native double；失败或中断证据不会覆盖原记录。运行拒绝非零的 4–15 号未使用执行器通道，同进程第二个配置模型生命周期也被拒绝。

## 来源、默认参数和映射

沿用 [22 项参数对应证据](../validation/model-reference-provenance-20260907/parameter-correspondence.json) 与 [来源报告](plan/model-reference-provenance.md)，并实际读取本机固定 ZIP 的生成 cpp/h。所有原始字节哈希先校验；仅在新目录内，把唯一的 `ModelParam_uavMass` initializer 从 1.515 替换为配置值，保留其余字节。生成头第 543 行声明质量，第 1632–1646 行显示参数是 public static；直接参数化源避免写回生产模型或运行中调参。匹配必须唯一，不对随意浮点文本全局替换。

配置记录质量加 21 个固定具名参数/初态；数值完整保留原 22 项对应。单位按源码方程解释：质量 kg、长度 m、惯量 kg·m²、motorCr/Wb 为角速度关系、motorT 为秒、旋翼系数分别 N/(rad/s)² 与 N·m/(rad/s)²。`uavCd` 的源公式是力对速度平方的系数，不能误标为无量纲。`ModelInit_RPM` 保持源原名及固定零值，不开放非零初始转速单位换算。

四电机输入 **0=前右、1=后左、2=前左、3=后右**，FRD 平面角度 **45°、225°、315°、135°**，源旋转符号 **−1、−1、+1、+1**。生成 cpp 3874–3899 的实值表及 4755–4834 的选择/执行式支持 `uavType=3 → d[2]=4`；各 `inPWMs[0..3]` 在 4641–4679 直接对应 MotorNonlinearDynamic1–4。`ModelParam_uavMotNumbs` 没有同名生成参数，配置明确写出这个边界。电机、旋翼、机架/惯量和映射都是只读组件描述。

固定来源：ZIP SHA256 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`；生成 cpp `a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019`；生成头 `2d89ad1b492c5e70e80682a9f53896e0538260946a0180a2ca44e500ba1589bd`。模型版本 **11.0 / R2022b**；本轮编译器 **g++ Ubuntu 11.4.0-1ubuntu1~22.04.3**，C++17、O2、`-fno-fast-math`、1 ms ODE4。完整五个成员 pin、基包装 pin、构建 recipe 都进入配置身份；具体编译器/命令、工具源码 SHA 和产物 SHA 留在每份 build manifest。

## 预声明实验及结果

[最终协议](../validation/quad-parameters-native-20260909-b/protocol.json) 在该轮任何构建/响应前写入，SHA256 `10b229dcbd7606a9f3f1e78b8f23bd701a5aebb2c2cd21ae6bcebd0ce136319d`。固定质量 **1.515 与 1.818 kg**，原始默认初态，四电机各 **0.8**、其余 12 通道零；推进 **500×1 ms**。观测是 `-output[5]` 向上速度、`-output[8]` 高度和 `output[16:20]` 电机转速。源码依据是 cpp 4833–4834 的 `T=Ct*omega²` 和 4955–4963 的合力除质量；源 7823–7828 将 NED 速度/位置映射到这些输出。预期轻载上升速度和高度均大于重载，且均正；电机响应相同。没有用飞控跟踪阈值充当物理误差预算，也没有观察后调参或拟合阈值。

| 500 ms 观测 | 1.515 kg | 1.818 kg | 导出/导入重建 1.818 kg |
| --- | ---: | ---: | ---: |
| 向上速度 m/s | 5.175467166591079 | 3.6064825176689865 | 3.6064825176689865 |
| 高度 m | 1.1962407914482234 | 0.8221303046977115 | 0.8221303046977115 |
| 每个电机 RPM | 6651.18056430211 | 6651.18056430211 | 6651.18056430211 |

三次运行是独立 native 进程，真实生成 C++ 积分模型直接产生数据，没有启动 SITL、ROS、UE 或真实飞控。电机转速的 **500 个样本逐个相等**；导入重建的 **500×120 个输出逐个相等**，质量读回、完整配置、模型身份与库 SHA 也相等。本机两个重建产物一致不扩展成跨编译器逐位再现保证。

基线模型身份 `sha256:72f7c93a443fde765dfc7bdbac18c458d35af9d927e65bb50d67c885ccef2b5a`，重载及导入身份 `sha256:dd71d97af9b93ca75c9bc82e681637bd416ef5d775edde24060729085173086b`。基线库 SHA256 `9717918949cf9f1fcb6d5087845999964923c8c75a6bce05dc5daf3cd1d44029`；重载及导入库 `d0ac9a963c6f7b4694f29715e843fe73af9d9a7cfa2a81f216d025b5a05a2b3d`。

最终 [summary.json](../validation/quad-parameters-native-20260909-b/summary.json) 的 **10 项检查通过**；[测试文件](../validation/test_quad_model_parameters.py) 的 **6 个 unittest 方法通过**（含多组子用例）。真实负例保留配置/库交叉错配、库字节篡改、错误源 ZIP、未使用通道和第二生命周期拒绝日志；离线覆盖非法质量、缺字段、单位/组件/来源/身份篡改、重复 JSON 键、原源哈希和唯一 initializer 映射。拒绝发生在运行前或第一步前。复现命令：

```bash
python3 validation/test_quad_model_parameters.py
python3 validation/test_quad_model_parameters.py --native validation/quad-parameters-native-fresh-name
```

首次版本实验保留在 `validation/quad-parameters-native-20260909-a/`，其方向检查也通过；补齐运行保护后按同一参数/观测协议重跑到 `-b/`，没有覆盖前轮。`-b` 内保存配置、逐步 JSONL、协议、summary、三个 build manifest 和故意失败日志；原始厂商源/构建目录仅本机保存，不分发。探索阶段一次 Windows 默认 UTF-8 解码生成源失败，改以原字节 hash 和 Latin-1 无损文本视图读取；没有因此改写源文件。

## 验收边界与后续行

本票 AC1–AC3 对本次有限 Quad X 质量工具已有实现和实际静态证据；AC4 保留下面的后续行；AC5 的主代理复核尚待完成。本报告不能自行关闭 #24。

| 后续能力 | 本轮状态 |
| --- | --- |
| Full 可组合组件库与组件型号选择 | 未实现；当前为固定来源的只读组件描述 |
| 性能计算、设计优化、完整参数编辑 | 未实现；仅质量可写，不改变惯量/动力参数 |
| 其他构型 | 未开放；固定 Quad X |
| 正式调度入口/双飞控参数运行与飞行验收 | 未接入、未验证；本票采用明确允许的静态观测路径 |
| 独立物理精度 / G6 / R1 数值对照 | 未通过；本结果只证明参数确实作用及预声明方向关系 |

生产 `model.py`、`model.cpp` 及默认源 pin 未改。这里只按已知文件直接读取并新增模块/工具，未进行依赖新结构的图查询；没有因写报告触发全库索引。下一结构查询仍遵循 Codebase Memory 的检测/刷新规则。
