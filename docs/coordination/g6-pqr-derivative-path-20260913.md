# G6 / R1 首步 pqr(q) 导数上游只读定位

2026-09-13。负责人：Claude。承接目标端首步 trace（`g6-first-step-trace-20260913.md`）与参考端 run-03，对照 `validation/coordination/g6-target-first-step-20260913/comparison-v2.json`。本文件**只读定位**最早差异的上游精确算式/块路径，并给出**具体下一观测点**。不运行编译器/模型/MATLAB/ROS；不复制厂商源/二进制进仓库；不改 builder/recorder/参考 probe；不把 1 ULP 当作排除上游或 libm 的依据。

## 定位结论（事实，来自 comparison-v2.json)

13 个映射刚体状态中**最早差异**：**stage 2（第 3 次 derivatives 求值，t=0.0005)** 的 **p,q,r 导数 index 1(q/俯仰角速率导数）**:
- reference `bc56d4db33a987b8` = `-4.950785821689364e-18`
- target `bc56d4db33a987b9` = `-4.9507858216893644e-18`
- 差 **1 ULP**（量级 ~1e-18，近零）。

stage 0/1 的映射状态与导数**完全相同**;stage 2 的 p,q,r **连续状态相同**（仅导数输出不同）→ 分歧在**该次 q 导数计算内部**，不在状态传播。后续（stage 3）才传播到 q0q1q2q3（导数 idx2/3、末态 idx3）与 ubvbwb（导数 idx0、末态 idx0);xe,ye,ze 无差异。

## 精确算式（目标/生成 C 源运算顺序，非数学化简式）

q 导数 = `Exp1_MinModelTemp_B.Product2[1]`。链路（原始版 `a35d7c8f` 行号；与 R1 目标补丁版数值源表达式一致）:

**第一步：角动量残差**(`rtb_IntegratorSecondOrderLimi_d[1]`,5514–5521)。逐项（C 优先级/左结合；一元 `-` 先于二元 `*`):
```
t3 = ((-uavCCm[1]) * pqr[1]) * abs(pqr[1])      # 气动角阻尼；abs 精确不舍入
t4 = (-Fd[0]) * uavDearo                        # 气动力x * 力臂(常量 0.12)
s1 = t3 + t4 ; s2 = s1 + TT0gLR ; s3 = s2 + M1[1] ; s4 = s3 - Sum1_a[1]
g  = (Sum4_f[0]*pqr[2]) - (pqr[0]*Sum4_f[2])    # 陀螺/交叉项(Sum4_f 为 Product2 反馈)
residual[1] = s4 - g
```
各子项：`Fd`(=`-uavCd*|v|*v`，二次气动阻力，含 abs,4587–4896)、`M1`(电机力矩，4612–4616 线性于电机量）、`Sum1_a`(Selector1/dm_Value 相关，5478)、`TT0gLR`（该项点的力矩/陀螺中间量）、`Sum4_f`(=`Product2` 上次值 × ZeroOrderHold3_Gain,5550–5555 反馈）。

**第二步：惯性矩阵求解**(5546–5547)`Product2 = rt_mrdivide_U1d1x3_U2d_9vOrDY9Z(residual, Selector2)`。`Selector2` = `ModelParam_uavJ`(S53 Matrix Concatenation 取列 0–2,5367–5373 + 5534–5538)，即冻结**对角**惯性阵 `diag(0.0211, 0.0219, 0.0366)`；且只在 major 步重算（5529 `if rtmIsMajorTimeStep`)，步内四级不变。`rt_mrdivide`(3700–3751）是**手写部分主元高斯消元**（一串除法 + 乘减）。

## 块路径（目标侧）

模型根 → `6DOF1`(SubSystem SID `12216`)→ `Custom Variable Mass 6DOF (Quaternion)`(Reference SID `12216:1138` → `shared6dof/6DOF (Euler Angles)`，库 sha `7d12b7e6…`)。生成代码子系统：`Product2`=`<S52>/Product2`(mrdivide)，残差由 `<S279>/Integrator, Second-Order Limited` 输入路径（含 `<S88>` 叉乘、`<S2>/Sum1`、`<S3>/Add3`、`<S84>/Sum`)给出，状态来自 `<S48>/p,q,r` 积分器。S## → 库内命名子系统的精确映射需解析 `shared6dofsys.slx`/`shared6dof.slx` 的 system XML（离线已定位，见 `g6-reference-probe-20260913/block-map.json`)。

## stage 2 实际数据（target trace `first-step-trace.jsonl`)

t=0.0005。刚体映射态：q0q1q2q3=[1,0,0,0]、pqr=[1.28e-21,-2.48e-21,0]、xeyeze=[0,0,0]、ubvbwb=[0,0,-3.38e-6]。**注意**:index 0–5（二阶限幅）、19–27(TransferFcn)、28–35(MotorNonlinearDynamic，约 12.05）等**电机/推进相关状态非零**（电机在转），但这 23 个**不在参考端 13 个映射状态内**，现有对照未覆盖。

## 分析：区分源运算顺序与数学等价，不从 1 ULP 直接排除

- **数学等价式**:ω̇_q = M_net,y / J_yy。
- **源运算顺序（目标）**：残差按上式**特定左结合乘-加序**计算，再经**手写高斯消元**求解。参考侧 Simulink normal 的 `/` 走 **LAPACK**（另一套求解核），其表达式求值顺序也不同。
- **能确定**：惯性阵为冻结对角常量，两引擎逐位相同；目标侧 mrdivide 对对角 J 逐步可约成单个正确舍入除法 `residual[1]/0.0219`——**若**残差逐位相同，则目标输出确定。故目标侧解算本身在固定输入下是确定的。
- **不能据此排除**:① 参考侧 `/` 是否也约成同一单除法（LAPACK 路径不同，未观测）→ 求解差异**不排除**;② 残差上游子项可能含 libm(cos/sin 于 DCM/风、pow 等）或电机/气动上游态差异 → 上游**不排除**。1 ULP 本身不隔离这三者。

## 具体下一观测点（决定性，非泛泛）

在 stage 2(t=0.0005）的该次 derivatives() 求值内，对**双引擎**按全 binary64 捕获 mrdivide 输入与残差子项：

1. **`rtb_IntegratorSecondOrderLimi_d[0..2]`** —— mrdivide 分子（角动量残差），求解**之前**。这是把"残差计算"与"矩阵求解"分开的关键点。
2. **`Exp1_MinModelTemp_B.Selector2[0..8]`** —— 实际传入求解器的 3x3 惯性阵（确认就是冻结对角 `uavJ`)。
3. 残差子项：**`B.M1[1]`、`rtb_Sum1_a[1]`、`rtb_Fd[0]`、该点 `rtb_TT0gLR`、`rtb_Sum4_f[0..2]`**，及气动阻尼乘积 `-uavCCm[1]*pqr[1]*|pqr[1]|`。

判定树：
- 若 `residual[1]` 与 `Selector2` 双引擎逐位相同但 `Product2[1]` 不同 → 分歧在 **mrdivide 求解**(LAPACK `/` vs 手写高斯消元，即便对角 J)。
- 若 `residual[1]` 已不同 → 捕获/对照子项，定位是哪个力矩项（电机 M1 / 气动 Fd / 陀螺交叉 / 阻尼）分歧，并回溯其是否源自未映射的电机/气动上游态或某个 libm 调用。

目标侧接缝：在生成 cpp 第 **5546** 行 mrdivide 调用前插只读捕获（残差 + Selector2)，并在残差块（5506–5528）读子项；**属第二级（更深）插桩，由主会话实现，本任务不改 builder/recorder**。参考侧需对 6DOF 内部信号（M1/Fd 等）记录/日志——这些在 Aerospace 块内部，须实测其可观测性；并**补齐全 36 态映射**（现参考只捕 13 刚体态，电机/推进态未对照）。

## 边界

R1 仍 `numerical_failed`,G6 未通过；本文是只读定位 + 下一观测点规格，非根因证明，不把 1 ULP 当通过或当排除依据。目标生成源在 `/root/wksim-first-step-trace-20260913-01/`（未复制进仓库、未修改）。
