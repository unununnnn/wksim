# ArUco 有界图像消费端：离线接口验证

2026-09-09，为 [#40](https://github.com/unununnnn/wksim/issues/40) 增加独立、可测试的图像到目标接缝。只新增 `Simulator/wksim_perception/`、测试和本文；未修改 RGB Reader、UE、控制、SDK、原生飞控源或准入配置，没有启动 UE/ROS/SITL/飞行。**本轮不是 #40 的真实传感器到双栈飞行闭环验收，不能据此关闭工单。**

## 来源与选择

先读根目录路由、wksim AGENTS/CONTEXT 和 RGB 几何文档，再执行 Codebase Memory `list_projects`、`index_status`、`search_graph`。`wksim-prometheus` 返回 ready、50,865 节点/165,157 边；ArUco 查询完整返回 9 个符号、has_more=false，随后直接读取：

- `Modules/tutorial_demo/advanced/aruco_tracking/src/aruco_tracking.cpp` 与 `prosim_aruco_tracking.cpp`：光学系 x 右/y 下/z 前，米制目标经 `[pz,-px,-py]` 和相机偏移转换为机体 FLU；未检测时转保持。两者的指定 ID 过滤实际被注释，不能照搬为严格目标选择。prosim 版本还有丢失后继续移动逻辑，本接缝采用任务要求的立即无效策略。
- `Modules/common/prometheus_msgs/msg/Target.msg`、`TargetsInFrame.msg`：保留米制光学位置与帧对应的有用语义；没有把 `mode`（检测/跟踪）误当成有效性标志，也没有假造 score=1 的置信度。
- `compile_spirecv.sh` 及现有启动脚本指向外部 SpireCV。`detectMarkers` 图查询无结果，固定 Prometheus 源标签的目录清单与实际文件核实了本 checkout 没有对应检测器实现；不能从缺少源代码推出所有上游版本都没有。**本仓库没有可核实的原检测器字典或物理边长默认值，生产接口不提供这两个默认值。**
- 直接读取 `Simulator/ue55/rgb.py`、`WksimRgbSensor.cpp`、`docs/rgb-capture-component.md`、`docs/rgb-geometry-fixture.md`，使用现有 v2 元数据与通知结构、UE cm 安装位姿、零畸变 K 和像素边缘约定。新文件没有进行依赖新增结构的图查询，未为文档归档重复索引；图状态不表示新增文件已被覆盖。

本地默认 Python 缺少 cv2；只在忽略目录 `work/dependencies/aruco-python/` 创建 venv，安装固定 `opencv-contrib-python-headless==4.12.0.88` 和 `numpy==2.2.6`，没有全局依赖安装。运行时实读 OpenCV 4.12.0，并检查实际 `solvePnP` docstring。检测使用 `ArucoDetector`、亚像素角点和 `solvePnP(SOLVEPNP_ITERATIVE)`；与 [OpenCV 官方 ArUco 教程](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html) 的四角及字典概念一致，实际可用性以安装版 API/测试为准。

## 冻结的离线场景与门槛

以下是首次测试前写入测试代码的接口夹具参数，**不代替未来真实 UE 标记场景冻结**：

| 条件 | 值 |
|---|---|
| 字典 / ID / 黑边外缘正方形物理边长 | `DICT_6X6_250` / 23 / 0.5 m |
| 相机 | 640×480、水平 90°、fx=fy=320、cx=320、cy=240、5 项零畸变 |
| 安装 | UE 位置 `[30,20,10]` cm、单位四元数；另测 Z 轴 90° 旋转安装 |
| 第一帧光学平移 / Rodrigues 旋转 | `[0.12,0.04,2.0]` m / `[pi,0.12,0.1]` rad |
| 目标有效期 | 捕获 step 后 300 个 1 ms 权威步，边界包含；超期清空 |
| 最大机体相对距离 | 8 m |
| 连续有效帧世界目标速度 / 位移门槛 | 2 m/s / 0.5 m |
| 最大重投影 RMS | 1 px |
| 投影夹具位移每轴误差门槛 | 0.035 m |
| 速度夹具每轴误差门槛 | 0.12 m/s |
| 遮挡 / 丢失策略 | 遮挡中心条带或空白帧导致零匹配，立即清空；新鲜单帧可重新获取，首帧不输出历史速度 |

图像由 OpenCV 生成标记和单应性投影程序确定性产生；没有 AI 图像、真实相机截图或 UE 捕获。程序将 OpenCV 的像素索引坐标加 0.5 后配合现有 UE 的边缘坐标 K，避免引入半像素位姿偏置。

## 消费与输出契约

`Consumer(settings, run_id=..., instance_id=..., dictionary=..., marker_id=..., side_length_m=..., max_age_steps=..., max_distance_m=..., max_speed_mps=..., max_jump_m=..., max_reprojection_px=...)` 要求显式目标和门槛。

1. 从权威运行状态和当前 View 获取 epoch/generation/stream，调用 `bind(epoch=..., generation=..., stream_id=..., minimum_step=...)`。不从收到的帧学习身份。新流、新 epoch 立即清空目标；退役流或降代拒绝。
2. 对现有 `Reader.poll()` 的新鲜返回值调用 `consume(frame, now_step=authority_step)`。原 Reader 继续负责通知、路径与 PNG 头校验；消费端再次核实 run/instance/epoch/generation/stream/vehicle/sensor、单调 step/frame、1 ms 时间关系、有效期与实际 PNG 解码。测试直接通过真正的 `Reader._read` 产生消费输入，未绑定 UDP 或启动运行时。
3. 没有帧也必须在每次权威状态更新时调用 `current(authority_step)`；断开立即 `invalidate()`。同 epoch 权威步不能倒退。有效期按仿真时间，暂停不会通过墙钟虚构仿真推进；此处不是独立墙钟连接监视器。
4. 图像仅接受真实声明的 opaque RGBA8 PNG、冻结分辨率/FOV/K/零畸变、明确 UE cm/光学轴/像素语义；安装位姿须与配置一致，世界与安装四元数须有限、归一化。一个指定 ID 必须恰好匹配一次。错误、缺失、重复、超期、外来帧和质量/运动门槛失败都返回 `None`，并清空此前目标；`reason` 给出原因。

有效返回为可 JSON 序列化的 `wksim.aruco-target.v1`，包含完整帧身份、字典/ID/边长、`position_optical_m`、`position_body_flu_m`（前/左/上）、`position_world_ue_m`（世界 UE X/Y/Z，单位 m）、距离、重投影 RMS、四角边缘像素坐标、有效截止步和 OpenCV 版本。`marker_to_optical_rvec_rad` 只表示标记到光学系的 Rodrigues 旋转，不是飞控 yaw 指令。

位姿顺序为 `optical -> [z,x,-y] camera UE -> camera_in_vehicle -> body FLU [X,-Y,Z]`。世界位置使用本帧 `camera_world_pose`，因此连续帧速度/位移门槛在同一世界坐标计算，不把机体运动直接误当成目标运动。`velocity_world_ue_mps` 仅为连续有效帧的有限差分诊断，不是控制设定值；丢失、门槛拒绝、过期或重新绑定后首帧为 null，不复用旧目标。单标记平面位姿存在几何歧义，当前输出不声称姿态或速度具备飞行控制精度。

返回对象是拷贝，消费方改写不会污染内部目标。该库不发布 ROS/DDS、飞控或私有控制目标。未来闭环应由任务层使用已验收的公共速度接口，在同一 run/epoch/step 证据链上转换这些带有效期的观测；不应直接把诊断世界速度当作飞控命令。

## 可复现命令与结果

在仓库根目录运行：

```powershell
work/dependencies/aruco-python/Scripts/python.exe -m unittest validation.test_aruco_consumer -v
work/dependencies/aruco-python/Scripts/python.exe -m validation.test_aruco_consumer --evidence validation/aruco-consumer-20260909
```

最终 **12 项测试全部通过，0.425 s**。覆盖真实 Reader 文件读取返回值、相机和旋转安装位姿、出现/移动/遮挡/恢复/空白、重复 ID、错误字典与 ID、陈旧/未来/重复/外来帧、空流有效期、epoch/stream 切换和退役拒绝、配置/单位/标定、无法读取及非 RGBA/非 opaque 图像、运动/距离门槛和断开清空。没有启用未声明的依赖跳过路径。

本机小型证据目录 `validation/aruco-consumer-20260909/` 保存 5 张 PNG、对应元数据和带 PNG SHA256 的 `results.json`，可通过上述命令重新产生。该目录按仓库规则忽略，源码生成器和本文可版本管理。

| 案例 | 结果 |
|---|---|
| 出现 | 光学 `[0.120523,0.039705,1.993622]` m；相对真值最大轴差 0.006378 m；机体 `[2.293622,-0.320523,0.060295]` m；重投影 0.246253 px |
| 移动 | 光学 `[0.149957,0.041080,2.000113]` m；世界速度 `[0.064909,0.294347,-0.013747]` m/s；重投影 0.145850 px |
| 遮挡 | `not_detected`、目标 null |
| 恢复 | 光学 `[0.398027,0.039998,1.998844]` m；重投影 0.294728 px；历史速度 null |
| 空白丢失 | `not_detected`、目标 null |

未验证：实际 UE 标记渲染/材质、物理边长与标定实物一致性、真实成像遮挡和运动模糊、墙钟链路失联、真实飞行时的延迟预算、双栈任务控制和跟踪完成门槛。字典成员/边长配置校验不可能仅凭单张图像证明场景中的标记实际尺寸正确；这些必须由真实场景与同运行证据确认。#40 保持开放。
