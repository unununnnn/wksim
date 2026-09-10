# OMP ArUco flight 场景 case 5 源码切片（514743f 后续）

日期：2026-09-11。范围：只改 `Simulator/ue55/Source/WksimVisual/WksimRgbFixture.cpp/.h`、
`WksimVisualGameMode.cpp`、`Simulator/wksim_console/visual.py` 与本文。**只实现源码，
未编译、未运行 UE/SITL/MATLAB/ROS**；未 commit/push；未嵌套；未触碰其它代理文件
（aruco_task.py/其测试已冻结未动）。

前置说明：要求的 `orion-asset-management` 技能在本 Harness 技能表与仓库中均不存在
（实查两者），无法读取；已按实际源码与既有 #103/#53 合同执行。

## 变更内容（最小 diff；git diff 另含主会话此前未提交改动，注意区分）

1. `WksimRgbFixture.h`：`IsArUco()` 扩为 case 4/5；新增 `IsFlightArUco()`；
   `AdvanceArUco` 增加 `CameraInVehicle` 参数；新增 `SceneAnchor/SceneAnchorValid` 与
   `BuildArUcoGeometry` 声明。
2. `WksimRgbFixture.cpp`：
   - `Configure` 接受 0..5；case 5 走新分支：复用同一几何构建（64 格 + 白边 +
     遮挡块、两个临时 unlit 材质、Engine Cube、无碰撞——已抽出
     `BuildArUcoGeometry`，case 4 路径行为不变），**不设置 actor 变换**，保持出生点
     原样直到锚点求解。
   - `AdvanceArUco` case5 分支：epoch 切换沿用现有严格代次（新 epoch 要求
     Generation 严格升高，退役绑定不复活），并把 `SceneAnchorValid` 一并复位；
     epoch 内首个捕获请求步用 `CameraInVehicle.Inverse() * CameraWorldPose`
     （UE 组合语义：`CameraWorldPose = CameraInVehicle * VehicleTransform`）
     反解初始载具变换为 SceneAnchor（scale 归一），`SetActorTransform` 固定锚点，
     保留初始朝向；之后仅世界 +Y 平移。
   - 时间合同全按 authority step（1ms）：0–2s 静止；2–6s 移动
     `(Elapsed-2000)*0.025cm` clamp 到 4000 步 = 1m 总量（0.25m/s）；6–8s 遮挡块
     可见（完全遮挡）；8–12s 恢复静止；≥12s 保持。不用墙钟/DeltaTime。
   - `WriteManifest` case5 追加（case 4 字段不变）：`scene_case`、`anchor_valid`、
     锚点 position/quaternion（仅锚点已求解时写，BeginPlay 清单如实记
     `anchor_valid:false`）、`phase`/`phase_start_step`
     （pending_enable/static_initial/moving/occluded/recovered/settled）。
     每张捕获前保存实际 mesh bounds/材质/变换/相机/identity 沿用既有逐件读回。
3. `WksimVisualGameMode.cpp`：
   - BeginPlay fixture 块：case 5 与 case 4 同样要求 `UseCalibrationRendering`
     （校准后处理关闭），缺 RGB/config 错误照旧 `RequestExitWithStatus(24)` 明确拒绝；
     case 5 初始 `bRgbEnabled=false` + `RgbSensor->Invalidate()`。
   - `TickRgb` 调用点把 `RgbConfig.CameraInVehicle` 传入 `AdvanceArUco`。
     初始禁用/启用边界：TickRgb 的 `Current` 门（`bRgbEnabled && 双 JointVehicles
     当前步…`）在启用前阻止一切捕获，`AdvanceArUco` 只在首个真实捕获请求步执行，
     因此 SceneFirstStep 在暂停/未启用前不被消耗；启用只经既有
     `rgb_stream_control` 操作（`ApplyPacket`，enable 时换新 stream）。
4. `visual.py`：fixture case 校验扩为 0..5；case 5 时
   `View.rgb_enabled` 初始 `False`，与原生 `bRgbEnabled=false` 一致；
   后续启用用现有 `set_rgb_enabled(True)`（会生成新 stream 并关联原生 ACK）。
   未新增 RPC。

## 核验要点（主会话编译/真实捕获时核对）

- case 4 回归：几何/50cm 标记/2m 视距/1–2s 移动/2–3s 遮挡/5s 时序/清单字段不变
  （`BuildArUcoGeometry` 为纯抽取；`AdvanceArUco` case4 分支逐行未改）。
- case 5 启动后、`set_rgb_enabled(True)` 之前：UE 日志无 `WKSIM_RGB_READY`，
  输出目录无 `aruco-<epoch>-*.json`（SceneFirstStep 未消耗）。
- 启用后首张捕获清单：`anchor_valid:true`，anchor = 首张 `CameraInVehicle^-1 ×
  CameraWorldPose`，标记中心位于锚点前 2m、朝向保持；`phase=static_initial`。
- 2–6s：actor 位置 = anchor + 世界 +Y 偏移，6s 时偏移恰 100cm；6–8s 遮挡块可见且
  投影完全覆盖标记；8–12s 恢复。
- epoch 重置（冷重置新代次）：旧代次 Advance 拒绝，锚点按新 epoch 首帧重解，
  清单 identity 为新 epoch/generation/stream。
- `View` 快照 `rgb_enabled:false` 与 UE 初始 `bRgbEnabled=false` 一致；启用操作
  记录于 `rgb-actions.jsonl`。

## 明确未做/边界

未编译、未运行；未写静态源码字符串测试冒充 UE 验证。case 5 是实验候选，不是默认
生产替换（`Configure` 仍逐例显式选择）。飞行预算、真实双栈同场验收、运行器与独立
审计器仍属后续切片；当前不宣称任何飞行通过。
