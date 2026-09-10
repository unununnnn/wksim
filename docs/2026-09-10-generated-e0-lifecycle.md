# e0 11.8 真实生成、Linux 构建与冷重置

本轮已实际完成 SLX 11.8 → MATLAB/Embedded Coder C++ → Linux 共享库 → 核心 Model 加载、运行、重置与终止。没有把旧 11.0 ZIP 的编译当作本次生成，也没有改变旧模型准入 pin。

## 实际证据

| 阶段 | 结果与记录 |
| --- | --- |
| 默认准备 | `short-cycle-prepare-01`，真实 SDK 三文件复制/散列匹配；不启动 MATLAB |
| 真实生成 | `short-cycle-codegen-01`，MATLAB R2022b 退出 0；SIMULINK、Real-Time_Workshop、RTW_Embedded_Coder、Aerospace_Blockset、Aerospace_Toolbox 的 test 与 checkout 全部为 1 |
| 生成配置 | 原模型 ODE4/0.001s 读回；只在内存切 normal、ert.tlc、C++、GenCodeOnly；9 个阶段全部成功，关闭模型不保存 |
| 输入与产物 | 原厂与私有输入均未改变；主会话独立重算 6 个输入副本及 4 个生成文件 SHA，一致；新头文件版本 11.8，16 输入/60+30+30 输出 |
| Linux 首构建 | GNU g++ 11.4，独立 `/root/wksim-codegen-e0-build-short-cycle-01`；共享库 87,312 字节，SHA256 `7da6853201b89238c273f2e1360ad21fe479e267d0ed08cf3500f98bf535505e` |
| 独立冷重建 | 主会话从核验后的 6 个源码/头文件重新建新目录，没有复制库；新编译库 SHA 与第一次一致 |
| 核心生命周期 | 两个独立 Python 进程各创建/步进/销毁两次；每次 1000 步、1ms、120 输出；共 480,000 个输出值和四份原始 JSONL 字节完全一致 |
| 时钟与依赖 | 使用现有 `Model` 的 1e-8s 时钟门槛；所有输出有限。保存 ldd 与实际加载 maps，未发现 MATLAB/MCR/Simulink/Gazebo 运行库；MATLAB 生成进程已退出 |

生成记录位于 `validation/codegen-e0/short-cycle-codegen-01/`；首次构建在 `validation/codegen-e0-build-short-cycle-01/`；主会话独立冷重建和原始生命周期审计在 `validation/codegen-e0-lifecycle-01/`。

生命周期输入在运行前写入 `contract.json`：前 100 步全零；101–600 步前四路 0.5；601–1000 步前四路 0.45；其余十二路始终零。只比较本次同源模型的重置/冷重建，不以此声称与 MATLAB normal 仿真或旧 11.0 数值等价。G6/R1 原结果保持不变。

## 可执行入口

```powershell
python -B tools/generate_model_e0.py --run --run-id short-cycle-codegen-01 --timeout 300
python -B tools/build_generated_e0.py --generation-dir validation/codegen-e0/short-cycle-codegen-01 --build-id short-cycle-01 --run-test
wsl -d Ubuntu-22.04 -u root -- python3 -B tools/validate_generated_e0_lifecycle.py --manifest validation/codegen-e0-build-short-cycle-01/build-manifest.json --output validation/codegen-e0-lifecycle-01
```

这些是已执行身份；重跑必须使用新 ID/新目录。编译复用项目现有 `Simulator/wksim_core/model.cpp` C ABI 包装器，未新增不必要的另一套 ABI。生成后的核心运行不启动 MATLAB；生成阶段仍需要真实 MATLAB/Simulink/Embedded Coder。

本机开发用途依据见既有 G6 材料索引及 e0 开发说明，实际工具可用性以本次 checkout 和生成结果为准；这不授予公开再分发厂商模型或 MathWorks 文件的权限。SLX、init、生成 C++、MathWorks 头与 SO 留在 `work/` 或 `/root/wksim-*` 私有目录，入库只含项目自有驱动、原始运行数据、日志与哈希。

生成驱动的 18 项编排检查通过。构建工具修正版补齐必需凭证/完整阶段检查、路径与动态依赖负例后，主会话又发现直接 CLI 调用缺项目模块搜索路径（`ModuleNotFoundError: tools`，尚未创建构建目录）。修正入口并加入隔离工作目录下的真实 CLI 测试后，`short-cycle-02` 再次实际构建/探针通过，库 SHA 保持相同。主会话另使用独立脚本核对真实输入/库/生命周期。#70–#72 按原依赖顺序复核收口；父 #26 另保留 #9 等原依赖。
