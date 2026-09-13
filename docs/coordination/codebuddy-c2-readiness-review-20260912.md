# C2 就绪路径等价审查 — 2026-09-12

独立审查，非实现方（A 为改动方）。只读源码 + 受控临时目录纯行为对照；未编译、未加载模型、未跑 ROS/native、无嵌套委派、未用 Git。
纯测试不能证明性能；本报告只判等价性，不含性能结论。

## 1. 版本与冻结 SHA

- 范围：仅 Ubuntu-22.04 `/root/wksim-release-acceptance-fe3/tools/run_joint_flight.py`。
- 基线：HEAD `7cb7e84`，runner `fd0b7ee6…`（本轮以先前冻结的 fd0b7ee6 只读快照为对照，未用 Git）。
- 实际读到字节：`c208b1d07a9054458e13b3f7bf74c145cb8641ec495e46fc7df5b6fb1626e408`（78472B，mtime 2026-09-12 23:32:50 +0900）。
- 审核期间首读（14:33:00Z）与末尾复算（14:34:23Z）一致 → 无未审变化；A 已改动，当前 SHA ≠ 基线 fd0b7ee6。

## 2. 结论：有边界通过

A 的改动与描述完全一致：把循环内恒定的 go/ready/PV 两 leg 的 `Path` 构造搬到 `while` 前（新增 L909–913，删除循环内 L948–949 的构造），**不缓存存在/内容、不降频**。重建 fd0b7ee6 全文与 c208b1d0 的 `difflib` 对照为 **3 个 hunk、全部落在该 hoist**，无其它改动。

## 3. 具体差异（fd0b7ee6 → c208b1d0）

hunk 1（新增，L906 后）：
```
+            go_path_initial = live/'go.json'
+            ready_paths_initial = {name:live/name/'ready.json' for name in workers}
+            pv_go_paths = {leg:live/f'pv-go-{leg}.json' for leg in (1, 2)}
+            pv_ready_paths = {leg:{stack:live/stack/f'pv-ready-{leg}.json' for stack in workers}
+                              for leg in (1, 2)}
```
hunk 2（循环内 L946 区）：
```
-                if not (live/'go.json').exists() and all((live/name/'ready.json').exists() for name in workers):
-                    save(live/'go.json', clock.snapshot())
+                if not go_path_initial.exists() and all(path.exists() for path in ready_paths_initial.values()):
+                    save(go_path_initial, clock.snapshot())
                 if pv and clock.tick%4 == 0:
                     for leg in (1, 2):
-                        go_path = live/f'pv-go-{leg}.json'
-                        ready_paths = {stack:live/stack/f'pv-ready-{leg}.json' for stack in workers}
-                        if not go_path.exists() and all(path.is_file() for path in ready_paths.values()):
-                            offers = {stack:json.loads(path.read_text()) for stack, path in ready_paths.items()}
+                        if not pv_go_paths[leg].exists() and all(path.is_file() for path in pv_ready_paths[leg].values()):
+                            offers = {stack:json.loads(path.read_text()) for stack, path in pv_ready_paths[leg].items()}
```
hunk 3（L957 区）：`save(go_path, …)` → `save(pv_go_paths[leg], …)`。

未变：`initial = json.loads((live/stack/'ready.json').read_text())` 仍在循环内逐次读取（L956）；`clock.tick%4==0` 门、`.exists()`/`.is_file()` 的区分、身份校验与 `start_ns` 全部逐字保留。

## 4. 逐项核对

### 4.1 可重绑定安全性（前提检查）

`workers` 仅在 L817 `={}`、L842 `workers[stack]=child` 赋值，此后只读（L903/910/912/917/995/1009/1040）；`live` 仅在 L384 `mkdtemp` 绑定一次，之后只读。二者在 hoist（L909–913）之后不再变化 → 预计算的 path 字典不会失效。**因此 hoist 与逐次重建等价。**

### 4.2 每 tick / 每 4 tick 的调用顺序（无缓存、无降频）

- go 分支每 tick 执行一次 `go_path_initial.exists()`；仅当为假才 `all(path.exists() ...)`（`and` 与 `all` 均短路）。go.json 已存在后仍每 tick 调 `.exists()`，未缓存。
- PV 分支仍由 `if pv and clock.tick%4 == 0` 门控；每 leg 先 `pv_go_paths[leg].exists()`，为假才 `all(path.is_file()...)`，随后按需 `read_text()`、`save()`。频率与基线一致。

### 4.3 受控临时目录行为对照（纯 Python + tempfile，无 native/ROS）

把实际旧/新片段置于临时 `live/` 中，对 `Path.exists/is_file/read_text` 打点并记录 `save`，逐 tick 运行，比较旧/新的有序调用与保存负载。结果：

| 场景 | calls 相同 | saved 相同 | 异常 |
|---|---|---|---|
| A 全就绪 tick0–5 | 是（27 次调用） | 是 | 均无 |
| B px4/pv-ready-2.json 缺失 | 是（16 次） | 是 | 均无（leg2 短路，不 read/save） |
| C px4/ready.json 缺失 | 是（10 次） | 是 | 均 `FileNotFoundError`，同一点抛出 |
| D pv=False tick0–2 | 是（6 次） | 是 | 均无 |

场景 A 的实测调用序列（旧=新）：`go.json exists → arducopter/ready exists → px4/ready exists → save go → pv-go-1 exists → 两个 pv-ready-1 is_file → 两 read_text(offer) → 两 read_text(initial) → save pv-go-1`，leg2 同理；tick1–3 只 `go.json exists`，tick4 额外 `pv-go-1/2 exists`。保存负载 `start_ns=(0+1000)*1_000_000=1000000000`、`issued_tick=0`、leg=1/2，旧新一致。

场景 C 的 `exc_equal=False` 仅因异常文本内嵌各自临时路径（`.../old/...` vs `.../new/...`），调用序列与抛出点完全相同，非语义差异。

### 4.4 PV offer 身份校验与 start_ns

L958–961 的校验逐字未变：`version==1`、`profile==PV_PROFILE`、`leg`、`run_id`、`scene_epoch`、`uav_id`、`control_epoch==initial['control_epoch']`、`len(token)==32`；`start_ns=(clock.tick+1000)*clock.STEP_NS` 与 `save(pv_go_paths[leg], …)` 的字段均保留。

### 4.5 路径创建无 FS 副作用

L909–913 仅 `Path`/`/` 拼接与字典推导，路径构造不触发 I/O；对照中除显式 `save` 外无任何写/建目录/触碰调用。

## 5. 边界与说明

- `pv_go_paths`/`pv_ready_paths` 现在无条件构造（`pv=False` 时也构造），纯 `Path` 运算，无 I/O、无行为差异。
- 本报告等价性结论基于**源码逐字对照**与**受控临时目录行为对照**；不含运行期（SITL/ROS/native）证据，不构成性能结论。
- 仅审查该单文件；未用 Git，未核对其余文件相对基线是否变化。

## 6. 末尾 SHA 冻结

```
FROZEN_AT 2026-09-12T14:34:23Z
c208b1d07a9054458e13b3f7bf74c145cb8641ec495e46fc7df5b6fb1626e408  tools/run_joint_flight.py
基线 runner fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246
```

与首读一致。若 A 之后再次改动，本报告仅覆盖 c208b1d0 对应字节。报告文件自身 SHA256 见交付回执。
