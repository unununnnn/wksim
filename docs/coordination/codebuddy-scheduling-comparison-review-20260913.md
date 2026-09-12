# 独立审查：owned-scheduling 快照比较器 — 2026-09-13

独立审查，非实现方。只读源码 + 定向纯反例（不重复主会话已通过的 40 项原测试）；未跑 native/模型/ROS/构建、未改实现、无嵌套、未用 Git mutation。
**结论：身份复用/缺失相等/禁用 schedstats/负计数/对称匹配/输出覆盖 六项关注点均正确；另发现 2 项有界健壮性缺口（C1、C2），均为畸形快照输入，非当前自产快照可达。**

## 1. 版本（实际读到字节，与给定一致）

| 文件 | SHA256 |
|---|---|
| tools/compare_owned_scheduling.py | `033d8af81c8c785c5d28a6476aa909309f1bcae20f196d3d0c17b71b06103c7d`（21218B） |
| validation/test_compare_owned_scheduling.py | `20cc459052c2cf8d860e2c1583334e583abd3b95c3d022a8a0795580ab8642fe`（19740B） |

## 2. 关注点核验（源码 + 定向反例）

- **身份复用 — 正确。** 角色级比较 `pid/pgid/start_ticks` 三者（`_compare_role:354-355`、`_valid_identity:332-337`）；线程级按 `tid` 匹配并要求 `start_ticks` 为合法 int 且两侧相等（`:296-311`）。缺失/非法 `start_ticks` **不匹配**（显式拒绝 `None==None` 拼接，`:298-305`）；`start_ticks` 变 → `thread_reuse_not_stitched`，不产出 `delta`。
- **缺失相等不假 0 — 正确。** `_delta_pair` 任一侧为 `None` 即 `delta=None` + reason（`:152-157`）；反例 A：两侧 `utime` 均缺失 → `delta=None, unavailable=stat_metric_missing`（非 0）。`stat`/`schedstat`/`proc_status` 整体缺失分别给独立 reason（`:175-234`）。
- **禁用 schedstats / 负计数不假 0 — 正确。** 等待计数仅在**两侧 host** `sched_schedstats=="1"` **且两侧行 `runqueue_counters_valid`** 同时成立时计算（`:202-209`）；行标志为真但 host 禁用/缺失时不被信任（`:198-200,210-220`），`runqueue_ns/timeslices` 置 null + `host_sched_schedstats_not_enabled(...)`；`run_ns`(exec) 始终保留。负增量 → `delta=None` 且入 `negative_counters`，绝不 clamp（`:158-162`）。
- **对称匹配 — 正确。** 角色 `sorted(set(b)|set(a))`，缺失方记 `role_added_after`/`role_removed_after`（`:340-346,412-414`）；线程同样并集遍历，`thread_added_after`/`thread_vanished_after`（`:284-295`）。
- **输出覆盖 — 正确。** `self.output.open("x")`（`:452`），已存在即 `FileExistsError`；输入仅只读，`_load_snapshot` 对原始字节取 sha256（CRLF 安全，`:65-82`）。
- **绑定门**：children.sha256 同值且为 hex64、boot_id 同值非空、after.monotonic_ns 严格大于 before、角色身份一致（`:85-107`）；未绑定仍写显式 `unbound` 报告（`:449-454`）。

## 3. 定向独立反例（仅我有疑点处，未重复原测试）

用自造最小快照对（同 children/boot/monotonic 递增/身份一致）驱动 `SnapshotComparison`，`python`（Windows，纯 JSON）：

| 反例 | 观察 | 判定 |
|---|---|---|
| A 两侧 `utime_ticks` 缺失 | `delta=None, stat_metric_missing` | 正确（非 0） |
| B 后侧 `utime_ticks="25"`（字符串） | 抛 `TypeError: unsupported operand type(s) for -: 'str' and 'int'` | **缺口 C1** |
| C 后侧 `run_ns="300"`（字符串） | 同样抛 `TypeError` | **缺口 C1** |
| D 前侧 `utime_ticks=True`（bool） | 被当作 1 参与运算 → `delta=24`，无告警 | **缺口 C2** |

精确命令（可从 Windows 检出复现）：`python <上述反例脚本>`；结果如上。脚本为临时文件，已删除。

## 4. 有界缺口

- **C1 — `stat`/`schedstat` 计数非 int 时报错而非降级。** `_thread_delta` 对 `utime_ticks/stime_ticks/run_ns` 直接把快照值传给 `_delta_pair` 相减（`:182-183,194-196`），未做 `_as_int` 式强制；畸形（字符串）值触发 `TypeError`，整个比较中断，而非按契约“不可读 → null + reason”。触发：被人为改坏或跨版本快照；当前 capture 工具只写 int，正常运行不可达。建议对这三个字段套用 `_as_int`（其对 ctxt 已如此，`:232-234`）。
- **C2 — bool 计数被静默当作 1/0。** `_as_int` 明确拒绝 bool（`:141-143`），但 `stat`/`run_ns` 路径未用 `_as_int`，故 `True` 会参与减法（反例 D）。与 ctxt 路径不一致，可能伪造数值增量。同一修复可一并覆盖。

两项均非当前自产快照可达，且不影响 §2 六项关注点的正确性；主会话 40 项原测试未覆盖非 int 计数输入。

## 5. 结论与剩余阻断

- 比较器在其设计输入域（capture 工具产物）内行为正确：身份不复用、缺失不为 0、禁用等待计数与负增量不假 0、对称匹配、输出不覆盖。
- 剩余阻断：无（C1/C2 为有界健壮性建议，可在畸形快照上使比较抛错或被静默吸收）。未改动实现。
- 报告文件自身 SHA256 见交付回执。
