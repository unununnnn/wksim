# #70 模型代码生成路线与本机就绪度分析（基于 Commit 514743f）

**基线 Commit**：`514743f`  
**核验者**：Antigravity (`antigravity`，独立只读核查)  
**分析依据**：
1. `docs/plan/26-generation-contract.md`（特别是顶部最新的 G6 材料补充）；
2. `docs/g6-material-index.md`（厂家开发与标定材料索引）；
3. `docs/2026-09-09-model-reference-readiness-report.md`（e0 模型的 MATLAB normal 模式预检实测记录）。

---

## 核心原则与合规边界界定

在推进模型代码生成前，必须明确以下两个边界，避免因概念混淆而产生不必要的自我阻断：

1. **本地开发使用权与公开再分发权严格解耦**：
   - 厂家文档明确提供的二次开发模板、生成指引与教学材料，是本项目在**本机本地环境**进行模型二次开发、C/C++ 代码生成、编译与 SITL 仿真的直接技术依据与合法用途来源；
   - 缺少面向第三方的全文件或二进制开源“再分发权”，仅意味着厂商的原始 SLX/init、生成 C/C++ 源码及 MathWorks 头文件**不得复制进公开 Git 仓库或对外打包分发**，必须严格保留在本机受控隔离工作区；
   - **绝不能把“无再分发权”等同于“无本地使用权”，更不能以“缺少绑定每个文件哈希的单项授权合同”为由禁止本地工程实验。**

2. **MATLAB 构建期与日常运行期严格解耦**：
   - **构建期（Build-time）**：从 SLX 模型到 C++ 源码的代码生成过程**必须依赖真实商业工具链**（本机安装的 `MATLAB R2022b`、`Simulink`、`Embedded Coder (ert.tlc)` 及 `Real-Time_Workshop` 许可）。绝不能宣称“无 MATLAB 依赖的脚本直接从 SLX 生成 C++”；
   - **运行期（Runtime）**：由 Embedded Coder 生成的独立 C++ 源码在 WSL/Linux 下编译包装为共享库（如 `libwksim_e0.so`）后，在仿真环境中的日常运行是**完全脱离 MATLAB** 的（无运行时 license 依赖、无 MATLAB 进程常驻）；
   - 构建期与运行期职责、环境完全分离，不可混同。

3. **只读核查不变量**：
   - 本次分析仅进行静态文献与已有实测环境配置核验；
   - 不调用 `matlab.exe`，不运行仿真或实际代码生成，不修改任何现有生产文件与脚本。

---

## 一、已具备的本地开发与生成用途依据

根据 `docs/g6-material-index.md` 实际索引并核对哈希的厂商材料，本机进行 e0 模型二次开发与代码生成具有直接、充分的官方文档支撑：

1. **厂商整体二次开发工作流说明**：
   - **材料**：`E:/rflysimtools/RflySimAPIs/4.RflySimModel/Intro.pdf`（SHA256 `0af3660d6188535943e848cdbc2dcd06a40702cc4c164a4ed4f4a30931cffb68`）；
   - **位置**：PDF 第 3 页第 2.1 节、第 5 页；
   - **内容**：厂家明确声明平台提供载具模型二次开发模板，支持在 Simulink 中进行动力学建模与修改，支持生成 C/C++ 代码并可直接移植到嵌入式或外部仿真系统，同时列出了包含四旋翼在内的各类模板。

2. **e0 最小模型模板的开发指导**：
   - **材料**：`E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/Readme.pdf`（SHA256 `3ddc08409d8fd6f7f41b5185f73162d9eeae1e504acb31ff981c6d0c75bec942`）；
   - **位置**：PDF 第 1–3 页、第 5–10 页；
   - **内容**：直接指向当前选用的 `Exp1_MinModelTemp.slx` 与 `Exp1_MinModelTemp_init.m`，明确说明该模型为可供用户修改二次开发的最小模板，详细阐述了生成代码、封装 DLL 及参与 SITL 联仿的标准流程。

3. **官方 C++ 独立代码生成教程**：
   - **材料**：`E:/rflysimtools/RflySimAPIs/4.RflySimModel/0.ApiExps/2.UserDefinedC++/2.GenC++/Readme.pdf`（SHA256 `a26cba0d41706f998f97a2bd41d20111856896d52e57b99dd492f20b2a9b0caa`）；
   - **位置**：PDF 第 6 页、第 9 页；
   - **内容**：指导使用 `ert.tlc`（Embedded Coder）将 Simulink 模型生成为独立 C++ 源码，支持生成 `ert_main.cpp`、模型 `.cpp` 和 `.h` 头文件，目标跨 Windows、Linux 及嵌入式系统。这为后续绕过不透明的厂商黑盒脚本（如 `.p` 文件）、实现可独立审查与构建的源码生成提供了官方标准路径。

---

## 二、真实代码生成所需的本地工具、版本与配置清单

根据 `docs/2026-09-09-model-reference-readiness-report.md`（最终验收通过的 `attempt-07`，readiness SHA256 `d1fb57914f8382673a78548764c3837a259411168653c7d99d91d8ffc19f6f96`），本机已完全具备执行真实代码生成所需的工具链环境：

1. **MATLAB 运行时与路径**：
   - **版本**：`MATLAB 9.13.0.2049777 (R2022b)`；
   - **执行入口**：`D:/matlab/install date/bin/matlab.exe`；
   - **就绪状态**：已具备成熟的无头调用驱动能力（`-batch` 模式），可稳定完成工作目录隔离、环境覆盖及参数提取，进程退出码与机器 readiness 判定均已在 attempt-07 中验证退出 0。

2. **核心工具箱许可测试 (License Features)**：
   - 进程内 `license('test', feature)` 实测结果全部为 `1`（可用）：
     - `SIMULINK`：`1`
     - `Aerospace_Blockset`：`1`
     - `Aerospace_Toolbox`：`1`
     - `Real-Time_Workshop`（Simulink Coder / Embedded Coder 核心代码生成特性）：`1`。

3. **被生成模型源与配置基线**：
   - **模型文件**：`E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/Exp1_MinModelTemp.slx`（模型版本 11.8，SHA256 `c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392`）；
   - **配套初始化**：`Exp1_MinModelTemp_init.m`（SHA256 `9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991`）；
   - **求解器配置**：ODE4、固定步长 `0.001 s`（1 ms），已通过 22 项参数绑定与 7 组随机数种子的完整 normal load/update 预检。

4. **代码生成目标规格**：
   - **System Target File**：`ert.tlc`（Embedded Coder）；
   - **Target Language**：`C++`；
   - **接口形态**：16 维归一化输入（Quad X 占用 0..3，范围 [0, 1]），120 维双精度状态/传感器输出，1 ms 单步步进接口（`step`），生命周期管理（`create`/`destroy`）。

---

## 三、最小实施缺口（从当前状态到真实代码生成产物）

当前推进 #70，虽然官方材料提供了明确的本地开发用途依据，但实际 checkout 与工具链输出（从 SLX 到无头 C++ 生成）仍待真实工程验证；同时再分发权并不在此本地开发授权范围内。当前工程实施层面的直接缺口如下：

1. **缺口 1：自动化代码生成驱动脚本（持续推进已授权）**
   - *现状*：现有 `tools/probe_model_reference_readiness.py/.m` 仅执行 `load/update`，不调用 `slbuild`；而 `tools/quad_model_parameters.py` 内部硬编码了针对旧 ZIP (11.0) 的参数修改与编译，无法处理新 SLX 11.8 的代码生成。
   - *最小需求*：持续推进已获授权，无需用户再次审批写入权限。仅需编写独立的无头批处理生成脚本（例如 `tools/generate_model_e0.py` 配合 `.m`），通过 `matlab.exe -batch "..."` 调用真实 MATLAB R2022b 的 `slbuild('Exp1_MinModelTemp')` 与 Embedded Coder `ert.tlc`，自动将生成的 C++ 源码定向输出至隔离构建工作区。

2. **缺口 2：生成 C++ 源码到项目加载器的包装接缝**
   - *现状*：现有的 `Simulator/wksim_core/model.cpp` 包装层针对的是历史 11.0 ZIP 的函数导出布局。
   - *最小需求*：针对 11.8 生成的 C++ 类接口，提供一个符合 wksim 规范的动态库包装器源码，封装导出标准 C 接口（`wk_model_create`、`wk_model_step`、`wk_model_destroy`），并在 Linux/WSL 环境下编译为 `libwksim_e0.so`。

3. **缺口 3：本地隔离构建区与证据归档规范**
   - *现状*：尚未固定新生成源码的本地私有存放路径规则。
   - *最小需求*：确立受控本地输出路径（例如项目根下的 `work/codegen-e0/` 或 WSL 的 `/root/wksim-codegen-e0/`），严格确保厂商代码、中间头文件与编译产物不进入 Git 跟踪范围；在 `validation/` 目录下仅归档构建清单 JSON（包含生成命令、工具版本、输入/输出 SHA256 矩阵、动态依赖检查日志及编译退出码）。

---

## 四、推进路线与后续行动建议

```
[步骤 1: 工具准备]
  └── 编写 tools/generate_model_e0.py（基于 attempt-07 的无头调用模板，驱动真实商业 MATLAB R2022b 执行 slbuild 目标与 ert.tlc 配置）。

[步骤 2: 代码生成执行（真实 MATLAB 构建期）]
  └── 在本地隔离目录（work/ 或 /root/）无头运行该脚本，调用真实 MATLAB/Simulink/Embedded Coder 完成 Exp1_MinModelTemp.slx (11.8) 到 C++ 源码的实际生成。

[步骤 3: 包装与编译构建（脱离 MATLAB）]
  └── 在 WSL/Linux 下编译生成 libwksim_e0.so，核验其动态链接库依赖（确保日常运行期无 MATLAB/Gazebo 依赖）。

[步骤 4: 票据推进]
  └── 将生成与构建清单归档至 validation/，关闭 #70；随后由 Luna 领取并执行 #71（构建验证）与 #72（无 MATLAB 冷重建日常运行）。
```
