# #29 离线场景反馈候选 — 独立复核

日期：2026-09-14T09:29:39+09:00  
工作类别：new-development independent review  
只读源文件，未改源/refs/GitHub，未 git add/commit/push。

## 派发核验

| 项 | 值 |
| --- | --- |
| cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| branch | `main` |
| HEAD | `5370b2324672c9036d41239cb93e21fc5eb42897` |
| 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` | `git merge-base --is-ancestor` 退出码 **0** |
| 已读 | `AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`CONTEXT.md`、GitHub `#29` 与 `#9` |
| 本次 module / interface | 只读复核 `tools/inspect_aruco_native_targets.py` 离线准入辅助；不改模型/固件/UE/实验入口 |
| 独占写入 | 仅本目录 `review.md` / `review.json` / `SHA256SUMS` |
| 未跑 | native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83 |

三份候选在 HEAD 上为**未跟踪工作区文件**；本复核绑定的是工作区字节 SHA，不是 commit blob。

## 总评

**PASS**（离线准入辅助切片成立；**不是** #29 通过）。

P1 = 0；P2 = 3；P3 = 5。  
`correlated=true` 仍把 `#29/#79/#80/#81` 全部锁为 `false`，`issue_9_state` 固定 `OPEN`，报告 `status` 只有 `correlated`/`rejected`。  
检查项 2（类型级逐项拒绝）为 **PARTIAL**：主路径正负例成立，但空串身份、`False==0` 时间字段、非向量接触点仍可得到 `correlated`。

GitHub 实读：`#9` **OPEN**；`#29` **OPEN**，五条 AC 均未勾选；子票 `#79/#80/#81` 已 CLOSED，文档正确写明这不等于父票 AC 满足。

## 源 SHA

| 文件 | 期望 SHA256 | 实测 | 匹配 |
| --- | --- | --- | --- |
| `tools/inspect_aruco_native_targets.py` | `b370d12dd8574c4d70cd14eb426f12c19b71dc77e4f7aae025a5479c430d7a05` | 同左，22477 B / 601 行 | 是 |
| `validation/test_aruco_native_targets.py` | `fe391a386b26dfce54d99efe5610b167b15303c0e5e373d3d49b99d185cb1bc4` | 同左，16262 B / 382 行 | 是 |
| `docs/coordination/agy-aruco-native-correlation.md` | `f9c07b7588e3089bff23ecaf0da16685a92f310a2b01872726cb4af5edb602bc` | 同左，4958 B / 81 行 | 是 |

复核前后字节未变。

## 检查 1 — 完全离线 / 不写输入

**PASS。**

实现只导入 `argparse/hashlib/json/math/pathlib/typing`。无 `rclpy`、ROS、UE、`subprocess`、`socket`、`ctypes`、`importlib`、`eval/exec`。`digest_file`/`load_json`/`inspect_path` 只读；`write_report` 仅在显式 `--output` 下以 `'x'` 新建报告，拒绝覆盖，不改证据输入。默认/`--retained-paths` 只读已提交 JSON。

正式测试在导入后断言 `sys.modules` 无 `rclpy`/`rosidl_runtime_py`，源码无 `deserialize_message`/`JointPhysics`。本复核未启动任何运行时。

## 检查 2 — 逐项拒绝

**PARTIAL**（主家族成立；类型/空值漏洞见 P2）。

| 家族 | 实现 | 正式测试 | 本复核额外负例 |
| --- | --- | --- | --- |
| 坐标系 / 单位 | 场景与视觉须 `ENU`；单位须 `metre` | 缺框、NED/UE | CLI：`unit=meter` → `unsupported_unit` |
| 反馈有效时间 | `current_step` 须非 bool 的 `int>=0`；窗口外 `stale`/`future`；`sim_time_ns==step*1e6` | 缺字段、过期、超前 | `current_step=True` → `missing_feedback_valid_time`；`sim_time_ns=False` 且 `step=0` **仍 correlated** |
| 来源身份 | 视觉查 `None/""`；物理只查键存在 | 删除键 | 物理 `source_identity=""` **仍 correlated** |
| 冻结 / 断流 / 过期 | 缺语义拒绝；复用词表拒绝；`render_frame_advances_physics is True` 拒绝 | 空语义、reuse、render | CLI：`cache`/`silent_reuse` → `missing_stale_or_disconnect_semantics` |
| contact schema | 键齐全且 `wksim.contact.v1` | 视觉偏移伪信封 | `contact_point_enu_m="not-a-vector"` **仍 correlated** |
| 视觉偏移伪装 | 偏移键、`collision_from∈{visual,visual_offset,aruco}`、位姿与接触点全等 | 偏移包、复制 UE 位姿 | 未再扩 |
| 未批准物理预算 | 递归禁键；`contact_budget_invented` 恒 `false` | force/stiffness | 报告不含这些量 |

物理信封没有独立 `coordinate_frame`/`unit` 字段；只靠场景侧与字段名 `*_enu_m`。

## 检查 3 — `correlated` 语义

**PASS。**

`correlated = (rejection_reasons == [])`，`status` 为 `correlated` 或 `rejected`，测试禁止 `"pass"`。`parent_tickets_unlocked` 对 `#29/#79/#80/#81` 恒 `false`；自称 `issue_9_state=CLOSED` 记 `fabricated_issue_9_closure` 后仍写 `OPEN`。`inspect_evidence_manifest` / `inspect_retained_paths` 恒 `rejected`。文档写明关联不是 AC 通过。

独立完整包 sanity：`status=correlated` 且 `unlocked_any=false`、`issue_9=OPEN`。

## 检查 4 — 测试与 I/O 陷阱

**PASS，带 P2/P3。**

正式套件有独立构造的完整包（自有 `EPOCH`、视觉 `[4,1,2]`、接触 `[0,0,0]`）以及缺框/时间/身份/语义、复用、渲染推进、视觉偏移、预算、过期/超前、身份混写、规划哈希、静态场景单独不足、清单保 `#9`、缺 live 目录、损坏 JSON、独占输出、不导入 ROS。不是只复述实现常量。场景哈希从实现导入，但清单/静态场景文件充当外部钉；改错常量会与真实文件冲突。

缺口：正式测试未覆盖空串物理身份、`False`/`step=0` 时间、非向量接触点、`unit=meter`、跨 epoch。这些由 TEMP 额外负例补做。

`inspect_path` 对用户路径 `resolve()`，`..` 只解析到真实文件再只读，本轮 `nested/../neg2-*.json` 仍落在 TEMP。CLI 不沙箱化任意可读 JSON，属预期本地检查器行为。报告里的绝对路径来自 `__file__`/resolve，测试夹具用 `tempfile`。JSON 数组/残缺/非对象会 `InspectError`。`current_step=True` 被拒；`sim_time_ns=False` 在 `step=0` 漏过。

## 检查 5 — 文档 vs 当前 #9 / #29 AC

**PASS。**

文档与 `gh` 实读一致：`#9` OPEN；`#29` OPEN 且 AC 未勾；关闭 `#9` 前不解锁 `#29/#79/#80/#81`；子票已关不等于父票 AC。未宣称 UE 同置、坡面/接触力、FC/SITL/ROS 闭环。命令与 `'x'` 输出约定与实现一致。

本检出存在 `validation/lunar-29-static-contact/` 与 `lunar-29-live-contact/display-manifest.json`；`inspect_retained_paths` 仍因清单 `acceptance=false` / `blocking_issue=9` 拒绝，不编造 UE 已跑。

## 正式测试

```text
python -B -m unittest validation.test_aruco_native_targets -v
```

**28/28 OK**，约 0.011 s。未 skip。CLI 子项对完整包打印 `correlated` 且四票 `false`；对 `--retained-paths` 打印 `rejected` / `insufficient_offline_pair`。

## 额外 TEMP 负例（≥3，已精确删除）

根目录：`C:\Users\PC\AppData\Local\Temp\wksim-i29-neg-fumzt_g4`。事后 `glob wksim-i29-neg-*` 为空。

| 编号 | 途径 | 构造 | 结果 |
| --- | --- | --- | --- |
| sanity | `inspect_pack` | 独立 epoch/几何的完整包 | `correlated`，未解锁 |
| neg1 | CLI + `inspect_path` | `unit=meter` | `rejected` / `unsupported_unit` |
| neg2 | CLI，`subdir/../file` | 视觉/物理 epoch 不同 | `rejected` / `foreign_epoch`；resolve 仍在 TEMP |
| neg3 | `inspect_path` | JSON 数组 | `InspectError`：must contain a JSON object |
| neg4 | `inspect_pack` | 物理 `source_identity=""` | **仍 `correlated`**（P2） |
| neg5 | `inspect_pack` | `step=0` 且 `sim_time_ns=False` | **仍 `correlated`**（P2） |
| neg6 | `inspect_pack` | `contact_point_enu_m="not-a-vector"` | **仍 `correlated`**（P2） |
| neg7 | `inspect_pack` | `current_step=True` | `rejected` / `missing_feedback_valid_time` |
| neg8 | CLI `--output` | 复用词表；二次写入 | `rejected`；第二次 `FileExistsError` |

CLI 对拒绝包仍退出 0，属检查器惯例。二次 `--output` 未改写成 `InspectError`，会 traceback（P3）。

## 发现

### P1

无。未解锁父/子票，未发明接触预算，未把视觉当碰撞，未写输入，未跑 native/ROS/UE。

### P2

1. **空串物理来源身份仍可关联。** 视觉用 `in (None, "")`，物理只用 `field not in physical`。`source_identity=""` 得到 `correlated=true`。
2. **`sim_time_ns=False` 且 `step=0` 仍可关联。** `False == 0`，时间等式放过。`current_step=True` 已被 `_is_step` 挡住。
3. **接触几何只查键不查型。** 字符串/`NaN`/`Infinity`/`penetration_m=True` 只要键在即可关联。与“字段够用来对照”的文档承诺相比过宽。

以上均不改 `parent_tickets_unlocked` 或 `#9 OPEN`。

### P3

1. 正式测试未钉死空串身份、bool 时间、非向量接触、`meter`、跨 epoch。
2. 场景哈希从实现 import；文件钉减轻循环，但包夹具与常量同游。
3. `stale_feedback`/`disconnect` 只禁复用词，任意其它非空字符串可通过。
4. 视觉偏移只抓**完全相等**的位姿复制，近拷贝不抓。
5. 未知 `(scene_id, scene_hash)` 只要自洽即可关联；CLI 接受任意可读路径；单行无尾换行的合法 JSON 会被当成 truncated。

## 未决边界

- `#9` 仍 OPEN（环境合同已批，厂商 DLL ABI 仍 NO-GO）。
- `#29` 五条原 AC 未勾；本工具不能证明 UE 同置、真实断连、坡面/侧碰/接触力、动态对象、FC/SITL/ROS 闭环。
- `60ae5097…` 与 `4889e2ea…` 必须继续分列。
- `correlated` 不是类型安全 schema 验证；P2 未修前不要把它当接触信封已合法。
- 子票 CLOSED ≠ 父票可关。
- 本切片不改变 #29 阻塞集（`#9`/`#17`/`#23`）。

## 结论

候选可作为 **#29 离线准入辅助** 使用：完全离线、不写输入、不解锁、不声称真实接触或 AC 通过，文档与当前 `#9` OPEN / `#29` AC 一致。正式 28/28 通过。残留 P2 是关联门的类型宽度，不是验收越权。#29 保持 OPEN。
