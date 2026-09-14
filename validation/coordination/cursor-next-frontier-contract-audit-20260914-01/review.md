# 下一前沿合同测试审查（2026-09-14-01）

工作类别：review/triage（只读候选，不改候选、不改现有文件）。  
cwd / 分支 / HEAD：`C:/Users/PC/Documents/odid编译/wksim`，`main`，`5370b2324672c9036d41239cb93e21fc5eb42897`。  
架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`：`git merge-base --is-ancestor` 退出码 0。  
module：下一前沿合同测试。独占写入仅本目录三文件。  
未执行：native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83。  
未做：add / commit / push / 关票 / owner approval。

已读：根 `CONTEXT-MAP.md`、`wksim/CONTEXT.md`、父仓 ADR-0002 / ADR-0004（已被 ADR-0016 取代）/ ADR-0008（不自动约束本迁移）、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`docs/coordination/short-cycle-goal.md`，以及候选引用的 `docs/plan` 与真实 parser/runtime。  
开放票只查询一次：`gh issue list --repo unununnnn/wksim --state open --limit 80`。  
接口不能选择或核验 `gpt-5.6-luna`，本审查在主代理完成，未替换子代理设置。

**总体 overall = FAIL。** delivery 候选存在 P2；两候选均不得计为 #20 / #29 / #33 / #46 / #84 / Full 通过。

## 候选身份

| 候选 | 工作树 | 期望 SHA256 | 实测 SHA256 |
| --- | --- | --- | --- |
| `validation/test_delivery_entry_contract.py` | untracked | `682f3b20b29a1312becad6ec519fdb8434ff09270af118e55c23e3986cdcc808` | 一致 |
| `validation/test_scene_frontier_contract.py` | untracked | `3f593d8f3bdb3c34db5c7b51014c305fd9596a73ce803a1c187e3d509b6c3de2` | 一致 |

## 票映射（不得猜测）

一次开放票列表含 `#84/#46/#33/#29/#26/#20/#9` 等，**不含 #102**。

| 候选 | 最相关开放票 | 不映射 |
| --- | --- | --- |
| delivery | **#84**「提升同一已证实组合并验证正式入口」；次要 **#33**（mixed/PV 门与 mixed pin）、**#26**（`audit_26` CLI 子串） | #20（暂停/单步/冷重置）、#46（固定输入重跑）、#29；#83 不在开放列表且本审查禁止 |
| scene | **#29**「坡面与障碍场景的物理反馈」 | #20/#33/#46/#84；候选正文写 #102，但当前开放票列表无 #102，故不把 #102 当作现票 |

## 实测 unittest

本机 Linux sibling **可达**：`\\wsl$\Ubuntu-22.04\root\wksim-release-acceptance-fe3`（历史对照 `fe3`，不是新架构验收候选）。因此 **0 skip**，没有出现“sibling 缺失 → skipTest”路径。

```text
python -B -m unittest validation.test_delivery_entry_contract
Ran 9 tests in 0.022s  OK
passed=9 failed=0 skipped=0

python -B -m unittest validation.test_scene_frontier_contract
Ran 6 tests in 0.002s  OK
passed=6 failed=0 skipped=0
```

`fe3` runner SHA `1c600d7f018376f5…` ≠ 当前 main `tools/run_joint_flight.py` SHA `c8577093a62e4993…`。字符串门在两边都绿，不能证明正式入口同一文件。

独立复算（测试本身不做）三份外部清单字节：

| 路径 | 字节 | SHA256 与 VERIFIED_* |
| --- | --- | --- |
| `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json` | 914 | 匹配 `1e6250ef…` |
| `/root/wksim-joint-control-c2IXOr/build.json` | 12091 | 匹配 `6fe8c0b3…` |
| `/root/wksim-ros2-Rzj3Pf/message-build.json` | 7149 | 匹配 `29969da0…` |

这只说明**本机此刻**文件碰巧等于短周期冻结组合；测试只 `is_file()`，绿不能当发布证据。

## 逐候选

### 1. `test_delivery_entry_contract.py` — verdict **needs-fix**（P2×4）

对照真实源，字符串目前都还在：`run_joint_flight.py:1183-1195` 的 flag / name 循环、`ap_mixed_candidate.py:108-116` 的 incomplete/exact-manifest 拒绝、`joint_control_candidate.py:148-149` 与 `joint_message_candidate.py:109-110` 的 `fullmatch` + `SHA256 differs`、`audit_pv_trajectory.py:877-879`、`audit_26_closure_readiness.py:1739-1740`、`joint.py:54`、`joint_rate_probe.py:14,36`、`run_joint_flight.py:423-428,473`。  
**绿只证明子串还在，不证明 parser/admit 失败语义。**

P2：

1. **只断言字符串（假阳性）** — L59-84、L90-105、L128-149。不调用 `parse_args` / `admit()` / `check()`。`fullmatch` 可命中目录名校验。rate-probe 报文字面仍是 `candidate/PV`（L142，对 `run_joint_flight.py:425`），真实允许集已是 `PV_PROFILE, MIXED_PROFILE`。
2. **外部路径 + 固定哈希当发布证据** — L31-33、L107-122。`FINAL_*` 只比 LINUX 源码字面；清单只 `is_file()`。本机独立哈希碰巧匹配，换字节仍绿。
3. **Linux sibling 缺失 fail-open** — L60-62、L91-93 用 `continue`，不 `skipTest`。只有 pin 测试（L108-109）会 skip。本机 sibling 在，故 0 skip；缺 sibling 时 8/9 仍可绿。
4. **过期执行身份** — `_linux_root()` 钉历史 `fe3`。接续合同写明该对照不得把 PASS 转给新候选。main/fe3 runner 已漂移（`c8577093…` / `1c600d7f…`），测试仍把两边当同一入口合同。

P3：未覆盖 bool/NaN/空对象/重复键；未比 main 的 `FINAL_*`（今日碰巧与 LINUX 相同）；`omp-delivery-gates-20260912.md` 写的 `--output` 覆盖缺口已过期——`audit_pv_trajectory.py:881-888` 现拒绝覆盖既有输出，本测试不钉该语义。

不纳入下一批。

### 2. `test_scene_frontier_contract.py` — verdict **ready**（无 P1/P2）

真实接口一致：`planner_scene_binding.py:792-809` 对非规范清单 raise `PlannerSceneIdentityError`；probe 走通用 mismatch，不是具名 probe 门，但 `4889e2ea…` / `static-plane-box-v1-real-tick0` 会被拒绝。`TerrainFeedback.__init__`（L45-48）要求观察器键恰好为 `{arducopter,px4}`。`query_terrain` 把运行 epoch 传入 `observe_step`；`contact_observer.py:132-133` 在 epoch 不等时 `foreign_epoch` 冻结且不写 `last_step`。`[0.0]*120` 在平坦夹具上得到 `[0.0]*15`，`manifest()["scene_hash"]` 仍是 `FROZEN_SCENE_SHA256`（`60ae5097…`）。清单加载拒绝重复 JSON 键。身份与已跟踪的 `29-terrain-evidence-manifest.json`、`EGO_SINGLE_BOX_BINDING`、`FROZEN_SCENE_SHA256` 一致。

与已纳入测试的关系：`test_display_scene_binding.py` 拒绝 probe **作为 display**；`test_planner_scene_binding.py` 拒绝 **legacy** 夹具。本候选的 planner-probe 替换与 `observers=` 注入在 `validation/*.py` 中仍是唯一覆盖。不是 duplicate。

P3：前两个身份测试与 display 合同重叠；双键替换用父类 `PlannerSceneBindingError`（子类 IdentityError 也会通过）；只断言异常含 `"froze"`；未铺 bool/NaN/空对象矩阵（实现侧 `query_terrain` / `_epoch` 已拒）；2026-09-12 的“全仓零覆盖”说法已过期。

6/6 绿只证明这四条离线接缝，不是 #29 AC，也不是 UE/FC/SITL/ROS 闭环。

## 下一张最小卡（不要在本审查改）

- 工作类别：new-development（首次纳入已有未跟踪测试；不改 runtime）。
- 独占文件：`validation/test_scene_frontier_contract.py`（仅 `git add` 该文件；保持 SHA `3f593d8f…`）。
- 只读依赖：`planner_scene_binding.py`、`terrain_feedback.py`、`contact_observer.py`、`docs/plan/29-terrain-evidence-manifest.json`、`Simulator/wksim_runtime/static-scene-v1.json`。
- 测试：`python -B -m unittest validation.test_scene_frontier_contract`。
- 不要纳入 / 不要改：`validation/test_delivery_entry_contract.py` 及任何 tools/runtime。
- 不能宣称：#20/#29/#33/#46/#84/#26/#102、Full、G6、正式 MIXED/入口、UE 同置、坡度/接触力、显示断开。
- delivery 若另开修复卡：必须调用真实 parser/`admit`/`check`、对清单做 SHA256、sibling 缺失用 `skipTest`、停止把 `fe3` 当当前正式入口；仍不能宣称 #84。

## 回执文件

本目录恰好三个文件：`review.md`、`review.json`、`SHA256SUMS`（只覆盖前两个，路径相对本目录）。
