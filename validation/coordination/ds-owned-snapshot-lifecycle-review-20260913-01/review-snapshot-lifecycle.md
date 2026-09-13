# 独立复核：owned-scheduling snapshot 生命周期（2026-09-13）

复核目录：`validation/coordination/ds-owned-snapshot-lifecycle-review-20260913-01`（唯一写入目录）。
只读作者文件；纯事件夹具 + 临时目录；**无模型 / 无 ROS / 无编译 / 无运行时执行**；未改动作者任何文件、helper 或 `tools/run_joint_flight.py`。

被审对象（只读）：

| 对象 | sha256 |
| --- | --- |
| baseline `08e20642`（`ds-parent-probe-retention-20260913-01/run_joint_flight-candidate.py.txt`） | `08e20642f82f9052284f3054ae91c57d5d7e77017fb996e11d748bb98a86db99` |
| v1 `run_joint_flight-owned-snapshot-candidate.py.txt` | `080476dfaf4723956c4bb98eb649aab868eb47591aff336d0ea6100e6caddc57` |
| v2 `run_joint_flight-owned-snapshot-candidate-v2.py.txt` | `acc2713e57b509c5156dc04908c956b065197bf8265801045fded3de74ae4b23` |
| v3 `run_joint_flight-owned-snapshot-candidate-v3.py.txt`（复核期间到场） | `1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373` |
| helper `tools/capture_owned_scheduling.py` | `a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e`（与 v2/v3 内置常量一致） |

v3 在本次复核进行中到场（`prepare-report-v3.json` 记录 candidate `1c600d7f…`、baseline `08e20642…`、helper pin 一致）。因此本报告先交付 v2 真实缺口证据，再对 v3 逐条验收，未轮询等待。

## 结论

- **A（v2 缺口）：成立。** 主审判断正确，且比"仅依赖 ExitStack LIFO"更强：v2 的 after 抓取**必然发生在模型退出之后**。
- **B（v3 验收）：四项要求全部满足**（唯一顺序、异常兜底只一次、connect 失败不伪造、after 在 stop 与模型 close 之前）。
- **C（失败 capture 文件被错误重新认定 validated）：v2 成立，v3 已修。**
- 残余 3 项：**R1** v2 的 block 7 必须修（已被 v3 覆盖）；**R2/R3** 为 v3 的两个轻微问题，不阻塞。

## 1. 方法：不是两个随意 mock callback

`lifecycle_fixture.py` 的每个事件都带 **真实源文件 + 行号 + 逐字文本锚点**，测试先断言这些行仍逐字存在（`test_every_cited_line_matches`），再按原 runner 的成功/异常控制流重放。关键锚点：

| 事件 | 源 | 行 | 文本 |
| --- | --- | --- | --- |
| after 注册（v2） | v2 | 1094 | `resources.callback(owned_snapshot_after)` |
| stop 请求 | v2 | 1244 | `clock.request(dict(…,action='stop'))` |
| 模型关闭 | v2 | 1249–1250 | `for child in workers.values():` / `child.stdin.close(); child.wait(timeout=3)` |
| finally 组清理 | v2 | 1262 | `cleanup_children(result, children, child_specs,` |
| after 注册（v3，异常兜底） | v3 | 1115 | `resources.callback(owned_snapshot_after_once)` |
| after 成功路径调用 | v3 | 1271 | `owned_snapshot_after_once()` |
| stop 请求（v3） | v3 | 1273 | `clock.request(dict(…,action='stop'))` |
| 模型关闭（v3） | v3 | 1278–1279 | 同上两行 |
| once 守卫 | v3 | 1088 | `if meta.get('after_attempted'):` |
| validated 标记 | v3 | 1084 | `meta[phase + '_validated'] = True  # only a validated capture earns this` |

这正是"对应真实源手工清理位置"：夹具断言的是 runner **自己的** `child.stdin.close()/wait()`（1249–1250）与 `cleanup_children`（1262/1291），不是自造的回调。

## 2. A：v2 的 after 在模型退出之后（实测缺口）

v2 成功路径顺序（结构化推导 + 夹具实测）：

1. Enter `with ExitStack()`（907）；
2. `resources.callback(owned_snapshot_after)`（**1094**）——只登记，不执行；
3. 计时段收尾：`clock.request(action='stop')`（**1244**）；
4. **runner 自己**把模型关掉：`child.stdin.close(); child.wait(timeout=3)`（**1249–1250**）；
5. `result['status']='pass'`（1252）；
6. 离开 with 块才回转 ExitStack → after 回调此刻才跑；
7. `finally` → `cleanup_children`（**1262**）再退休 worker（`retire_model_workers` 233，`stream.close()` 252）。

夹具实测（`evidence/lifecycle-traces.jsonl`，`v2-success`）：

```
order        = stop_action → model_close → after_capture → exitstack_unwind → cleanup_children
before_after = [stop_action, model_close]      # 抓取时 stop 与模型 close 已经发生
```

即：**after 快照读到的 /proc 里，被测模型已经 EOF 退出**（模型 close 在 1249–1250 已经完成），`cleanup_children` 又在 after 之后执行。这比"LIFO 顺序不对"严重一档：v2 无论成功还是失败，after 都晚于模型退出。

其余分支（同夹具）：

- `v2-connect-failed`：`attempts=0`，`after=None` 且无 `after_error`——**不伪造**，这点 v2 本来是对的（`physics.connect()` 在 1079 抛错，1094 的登记从未发生）；
- `v2-business-error` / `v2-after-capture-failed`：after 仍在**回转期间**跑（`after_attempted` 不存在，故每次回转都会尝试，但 ExitStack 保证同一次回转只跑一次）。

由此确认主审"v2 仅依赖 ExitStack LIFO"成立，并给出更准确的表述：**v2 的 after 只在 with 块回转时执行，因此必然晚于 1249–1250 的模型 close 与 1262 的组清理**。

## 3. B：v3 逐条验收（全部满足）

| 要求 | v3 事实 | 夹具证据 |
| --- | --- | --- |
| after 在 stop 与模型 close **之前**，且**只一次** | 成功路径显式调用 `owned_snapshot_after_once()`（**1271**），位于 1273 `action='stop'` 与 1278–1279 模型 close **之前**；`after_attempted` once 守卫（1088/1090）保证一次 | `v3-success`：`order = after_capture → stop_action → model_close → exitstack_unwind → cleanup_children`，`before_after = []`，`attempts=1`，`validations=1` |
| 异常退栈兜底**只一次** | `resources.callback(owned_snapshot_after_once)`（1115）注册**最后**，仅在异常回转时执行；成功路径已置 `after_attempted`，兜底变 no-op | `v3-model-close-error-once-guard`（模型 close 抛错）：`attempts=1`，`validations=1`，`after_skipped_once=1`；失败 capture 场景同样 `attempts=1` + `skipped_once=1` |
| connect 失败**不伪造** after | `physics.connect()`（1107）抛错时 1115 的登记从未发生；且 `after_attempted` 保持未设 | `v3-connect-failed`：`attempts=0`，`after=None`，无 `after_error`，`after_skipped_unconnected=1` |
| 反向回归（防"挪到 stop 之后也算修"） | — | `after_mode='after-stop'` 时夹具报 `before_after=['stop_action']` → 判定不达标 |

v3 同时保留了 v2 的正确点：`before` 失败只记 `before_error`（1098–1103），不会连带压制 after；boot 变化不写文件也不标 validated（1053–1055）。

## 4. C：失败 capture 文件是否被错误重新认定 validated

**v2：是。** block 7 元数据刷新（1350–1369）对 `before`/`after` 只做 `path.is_file()` 检查，然后把 `file=path.name` + `sha256` 记入结果——**既不读文件内容、也不校验 `phase`、也不区分是否本次运行所写**。夹具两种反例：

- `v2-adopts-a-wrong-phase-file`：helper 在 after 路径写出的文件 `phase` 字段为 `before`，v2 仍把它作为 `owned_scheduling.after` 呈现；
- `v2-adopts-a-stale-file`：本次 after 抓取失败（`targets file differs from history`），但 live 目录里留着**上一次运行**的 `owned-scheduling-after.json`（`host.boot_id = boot-OLD`），v2 仍把它重新认定并记入 `after`，仅旁边留一个 `after_error`。

**v3：已修。** `meta[phase+'_validated']`（1084）只在 helper 返回且 `captured['host']['boot_id'] == boot`（1081–1082）之后置位；刷新时 `validated = bool(meta.get(phase + '_validated'))`（1386），未 validated 的文件保留原名+哈希但显式标注 `validated=false` 与 `note='raw file retained; capture did not validate'`（1390–1392），不再作为已验证证据；反过来 "validated 但文件丢失" 才抛 `metadata_error`（1393–1394）。夹具以 `v3-legacy-refresh`（v3 调用点 + v2 式刷新）隔离验证：同一 stale 文件在旧刷新下被采纳、在新刷新下被降级为 raw。

## 5. 残余问题（不阻塞）

- **R1（v2，必须修，v3 已覆盖）**：v2 block 7 的"任意文件即采纳"刷新需加入 validated/phase 判定；v2 已不能作为送审候选。
- **R2（v3，轻微）**：内部簿记键会泄漏到产物。`meta['after_attempted']`、`meta['after_validated']` 直接写在 `result['owned_scheduling']` 上，而刷新是 `meta.update(refreshed)`（1405）——只能增/改键，不能删键，因此 `result.json` 的 `owned_scheduling` 会带上这两个内部标记。不影响判定，但建议放入单独的内部字典或在写盘前剔除。
- **R3（v3，说明性）**：刷新只信任内存中的 `_validated` 标记，**从不重新打开 capture 文件**，因此文件内 `phase`/`schema` 的写入正确性完全依赖 `owned_snapshot_capture(phase)` 的调用方传参正确。对当前 helper（始终写请求的 phase，`capture_owned_scheduling.py:462` 独占创建）是成立的，但建议在文档中写明，或在刷新时顺带核对文件 `phase` 字段。

## 6. 边界与未做

未运行任何模型/ROS/编译；未执行 `run_joint_flight`；未读取 live 实验数据；未改动 helper、运行时、作者候选或 `tools/run_joint_flight.py`。夹具对真实 runner 的建模范围限于快照生命周期相关控制流（ExitStack 登记/回转、stop、模型 close、`cleanup_children`、block 7 刷新、once 守卫、validated 标记）；与快照无关的业务逻辑不建模。

## 7. 复现

```
python -B validation/coordination/ds-owned-snapshot-lifecycle-review-20260913-01/test_snapshot_lifecycle.py
python -B validation/coordination/ds-owned-snapshot-lifecycle-review-20260913-01/run_lifecycle_review.py
```

第一条：29 tests，`OK`（含 12 个源行锚点完整性断言）。第二条：输出 `anchors all verified: True` 与 7 个场景的顺序表，证据写入 `evidence/lifecycle-review.json`、`evidence/lifecycle-traces.jsonl`。哈希见 `sha-receipt-20260913-09.json`。
