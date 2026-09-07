# 深度相机与点云实施方案（待 #31 约定批准后执行）

2026-09-08。方案按 [深度约定提案](2026-09-07-depth-cloud-convention-proposal.md) 与既有 RGB 组件架构（`Simulator/ue55/Source/WksimVisual/WksimRgbSensor.{h,cpp}` 实读）拟定；批准前不实施。

## 传感器侧（UE C++，`WksimDepthSensor`）

- 镜像 RGB 结构：`UWksimDepthCapture : USceneCaptureComponent2D`，`CaptureSource=SCS_SceneDepth`（R32 浮点场景深度），TAA/动态模糊关闭、PostProcessBlendWeight=0、`bCaptureEveryFrame=false`；目标 `UTextureRenderTarget2D::InitCustomFormat(W,H,PF_R32_FLOAT)`。
- 采集路径与 RGB 相同：权威位姿 SetWorldTransform→CaptureScene→ENQUEUE_RENDER_COMMAND + FRHIGPUTextureReadback→工作线程落盘；step/sim 时间单调门、DroppedStale/DroppedBusy/Failed 计数、32-hex StreamId、epoch/代次过期拒绝——逐条复用 RGB 已验收语义。
- **编码（对应约定第 1/3 条）**：每像素 float32，值为视空间平面 Z（米）；无几何/远平面像素写 NaN；元数据 JSON 携带运行代次、步号、模型时间、载具/传感器/帧身份、实际采集位姿、宽高/编码、由内参（宽/高/水平 FOV 导出的 fx/fy/cx/cy）与安装外参；墙钟采集/传输时间单独记录；文件为原始 `.f32`+元数据（不冒称图像编码）。
- 界限：平面 Z 与径向距离均在元数据中明确标注为平面 Z；消费者按内参反投影。

## 消费者侧（验证驱动，镜像 RGB 消费者）

- 读 `.f32`+元数据 → 按内参反投影为相机帧点 → 采集位姿变换到公共 ENU map 帧 → 输出点云（组织化索引或非组织化列表），每点携带同一采样身份与坐标；NaN/无效像素不出现在点云。
- 校验：采样身份与权威状态一致、点云坐标与已知几何（RGB 几何/遮挡固定件同款平面/盒，已知距离）的距离/投影误差在运行前冻结阈值内、丢帧可见、旧 epoch 拒绝、消费者断开期间物理继续。
- 进程/资源边界与 RGB 相同：显示/图像/点云断流不决定物理节拍。

## 里程碑（批准后）

1. C++ 传感器+构建清单接入（build-ue55.ps1 输入表加两个源文件）。
2. 地面固定件四例（平面/盒/遮挡/无效区）与阈值冻结文档。
3. 空中公共任务实时深度+点云回归与原始审计（镜像 RGB airborne 流程）。

#31/#21/#20/#42/#6/1× 各自未决状态不变；本方案不预先宣称满足任何验收标准。
