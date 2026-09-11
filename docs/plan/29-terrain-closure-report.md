# #29 坡面/障碍地形闭环验收证据映射

## 审查范围与结论

- **审查基线**：地形证据截至 `b8d141c`；主代理在 `ff6fc47` 上完成本报告复核，后一个提交只增加 ROS2 命令高水位，与本报告的地形证据无关。
- **本切片范围**：只复核已保留证据、#29 原始 AC、#80/#81 子票和 #9 当前依赖；不运行模型/构建/UE/SITL，不修改源代码、测试、协调 JSON 或既有证据。
- **总体结论：#29 仍保持 OPEN。** #80/#81 已关闭，且本次冷重置证据补齐了生成模型 terrain ingress、状态反应和 elevated 冷重置精确复现；但对 #29 这条联合地形/可视场景验收，实际 UE 运行、SITL/FC/ROS/MATLAB 联调、接触动力学/侧碰/动态对象，以及 #9 的 DLL/插件依赖仍未满足父票的完整边界。#17/#23 各自票据的独立证据不等于 #29 联合验收通过。

状态含义：`PASS` 仅表示该 AC 在本报告明确的证据边界内成立；`PARTIAL` 表示有可复核子项但仍缺父 AC 要求；`BLOCKED` 表示剩余项需要新的运行、批准或依赖解除，不能由当前静态/离线证据补足。

## 证据索引

### 1. #80 静态接触夹具

目录：`validation/lunar-29-static-contact/`

- `commands.txt:3-19` 固定了 #79 入口、场景和输入 SHA，记录了实际命令：
  - `python -B validation/lunar-29-static-contact/run.py`：exit 0，13 cases。
  - `python -B validation/lunar-29-static-contact/audit.py`：`85 assertions, 13 cases, skipped 0, status pass`。
- `cases.json:1-14` 覆盖 `z=0` 平面、盒顶/侧面/中心棱带/表面、自由空间，以及 fresh/stale/future/foreign-epoch/scene-hash-mismatch 反馈语义。
- `results.jsonl` 保留逐案结果和 `wksim.contact.v1` 信封字段：`scene_id`、`scene_hash`、`epoch`、`step`、`sim_time_ns`、单步有效区间、几何、接触点、法线、穿透深度和 `source_identity`。
- `audit.py:47-74` 独立重算几何并逐字段核对结果，不导入被测静态接触模块。
- 该夹具的场景身份是 `static-plane-box-v1`，场景 SHA-256 为 `60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514`。

### 2. #81 可视场景/反馈记录

目录：`validation/lunar-29-live-contact/`

- `commands.txt:7-24` 固定只读 ArduCopter truth、命令、脚本/结果身份，并记录独立审计：`30895 assertions, 3253 rows, skipped 0, status pass`。
- `run-config.json:2-10` 明确 epoch、坐标/单位映射和反馈缺口：`1 ms` frame，`30000 < frame <= 30020` 缺少必需反馈，要求冻结于已完成边界并显式恢复；同时声明没有新物理计算，也没有向飞控发送内容。
- `events.json:3-11` 记录 `freeze` 于 frame `30019`、`boundary_step=29999`，以及 frame `30039` 的 fresh recovery。
- `display-manifest.json:1-28` 绑定：
  - `scene_id=static-plane-box-v1`
  - `scene_hash=60ae5097…`
  - `coordinate_frame=ENU`
  - `unit=metre`
  - `plane_z0` 与 `box_0`
  - `authority`: physics 在 WSL；manifest 仅 display-only，不能修改 physics。
- `audit.py:25-80` 从静态场景配置重算 hash，逐行检查 truth/record，检查 epoch、步号、时间、单步有效区间、几何和 manifest 绑定。

本次复核重跑了两个独立审计器，实际输出仍为：

```text
python -B validation/lunar-29-static-contact/audit.py
{"assertions": 85, "cases": 13, "skipped": 0, "status": "pass"}

python -B validation/lunar-29-live-contact/audit.py
{"assertions": 30895, "rows": 3253, "skipped": 0, "status": "pass"}
```

### 3. 真实生成模型 terrain/reset 证据

文件：`validation/lunar-29-terrain-reset-c8f05c6e/result.json`

- 顶层 `.status=passed`、`.ticks=50`、`.fixed_step_ns=1000000`、`.macro_barrier_ticks=[4,8,...,48]`。
- `.claims.terrain_feedback` 明确为 `state[k-1].Vehicle60 -> ENU support height -> Terrain15D`；`.claims.cold_reset` 明确为 `elevated -> elevated_reset exact replay under a new epoch`。
- `.comparison` 保留 baseline/elevated 的 final-state SHA 和两栈共同变化的 14 个状态索引；这证明零地形与 `[-1.0, +0.0 x14]` terrain 输入对生成模型状态有可观察反应。
- `.elevated_reset_comparison` 显示：
  - `epoch_changed=true`；两个 epoch 不同；
  - `scene_hash_equal=true`；
  - 两栈 `initial_state_equal=true`；
  - 两栈 `state_trace_equal=true`；
  - `.initial_state_sha256` 与 `.state_trace_sha256` 分别保留 elevated/elevated_reset 的紧凑 SHA-256，值相等；
  - `reason_code=cold_reset_elevated_exact_replay`。
- `.scenarios.elevated` 与 `.scenarios.elevated_reset` 各自保留 `tick0_enu`、`scene_manifest`、`terrain_by_trace`、`initial_state_sha256`、`state_trace_sha256`、`clock_snapshots`、`children` 和 trace 路径。两次 elevated 场景的 `tick0_enu` 均为 `[0.0, 0.0, -0.0]`，生成场景身份均为 `static-plane-box-v1-real-tick0`、scene SHA 为 `4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300`；两次 trace 的 Terrain15D 为 `[-1.0, 0.0 x14]`。
- `.scenarios.*.children` 保留六个 worker 的 `returncode=0` 和 `reaped=true`；`.clock_snapshots` 保留每个场景的 51 个时钟快照。
- `.library.sha256=e59ab914…`，`.source_sha256` 保留模型、worker、joint、scene clock、terrain feedback、静态场景和 probe 的源身份。

**两个场景 hash 层不可混写：**

1. `60ae5097…` 是 #80/#81 的冻结静态夹具及 `display-manifest.json` 的共同身份（盒体中心 `[2,0,0.5]` m）。它证明物理夹具与显示清单的同源绑定，但不证明 UE 已经运行。
2. `4889e2ea…` 是真实生成模型 probe 根据 elevated tick-0 ENU 状态生成的场景身份；它证明 `elevated` 与 `elevated_reset` 使用同一生成场景并精确重放，但不是 `display-manifest.json` 中的 hash。

因此，已证明的是“相同静态夹具身份/显示清单绑定”以及“生成模型 terrain ingress、状态反应、冷重置精确复现”两个分别可复核的事实；不能把它们合并成“UE 已显示并驱动物理”的事实。

## #29 原始 AC 逐项映射

| 原始 AC | 判定 | 已证明的证据与字段 | 未证明/剩余边界 |
| --- | --- | --- | --- |
| 1. 冻结一个可核验场景的物理表示、视觉表示、坐标和反馈有效时间。 | **PASS（表示合同/证据层）** | #80 `cases.json`、`results.jsonl`、`commands.txt` 和独立 `audit.py` 固定物理几何、`wksim.contact.v1` 单步时效及 `60ae5097…`。#81 `display-manifest.json:2-28` 以同一 `scene_id/scene_hash` 绑定 plane/box、ENU、米制和 display-only authority；`audit.py:54-78` 实际核对该绑定。 | 这是静态配置和 manifest 的可核验身份，不是 UE5.5 实机显示运行证明；父票 What to build 所要求的可见运行仍未完成。 |
| 2. 在坡面/接触工况中检查高度、接触位置与模型反应，重置后按批准预算可复核。 | **PARTIAL** | #80 独立几何审计覆盖平面/盒体接触点、法线、穿透、自由空间和时效。#81 逐 3253 条记录检查 contact/no-contact 与显式 freeze/recover。terrain reset `.comparison` 证明 elevated terrain 对真实生成模型状态的反应；`.elevated_reset_comparison` 证明不同 epoch 下两栈初态和 50 行 120-state trace 精确相等。 | 没有坡度/真实飞行接触的动力学反应、接触力/冲量/刚度/阻尼/摩擦、侧碰动力学或动态对象；probe 的 native I/O 是确定性 ACK/4 ms barrier stub，不是 FC 闭环。 |
| 3. 显示断开及反馈过期按批准契约处理，不能永久复用旧反馈或依赖渲染帧推进物理。 | **PARTIAL** | #81 `run-config.json:8-10`、`events.json:3-11` 和 `audit.py:43-73` 证明缺口内按 stale feedback 冻结于 step 29999，frame 30039 由 fresh feedback 显式恢复；`display-manifest.json:28` 明确显示不能修改物理。terrain result 的固定 1 ms / 4 ms 字段和各场景 clock snapshots 证明该 probe 的权威步进不靠渲染帧。 | 没有实际 UE 显示断开/重连运行，也没有 UE/WSL/FC/ROS2/DDS 联合时钟的闭环证据；因此不能把记录式 truth/manifest 审计提升为实际产品链路证明。 |
| 4. 保留动态地形/对象变化等额外能力行，不把视觉地面偏移当作碰撞实现。 | **PASS（能力行/边界层）** | `docs/plan/9-abi-environment-accepted.md:9-16` 保留 WSL 权威物理、UE 显示边界和动态反馈过期语义；#81 manifest 明确 display-only；#80/#81/#29 证据均没有以视觉偏移冒充碰撞。 | PASS 表示能力行和权威边界被保留。动态地形、动态对象、坡度变化和侧向接触本身仍为 BLOCKED，当前只实现静态 plane/box 几何与垂直 terrain-height seam。 |
| 5. 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。 | **PASS（交付审查层）** | #80 `commands.txt:3-19`、#81 `commands.txt:3-24` 给出命令、输入/脚本/结果 SHA、exit 和审计结果；terrain result 顶层 `.library.sha256`、`.source_sha256`、`.claims`、`.status`、`.scenarios` 和两种 comparison 给出生成模型身份、预期、结果和边界。#29 最新交付评论还保留了首个 probe 失败目录 `validation/lunar-29-real-terrain-b4bb4e5c/` 及失败原因，并明确 no UE/SITL/FC/ROS/MATLAB。本文完成主代理侧的 AC 映射复核。 | PASS 只表示证据交付和边界记录齐全，不覆盖前四项尚未满足的运行/物理范围。 |

## 依赖与关闭判断

### #9 当前状态

GitHub `unununnnn/wksim#9` 当前为 **OPEN**（label `wayfinder:grilling`）。

- `docs/plan/9-abi-environment-accepted.md:3-16` 记录：环境/视觉合同已批准，但不宣称完整动态环境或 ABI 完成。
- 同文档 `:18-36` 和 #9 最新评论（2026-09-11 07:48:14）确认官方 DLL/插件 ABI **NO-GO**：没有可审阅的权威 C/C++ 原型、调用约定、精确类型、错误/所有权/生命周期/线程隔离合同；#73/#74/#76/#77/#78 继续 blocked。
- #9 的环境路径不等于未知厂商 DLL 已兼容；不能用 ctypes 推测或 wrapper 可导入性替代 ABI 证明。

#17 当前 CLOSED，#23 当前 CLOSED；#23 的 R1=`numerical_failed`、G6/Full 边界仍按其关闭评论保留，不能被误读成 #29 接触动力学通过。#29 自身当前仍为 **OPEN**，且原票 blocked-by 仍列出 #17/#23/#9；本报告不改写 issue 元数据。

### 建议

1. **保持 #29 OPEN，不关闭父票。** 当前最强结论是：静态身份/manifest 绑定、生成模型 terrain ingress、状态反应和 elevated 冷重置精确复现已具备可复核证据；父 AC 的实际 UE/联合闭环和未批准物理范围仍未满足。
2. 下一次关闭前证据应明确补齐实际 UE5.5 运行边界，并把 UE 显示清单与权威物理场景的身份关系在同一次可复核链路中落地；不能把 `60ae5097…` 与 `4889e2ea…` 两个 hash 层自动视为同一场景。
3. 需要动态地形/对象、坡度或侧碰时，先冻结批准的输入、预算和失败语义；不能通过增加视觉偏移或未批准接触力字段绕过 #9/#23/#G6 边界。
4. 任何厂商 DLL/插件接入先解除 #9 的 ABI 证据阻塞；在此之前继续使用已审查的 wksim 自有 `wk_model_*` seam，不推断未知导出。

本文件是文档审查切片；未提交、未推送、未运行真实模型/build/UE/SITL/FC/ROS/MATLAB，也未修改源代码、测试、协调 JSON 或既有保留证据。
