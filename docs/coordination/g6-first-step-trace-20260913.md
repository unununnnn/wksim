# G6 / R1 目标端首步 ODE4 trace 构建器（源码变换 + 命令生成，不编译不运行）

2026-09-13。负责人：Claude。承接首步静态调查与参考端 probe（参考端 run-03 已实证：每积分器每步 4 次 PostDerivatives，时间 0/.0005/.0005/.001，状态/导数均以 double hex 读到，240 个 major 输出与原 C3G f64 逐位相同）。本任务准备**目标端**首步 trace：只读插桩生成的 ODE4 求解器，只跑 k=0→1。

**边界**：只做源码变换 + 命令生成 + 纯行为测试；**不运行编译器/模型/MATLAB/ROS**；不把生成（厂商）源或二进制复制进仓库（插桩产物只写入独立构建暂存目录）；不把它当 G6 通过；不重排原乘加表达式。

## 交付物

- `tools/build_first_step_trace.py` — 构建器（instrument + 命令生成，拒覆盖，SHA 绑定，可逐字复原）。
- `tools/first_step_trace_recorder.cpp` — 目标端记录器驱动（捕获钩子定义 + 单步 main)。
- `validation/test_first_step_trace.py` — 纯 Python 测试（10 项，真实只读 cpp + 合成 fixture)。
- 本文档。

## 插桩设计（只读、逐字可复原）

`instrument()` 对冻结生成 cpp（原始版 SHA `a35d7c8f…`；与 R1 目标补丁版 `a3eba68e…` 的数值源表达式一致，仅差既有 `wk_capture_major` 钩子）插入**只读**捕获调用，位置在真实 ODE4 求解器 `rt_ertODEUpdateContinuousStates`(`MulticopterModelClass`,ERT 生成）内：

- 四个 `Exp1_MinModelTemp_derivatives()` 求值之后各插一个 stage 捕获（锚定唯一的 `rtsiSetdX(si, fN)` 上下文）:
  - stage0:`wk_trace_ode4_stage(0, t, y, f0, nXc)`（该级状态=y=t 时刻态，导数 f0);
  - stage1/2/3:`wk_trace_ode4_stage(N, rtsiGetT(si), x, fN, nXc)`（该级中间态 x，导数 fN)。
- 末次加权更新循环之后插一个 update 捕获：`wk_trace_ode4_update(rtsiGetT(si), y, x, nXc)`（更新前 y、更新后 x)。

捕获只读局部变量，**不改变/不重排任何原表达式**;`instrument()` 校验去掉全部插入字节后与原源逐字一致。这与参考端 run-03 实测的 4 级粒度（0/.0005/.0005/.001）逐级对应，可逐点对照。

## 连续状态扁平布局（nXc=36，取自生成头 `X_Exp1_MinModelTemp_T`，非猜测）

`[0..5]` IntegratorSecondOrderLimited_CS;`[6..9]` **q0q1q2q3**（四元数）;`[10..12]` **pqr**（角速率）;`[13..15]` **xeyeze**(NED 位置）;`[16..18]` **ubvbwb**（机体速度）;`[19..24]` IntegratorSecondOrderLimited__n;`[25..27]` TransferFcn4/1/2;`[28..35]` MotorNonlinearDynamic8..1(`.x`)。

首分歧相关：`Vehicle60[3]`(VelE 北向）← `ubvbwb`[16..18];`Vehicle60[11]`(Euler 偏航）与 `[15]`（四元数 qz)← `q0q1q2q3`[6..9]。

## 记录器输出（全 binary64 精确 hex)

每条记录一个 JSON 行：`ode4_stage`{stage, time_s, nXc, state_hex[36], deriv_hex[36]}、`ode4_update`{time_s, nXc, pre_hex[36], post_hex[36]}；外加 start（含输入绑定与 k=0 施加输入 hex）与 end。hex 为 binary64 位模式精确表示。

## 精确命令（主会话执行；构建/运行在 WSL Ubuntu-22.04,g++ 同 R1 目标 flags)

```bash
# 1) 准备（源码变换+命令生成，不编译）：写出插桩源/记录器/build-command.json 到新目录
python3 tools/build_first_step_trace.py \
  --input "/mnt/c/Users/PC/Documents/odid编译/wksim/validation/numerical-conformance-gxxh6xhr/C3G/input.csv" \
  --out-dir /root/wksim-first-step-trace-<fresh>

# 2) 编译（主会话；argv 也见 build-command.json）
g++ -std=c++17 -O2 -fno-fast-math -Wl,--no-undefined -I <out> \
  <out>/Exp1_MinModelTemp.cpp <out>/first_step_trace_recorder.cpp -o <out>/first_step_trace_recorder

# 3) 只跑 k0→1
<out>/first_step_trace_recorder --record <out>/input.csv --output <out>/first-step-trace.jsonl
```

- **输入源 SHA256(C3G `input.csv`)**:`721c88bf3f621923b98bb43251c50bae7817106a984be64345c0528d34d3adcf`。
- 身份绑定：`build-command.json` 记录 archive/原始 cpp/插桩 cpp/记录器/输入/构建器 SHA256。

## 仍需真实编译/运行验证的边界（本任务不做）

1. 插桩源能否编译（extern 声明 + 钩子的 C++ 语法、与记录器定义的链接匹配）——需真实 g++。
2. 记录器 hex/JSON 输出正确性与单步运行行为——需真实运行。
3. 各级时间是否为 0/.0005/.0005/.001、f0..f3/状态与参考端 run-03 逐点对照——需真实运行 + 对照。
4. nXc=36 与扁平布局在实际求解器中的一致性（已在头文件核实，编译时确认）。
5. 探针式 extern 钩子在 `-O2` 下不被优化掉（捕获写全局缓冲，有副作用，预期保留；以真实编译产物为准）。

## 边界

R1 仍 `numerical_failed`,G6 未通过；本包是目标端观测入口准备，不是数值验收，不改冻结契约/预算/门/既有证据。参考端 `.m` 与 mapper 已由主会话修订，本任务未触碰。
