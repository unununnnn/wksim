# OMP G6 首步两端对照独立审查（2026-09-13，只读）

对象：`validation/coordination/g6-target-first-step-20260913/`（comparison-v2 +
顶层/with-major trace + instrumentation-check）与参考 run-03。未执行模型/
MATLAB；未编译；未改源/数据；无嵌套/Git。

## 先更正我上一轮 review（omp-reference-first-step-review-20260913）两处

1. ~~"本次执行用的是 staged 副本"~~ 错误：本次新 probe **既不调用仓库也不调用
   staged 的 `run_numerical_conformance.py`**；input-checks 中该条 False 是
   `unused_changed_driver` 的如实记录，不是"使用了 staged 版本"。更正。
2. ~~"只能按内容区分"~~ 不完整：JSON 数组保存真实回调顺序，两个同时间
   0.0005 观测**可由序位严格区分**（内容差异另存为佐证）。更正。
3. CREATE_NEW 半成品边界属**有意保留证据**，后续用新目录；不再建议覆盖原路径。

## 对照原件核验

### 哈希与取代关系
- comparison-v2 `reference_sha256=99fc1ec8…` 与参考 run-03 文件 sha256sum
  逐字一致 ✓；`target_trace_sha256=34350997…` 与**顶层**
  `first-step-trace.jsonl` 实测逐字一致 ✓（`with-major/` 是带 major 的另一
  变体，哈希 `d55542d7…`，两者身份不同但 v2 引用对象明确无误）。
- v1 `comparison.json` 保留未删 ✓，v2 `supersedes` 说明如实：v1 用首个
  t=0.001 PostOutputs（第四级 minor 态），v2 改取最后一个。

### 阶段顺序与末态选择
目标 trace 行序：stage0(0)→stage1(0.0005)→stage2(0.0005)→stage3(0.001)→
**ode4_update(0.001)**。v2 末态取最后的 0.001 记录（update，RK4 积分终态），
不取第四级 minor ✓（阶段时间逐字节解码核验：0/0.0005/0.0005/0.001）。

### 最早差异与传播（2026-09-14 精度更正版；逐项取自 comparison-v2.json 重算）

跨块最早差异：**p,q,r 块 stage2 `derivatives[1]`**（0 基）1 ULP
（`bc56d4db33a987b8`→`…b9`）。−4.95e-18 是该差异 double 的**值量级**，
不是 ULP 差值——该处 1 ULP 的格点差值约 −7.7e-34。其后各差异逐项为：
q 块 stage3 `derivatives[2]` 1 ULP（`bba76121ffa77473`→`…74`）；q 块
stage3 `derivatives[3]` **64 ULP**（`36494aa6d36ff400`→
`36494aa6d36ff3c0`）；p,q,r 块 stage3 `cont_states[1]` 1 ULP
（`bbb76121ffa77473`→`…74`）；ub,vb,wb 块 stage3 `derivatives[0]`
1 ULP（`baa3bfd397a2d0d5`→`…d6`）。**不存在"后续传播均 1 ULP"的
普遍规律**。末态（最后 0.001 PostOutputs）差异：q 块 index3
**44 ULP**（`3581440763f7c6a8`→`3581440763f7c67c`）；ub,vb,wb 块
index0 1 ULP（`b9e48cb0f57301da`→`…db`）；p,q,r 与 xe,ye,ze 块末态
零差异。3.46e-47 及上述全部差异 double 均为**规格化（normal）
double**，非 subnormal；相关值在 1e-18~1e-47 量级属微小但规格化。
xe,ye,ze 块全程零差异。与主会话"stage2 pqr.derivative[1] 一 ULP
后传播"一致 ✓（传播链含 64/44 ULP 大格点距项）。

### major 与解析边界
instrumentation-check：major 240 值全核、对旧 C3G target.stdout
**零位失配**（legacy_target_bit_mismatches=[]、R1 符号零失配=[]）、
stage/update trace 未变 ✓；`parse_int=Decimal` 保全旧 JSON 的 `-0` 符号
（普通 json.loads 会丢）——R1 的 signed-zero 相等成立 ✓。

### 未覆盖边界
36 连续状态中 13 个已映射（q/p,r/位置/机体系速度四块），**23 个状态未覆盖**；
scope 自声"非全模型一致、非全部上游状态" ✓ 无越界声称。

## 结论（有界）

两端对照证据链成立：最早差异定位、ULP 传播链、末态选择、240 位 major
一致、-0 解析保全、原件哈希逐字一致均核验通过；**仅 13/36 状态已对照，
不构成全模型一致或 G6 通过**；stage2 pqr.derivative[1] 的 1 ULP 差异源因
未定（编译器/库差异候选未证）。本轮未发现需主会话修正的缺陷。
