# #29 离线场景身份/时效前沿合同 — 独立复核

工作类别：review。  
cwd / 分支 / HEAD：`C:/Users/PC/Documents/odid编译/wksim`，`main`，`5370b2324672c9036d41239cb93e21fc5eb42897`。  
架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`：`git merge-base --is-ancestor` 退出码 **0**。  
module：#29 offline scene identity/timeliness frontier。  
独占写入：仅本目录 `review.md` / `review.json` / `SHA256SUMS`。  
候选与实现：未改。未 add / commit / push / 关票 / owner approval。  
未执行：native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83。

已读：根 `CONTEXT-MAP.md`、`wksim/CONTEXT.md`、父仓 ADR-0002 / ADR-0004（已被 ADR-0016 取代）/ ADR-0008 / ADR-0009（不自动约束本迁移）、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`docs/coordination/short-cycle-goal.md`、`docs/coordination/ds-scene-frontier-20260912.md`、`docs/plan/9-abi-environment-accepted.md`、`docs/plan/29-102-scene-binding-contract.md`、`docs/plan/29-terrain-evidence-manifest.json`，以及真实导入 `contact_observer.py` / `planner_scene_binding.py` / `terrain_feedback.py`。历史综合审查：`validation/coordination/cursor-next-frontier-contract-audit-20260914-01/`（只读，未改写）。  
GitHub 实读：`#29` OPEN（五条 AC 未勾）；`#9` OPEN；子票 `#79/#80/#81` 已 CLOSED，不等于本切片解锁父票。

接口不能选择或核验 `gpt-5.6-luna`，本审查在主代理完成，未替换子代理设置。

## 总评

**PASS**（0 P1 / 0 P2）。该单文件可作为离线回归纳入下一批。  
**不是** #29 AC、物理消费、真实 UE、Full 或 Goal 通过。`#9` 仍 OPEN；`#29/#79/#80/#81` 不因本 PASS 解锁。

| 项 | 值 |
| --- | --- |
| 候选 | `validation/test_scene_frontier_contract.py`（工作树未跟踪） |
| 期望 SHA256 | `3f593d8f3bdb3c34db5c7b51014c305fd9596a73ce803a1c187e3d509b6c3de2` |
| 实测 SHA256 | 一致 |
| 纳入下一批 | 是（仅此单文件；保持上述 SHA） |

## 检查 1 — 官方 unittest

```text
python -B -m unittest validation.test_scene_frontier_contract -v
Ran 6 tests in 0.002s
OK
ran=6 passed=6 failed=0 skipped=0
```

| 测试 | 结果 |
| --- | --- |
| `test_three_identity_layers_are_pairwise_distinct` | ok |
| `test_runtime_terrain_seam_binds_the_frozen_fixture_not_the_probe` | ok |
| `test_probe_identity_is_never_accepted_as_planner_identity` | ok |
| `test_foreign_epoch_observer_fails_closed_at_the_real_seam` | ok |
| `test_observer_set_must_exactly_match_supported_stacks` | ok |
| `test_matched_epoch_injection_still_binds_the_frozen_fixture` | ok |

## 检查 2 — 真实接口，不是只搜字符串

**PASS。** `sys.settrace` 在官方 6 项运行期间记到：

| 真实可调用 | 次数 |
| --- | --- |
| `planner_scene_binding.py:validate_manifest` | 4 |
| `terrain_feedback.py:query_terrain` | 3 |
| `terrain_feedback.py:__init__` | 4 |
| `contact_observer.py:__init__` | 6 |
| `contact_observer.py:observe_step` | 2 |
| `test_scene_frontier_contract.py:_load_manifest` | 3 |

`validate_manifest` 覆盖单键 probe 替换、双键替换与合法清单。`query_terrain` 覆盖外来 epoch 首次查询、冻结后再次查询、以及匹配 epoch 的合法注入。第二次 `query_terrain` 在 `TerrainFeedback` 的 `frozen` 短路处失败，不再进入 `observe_step`（故 3 次 query / 2 次 observe）。候选导入并实例化 `ContactObserver` / `TerrainFeedback` / `EGO_SINGLE_BOX_BINDING`，不是对源文件做 `assertIn` 子串门。

## 检查 3 — 三层身份与 fail-closed

**PASS。** 当前源/清单机械核对：

| 层 | scene_id | scene hash |
| --- | --- | --- |
| visual / frozen fixture | `static-plane-box-v1` | `60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514` |
| real / generated probe | `static-plane-box-v1-real-tick0` | `4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300` |
| planner ego binding | `ego-single-box-v1` | `40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba` |

三者 id 与 hash 均 pairwise distinct。visual hash 等于 `FROZEN_SCENE_SHA256` / `LEGACY_SCENE_HASH` / 磁盘 `static-scene-v1.json` / `StaticScene` 按盒心 `[2,0,0.5]` 重算。probe hash 等于清单 `real_terrain_scene`，且 `StaticScene` 按盒心 `[0,0,0.5]` 重算通过。planner hash 等于 `EXPECTED_SCENE_HASH` 与绑定运行时计算值。重复 JSON 键、外来 epoch、过期/未来窗口、错误 scene/stack/observer 语义均 fail closed；合法双栈边界仍通过（见检查 4）。

## 检查 4 — 独立 TEMP/内存矩阵（≥12）

系统 TEMP：`C:\Users\PC\AppData\Local\Temp\wksim-scene-frontier-ir-*`。脚本与结果只写该目录，复核后已删除，无残留。仓库内未写临时脚本。

33 条独立构造全部按预期（不含 trace 元项）：

| 构造 | 结果 |
| --- | --- |
| tick=`True`/`False` | `ContactError: contact_invalid` |
| tick=`-1` | 同上 |
| 先 2 后 1（倒序） | `RuntimeError` / `stale_feedback` |
| 信封 current=10 / valid=15 | `future_feedback` 冻结 |
| 信封 current=16 / valid=15 | `stale_feedback` 冻结 |
| epoch=`""` / `{}` / `None` | `ContactError: contact_invalid` |
| 状态含 `NaN` / `±Infinity` / `True` | `ValueError` |
| planner `load_manifest` 重复键 | `duplicate JSON key` |
| 候选 `object_pairs_hook` 重复键 | `ValueError` |
| 注入 foreign epoch | `RuntimeError` / `foreign_epoch`；另一栈未冻、`last_step is None` |
| `expected_sha256=probe` 加载夹具 | `scene_hash_mismatch` |
| planner 换 probe id/hash 或 `0*64` | `PlannerSceneIdentityError` |
| 未知 stack / 缺栈 / 多栈 | `ValueError` |
| 空对象/`None` 清单 | Identity/BindingError |
| planner origin `NaN`/`Infinity` | 不可规范序列化 |
| 倒序 valid 窗口 | 冻结 |
| 查询点 `NaN` | 非有限实数 |
| 合法双栈 tick=1 | 两栈 `[0.0]*15`，hash 仍 `60ae5097…` |
| 合法 planner / 证据清单 | 接受；清单 `partial_open`、`blocking_issue=9` |

## 检查 5 — 宽异常 / 重复 / 依赖

**不是 duplicate。** 已跟踪测试关系：

- `test_planner_scene_binding.py` 拒绝 **legacy 夹具** 作 planner，不测 probe。
- `test_display_scene_binding.py` 拒绝 probe 作 **display**，不测 planner `validate_manifest` 或 `observers=`。
- `test_audit_29_terrain_evidence.py` 守 visual/real 两层清单互换，不接 `TerrainFeedback(observers=)`。
- `test_contact_observer.py` / `test_terrain_feedback.py` 覆盖直接 foreign/stale，但 **`observers=` 注入零出现**（全仓 `validation/*.py` 仅本候选）。

独有接缝：planner 拒绝 probe id/hash；`TerrainFeedback(observers=)` 外来 epoch 冻结；观察器键必须恰好 `{arducopter,px4}`。

宽异常：候选无 `except`。三份真实导入无 `except Exception` / 裸 `except`。`observe_step` 只把 `ContactError` 收成冻结信号，再由 `query_terrain` 抛 `RuntimeError`，不是吞错。planner 把不可序列化/路径错误收成 typed Binding/IdentityError，fail closed。

依赖：实现与 `docs/plan/29-terrain-evidence-manifest.json`、`Simulator/wksim_runtime/static-scene-v1.json`、`static_contact.py`、`scene_profile.py` 均已跟踪。候选本身未入库。无 WSL/UE/ROS/环境变量/sibling 路径。不依赖其它未跟踪工作树文件。

## 检查 6 — 裁决规则

0 P1 / 0 P2 ⇒ **PASS**。即使 PASS，也只说明该离线回归可纳入下一批。

### P1

无。

### P2

无。

### P3

1. 前两个身份常量测试与已纳入 display / audit_29 部分重叠；不取消 planner-probe 与 `observers=` 的独有覆盖。
2. 双键替换断言父类 `PlannerSceneBindingError`；实现仍 raise 子类 `IdentityError`。
3. planner 对 probe 走通用 mismatch，不是具名 probe 门。
4. 候选自身未铺 bool/NaN/重复键/过期未来窗口矩阵；实现与本审查额外矩阵已 fail closed。
5. `ds-scene-frontier-20260912.md`「全仓零覆盖 `4889e2ea`/`40ee9281`」已过期：display 合同现拒绝 probe 作显示身份。

## 限制

- `#9` OPEN（ABI 证据阻塞仍在）。
- `#29` OPEN，原 AC 未勾；子票 CLOSED ≠ 父票验收。
- 未证明物理接触力/坡度/侧碰、真实 UE 同置、FC/SITL/ROS 闭环、显示断开。
- 纳入后仍须只 `git add` 该候选并保持 SHA `3f593d8f…`；本审查不执行纳入。

## 回执哈希

| 文件 | SHA256 |
| --- | --- |
| 候选 `validation/test_scene_frontier_contract.py` | `3f593d8f3bdb3c34db5c7b51014c305fd9596a73ce803a1c187e3d509b6c3de2` |
| 本目录 `review.md` / `review.json` | 见 `SHA256SUMS` |
