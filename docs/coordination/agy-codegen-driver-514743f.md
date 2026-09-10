# #70 模型代码生成隔离驱动交付与可读入口说明（基于 Commit 514743f）

**交付日期**：2026-09-10  
**负责人**：Antigravity (`antigravity`，独立实现与编排单测)  
**当前状态**：驱动代码与离线编排测试已交付并通过（18 项单测全部 PASS），**未执行真实 MATLAB，未运行 SITL/UE 仿真**。

---

## 一、 交付文件清单

根据主会话初审意见与切片要求，在以下 4 个受控文件内完成实现与修复：

1. **[tools/generate_model_e0.py](file:///C:/Users/PC/Documents/odid编译/wksim/tools/generate_model_e0.py)**：
   - 独立 Python 调度驱动。默认仅执行 dry prepare/manifest 准备；仅在显式传入 `--run` 时才调用本地商业 MATLAB；
   - 引入 `ProcessTracker`（基于启动时绑定的 Popen 对象与 `create_time` 定向追踪进程树，防 PID 复用，无 broad taskkill，超时或未完全退出标注 `cleanup_unverified`）；
   - Windows 下使用 `CREATE_NO_WINDOW` 隐藏窗口；异常路径完整保留真实退出状态与 `command.json` 证据；
   - 实行原厂源与 private staged 输入双重固定 SHA 校验；检查 `run_id` 命名与所有路径越界。
2. **[tools/generate_model_e0.m](file:///C:/Users/PC/Documents/odid编译/wksim/tools/generate_model_e0.m)**：
   - 伴随 MATLAB 内部无头批处理脚本（`-batch` 模式执行）；
   - 记录 MATLAB 产品版本（`ver`）；独立校验并记录 `test` 与 `checkout`（包含 `RTW_Embedded_Coder` 与 `Real-Time_Workshop`）；
   - 显式核验/冻结 `Solver=ode4` 与 `FixedStep=0.001`，内存切换 `SimulationMode=normal`；
   - 内存覆盖 `ert.tlc`/`C++`/`GenCodeOnly=on` 目标配置并调用 `slbuild`，不调用厂商 `.p` 脚本、不运行仿真、不保存修改模型。
3. **[validation/test_generate_model_e0.py](file:///C:/Users/PC/Documents/odid编译/wksim/validation/test_generate_model_e0.py)**：
   - 驱动编排、隔离边界与合规门槛的离线单元测试套件（18 项测试用例全部 PASS，包含新增的 staged 输入篡改、Embedded Coder 许可缺失、slbuild 阶段缺失、solver 配置不符、异常证据保留等真实负例）。
4. **[docs/coordination/agy-codegen-driver-514743f.md](file:///C:/Users/PC/Documents/odid编译/wksim/docs/coordination/agy-codegen-driver-514743f.md)**（本文）：
   - 架构说明、硬性隔离保证、实测工具路径及交接清单。

---

## 二、 架构解耦：MATLAB 构建期 vs 待验证运行期

必须严格区分两个不同的系统生命周期阶段，避免概念混同：

```
[构建期 (Build-time) — 依赖真实 MATLAB 商业工具链]
  E:/rflysimtools/.../Exp1_MinModelTemp.slx (11.8)
  └── 调用 tools/generate_model_e0.py --run
        └── D:/matlab/.../matlab.exe (-batch generate_model_e0)
              ├── 校验 SIMULINK / Real-Time_Workshop / RTW_Embedded_Coder / Aerospace 许可
              ├── 设置 Simulink.fileGenControl 私有缓存与输出目录
              ├── 校验 Solver=ode4 / FixedStep=0.001，内存切换 SimulationMode=normal
              ├── 内存配置 SystemTargetFile='ert.tlc', TargetLang='C++', GenCodeOnly='on'
              └── slbuild('Exp1_MinModelTemp')
                    └── 输出至 work/codegen-e0/run-<id>/codegen (独立 C++ 源码与头文件)

-----------------------------------------------------------------------------------------

[日常运行期 (Runtime) — 尚未生成/编译，运行期无MATLAB为后续待验证]
  work/codegen-e0/run-<id>/codegen/*.cpp, *.h
  └── 后续在 WSL/Linux 下通过 g++ 编译包装为 libwksim_e0.so (导出标准 C 接口)
        └── 待通过 ldd 与脱离 MATLAB 环境冷启动验证其是否完全无 MATLAB 依赖
```

1. **代码生成必须使用真实商业工具链**：SLX 模型生成 C++ 源码必须调用本地真实安装的 `MATLAB R2022b` 及其 `Embedded Coder` 核心能力，绝非“无 MATLAB 脚本直接转换 SLX”；
2. **尚未生成/编译，运行期无 MATLAB 为后续待验证**：生成的 C++ 源码包装为共享库后，其在 Linux/WSL SITL 动力学解算中的独立性（脱离 MATLAB 运行时），属于 #71/#72 阶段的待核验目标，当前不作提前断言。

---

## 三、 已实测查证的 #70 本地工具路径与源材料清单

根据前置预检 `validation/model-reference-readiness-20260909/attempt-07/` 及 `docs/plan/model-reference-provenance-supplement.md:14`，查证到的本地工具链配置如下：

- **MATLAB 二进制入口**：`D:/matlab/install date/bin/matlab.exe`
- **MATLAB 版本**：`MATLAB 9.13.0.2049777 (R2022b)`
- **必需工具箱与 License 特性清单**：
  - `SIMULINK`：Simulink 核心建模环境；
  - `Real-Time_Workshop`：Simulink Coder 代码生成基础；
  - `RTW_Embedded_Coder`：Embedded Coder 官方代码生成特性（`ert.tlc` 所属核心）；
  - `Aerospace_Blockset`：航天动力学库；
  - `Aerospace_Toolbox`：航天坐标变换工具。
- **输入源模型及基线（只读检查）**：
  - 目录：`E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/`
  - `MulticopterModel.zip`：`d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`（134,827 字节）
  - `Exp1_MinModelTemp.slx`：`c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392`（122,461 字节，Simulink 11.8）
  - `Exp1_MinModelTemp_init.m`：`9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991`（2,519 字节）
- **本地开发用途官方依据**：
  - `Intro.pdf` (p.3, p.5)：模板支持二次开发、生成 C/C++ 并移植外部系统；
  - `Readme.pdf` (e0 模板，p.1-3, 5-10)：最小四旋翼动力学模板修改、代码生成与联仿步骤；
  - `Readme.pdf` (GenC++，p.6, p.9)：使用 `ert.tlc` 生成独立 C++ 源码。

---

## 四、 硬性隔离与安全设计机制（初审针对性修正）

1. **定向进程追踪与安全清理（针对问题 1 修复）**：
   - 驱动引入 `ProcessTracker`，在 `Popen` 启动时立即获取其 PID 与 `create_time` 绑定身份，超时或异常终止时校验 PID 存活与创建时间一致性，杜绝超时后按裸 PID 查杀导致的 PID 复用风险；
   - 仅终止自建进程与其 `psutil` 查证的子进程，若 `psutil` 不可用或子进程无法完全核验退出，严格标记 `cleanup_unverified`，杜绝返回伪 `True`；
   - Windows 下通过 `creationflags=0x08000000`（`CREATE_NO_WINDOW`）隐藏控制台窗口；
   - 异常路径（如执行异常或超时）完整回写 `command.json`，保留真实退出状态与错误描述，不直接 raise 丢失上下文。
2. **输入双重不变性门槛（针对问题 2 修复）**：
   - `audit_and_finalize` 显式校验 `source_tampered` 与 `staged_tampered`；
   - 不仅原厂源文件必须与预设 SHA 吻合，私有 `staged-model` 内的模型与初始化文件也必须在执行前后与预期 SHA 严格一致。任何一方被改动，均判定为 `rejected_input_tampered`。
3. **Solver 校验与 SimulationMode normal 切换（针对问题 3 修复）**：
   - `generate_model_e0.m` 载入模型后显式读取 `Solver` 与 `FixedStep`，如果不等于 `ode4` 与 `0.001`，则判定 `invalid_solver_config` 并退出码 1；
   - 显式在内存中切换 `set_param(model, 'SimulationMode', 'normal')`（满足前置 readiness 必要配置，不修改物理预算），且关闭时严禁 `save_system`，磁盘文件保持只读。
4. **Embedded Coder 准确 Feature 与版本记录（针对问题 4 修复）**：
   - `REQUIRED_LICENSES` 明确纳入 `RTW_Embedded_Coder`，与 `Real-Time_Workshop` 分立检验；
   - MATLAB 内部通过 `ver` 记录所有产品版本及发布版本，任一必需特性 `test` 或 `checkout` 非 1 即判定 `rejected_license_failure`。
5. **严密路径安全与阶段状态真实校验（针对问题 5 修复）**：
   - 对 `run_id` 实施字符集正则校验（`^[a-zA-Z0-9_-]+$`），严格禁止包含 `/`、`\\`、`..` 等路径分隔符；
   - 校验 `work_dir` 与 `evidence_dir` 严格受限于项目根，严禁复用已存在的非空目录；
   - 最终判据不仅检查非空产物与 `status` 字段，必须逐项校验 `REQUIRED_STAGES` 中的 9 个阶段全部为 `ok`，重点校验 `slbuild == 'ok'`。
6. **代码防泄漏与 Git 边界**：
   - 生成的 C++ 源码及构建中间产物留在 `work/codegen-e0/run-<id>/`（gitignored）；
   - `validation/codegen-e0/run-<id>/` 目录仅记录元数据清单与 JSON 日志，**严禁包含专有源代码正文**。

---

## 五、 单元测试验证结果

执行测试命令：
```powershell
python -B -m unittest validation.test_generate_model_e0 -v
```

实测输出（18 项测试用例全部 PASS，0.214 秒）：
```text
test_dry_prepare_default_does_not_launch_matlab (validation.test_generate_model_e0.TestGenerateModelE0.test_dry_prepare_default_does_not_launch_matlab)
Default execution (run_flag=False) must only stage files and generate manifests. ... ok
test_embedded_coder_feature_required_and_rejected_on_failure (validation.test_generate_model_e0.TestGenerateModelE0.test_embedded_coder_feature_required_and_rejected_on_failure)
RTW_Embedded_Coder must be checked; if its checkout fails, must reject. ... ok
test_empty_artifact_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_empty_artifact_rejected)
A generated .cpp file with 0 bytes must be rejected. ... ok
test_execution_exception_preserves_evidence (validation.test_generate_model_e0.TestGenerateModelE0.test_execution_exception_preserves_evidence)
Unexpected execution exceptions must be recorded into command.json rather than dropped. ... ok
test_input_sha_mismatch_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_input_sha_mismatch_rejected)
Preparation must fail immediately if any source file hash differs from EXPECTED. ... ok
test_invalid_run_id_characters_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_invalid_run_id_characters_rejected)
Run ID containing separators, traversal, or invalid characters must be rejected. ... ok
test_license_failure_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_license_failure_rejected)
If Real-Time_Workshop checkout fails, status must be rejected_license_failure. ... ok
test_matlab_failure_exit_code_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_matlab_failure_exit_code_rejected)
A non-zero return code from MATLAB must cause status='failed'. ... ok
test_missing_artifacts_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_missing_artifacts_rejected)
Exit code 0 but missing C++ files must be rejected as missing_artifacts. ... ok
test_missing_input_file_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_missing_input_file_rejected)
Preparation must fail if an expected source file is missing. ... ok
test_mock_successful_generation (validation.test_generate_model_e0.TestGenerateModelE0.test_mock_successful_generation)
Mock successful slbuild: verifies artifact audit, manifest generation, and 'generated' status. ... ok
test_path_traversal_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_path_traversal_rejected)
Paths pointing outside repository root must be rejected. ... ok
test_reuse_nonempty_directory_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_reuse_nonempty_directory_rejected)
Driver must refuse to reuse an existing non-empty work or evidence directory. ... ok
test_slbuild_stage_missing_or_failed_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_slbuild_stage_missing_or_failed_rejected)
If slbuild stage failed, driver must reject even if status='generated' and files exist. ... ok
test_source_tampered_during_run_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_source_tampered_during_run_rejected)
If original source files are modified during run, post-check must reject. ... ok
test_staged_input_tampered_during_run_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_staged_input_tampered_during_run_rejected)
If staged private inputs are modified while original sources are untouched, must reject. ... ok
test_timeout_and_process_cleanup (validation.test_generate_model_e0.TestGenerateModelE0.test_timeout_and_process_cleanup)
Timeout must terminate process tree and record cleanup status. ... ok
test_verify_solver_stage_failed_rejected (validation.test_generate_model_e0.TestGenerateModelE0.test_verify_solver_stage_failed_rejected)
If solver check failed, driver must reject. ... ok

----------------------------------------------------------------------
Ran 18 tests in 0.214s

OK
```

---

## 六、 未验证边界与交接说明

1. **未启动真实商业 MATLAB**：本次任务严格遵守“只实现/纯测试，不执行 MATLAB”指令，未调用商业 `matlab.exe`；
2. **首次真实生成启动权归主会话**：由主会话再次审查后，按需在授权下触发首次真实构建：
   ```powershell
   python tools/generate_model_e0.py --run
   ```
3. **运行期无 MATLAB 依赖性为后续验证项**：当前阶段尚未生成且尚未在 Linux 下编译出共享库，其在日常仿真中的无 MATLAB 依赖性属于后续在 WSL 环境下验证的目标；生成的任何代码与二进制严格保留在本地私有空间，不得提交至 Git 仓库。
