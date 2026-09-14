# #59 G6 36 态离线覆盖图（覆盖清单，非验收）

2026-09-14。本文与机器可读记录 `validation/g6-uncovered-state-map-20260914.json`（schema `wksim.59-g6-uncovered-state-map.v1`，kind `g6_uncovered_state_map`）成对交付，确定性生成器为 `tools/map_g6_uncovered_states.py`，离线自测为 `validation/test_map_g6_uncovered_states.py`。

本切片是新开发的**证据清单**：它把冻结 R1/C3G 目标模型（`nXc=36`）的扁平连续状态逐索引登记为"已覆盖/未覆盖"，并把每个索引挂到**仓库已跟踪**的块符号、行/文本证据与 mrdivide 残差/输出编码分类上。它没有重跑任何 trace、没有做数值验收、没有 G6/Full 结论：**#84、G6、Full 仍开放**，`r1_status` 仍为 `numerical_failed`，`g6_acceptance=false`、`physical_accuracy=false`、`issues_closed=false`、`budget_approved=false`。

生成器不依赖未跟踪的冻结 ZIP：ZIP 缺失处一律记为 **unresolved**，不猜、不补。

## 检出身份

| 项 | 值 |
| --- | --- |
| 工作类别 | new-development |
| cwd / 分支 | `C:\Users\PC\Documents\odid编译\wksim` / `main` |
| 稳定锚点 | `ee6eb88819cefe255f22e788c39a77c0bbab490e`（证据树与 `tracked_at_anchor` 标志均在此锚点读取，随后续提交冻结不变） |
| 锚点祖先门 | `git merge-base --is-ancestor ee6eb88819cefe255f22e788c39a77c0bbab490e HEAD` → exit 0（当前 HEAD 仅观测，不写入地图） |
| 证据漂移 | `git diff --name-only ee6eb888… HEAD -- <10 份证据>` → 空（锚点以来证据零改动） |
| 基线祖先 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0 |
| 独占文件 | 本文、`validation/g6-uncovered-state-map-20260914.json`、`validation/test_map_g6_uncovered_states.py`、`tools/map_g6_uncovered_states.py` |
| 未改 | 现有 trace/证据字节、比较器、R1 合同、参考 probe、builder/recorder、#83/#84 |

## 覆盖清单（36 / 13 / 23）

扁平索引域为 `0..35`，每索引恰好登记一次，升序、无重复、无空洞：

- **已覆盖 13 个：索引 6..18**（`q0q1q2q3_CSTATE` 6..9、`pqr_CSTATE` 10..12、`xeyeze_CSTATE` 13..15、`ubvbwb_CSTATE` 16..18）。这四个块的扁平索引端点由**已跟踪**的 `comparison-v2.json` 的 `target_indices` 给出，参考 probe 的 `state_integrator_paths` 对同名刚体积分器注册了 listener，两者一致，因此符号判定为 `resolved`。
- **未覆盖 23 个：索引 0..5 与 19..35**（`IntegratorSecondOrderLimited_CS` 0..5；19..35 的块归属见下方"符号冲突"，不作判定）。参考侧只对四个刚体积分器注册了 listener，故这些索引没有参考侧观测。

## 证据绑定规则

- 每个 pin 记录 `path`、`sha256`、`size`、`tracked_at_anchor`。`tracked_at_anchor` 由构建时的 `git ls-tree -r <锚点>` 实读得出，不假设：本切片之前已存在的 10 份证据与 4 个既有工具/探针在锚点树中均为 `true`；生成器与自测文件在锚点之后加入，如实记为 `false`，且该标志随锚点冻结、不随后续提交或任何临时索引内容改变，因此地图只依赖锚点树与磁盘字节。
- 行/文本证据按 `(文件, 起止行)` 绑定，并从**同一份已跟踪字节**摘取原文（例如残差链 `docs/coordination/g6-pqr-derivative-path-20260913.md:18`、求解调用 `:28`、未覆盖说明 `:36`、输出编码 `docs/coordination/g6-first-step-static-20260913.md:41-51`、观测点 `:69-74`、边界 `:113-115`）。自测同时校验工作树字节与锚点 blob 的逐行一致。
- 未跟踪但确有哈希的磁盘来源（生成 ERT C，`a35d7c8f…`）单列为 `untracked_provenance`，其字节**不参与**任何覆盖/分类判定。

## mrdivide 残差/输出编码（只登记有据者）

冻结首步 trace 与跟踪文档支持的最小分类只有求解入口的三个扁平索引：

| 索引 | 分类 | 依据 |
| --- | --- | --- |
| 10、11、12 | `mrdivide_residual_input`（残差向量 `rtb_IntegratorSecondOrderLimi_d[0..2]`） | `g6-pqr-derivative-path-20260913.md:16,18`（q 分量为 index 1）与 `:28`（`Product2 = rt_mrdivide_U1d1x3_U2d_9vOrDY9Z(residual, Selector2)`，行 5546–5547） |
| 11 | 同时登记 `mrdivide_output` 编码证据 | 跟踪 trace stage 2 `deriv[10..12] = 3c47b1ebce4a1e30 / bc56d4db33a987b9 / 36f8ccceed35d6fd`（p/q/r 三分量）；其中 index 11(q) 对跟踪 `comparison-v2` 参考 `bc56d4db33a987b8` 为 **1 ULP** |

3×3 惯性阵输入来自 `ModelParam_uavJ` 的 `Selector2`（行 5529–5540 的 major 步重算），**不是**扁平连续状态向量的一片，因此本图不为任何 `0..35` 索引登记"矩阵输入"分类。其余 33 个索引一律记为 `out_of_mrdivide_path`：跟踪证据没有把任何非 10/11/12 的扁平索引绑到 mrdivide 操作数或结果上，故不作物理语义或方程角色的发明。`entry_kind` 只区分 `mrdivide_numerator_vector` 与 `unmapped_state`/`mapped_reference_compared_state`，物理量名、单位、机体/地理语义仅作为**转述文本**（如参考侧状态名 `ub,vb,wb`）出现，不构成断言。

## 未解决项（需要冻结 ZIP 或新证据）

`unresolved` 逐条给出范围、所需输入与理由：

1. `archive_source_line_mapping`（全部 36 索引）：逐索引源行映射只有冻结归档成员 `e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp` 才可复现；仓库不跟踪厂商生成源码。
2. `authoritative_state_layout`（全部 36 索引）：`0..35 → 状态名` 布局取自未跟踪 builder 表，权威来源是归档成员 `Exp1_MinModelTemp.h`。
3. `transferfcn_motor_symbol_order`（索引 19..35）：跟踪的 builder 布局把 `IntegratorSecondOrderLimited__n` 放在 19..24、`TransferFcn4/1/2_CSTATE` 放在 25..27，而需求文本 `g6-pqr-derivative-path-20260913.md:36` 把 19–27 都划给 TransferFcn（`19-27(TransferFcn)、28-35(MotorNonlinearDynamic…)`）；两者在 **19..24 的块归属（边界）** 上不一致，记录为 `conflicted_requires_archive_input`，不猜。
4. `residual_component_binding_10`、`residual_component_binding_12`：这两个分量只被证明是 3 向量分子成员，逐分量源行表达式未被跟踪行证据绑定。
5. `unmapped_reference_states`（索引 0..5、19..35）：参考侧需扩展 probe 才能产出对照。
6. `untracked_generated_cpp_absent`（仅当磁盘上生成 C 缺失时出现）：暂用行锚点随之失效。

索引 10..12 的 `source_line_mapping` 记为 `mapped_via_untracked_generated_cpp`（行锚 5506–5528 残差、5529–5540 Selector2、5546–5547 求解调用，来源 SHA `a35d7c8f…`）；其余 33 个索引记为 `unresolved_requires_archive_input`。

## 非声明

- 无数值验收：没有重放、重算或新的比较。
- 物理精度不成立；状态名/单位只作转述。
- G6 与 R1 均未通过，`r1_status=numerical_failed`。
- 不关闭 #84、G6、Full 中任何一项。
- 不提议、不申请、不登记任何预算、批准、验收或合同冻结。
- 13 个已覆盖索引只是清单覆盖，不代表数值符合；其中索引 11 本身记录着 1 ULP 分歧。
- 不启动 MATLAB/native/ROS/DDS/SITL/飞行/UE/#83；不构建。
- 不修改任何既有 trace、合同、比较器或证据字节。

## 可复现

```powershell
python -B tools/map_g6_uncovered_states.py --repo-root . --out validation/g6-uncovered-state-map-20260914.json
python -B -m unittest validation.test_map_g6_uncovered_states
```

写入为独占创建（不覆盖既有文件）；`dumps()` 固定键序、缩进、ASCII 转义与结尾换行，自测重算并逐字节比对。自测覆盖 36/13/23 计数、索引唯一连续、锚点/祖先与证据漂移校验、负向篡改（域/重复/计数/覆盖/分类/符号冲突/pin/行绑定/输出编码 hex/未解决项/锚点字段/验收翻转），全程离线且不写真实 git 索引；仓库外临时 `GIT_INDEX_FILE`（exact4）下额外校验四个候选文件的暂存字节。
