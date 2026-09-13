# OMP ArUco 物理审计器只读复核

日期：2026-09-11。对象：`tools/audit_aruco_tracking_physical.py` 与
`tools/audit_aruco_flight_scene.py` 的 experiment 分支。只读复核 + 针对性错位负例；
未改实现；未启动 ROS/仿真/构建；未 commit/push；未嵌套。**结论：未发现缺陷。**

## 坐标/索引约定核对（证据锚定）

- 真值布局经留存 scene-03 真实轨迹证实：`state[2]`=秒（tick/1000）、
  `state[6:9]`=NED（地面 [0,0,0]，空中 tick 53168 处 Down≈-3.0）、
  `state[12:16]`=WXYZ 单位四元数（实测值，非推定）。
- 审计器映射 `[N,E,-D]`（`evaluate_trace:32`）与 quat `[-x,-y,z,w]`（`:34`）与
  bridge 约定一致；`rotation()`（audit_aruco_scene.py:15-20）为标准 xyzw→矩阵。
- 目标真值重建：`anchor + anchor_rotation@[2.3,.32,.06] + 世界+Y 移动`
  （`:43-44`）与 fixture case5 局部坐标（230.05/32/6 cm）和锚点求解语义一致；
  锚点取自场景 manifest 实际读回，不假定原点/朝向。移动 0.25m/s、clamp 4000 步
  与 profile scene 时序逐值吻合。
- body FLU 计算 `(target-position)@rot * [1,-1,1]`（`:45`）= 世界差逆旋转 + 右→左
  翻转到 FLU，与 desired_body_flu_m 同系比较。

## 针对性测试（实际命令与结果）

```powershell
work/dependencies/aruco-python/Scripts/python.exe -B -m unittest validation.test_aruco_physical_review -v
```

**9/9 OK（6.8s）**。新增的关键错位负例（旧 4 合成 + 6 场景回归之外）：

| 用例 | 证明 |
| --- | --- |
| 真实留存轨迹索引/符号确认 | 索引映射不是推定 |
| 偏航 90° + 正确四元数映射 → 通过 | 映射正确性是承载性的（非平凡恒等） |
| 同物理场景但 quat z 符号翻转 → tracking 失败 | 桥接约定缺失会被发现 |
| 位置 z 正号（NEU 冒充 NED）→ 失败 | 坐标轴约定错位被发现 |
| 缺 tick → 区间不完整拒绝 | 真值索引/丢行被发现 |
| 0.7m 跟踪误差、0.4m 恢复窗误差 → 分别触发 0.65/0.3 门 | 双门槛独立生效 |
| peer 栈无跟踪门 | 双栈评估分工正确 |

## 身份链核对（阅读级）

- 双任务 binding 对账（`audit():87-90`：两任务消费同一 first_step/stream/end +
  profile sha）；profile 与 coordinator/runtime 两侧 SHA 一致（`:65-66,75-76`）；
  单 epoch、experimental=True、production_admitted=False、无 changed_sources/
  cleanup_errors（`:68-74`）。
- experiment 分支（audit_aruco_flight_scene.py:53-58）现已核对通知 generation 与
  metadata 文件名绑定——此前复核提出的 generation 缺口已闭合；图像/场景/manifest
  的 SHA 重算对照在 `:44-46`。
- 任务侧 image_sha256 格式级校验由审计处 PNG 重算兜底，链路完整。

## 观察项（非缺陷，不阻止执行）

- `evaluate_trace` 目标点取标记中心局部 [2.3,.32,.06]，fixture 实际板心 x 为
  230.05cm，与可见前表面中心230.0cm相差0.05cm（0.5mm）。物理审计取的是图像对应的可见前表面中心，不能把它称为5mm偏差。
- 半径门以窗口首 tick 位置为参考（任务侧以悬停点为参考）；5m 预算下语义差异无影响。
- `audit(root)` 全树端到端本次未跑——当时尚无通过的 tracking 运行可供完整端到端审计；
  场景-03 为场景验收树，不适用 experiment 入口。

## 边界

未修改任何实现；agy 的 aruco_raw_capture、Claude 的 PX4 构建资源、主会话冻结的
运行源码均未触碰。原始 CDR 链审计是独立后续门（该审计器 docstring 已声明）。
