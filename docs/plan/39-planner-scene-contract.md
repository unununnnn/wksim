# #39/#102 `ego-single-box-v1` 离线场景与净空合同

日期：2026-09-12。本文冻结一个纯 Python、纯离线的规划输入几何切片，供后续
EGO→TrajectorySession 接缝和离线回归共同引用。它没有接入 ROS/ROS2 planner、点云
传输、地图服务、SITL、UE、飞行控制器或真实飞行，也不能单独证明 #29 的绕障验收。

本合同承接 [39-planner-contract](39-planner-contract.md) 的 `ego-single-box-v1`
数值和 [39-planner-run-contract](39-planner-run-contract.md) 的 `map`/ENU 约定。实现仅
新增 `Simulator/wksim_planning/scene_profile.py` 与
`validation/test_scene_profile.py`；不改 `ego_bspline_bridge.py`、
`trajectory_session.py` 或任何 runtime。

## 固定 profile

几何坐标是 ENU `map`，长度单位为 metre（`m`），时间单位为 second（`s`），偏航单位
为 radian（`rad`）。没有隐式的 NED、body、world 旋转或单位换算。profile 身份为
`ego-single-box-v1`，版本为 `1`。

| 字段 | 冻结值 |
| --- | --- |
| 地图原点 | `(-10, -6, 0)` m |
| 地图尺寸 | `(20, 12, 6)` m |
| 网格分辨率 | `0.1` m |
| 地面 / 虚拟天花板 | `z=0` / `z=5.5` m |
| 唯一障碍 AABB | `min=(-0.5,-1,0)`, `max=(0.5,1,5.5)` m |
| 机体保守包围球半径 | `0.35` m |
| 要求的扫掠净空 | `0.30` m |
| 体素排序 | x 索引升序，再 y，再 z |

障碍 AABB 的边界与网格对齐。每个体素采用半开单元 `[lower, upper)`，点云值是
`lower + (index + 0.5) * 0.1`；所以不把上界面当成另一个中心点。障碍索引范围为
`x=95..104, y=50..69, z=0..54`，总计 `10*20*55 = 11,000` 个点。首点是
`(-0.45,-0.95,0.05)` m，末点是 `(0.45,0.95,5.45)` m。`voxel_indices()` 使用
整数索引生成顺序，避免浮点 range 或平台差异。

物理碰撞 AABB 和点云都从同一 profile 几何生成，但分别记录哈希。当前 canonical
SHA-256 值（UTF-8、JSON `sort_keys=true`、紧凑分隔符、禁止 NaN/Infinity）为：

| 哈希 | 值 |
| --- | --- |
| profile canonical hash | `49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7` |
| collision AABB hash | `08b88651775ae2181e5082f124d16c6a434597703fdf2ff08bfc0bd59205c07c` |
| ordered voxel/index hash | `3602530733cf10fd0960212dc413b157e56e662d330b4b314a71f4c21abae638` |

profile hash 对 hash 字段本身做排除，输入内容包括 profile 身份、版本、坐标/单位、
原点、尺寸、分辨率、体素顺序/中心约定、地面/天花板、障碍、机体半径和净空门槛。
`to_dict()` 同时携带 `canonical_hash`/`profile_hash`、`collision_hash` 和
`voxel_hash`；`validate_profile(..., require_hash=True)` 会在消费前逐一核对。任何
单位、frame、字段、数值、AABB、profile hash、碰撞 hash 或体素 hash 不匹配都抛出
`SceneProfileError`/`ProfileMismatchError`，不会修正或猜测输入。

## 净空规则

`segment_surface_distance(start, end)` 求中心线线段到 AABB 的精确最小欧氏距离：算法
按线段穿越 AABB 六个面的位置分段，再求每段点到盒距离二次函数的驻点，不依赖采样
间隔。`segment_clearance(start, end)` 返回：

```text
minimum_surface_distance(segment, obstacle) - vehicle_radius
```

`path_clearance(points)` 取连续线段中的最小值，`path_meets_clearance`/`validate_clearance`
要求结果 `>= 0.30 m`。穿过障碍的中心线距离为 `0`，因此净空为 `-0.35 m`；中心线在
`x=0.5+0.35+0.30` 的理想边界上得到约 `0.30 m`，向内移动即失败。输入必须是有限
三维点、至少两点的有限路径、`frame="map"` 和 metre 单位；没有自动坐标旋转或单位
换算。

## no-route 与 replan 输入

`no_route_profile()` 产生显式的派生 case `ego-single-box-v1-no-route`：障碍改为
`min=(-0.5,-6,0)`、`max=(0.5,6,6)`，封死整个 y 截面并覆盖整个 z 范围。它有独立
profile/collision/voxel hash（体素数 `10*120*60 = 72,000`），不复用主 profile hash。
这个几何只证明“输入障碍封死截面”；规划器是否返回 `no_route` 或
`planning_timeout`、何时 HOLD，必须由后续真实 planner 接缝验证，不能由本模块宣称。

`validate_replan_input` 要求显式 `profile_id`、`profile_hash`、`frame`、`units`、有限
`start`/`goal`，可选非负 `generation`。标准任务起点 `(-4,0,3)`、目标 `(4,0,3)`，
重规划目标 `(4,2,3)` 都在 map 边界内且不在障碍中。起点/目标、profile 身份、hash、
单位、frame 或 generation 不合法时 fail closed；函数只返回规范化的离线
`ReplanInput`，不生成 trajectory ID、command ID、generation，也不改变任何 session。

## 验证边界

```powershell
python -B -m unittest validation.test_scene_profile -v
python -B -m py_compile Simulator/wksim_planning/scene_profile.py validation/test_scene_profile.py
git diff --check -- Simulator/wksim_planning/scene_profile.py validation/test_scene_profile.py docs/plan/39-planner-scene-contract.md
```

这些命令只覆盖 profile 解析、哈希、确定性体素、线段净空、边界、no-route 几何和
replan 输入拒绝。它们不启动进程，也不宣称 ROS/地图/SITL/UE、真实轨迹、控制 ACK、
命令倍率或飞行成功。
