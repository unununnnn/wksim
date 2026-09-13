# G3 exact-clearance repair3 独立敌意复审

2026-09-14。只读复审未入库、未接线的第三轮修复候选。**未改候选。** 本审查写入仅在
`validation/coordination/cursor-g3-exact-postrepair3-review-20260914-01/**`。

**裁决：PASS。** 无 P1 / P2。三则 P3（一则公开不可达的防御门，两则文档措辞）。

四道派遣门均成立：

* 所有采样前失败路径：`admitted=false`、`evaluations=0`、`spans` 空、四全局界空、无 binding，且 **`spline.position.evaluate` 一次都未调用**；
* 无伪造 per-span 记录；
* 探针与正式套件未见不安全 admit；
* 候选合同未把未验证性质写成已证明。`57.6 m/s` 散文相对真导数上确界 `60.0 m/s` 记为 P3。

这不是晋升，不关闭 #102 / #39 / G3 / Full，也不涉及动力学、跟踪、力、地形、规划器、套接字或飞行安全。

## 派发

```text
工作类别：独立离线敌意复审（非新架构验收、非历史对照、非晋升）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、102-exact-clearance-candidate.md、
      候选源码与测试、repair3 收据、DeepSeek 未完成 postrepair3 产物（仅作对照，不当证据）
module / interface：只读评估 ego_exact_clearance.certify_exact_clearance
                   与 derivative_speed_bounds
独占写入：validation/coordination/cursor-g3-exact-postrepair3-review-20260914-01/**
依赖（只读）：ego_evaluator.py、planner_scene_binding.py
验证：probe/hostile_probe.py（721 项），以及候选 pytest/unittest
      与四文件套件，Windows 与 Ubuntu-22.04
范围外：native / model / MATLAB / ROS / DDS / SITL / FC / UE /
        build / flight / #83、晋升、Git/GitHub 变更、无关脏文件
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审查在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 身份与冻结哈希

开工冻结并在全部运行后回检，字节未变：

| 路径 | SHA-256 |
| --- | --- |
| `Simulator/wksim_planning/ego_exact_clearance.py` | `8b1d2dd8c097447d32d5d4f22b5827f8712ac84c9de0e963983d24e73efd46ea` |
| `validation/test_ego_exact_clearance.py` | `d3541280c8d03127b047a2c7d67ce5581b6ff0c4dd0378b96209550ff762ae17` |
| `docs/plan/102-exact-clearance-candidate.md` | `7b1e9bfa71db69e1b12dce71cb9ac5a597b548eaf7b0ec1cda80eed63486abb7` |

与 repair3 收据一致。G3 封印未变：`ego_scene_admission.py` `f88fa9c6…`，`planner_transport_pump.py` `c9b541b4…`。工作树上原先已有的两处已跟踪改动（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`）未触碰。无 commit / stage / reset / clean。

## 如何证伪（不复用既有 PASS）

`deepseek-g3-exact-postrepair2-review-20260914-02` 曾在哈希 `f4d9535e…` 上报「相邻浮点 0 次求值、无伪造括号」；repair3 收据在同一哈希上复现 `evaluations=5`、五条 `SpanBracket`、`bounds_scope=partial_evaluated_spans`。该推理不作证据。

DeepSeek 的 `…postrepair3-review-20260914-01` 已有较完整草稿，但缺本派遣要求的 `review.json` / `SHA256SUMS`，且其计数不当成本次证据。本审查用独立探针 `probe/hostile_probe.py` 重做：

* 把 `spline.position` 换成代理：一次 **hard-fail**（第一次 `evaluate` 即抛），一次 **计数**；
* 独立 `fractions.Fraction` de Boor、点到 AABB 距离、导数控制点范数；
* 静态 AST：无 `peak_prepared_speed`、无 `> 1e6`、无 “charge one evaluation” / “inspectable evidence”，无大幅值浮点比较阈值；import 仅 `__future__` / `dataclasses` / `math` / `numbers` / `typing` / `Simulator`。

## 主门 — 4×4 采样前失败矩阵

起点 `1 / 1000 / 1e6 / 1e15`，间距 `1/2/4/8` ulp。中点可表示性用本探针自己的 `u_start + 0.5*(u_end-u_start)` 判定，不调用模块私有助手。

| start | spacing | 预测不可表示跨度 | hard-fail | 计数调用 | status | reason |
| --- | --- | --- | --- | --- | --- | --- |
| 全部 4 个起点 | 1 ulp | `[3,4,5,6,7]` | 未抛 | 0 | rejected | `certificate_structure_invalid` |
| 全部 4 个起点 | 2/4/8 ulp | `[]` | 未抛 | 0 | indeterminate | `parameter_roundoff_exceeds_envelope` |

16 例全部：`admitted=False`，`evaluations=nodes=evaluated_span_count=0`，`spans=()`，`bounds_scope=None`，四全局界 `null`，`binding_object=binding_span_index=max_speed_bound=None`，无 `conclusive` 跨度，**0 次 instrumented `evaluate`**。4 rejected / 12 indeterminate。关闭上一轮漏报。

## F1 — 相邻浮点 + 精确有理批评

16 例各自在某活动跨度上存在精确 de Boor 点落在障碍 AABB 内部（`exact_distance_sq == 0`），跨度 3 的有理扫描净间隙 ≤ `-0.35 m`。全部未 admit，全部 0 次 `evaluate`。

## F2 — 平移与包络

Family-13，本探针按 `0.5 * V * ulp(max|u|)` 计费：

| δ (s) | charge (m) | status | evaluations / calls |
| --- | --- | --- | --- |
| 0 / 1 / 4 / 1e3 / 1e6 | ≤ `2.46e-10` | admitted | 4646 / 4646 |
| 1e7 / 1e12 / 1e15 | `3.93e-9` … `0.272` | indeterminate / roundoff | 0 / 0 |

包络外三例 hard-fail 代理未触发，空 fail-closed 形。普通 `+1/+4/+10 s` 保持 verdict 与净界（9 位）。`+1 s` corner-dip 仍为 `rejected` / `obstacle_clearance_below_required`。

## F3 — 工作帽与 bounds_scope

4 条几何 × `max_nodes_per_span ∈ {1,2,7,64,65536}` × `max_evaluations ∈ {1,2,5,10,50,1000,2097152}`（140 张证书）：

* 74 张 `partial_evaluated_spans`：四全局界均为 `null`，且 `0 < len(spans) < span_count`；
* 66 张 `continuous_curve`：四全局界均在，且 `evaluated_span_count == span_count == len(spans)`；
* 0 张 `null` scope 却带 span 证据；
* `admitted` 与 `status=="admitted"` 逐张一致；无证书超过任一帽。

## F4 — 溢出与私有大整数

`±1e308` × 间隔 `1e-8/1e-12/1e-16`：6 例 `rejected` / `certificate_structure_invalid`，0 求值，hard-fail 未触发，无异常。私有 knot / 控制点 `10**400`：同样空 fail-closed，无 `OverflowError`。证书可 `json.dumps(..., allow_nan=False)`。

## n 划分可达性、速度界、阈值缺席

* **n-partition（P3-N1）。** 66 个公开配置（family 9/13/33 × 平移 × 帽/公差，外加直线）无一例由 n-partition 门裁决。塌缩步长需求与 `t > 4g` 的可接纳公差不相容：包络上限 `2g = 2e-9 m`，默认公差下塌缩收费 `4(t-2g) = 3.999992e-3 m`。把 `_interior_partition` 打成恒 `None`（含 preview 再检查）仍得到空 fail-closed，0 次 `evaluate`。`1e15`/1-ulp 同时触发中点与包络时报告 `certificate_structure_invalid`（中点优先）。
* **速度界。** 独立复算 `Q_i = p (P_{i+1}-P_i)/(U_{i+p+1}-U_{i+1})` 与模块超集窗；7 条几何、4560 个有理内点，**0 次越界**，最坏真值/界比 `1.00`。
* **无探针专用阈值。** 源码 AST 与文本均无 `peak_prepared_speed`、`> 1e6`、charge-one-evaluation。密封门与泵不引用本模块。每张证书 `candidate_only=True`，`evidence_kind=lipschitz_bracket_certified`。

## 57.6 m/s 散文对 60.0 m/s 上确界（P3-DOC-576）

`alternating_witness()` 是磁盘上唯一给出 `V = 120 m/s`、200 跨度、60200 次求值的夹具。它 **不安全**（`rejected` / `obstacle_clearance_below_required`，真净间隙约 `0.20 m`）。合同却把它写成 “safe curve” 且 “dense maximum 57.6 m/s (ratio 2.08)”。

导数是交替控制点 `±120` 的二次 B 样条。均匀跨度中点基为 `1/8, 6/8, 1/8`：

`0.125·120 + 0.75·(-120) + 0.125·120 = -60`

故 `||γ'||` 上确界是 `60.0 m/s`，真比值 `2.00`。本探针 mid-span 有理值 `60.00000000000118`，跨度内 200 分点密采样 `59.99851488824652`。网格扫描：

| 点数 | max |γ'_x| (m/s) |
| --- | --- |
| 401 / 2001 / 40001 | `60.00000000000118` |
| 1000 | `59.99993987981972` |
| **1001** | **`57.60000000000137`** |
| 5000 | `59.99999759903967` |

`57.6` 只在 `u = 0, 0.001, …, 1.0`（1001 点，步长为交替周期 `0.01 s` 的十分之一、永不落在跨度中点）上精确复现。偏差方向偏保守（把内部界说得更松），不改任何证书字段。

## 文档 R2 措辞（P3-DOC-R2）

合同写 “an unclosed certificate is indeterminate rather than admitted”。`admitted=False` 成立；status 不总是 indeterminate：穿障直线 `max_nodes_per_span=1` → `rejected` / `obstacle_clearance_below_required`，`tolerance_met=False`。模块 docstring 没有重复这句过窄的 status 说法。

## 发现（P1–P3）

| id | 级 | 标题 |
| --- | --- | --- |
| — | P1 | **无** |
| — | P2 | **无** |
| P3-N1 | P3 | n-partition 采样前门已实现且 fail-closed，但不是公开 API 的可演示裁决路径 |
| P3-DOC-576 | P3 | 合同把 `57.6 m/s` / 比值 `2.08` 写成密采样极大，且把不安全夹具写成 safe |
| P3-DOC-R2 | P3 | “未闭合 ⇒ indeterminate” 对 status 过窄；未闭合仍可为 conclusive rejected |

无发现构成可靠性逃逸或语义超售。

## 本审查亲自执行的运行

Linux 使用发行版 **Ubuntu 22.04.5 LTS**、Python 3.10.12，经 `/mnt/c` 读同一钉扎工作树（候选本身未入库，不能改用无候选的干净克隆）。只向本审查目录写文件。

| 平台 | 命令 | 结果 |
| --- | --- | --- |
| Windows，Python 3.13.11 | `python probe/hostile_probe.py --label windows` | **721 / 721 PASS** |
| Ubuntu-22.04，Python 3.10.12 | `python3 probe/hostile_probe.py --label linux-ubuntu-22.04` | **721 / 721 PASS** |
| Windows | `python -m pytest validation/test_ego_exact_clearance.py -q` | **53 passed, 162 subtests** |
| Windows | `python -m unittest validation.test_ego_exact_clearance` | **53 tests OK** |
| Windows | 四文件 pytest（exact + admission + pump + receiver） | **179 passed, 216 subtests** |
| Ubuntu-22.04 | 候选 pytest | **53 passed, 162 subtests** |
| Ubuntu-22.04 | 候选 unittest | **53 tests OK** |
| Ubuntu-22.04 | 四文件 pytest | **179 passed, 216 subtests** |

跨平台：检查名序列相同，状态序列相同，主门 16 行、F2 收费与 57.6 网格峰值一致。

## 本审查未消除的残余风险

* 界是声明公差下的 Lipschitz 括号，不是 exact-real 证明；`FLOAT_GUARD_M` 是声明包络。
* 障碍在全程是承诺的竖直 AABB；车辆范围为球。未重推导这两条假设。
* 有理批评只作证伪，不是证书。
* n-partition 门的公开不可达性意味着其 fail-closed 只能靠故障注入演示。
* 无 map→planner→飞行证据。

## 非声称

不关闭 #102 / #39 / G3 / Full，不批准把该谓词升为默认严格门。无动力学、跟踪误差、控制器滞后、力、冲量、地形、规划器、套接字、发布或飞行安全声称。未做 native / model / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83。无 Git 或 GitHub 变更。
