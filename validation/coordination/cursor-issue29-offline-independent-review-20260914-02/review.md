# #29 离线场景反馈辅助 — 第二轮独立复核

日期：2026-09-14T09:41:33+09:00  
工作类别：review  
只读源文件与第一轮目录，未改三个源文件、未覆盖 review-01、未 git add/commit/push、未关票。

## 派发核验

| 项 | 值 |
| --- | --- |
| cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| branch | `main` |
| HEAD | `5370b2324672c9036d41239cb93e21fc5eb42897` |
| 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` | `git merge-base --is-ancestor` 退出码 **0** |
| 已读 | `CONTEXT-MAP.md`、`wksim/CONTEXT.md`、ADR-0002/0004/0008/0009、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`docs/coordination/short-cycle-goal.md`、`docs/coordination/module-delivery-policy-20260912.md`、`docs/plan/29-display-binding-contract.md`、`docs/plan/9-vendor-abi-defer-boundary.md`、GitHub `#29`/`#9`/`#79`/`#80`/`#81`、第一轮 `validation/coordination/cursor-issue29-offline-independent-review-20260914-01/` |
| 本次 module / interface | 只读复核 `#29` offline scene-feedback admission/correlation helper：`tools/inspect_aruco_native_targets.py` |
| 独占写入 | 仅本目录 `review.md` / `review.json` / `SHA256SUMS` |
| 未跑 | native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83 |
| 第一轮 | 只读；SHA 未变；本轮未改写 |

三份候选在 HEAD 上仍为**未跟踪工作区文件**；本复核绑定工作区字节 SHA，不是 commit blob。相对第一轮，三份文件已换成修复后字节。

## 总评

**PASS**（0 P1 / 0 P2；离线准入辅助切片成立；**不是** #29 / Full / Goal 通过）。

第一轮三个 P2 在本字节上均已 fail closed，错误码稳定：

| 第一轮 P2 | 本轮 `inspect_pack` / CLI | 稳定理由 |
| --- | --- | --- |
| 物理 `source_identity=""` | `status=rejected`，`correlated=false` | 仅 `missing_source_identity` |
| `step=0` 且 `sim_time_ns=False` | 同上 | 仅 `missing_feedback_valid_time` |
| `contact_point_enu_m="not-a-vector"` | 同上 | 仅 `invalid_vector` |

`correlated=true` 仍把 `#29/#79/#80/#81` 全部锁为 `false`，`issue_9_state` 固定 `OPEN`，报告 `status` 只有 `correlated`/`rejected`，不含 `pass`。GitHub 实读：`#9` **OPEN**；`#29` **OPEN** 且五条 AC 未勾；子票 `#79/#80/#81` **CLOSED**，不等于父票解锁。

## 源 SHA

| 文件 | 期望 SHA256 | 实测 | 匹配 |
| --- | --- | --- | --- |
| `tools/inspect_aruco_native_targets.py` | `03a36c58c67e1e361ddd035d3e3cc440f9ac0544256126687bfec5c7d500838e` | 同左，26202 B / 672 行 | 是 |
| `validation/test_aruco_native_targets.py` | `e42a0824b8c2a8287dbfda178fa6f17c6e3840cce9bb2913262cdb84e7ed1097` | 同左，20271 B / 460 行 | 是 |
| `docs/coordination/agy-aruco-native-correlation.md` | `c2d863c76c1cf832699e919125b412c6280b036f7cd6c3bfd2454af505eaef51` | 同左，6305 B / 95 行 | 是 |

复核前后字节未变。第一轮绑定的旧 SHA（`b370d12d…` / `fe391a38…` / `f9c07b75…`）仅作历史对照，未改写。

## 检查 1 — 精确重放第一轮三个 P2

**PASS。**

实现现用 `_is_identity`（`:138-146`）、`_is_nonneg_int` 显式排除 `bool`（`:149-150`）、`_is_finite_vector` 拒绝 `str`/`bytes`（`:165-171`）。物理路径在键存在后仍做类型门（`:347-356`）。

独立包（自有 epoch `r02-independent-epoch-9f3c1a70b4e8d216`、视觉 `[3.5,-1.25,0.8]`、接触 `[0.25,-0.5,0.0]`）上：

- 空串身份两次调用理由相同：`["missing_source_identity"]`。
- `step=0` + `sim_time_ns=False` + `current_step=0` 不再因 `False==0` 过关。
- 字符串接触点不再只查键。
- CLI `--evidence` 与 `inspect_pack` 理由一致；`nested/../subdir` 仍解析到 TEMP。

四票始终 `false`，`issue_9_state=OPEN`。

## 检查 2 — 扩展 `source_identity`

**PASS。**

| 构造 | 结果 | 理由 |
| --- | --- | --- |
| 物理缺键 | rejected | `missing_source_identity` + `incomplete_physical_envelope` |
| `null` / `{}` / `True` / `False` / `[]` / `{"": "x"}` / `{"module": ""}` | rejected | `missing_source_identity` |
| 视觉缺键或 `""` | rejected | `missing_source_identity` |
| 场景键存在且 `""` | rejected | `missing_source_identity` |
| 合法非空对象 / 嵌套对象 | correlated | 理由空；四票仍锁 |

错误码按构造稳定；缺键比空值多一条信封不完整，不是同一输入的抖动。

## 检查 3 — 时间 / 步骤

**PASS。**

`bool` 冒充（`current_step=True/False`、`step=True/False`、`sim_time_ns=True` 且 `step=1`）、负值、`7.0`、`"7"`、`None`、缺窗口均 `missing_feedback_valid_time`。缺 `step`/`sim_time_ns` 为 `incomplete_physical_envelope`。`sim_time_ns != step*1_000_000` 拒绝。极大整数 `10**18` 在窗口外记 `stale_feedback`；与窗口/纳秒对齐时可关联。**合法整数 `0` 且 `sim_time_ns=0` 不被误拒**，四票仍锁。

## 检查 4 — 向量 / 标量

**PASS。**

`contact_point_enu_m` 与 `normal_enu`：字符串、字典、长度 0/2/4、`bool` 元素、`NaN`/`±Infinity` 均为 `invalid_vector`。合法有限 3-vector 可关联。视觉 `position_world_ue_m` 含 `NaN`、场景 `origin_enu_m` 长度 2 同样拒绝。`penetration_m` 的 `True`/`False`/`NaN`/`±Infinity` 为 `invalid_scalar_type`。有限负值 `-0.02` 按文档“有限数值”被接受，不解锁父票。

## 检查 5 — 标记 / 过期 / 未来 / 身份 / 重复乱序 / `correlated` 语义

**PASS。**

过期 `stale_feedback`、超前 `future_feedback`、场景错配、`60ae5097…`/`4889e2ea…` 混写、规划哈希 `40ee9281…`、跨 epoch、复用/`cache`/`silent_reuse`、`render_frame_advances_physics=True`、自称 `#9 CLOSED` 均拒绝。物理目标为列表 → `missing_physical_target`。倒序窗口同时记 stale/future。JSON 数组 → `InspectError`。

本工具是单包检查器，没有 boot/source/full-window/latch/overflow/lost 流式状态机。这些条件映射到已有门（缺身份、缺窗口、复用词、过期/超前、身份冲突、残缺信封）时 fail closed。包上多写 `overflow`/`lost`/`latch`/`acceptance=true` 会被忽略且仍可 `correlated`，但报告不泄漏 `acceptance`、不改 `parent_tickets_unlocked`、不把 `correlated` 写成物理已消费或 #29 AC 通过。重复 `inspect_pack` 无锁存；视觉/物理 `step` 不一致但窗口覆盖 `current_step` 仍可关联（见 P3）。

## 正式测试

```text
python -B -m unittest validation.test_aruco_native_targets
```

**34/34 OK**，约 0.013 s。未 skip。CLI 子项对完整包打印 `correlated` 且四票 `false`；对 `--retained-paths` 打印 `rejected` / `insufficient_offline_pair`。

## 额外 TEMP 负例

根目录：`C:\Users\PC\AppData\Local\Temp\wksim-i29-r02-a7384b07`。事后已删除，`wksim-i29-r02-*` 无残留。仓库内未写临时脚本。

91 条独立用例全部按预期：3 个第一轮 P2 的 API/CLI 重放、身份/时间/向量矩阵、过期/未来/错配、独占写入、单行无换行视为 truncated。0 条意外关联解锁。

## 发现

### P1

无。未解锁父/子票，未发明接触预算，未把视觉当碰撞，未写输入，未跑 native/ROS/UE，未声称 Full/Goal。

### P2

无。第一轮三条类型门漏洞在本 SHA 上已关闭且理由稳定。

### P3

1. **正式测试仍未钉若干额外边界。** `validation/test_aruco_native_targets.py` 现有 `TypeGateTests`（`:257-331`）覆盖三个第一轮 P2、空对象/`bool` 身份、NaN/Inf/错长与合法 `0`；仍无 `unit=meter`、跨 epoch、视觉-only 空身份、有限负穿透、包级 overflow 键。TEMP 已补做。
2. **夹具哈希仍从实现 import。** 测试从 `tools.inspect_aruco_native_targets` 取 `VISUAL_STATIC_SCENE_HASH` 等；静态场景文件与证据清单减轻循环，但包夹具与常量同游。
3. **过期/断流词表仍是否定列表。** `:104` `REUSE_TOKENS` 与 `:369-372` 只拒复用词。`stale_feedback="overflow"` / `disconnect="lost"` 可关联（TEMP `policy_overflow_lost_strings`）。
4. **视觉偏移只抓完全相等的位姿复制。** `:226-229` 要求 `list(contact)==list(pose)`；近拷贝不抓。
5. **单包语义宽度。** 未知但自洽的 `(scene_id, scene_hash)` 可关联（`:233-246` 末尾恒 `False`）。`:433-437` 只把 `current_step` 与窗口比较，不要求 `physical.step` 落在窗口内，也不要求视觉/物理 `step` 相等。CLI 可读任意 JSON 路径；单行无尾换行被 `:126-127` 当成 truncated；二次 `--output` 抛 `FileExistsError`（`:609-610`）而非 `InspectError`。以上均不解锁票、不改 `#9 OPEN`。

## 未决边界

- `#9` 仍 **OPEN**（厂商 DLL ABI 仍 NO-GO；推迟边界是提议，不是关闭）。
- `#29` 五条原 AC 未勾；`#79/#80/#81` CLOSED ≠ 父票可关，本工具保持四票 `false`。
- 本工具不能证明 UE5.5 同置、真实显示断开、坡面/侧碰/接触力、动态对象、FC/SITL/ROS/DDS 闭环。
- `60ae5097…` 与 `4889e2ea…` 必须继续分列。
- `correlated` 只表示这包离线字段够对照，不是物理已消费，也不是 #29 AC / Full / Goal 通过。
- `#29` 仍被 `#9`/`#17`/`#23` 阻塞。本切片不改变阻塞集。

## 结论

修复后的离线辅助可继续作为 **#29 准入协助**使用：完全离线、不写输入、不解锁、不声称真实接触或 AC 通过。第一轮三个 P2 已关闭。正式 34/34 通过；TEMP 91/91 按预期。#29 保持 OPEN。Full / Goal 未通过。
