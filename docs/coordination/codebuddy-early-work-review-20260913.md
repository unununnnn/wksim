# 早期工作诊断独立审查 — 2026-09-13（R1/R2 + readiness 回归复验）

独立审查，非实现方。只读源码 + 纯 mock + 临时文件行为对照；未跑 native/模型/ROS/构建、未改实现、无嵌套、未用 Git。
**结论：R1/R2、取消语义、真实 segment、C2 readiness 缩进回归、以及 R3 均已在最新 runner 上关闭。无剩余阻断。**

## 1. 版本（实际读到字节）

| 文件 | SHA256 |
|---|---|
| tools/run_joint_flight.py | `65c7a86765a99d2173a62ffafaf56c43243674dd1e3cbbc1150147b4c56d8161`（R3 主修一行后） |
| tools/early_manager_work_probe.py | `a5def2ba01919ad010cec65a73c4208342279bda9cb6d276044ded0debfb90b8` |
| validation/test_early_manager_work_probe.py | `4cabf245cbd49808c1aa3ba73fc5739272d204b9af4490a3d7d1d44aa9661cb4`（30678B，mtime 2026-09-13 01:44:40 +0900） |

取代上一版（`a6d2c299`/`201d1c2f`/`086d25dc`）。本轮只读该三文件，未核对全库。
**未审变化**：测试文件在本轮审核期间由 `b27fa573…` 变为 `4cabf245…`（runner/helper 未变）。§2/§3 结论建立在 runner `7b81bdc1` 与 helper `a5def2ba` 上，不受该测试变化影响；测试文件本轮仅复核到“新字节下 34 tests OK”，其新增断言未逐条审阅。

## 2. R1/R2/取消/segment 关闭核验（mock 实跑）

- **R1 Region 真实 end_tick/epoch/segment — 已关闭。** `Region` 现携带 `tick_of/epoch_of/segment_of` 且 `end()` 幂等（helper `:62-98`）；`_finish` 用真实 `tick_of()` 得 `end_tick` 并复查 `epoch_of`/`segment_of`（`:175-179`）。mock：`end_tick==42`、重复 `end()` 仅 1 个样本、epoch 变 → 记 `ValueError('epoch changed…')` 无样本、segment 变 → 记 `ValueError('segment changed…')` 无样本、`anchor_segment==5`（真实 int）。
- **R2 diagnostic_errors 有上限 — 已关闭。** `MAX_DIAGNOSTIC_ERRORS=1024`、`_record_diagnostic_error` 截断并计 `total/dropped`（`:48,157-162`）；`report` 输出 `diagnostic_error_total/dropped` 且 `diagnostic_clean` 依据 `total==0`（`:285-287`）。mock：上限 3、触发 5 次 → `len==3, total==5, dropped==2`。
- **取消不吞 — 已关闭。** `_finish` 异常分支：action 自身失败 → 记诊断并 return（原错优先，绝不遮蔽）；action 成功而诊断为 `KeyboardInterrupt/SystemExit/InterruptedError` → 重新抛出（`:185-192`）。mock：action 成功 + 末次读 `KeyboardInterrupt` → 异常传播；action 抛 `RuntimeError` + 末次读 `KeyboardInterrupt` → 外抛仍是**同一 RuntimeError 对象**。
- **真实 segment（非 'config' 冒充）— 已关闭（probe 路径）。** `set_window` 要求 `segment` 为 int（字符串 `'config'` 被拒，mock 报 `segment must be an integer segment id`，`:143-154`）；runner `set_window(segment=rate.segment_id)` 且 wrap/begin 均传 `lambda: rate.segment_id`（runner `:942,945,961,963,976,985`）。`rate.segment_id` 为真实 int（`joint_rate.py:26` 初始化、`:51` 递增）。
- **默认无诊断 lambda — 仍成立。** 所有 `lambda: clock.tick/clock.epoch/rate.segment_id` 均位于 `if early_probe is not None:` 内；readiness 用 `begin(...) if early_probe is not None else None`（惰性），关闭时走直接调用分支。

## 3. C2 readiness 缩进回归 — 已修复并经执行对照

**修复确认**：runner `:990-1004` 中 `save(pv_go_paths[leg], ...)` 现位于 `if not pv_go_paths[leg].exists() and all(path.is_file() ...)` 之内（缩进 32，与 `offers=` 同级），不再是条件外。故 ready 不齐不会用未定义 `offers`，也不会重写已有 `pv-go-*.json`。

**执行对照**：将 C2 基线（208e0e4/c208 的循环内构路径版本）与当前 readiness 块放入受控临时目录，逐场景运行并比较 `save` 调用序列/内容/异常/落盘文件（纯 fixture，无 AST/字符串镜像）：

| 场景 | 与基线相等 | 观察（当前 = 基线） |
|---|---|---|
| S1 合法两 leg（tick0） | 是 | save go + pv-go-1 + pv-go-2 |
| S2 pv-ready-2 缺失 | 是 | 仅 save go + pv-go-1（leg2 短路） |
| S3 leg1 部分就绪（px4 pv-ready-1 缺） | 是 | 仅 save go + pv-go-2（leg1 短路，无 NameError、无重写） |
| S4 已有 go + pv-go-1 | 是 | 仅 save pv-go-2；go/pv-go-1 **未被重写** |
| S5 坏 offer（leg1 run_id） | 是 | `ValueError: P+V readiness identity differs`，无 pv-go save |
| S6 tick%4!=0 | 是 | 仅 save go |
| S7 pv 关闭 | 是 | 仅 save go |

`ALL_EQUAL`。缺 `ready.json` 的路径在 C2 对照（场景 C）中已证等价：两版同样不 save go，并在 PV `initial` 读取处同样抛 `FileNotFoundError`。

## 4. R3 关闭核验（最新 runner `65c7a867`）

- **R3 — flush identity 的真实 segment — 已关闭。** runner `:1127` 现为 `segment=(rate.segment_id if rate is not None else None)`（主修一行），不再用字符串 `'config'`。
- **rate 初始化 None 覆盖早期异常 — 安全。** `rate` 在 `:421` `pause_probe = lifecycle = rate = messages = None` 初始化，仅在 `:822` 被赋值为真实 `JointRate`；若在此之前抛异常，`finally` 中 `rate is not None` 为假 → `segment=None`，不会 `AttributeError`。该 flush 位于 `try/except` 内（`:1122-1130`），失败仅记 `early_manager_work_error`，不遮蔽原异常。`report()` 对 `identity` 原样 `dict()`，接受 `segment=None`。
- 保留说明：`anchor_segment` 仍为 probe latch 时的真实 `rate.segment_id`（int）；`identity.segment` 在同一次正常运行的 flush 时刻同样取 `rate.segment_id`，二者一致。

无其它新问题；未发现 ready 重写、异常遮蔽或频率改变。

## 5. 测试与证据

- 现有套件：`python3 -B -m unittest validation.test_early_manager_work_probe` → **Ran 34 tests ... OK**（在测试文件新字节 `4cabf245` 上复跑；含 R1 Region、R2 cap、取消语义、segment 类型、default off、CLI/run 守卫）。
- 本轮独立 mock：R1（end_tick/幂等/epoch/segment）、R2（cap/total/dropped）、取消（成功时传播 / 失败时原错优先）、字符串 segment 被拒；以及 §3 的 readiness 基线-当前与 7 场景执行对照。均纯 Python，临时文件已删除。
- 未执行：native、模型加载、ROS/SITL、构建、真实飞行；未重跑全库。

## 6. 覆盖与开销（不得夸大）

仍**不声称零开销、不构成性能通过**。helper 自述每采样调用 2 次 wall + 2 次 thread-CPU 读、越界 1 次 wall 读、首 anchor 前 0 读；`diagnostic_errors` 现有 1024 上限。覆盖仅首 anchor→+10 s；steady 之后与 reset/epoch 段未覆盖。

## 7. 未审差异

本报告覆盖第 1 节 runner `65c7a867` 与 helper `a5def2ba`（helper 自上次审查未变）；`segment` 一行仅在 runner，R3 结论基于该 SHA 的字节。未重跑 34 测试套件（避免重复已通过项），R3 由源码只读核验（`:421,822,1122-1130`）。报告文件自身 SHA256 见交付回执。
