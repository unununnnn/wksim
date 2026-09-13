# G6 / R1 首步（k=0→1）分歧有界静态调查

2026-09-13。负责人：Claude。承接首分歧定位（`g6-first-divergence-20260913.md`：最早分歧 C3G / k=1 / `Vehicle60[3]`，2 ULP)，本文件做**只读静态**根因调查：把 `Vehicle60[3]/[11]/[15]` 在 k0→1 的计算链落实到实际 ODE4 更新/归一化/数学函数/常量，核实实际编译 flags/目标 ISA 与 FMA 指令是否存在。

**只读、无副作用**：不运行模型/MATLAB、不启动 native/ROS、不构建、不改生成源码/编译/SLX、不改零容差 R1 门、不动现有诊断器与其测试。本文件与配套证据目录只含"可重核源索引 + 命令输出"，**不拷贝厂商/生成源码或二进制**。

- 证据目录：`validation/coordination/g6-first-step-static-20260913/`(`source-index.json`、`compiler-target-query.txt`、`r1-binary-absent.txt`)

## 可读性与一致性前提

- R1 目标用的**冻结生成补丁版** `Exp1_MinModelTemp.cpp`(SHA `a3eba68e…`）与目标二进制（SHA `c685817a…`)**当前不在盘**:WSL 构建目录 `/root/wksim-major-recorder-j_3guvtn` 已随资源窗口清理（见 `r1-binary-absent.txt`)。
- 但**数值源表达式**可证明未变：`tools/build_major_model_recorder.py` 的 `instrument()` 只插入 `wk_capture_major` 钩子（`#include` 后加 extern 声明 + 主时间步块内加一行采集调用），并断言"去掉这两段插入字节即还原原始字节"。**注意：这只证明原始版↔补丁版的数值源表达式一致（instrumentation-only)；它不证明历史执行二进制与原源码新编译产物逐位等价**——历史二进制未留存，其位内容不可再核验，二进制等价是另一问题。本文按原始版行号引用（与 R1 合同 source 引用一致）。
- 参考侧是 **MATLAB R2022b Simulink normal** 解释器，内部求值不透明、不可读源码。

## 每个 major step 的时间线（目标侧）

记录器每 k 调一次 `model->step()`：先在主时间步计算根输出（`wk_capture_major` 采集 `Exp1_MinModelTemp_Y` 的 `VehileInfo60d/Sensor30/GPS30`)，再做 ODE4 更新把状态从 t_k 推进到 t_{k+1}(ODE4 内部各阶段为 minor step，不重复采集，故每 k 恰 1 次 major 采集）。

因此 **k=1 的输出 = 初始静止状态经一次 ODE4 更新后的状态的函数**。首个分歧（k=1）要么来自这次 ODE4 更新/其导数求值，要么来自 k=1 的输出编码。

## 计算链落实（原始版 `a35d7c8f` 行号；与合同 source 引用一致）

### ODE4 求解器（逐项列出实际源码求值顺序，不代数化简）

`MulticopterModelClass::rt_ertODEUpdateContinuousStates`(2970–3034),`nXc=36` 个扁平连续状态。本任务研究的正是舍入，故按**实际源码的乘法/加法括号顺序**逐项列出，不把加权和化简为 `(h/6)(f0+2f1+2f2+f3)`:

阶段中间态（`0.5` 是 2 的幂，对 h 为精确缩放，不引入舍入）:
- L2997 `temp = 0.5 * h`;
- L2999 `x[i] = y[i] + (temp*f0[i])`(`temp*f0` 舍入，`y+` 舍入）;
- L3009 `x[i] = y[i] + (temp*f1[i])`（同上，temp=0.5h);
- L3018 `x[i] = y[i] + (h*f2[i])`(`h*f2` 舍入，`y+` 舍入）。

末次加权更新（L3028–3030)，逐项：
- L3028 `temp = h / 6.0`(h=0.001 非二进制精确，`/6` 舍入 → temp 为已舍入常量）;
- 内层和（左结合）`s = ((f0[i] + 2.0*f1[i]) + 2.0*f2[i]) + f3[i]`(`2.0*f1`、`2.0*f2` 为 2 的幂精确缩放、不舍入；三次加法各舍入一次）;
- `p = temp * s`（舍入）;
- `x[i] = y[i] + p`（舍入）。

**参考侧 ODE4**:Simulink normal 的 ode4 是**另一套代码库**，其确切 FP 求值顺序/系数形式（例如是否用预计算 `hB[j]` 加权求和而非此 `temp*(sum)` 形式）属内部实现、无 FP 级文档，现有材料不可观测 → **未证**。两种形式代数等价但舍入路径不同，不能据代数等价推断逐位一致。

### Vehicle60[3] — velocity_ned 北向（m/s)
- 输出（7823):`VehileInfo60d[3] = B.Product[0]`。
- 上游：`B.Product[i] = Σ_j VectorConcatenate[3i+j] * ubvbwb_CSTATE[j]`(4161–4163，乘-加循环）——即 **VelE = DCM · ubvbwb**（姿态矩阵乘机体速度）;`VectorConcatenate` 为 DCM，由归一化四元数构造；`ubvbwb_CSTATE` 由 ODE4 更新。

### Vehicle60[11] — Euler 偏航（rad)
- 输出（7846):`VehileInfo60d[11] = rtb_sincos_o1_j_idx_0`。
- 上游：`= rt_atan2d_snf( 2*(q1*q2 + q0*q3), (q0²+q1²) - q2² - q3² )`(4228–4231)，作用于**归一化**四元数（范数 `sqrt(Σqᵢ²)` 在 4183，各分量除法在 4194–4213);`rt_atan2d_snf` 包装 `std::atan2`(3628–3658)。**atan2 为超越函数**。

### Vehicle60[15] — 四元数 qz（无量纲）
- 输出（7850):`VehileInfo60d[15] = B.Merge_j[3]`。
- 上游：`Merge_j` 来自 **DCM→Quaternion**(Shepperd 开方：PositiveTrace 3042–3067,sqrt 3052;NegativeTrace 3090–3284,sqrt 3123/3182/3241)+ 定号（fix_quat_sign);DCM 由归一化四元数构造。

## 编译 flags / 目标 ISA / FMA（实测，不靠 -O2/-fno-fast-math 猜）

- **实际 argv**(`build.json`,SHA `6e16102a…`):`g++ -std=c++17 -O2 -fno-fast-math -Wl,--no-undefined`,**无 -march / 无 -mfma**；编译器 `g++ 11.4.0`，目标三元组 `x86_64-linux-gnu`。
- **编译器默认目标查询**（只读：`-fsyntax-only`，未编译模型、无产物，见 `compiler-target-query.txt`)：该 flag 集合下 `-march=x86-64`（基线）,**`-mfma [disabled]`,`-mavx2 [disabled]`，全部 AVX/AVX-512 disabled**;`-ffp-contract=fast` 虽置位，但基线 x86-64（仅 SSE2)**没有 FMA 指令可融合**，`a*b+c` 只能编成 `mulsd + addsd`（两次舍入）。

## 假设评估（能排除给出处，否则标未证）

| 假设 | 判定 | 出处 / 说明 |
| --- | --- | --- |
| H1 目标侧 FMA 收缩 | **排除（目标侧，含前提）** | **历史构建记录**(`build.json` argv 无 `-march/-mfma`）与**当前编译器默认查询**(`compiler-target-query.txt`：该 flag 集合下 `-march=x86-64` 基线、`-mfma` 禁用、全部 AVX/AVX-512 禁用）共同指向基线 SSE2 无 FMA 指令，`-ffp-contract=fast` 无 FMA 可融合。**前提**：历史 R1 二进制未留存（`r1-binary-absent.txt`)，无法对其做 objdump 指令级复核；结论依赖记录 flags + 该 flags 下编译器默认目标，而非直接读历史二进制。参考侧（MATLAB）内部 FMA/向量化不透明，**未证**。 |
| H2 超越函数 libm 差（asin/atan2) | **未证（部分）** | `std::asin`(7845)、`rt_atan2d_snf`/`std::atan2`(4228）非正确舍入、libm 相关，glibc 与 MATLAB libm 可差 ~1 ULP。**只可能解释 Euler 编码 [11]/[10]**；无法解释只用 mul/add/div/sqrt 的 `velocity[3]` 与 `quaternion[15]`。 |
| H3 归一化 sqrt | **未证** | 更正前稿"排除":`std::sqrt` 仅在**给定输入**时正确舍入；但 sqrt 的**输入**（四元数平方和 `Σqᵢ²`，或 Shepperd 的 `traceDCM+常量`）本身是**未观测**的乘-加/求和链，其舍入可随引擎不同。输入未观测 → 归一化既不能被排除也不能被定位；sqrt 正确舍入只保证固定输入下结果确定。 |
| H4 求值顺序 / 双引擎 FP 工具链（残余） | **未证** | 两引擎是共享同一模型的**不同代码库**：参考=Simulink normal 解释器（自有 ode4+libm，宿主优化、可能用 AVX/FMA/向量化）；目标=生成 ERT C(`rt_ertODEUpdateContinuousStates`，基线 x86-64,glibc)。乘-加链与 ODE4 加权和的求值顺序/舍入可不同；确切首个分歧运算需首步步内 trace（现存证据只有逐 1ms 主输出）。 |

**结构性事实**：这不是"同一份 C、两个编译器"，而是 **Simulink normal 解释器 vs 生成的 ERT C** 两个独立求值/求解引擎。目标侧可完全读源码，参考侧内部不可读。

## 精确首步 trace 观测点（目标/生成 C，变量名 + 原始行号）

- **ODE4 求解器**(`rt_ertODEUpdateContinuousStates`,2970–3034):`id->f[0..3]`（四级导数）、`id->y`(t_k 态）、`x`（更新后态），取 `ubvbwb_CSTATE` 与 `q0q1q2q3_CSTATE` 对应的扁平索引；加权和 3029–3031。
- **导数函数**(`Exp1_MinModelTemp_derivatives`,8313–8347):`_rtXdot->ubvbwb_CSTATE[0..2]`(=`B.Sum_p`，机体速度导数）与 `_rtXdot->q0q1q2q3_CSTATE[0..3]`（四元数导数，运动学方程 7934–7956)。
- **k=1 输出编码**:`B.Product[0]`→`VehileInfo60d[3]`;`rtb_sincos_o1_j_idx_0` 及其 atan2 两参数→`VehileInfo60d[11]`;`B.Merge_j[3]`→`VehileInfo60d[15]`。
- **中间量**：四元数范数 sqrt(4183)、归一化四元数分量（4194–4213)、DCM(`VectorConcatenate`)、`Merge_j` 的 merge 选择（7769–7770)。

## 两个引擎对照的最小证据需求

用于把分歧落到"导数求值 / ODE4 加权和 / 输出编码"三分支的判定树：

- 四级导数 `f0..f3`（相关状态）在 k=0→1 即不同 → **导数/方程求值**分歧；
- `f0..f3` 相同但更新后状态不同 → **ODE4 加权和**算术分歧；
- 状态相同但 `VehileInfo60d[3]/[11]/[15]` 不同 → **输出编码**(VelE 旋转 / DCM→quat / Euler atan2）分歧。

**最小证据**：双引擎各做一次 k=0→1 单步，按全 binary64 导出：四级 ODE4 导数向量（相关状态）、更新前后连续状态、三个输出编码及其直接中间量（四元数范数、归一化分量、DCM、`Merge_j`、atan2 参数）。

**参考侧缺口（更正）**：此前"不改 SLX 即拿不到步内导数"过于悲观。R2022b normal 有**文档化**的执行事件 listener + RuntimeObject 机制，可在**不改模型方程/求解器/步长**的前提下，于块方法执行点读取块 I/O/状态（见下节）。剩余**未证**：逐 RK4 阶段粒度与导数值捕获需实证（须运行 MATLAB，本任务不做）;SLX 具体块全路径需解析。按 10-g6-remediation 合同，落地此类新入口仍须由主任务在分配的 tools/ 范围实现，**此处不代建**。

## 参考端可观测性（R2022b normal，文档化机制；不改模型/求解器/步长）

结论：R2022b normal 模式**可以**在不改模型方程/求解器/步长的前提下，通过**执行事件 listener + 块运行时对象**捕获连续状态与块方法执行点；能否拿到 **ODE4 四级导数**的确切数值仍**未证**（需实证，本任务不运行 MATLAB)。以下仅列文档化 API/事件/属性，不编造。

### 执行事件 listener(文档化）
- API:`h = add_exec_event_listener(blk, event, listener)`。
- **支持事件**:`'PreDerivatives'`/`'PostDerivatives'`、`'PreOutputs'`/`'PostOutputs'`、`'PreUpdate'`/`'PostUpdate'`（三个块方法各前/后）。
- 回调收到两个参数：触发块的 runtime object + 一个 `EventData`（含 runtime object 与事件名）。
- **注册时机**：只能在仿真**运行中**注册；官方建议在模型 `StartFcn` 回调里注册以捕获全部事件。
- **限制**：不能对 virtual 块注册。官方页面未按仿真模式（normal/accelerator）列限制；该机制是 normal（解释）模式的 MATLAB 回调，accelerator 会把块编译为原生代码，超出本参考（按 R1 合同跑 normal）范围。
- 文档：https://www.mathworks.com/help/simulink/slref/add_exec_event_listener.html

### 块运行时对象 RuntimeObject(文档化）
- API:`rto = get_param(blk,'RuntimeObject')`(`Simulink.RunTimeBlock`)。
- **暴露**：块 I/O 端口、参数、采样时间、状态、DWork;**只读**。
- **可用范围**：每个 **nonvirtual** 块在运行/暂停期间；停止后为空；被 block-reduction 优化移除的块没有。
- **同步**：仅在 Level-2 MATLAB S-function 或 **事件 listener 回调**内保证同步；命令行直接读可能因内存复用而读到旧值——需清除配置里 "Signal storage reuse"。
- 官方明确：该事件机制可收集"块在计算其输出或导数**之前/之后**的状态值"（如 `PostOutputs`/`PostDerivatives`)。
- 文档：https://www.mathworks.com/help/simulink/ug/accessing-block-data-during-simulation.html

### 对 ODE4 四级导数/连续状态的可行性
- **连续状态**：可观测。除上述 listener/RuntimeObject 外，normal 模式本身支持状态（`xout`/Dataset/SDI）在**每个主时间步**的记录——但那是逐主步，不是 RK4 级步内。
- **ODE4 四级导数（f0..f3)**：结构上 ode4(RK4）每个主步调用 4 次 Derivatives 方法，故对积分器块注册 `PreDerivatives`/`PostDerivatives` listener **原则上**每步触发 4 次，可读取各级状态与导数。**对 Integrator 块，输入端口即 d(state)/dt**：在 Derivatives 事件读其输入端口可得该级导数；在 Outputs 事件读其输出端口得该级状态。**未证点**:MathWorks 页面未按 RK4 阶段明确文档化事件粒度，"每步 4 次触发"是由求解器结构推断、非文档保证，须实证后方可依赖。
- **当前 SLX 块标识**(取自生成 cpp 注释；完整 SLX 块路径须打开 SLX 解析，本任务无 MATLAB 不打开）：速度积分器 `<S48>/ub,vb,wb`(`ubvbwb_CSTATE`)、角速率积分器 `<S48>/p,q,r`(`pqr_CSTATE`)、位置积分器 `<S48>/xe,ye,ze`(`xeyeze_CSTATE`)、四元数积分器 `<S51>/q0 q1 q2 q3`(`q0q1q2q3_CSTATE`)。

## 边界

未运行任何模型/MATLAB/native/ROS，未构建；未改生成源码/编译/SLX；未造抽象 trace 框架；现有诊断器与其测试冻结（本任务未触碰）。R1 仍 `numerical_failed`,G6 未通过；本文是定位 + 假设评估 + 观测点规格，不是根因证明。
