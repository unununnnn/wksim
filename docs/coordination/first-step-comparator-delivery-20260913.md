# 首步对照比对器交付（2026-09-13）

把已实证的 G6 首步 13 状态对照做成可重复运行的纯 Python 比对器。
未改目标 recorder/MATLAB 文件；未跑模型/ROS/飞控/MATLAB/构建；无嵌套/Git。

## 交付物

| 文件 | 角色 |
|---|---|
| `tools/compare_first_step_trace.py` | 比对器（CLI：`--reference R.json --target T.jsonl --output O.json`） |
| `validation/test_compare_first_step_trace.py` | 纯测试（10 项全过） |
| `validation/coordination/first-step-comparator-20260913/replay.json` | 真实原件只读复跑结果 |

## 实际 schema 确认（先读后写）

- 参考 run-03：每块 18 事件 = 4 时点 × (Pre/PostOutputs/Pre/PostDerivatives) +
  末边界额外一对 Pre/PostOutputs（major 记录）；比对器按**数组序位**区分两个
  t=0.0005 观测，末态取**最后一个** t=0.001 PostOutputs。
- 目标 trace：start →（可选 major k=0）→ stage0..3（时间恰 0/.0005/.0005/.001）
  → update（t=0.001，pre/post 36 元）→（可选 major k=1）→ end；
  major 行可选但存在时须 0/1 夹住阶段。
- 映射（沿用 comparison-v2 target_indices）：q0..q3=[6,9]、p,q,r=[10,12]、
  xe,ye,ze=[13,15]、ub,vb,wb=[16,18]，恰 13/36。

## 真实原件复跑（replay.json）

`status=aligned`；最早差异精确重现 v2：**p,q,r 块 stage2 derivatives[1]**，
参考 `bc56d4db33a987b8` vs 目标 `bc56d4db33a987b9`，**1 ULP**；
块差异计数 q:2+final1、pqr:2+final0、xeze:0、ubvbwb:1+final1，与 v2 一致。

## 负例（全部不得出可信对齐）

缺 stage、错时间（0.002 替换 0.0005）、重复 stage 记录、非法 hex、非有限值、
参考缺块、合并同时间事件——逐一 rejected。

## 命令

```bash
python -B tools/compare_first_step_trace.py \
  --reference validation/coordination/g6-reference-probe-20260913/run-03/reference-first-step.json \
  --target validation/coordination/g6-target-first-step-20260913/first-step-trace.jsonl \
  --output <全新路径.json>
python -B -m unittest validation.test_compare_first_step_trace
```

## 限制（如实）

- 覆盖 13/36 状态；23 个未映射状态不在范围；不构成全模型一致或 G6/R1 通过。
- 输入各读一次、字节即哈希；输出独占创建，重名拒绝，历史不覆盖。
- 参考端为 UDD 观测值，目标端为 C 记录器 trace；比对器只核对数值与结构，
  不证明成因（stage2 pqr 1 ULP 的源因仍未定）。

## 主审 v1 修复轮（2026-09-13 同日）

main-review-v1.json 四失败已修：update 按唯一 kind 选择（major 行须恰为 k=0 在 stage 前、k=1 在 update 后）；dropped_events≠0 拒绝；update pre/post 全 36 项严格有限 hex+nXc；参考 payload 严格 dtype=double/shape/hex 对应 + 终端段精确身份（禁 substring 伪块）。补：缺 key/错类型结构化 rejected、跨符号 ulp=None+sign_flip（含 ±0）。真实 01 与 with-major 原件均 aligned 并重现 v2 最早差异；旧 replay/review 保留，新 replay-v2(-major)。json。测试 20/20。

## 求解操作数对照扩展（2026-09-13 同日）

支持实际 mrdivide trace + run-05 pqr_input_probe：严格校验 seq0..4、时间
0/.0005/.0005/.001/.001、major 1/0/0/0/1、3/9/3 有限 hex、行序模式；前四结果
须逐位等于对应 stage pqr 导数；参考须 traced/丢采 0/Inputs=*/ Matrix(*)/
2 输入 1 输出/double 1x3 3x3 1x3/order1..5。真实复跑：5 次分子/矩阵全相等、
仅 seq2 q 结果 1ULP。旧无求解 trace 仍按原合同通过；有 solve 行则两端证据
必须同时存在。负例：漏行/乱序/错映射/交换端口/错配置/单边证据全拒。
测试 28/28。

主会话验收补充：畸形容器/缺字段/输入端口数、bool序号/时间和默认关闭probe兼容已补齐。最终30测试及8子测试通过，对角候选实际比较仍零差异；最终源SHA与验证见validation/coordination/g6-diagonal-solve-candidate-20260913/main-verification-v2.json。aligned仅表示结构对齐。
