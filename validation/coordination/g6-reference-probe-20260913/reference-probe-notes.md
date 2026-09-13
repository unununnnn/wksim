# G6 参考端首步观测 probe 包（只读准备；主会话实跑 MATLAB）

主会话后续已实跑execution/run-01、02、03，详见docs/2026-09-13-reference-first-step-observation.md。run-03实际通过UDD对象Data属性取得4积分器四个导数时点的double状态/导数，240个major值与冻结参考逐位一致，源文件未变；仍不构成G6通过。当前脚本已增加输入哈希/版本约束、原子新目录与CREATE_NEW输出、独立cache/codegen、事件上限，并保持partial而非仅凭事件数标complete。下面的初始静态说明/首次命令属于历史版本；旧run目录已存在，不得覆盖或照抄重跑。

2026-09-13。负责人：Claude。承接首步静态调查（`docs/coordination/g6-first-step-static-20260913.md`)。本包**只做离线结构映射与脚本准备**，不运行 MATLAB/模型，不构建，不改冻结的 `export_model_reference.m` / SLX / 生成 cpp，不拷贝模型或厂商源码。

## 交付物

- `tools/probe_reference_first_step.m` — 参考端首步（k=0→1）观测探针（主会话实跑）。
- `tools/map_reference_blocks.py` — 离线 SLX/库结构映射器（元数据：路径/SID/SHA)。
- `validation/test_map_reference_blocks.py` — 纯 Python 测试（5 项，合成 SLX-ZIP fixture)。
- 本目录：`block-map.json`（真实映射输出）+ 本说明。

## 离线结构定论（真实 SLX/库 ZIP，只发元数据）

模型 `Exp1_MinModelTemp.slx` SHA256 `c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392`。刚体连续状态积分器**不在模型 XML 直接可见**，而在库链接的 Aerospace Blockset 6DOF 内部：

- 根 → `6DOF1`(SubSystem SID `12216`)→ `Custom Variable Mass 6DOF (Quaternion)`(Reference SID `12216:1138`,SourceBlock `shared6dof/6DOF (Euler Angles)`,SourceType `6DOF EoM (Body Axis)`)。
- 库 `shared6dof.slx` SHA256 `7d12b7e6c7c6ff21767aec5afb4c5f0e9959df2e2c815f77075fd06b2336c36a`：`ub,vb,wb`(SID `61:56`)、`p,q,r`(SID `61:17`)、`xe,ye,ze`(SID `61:26`)。
- 库 `shared6dofsys.slx` SHA256 `22f98f2e9a8a827b4e5159bdfb026809c5026a3e3d88a5234dcb2c9d1ce1e15c`:`q0 q1 q2 q3`(SID `380`)、`phi theta psi`(SID `359`，本模型未用）、`mass`(SID `289:14`)。
- 根 I/O:`inPWMs`(Inport SID `10053`)、`TerrainIn15d`(Inport SID `12106`)、`HILSensor30d`(Outport `10427`)、`HILGPS30d`(Outport `10428`)、`VehileInfo60d`(Outport `10429`)。

完整穿越库链接的运行时块路径**离线不可定**，由探针在运行模型中以 `find_system` 实际解析并记录（详见 `block-map.json` 与报告）。

## 探针设计（只用文档化 API，不编造 RTO 属性）

- **机制**:`add_exec_event_listener(blk,event,listener)`（文档化，事件 `Pre/PostDerivatives`、`Pre/PostOutputs`)，回调读 `Simulink.RunTimeBlock`：`CurrentTime`、`NumContStates`、`SampleTimes`、`ContStates()`、`Derivatives()`（均文档化）;`InputPort(1).Data`/`OutputPort(1).Data` 为尽力而为（try/catch，不可得则记 unavailable)。
- **复用冻结 R1 设置**：模型、`init.m`、C3G `input.csv`、`ode4`、固定 1 ms；仅把 StopTime 改为 `0.001`(k=0→1)。
- **不假设每步恰 4 次**：记录实际事件顺序/计数；**不把积分器输入直接当有效导数**——导数取文档化 `Derivatives()`，并逐块记录 limit/reset 配置（`LimitOutput`/`ExternalReset` 等）。
- **回调保留**：原 StartFcn/InitFcn 读取→链式→恢复（本模型原值为空）；临时 listener 与 base 变量在 `onCleanup` 中清理；模型 `close_system(...,0)` **不保存源**。
- **输出防覆盖**：报告 `reference-first-step.json` 须为新文件，`isfile` 已在先则报错拒绝；输出目录新建。
- **可运行地报告局限**：积分器无法解析/事件未触发/状态不可读时，报告 `status=unavailable|partial` + 具体 reason,**不造空 trace 充通过**。

## 静态验证（本任务无 MATLAB)

- `probe_reference_first_step.m`:6 个函数均闭合、控制流/括号平衡（逐项人工复核 + 脚本结构检查）；只用上述文档化 API；未实跑，事件粒度/导数可谈性以实际运行为准。
- `map_reference_blocks.py`:`validation/test_map_reference_blocks.py` 5 项通过（合成 SLX-ZIP fixture：根 I/O SID、6DOF 引用块、库积分器 SID、缺块拒绝、写一次后拒覆盖）；真实 SLX 跑通并产出 `block-map.json`。

## 精确主运行命令（主会话实跑，新进程）

```matlab
matlab.exe -wait -batch "probe_reference_first_step( ...
    '<REPO>\validation\numerical-conformance-gxxh6xhr\C3G\staged-model', ...
    '<REPO>\validation\numerical-conformance-gxxh6xhr\C3G\input.csv', ...
    '<REPO>\validation\coordination\g6-reference-probe-20260913\run-01')"
```

（`<REPO>` = 本工作区绝对路径；`run-01` 必须为不存在的新目录；报告落在 `run-01\reference-first-step.json`。)

- **输入 SHA256(C3G `input.csv`)**:`721c88bf3f621923b98bb43251c50bae7817106a984be64345c0528d34d3adcf`。
- 运行环境：MATLAB `9.13.0.2049777 (R2022b)` normal、ode4、固定 1 ms，与冻结参考一致。

## 仍需实测确认（本任务不做）

1. `Pre/PostDerivatives` 是否按 RK4 每步 4 次在每个积分器块上触发（文档未按阶段明确，探针记录实际计数，不假设 4)。
2. `RunTimeBlock.ContStates()`/`Derivatives()` 对内建 Integrator 块在 listener 回调中是否返回有效向量（不可得则报告记 unavailable)。
3. 库链接内部的积分器块是否可被 `add_exec_event_listener` 寻址（无法寻址则记 failed 并保留原因）。
4. 若上述成立，参考侧 f0..f3 各级状态/导数 hex 与目标侧首步 trace 的逐点对照——那才是把首分歧落到"导数求值 / ODE4 加权和 / 输出编码"的决定性证据。

## 边界

R1 仍 `numerical_failed`,G6 未通过；本包只准备参考端观测入口，不改任何接受门/预算/冻结证据。诊断器与其测试保持冻结，本任务未触碰。
