# #70 · 模型生成来源与导入合同

2026-09-09；稳定键 `26-generation-source`。结论：**blocked_source_authorization_and_generation_entry**。本票交付精确阻塞和后继合同，未交付已批准可执行生成流程，#70 保持 OPEN / needs-triage，#71 不可据本文开跑。父 #26、#9、G6、R1 和 RateUnmet 状态不变。

## 来源选择及证据范围

唯一候选选用本机 e0 的可编辑 `Exp1_MinModelTemp.slx` **11.8** 与相邻 init；不选相邻旧 ZIP **11.0** 作为“本次生成”。目录为 `E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp`。

| 材料 | 本次重新计算的 SHA256 |
| --- | --- |
| Exp1_MinModelTemp.slx | c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392 |
| Exp1_MinModelTemp_init.m | 9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991 |
| MulticopterModel.zip（仅历史复用） | d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed |

[normal readiness 报告](../2026-09-09-model-reference-readiness-report.md)的 attempt-07 原始 readiness SHA256 本次重算仍为 `d1fb57914f8382673a78548764c3837a259411168653c7d99d91d8ffc19f6f96`。它证明当时 normal load/update、ODE4、1 ms 成功；不证明代码生成、当前 checkout 或分发权。

[11.x 漂移报告](model-reference-drift-11x.md)保留历史；其“不能生成”的旧许可结论不能覆盖后来的 test=1，后来的 test=1 也不能覆盖 checkout/build 实证缺口。11.8 与 11.0 不构成同版本配对，不复用 11.0 输出当作 11.8 的预期数值。

复用 #24 [主复核](../2026-09-09-quad-parameters-closure-review.md)及 `validation/quad-parameters-main-review-20260909/review.json`（本次 SHA256 `43ead525bab46e93d64dad241eb0d219d3f5ffe35992734c2c47cb233d526a4c`）：历史报告 54 身份检查、3×500 tick、60000 导入输出值相同及6单元检查。此次未重跑，不能将历史统计计为本轮测试。无需为 #70 再执行 #25 六旋翼飞行或构建。

## 精确阻塞与许可边界

1. 没有在已读来源资料中找到绑定上述 SLX/init 哈希、允许本项目生成/修改/独立运行产物的条款或权利人确认。对 RflySimAPIs（含隐藏文件）的 LICENSE/license/版权/许可/COPYING 文件名搜索无匹配（rg=1）。这是**有界搜索结果**，并非证明全安装或合同不存在许可。版本说明的功能描述、可读文件、用户对本机操作的授权、仓库 Apache-2.0 均不自动授予外来材料权利。PDF 手册/外部采购合同的完整许可审查尚未完成。
2. 允许本机使用与允许再分发分开记录。即使本地生成使用获确认，厂商 SLX、init、生成 C/C++、MathWorks 头文件、DLL/SO 继续留在受控本地目录，除非另有覆盖具体文件的分发许可；本次只发布项目文档、命令及哈希，不复制厂商字节。
3. 当前 `tools/quad_model_parameters.py build` → `model_parameters.py` → `model.py` 固定校验旧 ZIP 和五个旧成员 SHA。它不是通用新生成源码导入器；新 SLX 产物应被拒绝，不能换 pin 掩盖来源变更。`GenerateModelDLLFile.p` 未执行，不能提供可审阅生成/包装来源。
4. `probe_model_reference_readiness.py` 明确只 load/update，不 sim/codegen。没有现成的已审查生成入口、独立生成审计器或新源码准入器。本票仅允许文档/证据，不能在 tools/ 或核心偷偷新增这些入口。#71 自身也只有证据写入范围。

解除来源阻塞所需输入：权利人/现有许可文件的路径、SHA256、适用版本和条款定位，明确 local_generate/local_modify/local_compile/local_run 与 redistribute_source/redistribute_binary 各项。后两项可以明确为禁止，不能以缺分发权自动否定已经确认的本地使用权。若选择替代自有/开源模板，须有对应可编辑源、生成方法、许可证和单位映射；当前没有把未核对替代来源称为可用。

解除入口阻塞所需工作：由主任务分配实际生成/准入/审计脚本的写入范围，完成源码审查并冻结命令与哈希，再恢复 #70 ready。不要求某条非 MATLAB 路线重新调用 MATLAB Coder；但本次所选 SLX 路线若继续，必须有实际合法工具 checkout 与生成退出结果。未取得这些输入前不存在可诚实声称“已支持”的生成命令。

## 后继导入与生命周期合同

以下是后继实现约束，不是声明未创建的脚本已经可运行。

- 固定来源、可编辑配置、实际有效库依赖和生成设置必须先冻结。SLX 11.8 原配置为 normal/ODE4/0.001 s；代码生成目标/硬件/优化另记录实际值，不能沿用旧 ZIP 的 Windows64 标记充当 Linux 编译证明。
- 配置身份沿用 #24 的规范 JSON 方法：UTF-8、sort_keys、紧凑逗号/冒号、allow_nan=false；身份字段不参与自身散列。新来源必须形成新的 schema/recipe 与 model_identity，不能伪装 `wksim.quad-mass.v1` 的旧固定 SOURCE。文件 SHA 与语义配置身份分别保存。
- 质量 kg；位置 NED/m，速度 NED/m/s，姿态 rad，角速率 FRD/rad/s；质量编辑不自动改变惯量 kg*m²。现有质量范围0.5–5.0 kg仅为 #24 输入范围，不是新模型物理包线。未验证的非零 ModelInit_RPM 单位不得开放。
- 现有归一化输入16个 finite double，范围[0,1]；Quad X仅0..3有效，4..15必须零。顺序前右、后左、前左、后右需由新生成源再次核对。TerrainIn15d目前清零，不扩展成环境反馈已完成。
- C入口沿用项目包装语义：create 初始化并清输入；step每次1 ms；destroy执行terminate。输出120 double按 Vehicle60 / Sensor30 / GPS30 排列。当前包装返回0成功、1非法参数、2模型错误、3非有限状态。新生成接口/布局必须按实际头文件审查，不靠同名类或120个数猜兼容。
- 当前已用观测：output[2]仿真秒、[3:6] NED速度、[6:9] NED位置、[16:20]电机RPM；新来源重新逐项绑定。其余输出应保存完整原始向量，在单位/语义未核对前不作为验收量。
- 一进程一载具生命周期，静态参数隔离；输入身份、配置、库及包装哈希、导出身份和实际质量在首步前核验。任何错配即拒绝，不推进首个tick。
- reset采用终止旧进程后冷重建，新run_id/PID/boot_id/starttime、tick0、相同源/配置/初态/种子；不宣称进程内热reset。终止后无额外step，记录退出码与最后tick。新模型还须证明重新初始化的随机状态与配置对应。
- #72要在生成进程退出后独立加载、运行、冷重建及终止；保存动态依赖和进程证据以证明不依赖 MATLAB 运行时。旧 #24 的独立 native 运行不替代新生成模型验证。
- 不预设11.0/11.8数值相等或自定物理误差预算。生命周期检查与物理精度分开；后者继续按原数值合同，R1 numerical_failed 不变。

## 现有可执行命令与当前缺口

项目根 PowerShell只读核对命令（本次实际执行原文与输出见证据）：

```powershell
python tools/quad_model_parameters.py --help
Get-FileHash -Algorithm SHA256 -LiteralPath 'E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/Exp1_MinModelTemp.slx'
```

旧链复用命令准确形状已在 #24 报告给出：`python3 tools/quad_model_parameters.py build <validated-config.json>` 和 `run <config.json> <library.so> <new-response.jsonl> --commands .8 .8 .8 .8 --ticks 500`。它们只支持固定 ZIP 参数化；**旧 ZIP 编译不能满足生成验收**。本次未执行build/run。

#71 所需完整生成命令目前缺失，不能用裸 `slbuild`、未审阅的 .p 或猜测CLI替代。新增入口交付前必须同时给出独占工作目录、输入manifest、依赖/工具许可检出、生成argv、超时、退出与清理、审计argv；这是恢复派发的门，不是让Luna临场补写。

## 后继输出 schema（待实现）

`wksim.model-generation-evidence.v1` JSON，必需字段：

| 字段 | 合同 |
| --- | --- |
| status | blocked / failed / generated / verified；缺失证明不能为verified |
| run_id, source_revision | 唯一运行与仓库commit |
| source_files, effective_dependencies | 绝对受控路径、原始SHA256、角色、生成前后哈希 |
| authorization | 证据路径/hash/条款定位与六项独立权限；unknown不可视为true |
| configuration | schema、canonical identity、单位、初态、seed、solver、step_s |
| generator | 实际工具版本、checkout原始结果、argv、cwd、环境覆盖、stdout/stderr路径/hash、exit_code |
| generated_files | 新产生源及头的本地路径/hash；不得只列旧ZIP |
| compiler | 版本、完整argv、日志hash、exit_code、动态依赖 |
| artifact | 模型身份、SO路径/hash、包装源hash、导出/I/O审核 |
| lifecycle | MATLAB退出证明、create/首步/终态/terminate、旧新进程身份、cold_reset关联 |
| audit | 独立审计器hash/argv/退出、各不变量原始证据与判定 |
| limitations | 许可、入口、数值、依赖等未验证项，不能省略 |

失败时原件追加新目录保存，停止该链；不得覆盖、换源、修改pin或放宽预算后将原失败改成通过。当前文档提供阻塞合同，没有产生此新schema的运行结果。

本次证据位于 `validation/lunar-70-source-20260909-01/`。仅hash/帮助命令，无模型/飞控/ROS/UE/MATLAB子进程。实际任务模型 `gpt-6-astra`、effort `low`，由当前 CODEX_THREAD_ID 对应session的最新turn_context核验；没有委派。
