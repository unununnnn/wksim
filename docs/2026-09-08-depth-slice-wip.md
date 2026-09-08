# 深度切片 WIP（2026-09-08）

依据五项批准记录和深度约定，本轮实现单个可选深度相机（默认验证分辨率 160×120，上限 640×480），复用 RGB 的权威 Actor 位姿 → SceneCapture → GPU readback → 工作线程写盘 → 当前代次通知顺序。尚未完成 #31 / 票 21 验收。

## 运行前冻结的光学预算

以下预算在任何本切片 UE 深度采集之前冻结，不是 G6 动力学误差预算：

- 原始平面 Z：float32 小端、米；UE SCS_SceneDepth 输出厘米后乘 0.01。有效范围 0 < Z < max_depth_meters，默认 100m；非有限、非正和超范围全部写 NaN。
- pinhole 内参：水平 FOV 90°、160×120、fx=fy=80、cx=80、cy=60；像素中心 index+0.5。
- 可见物体边界排除 2 像素；有效区域距离误差 ≤ max(0.01m, 0.002×期望深度)，符合率 ≥ 0.995；无效内部 NaN 符合率 ≥ 0.995；有效与无效内部各至少 100 像素，每例至少 5 帧。
- 固定件复用 `AWksimRgbFixture` 的真实引擎 Cube 边界、平面/盒遮挡及 native manifest。case 0 正面；case 1 平移安装；case 2 近遮挡；case 3 偏航安装。固定件仅视觉几何、没有碰撞/动力学权威。
- 点云以每点 pixel_index 和共享采样身份 envelope 表达，坐标公共 map ENU 米：east=UE_Y/100、north=UE_X/100、up=UE_Z/100；实际相机 pose 已包含安装外参，消费者不重复乘外参。有效掩码为逐像素 uint8 0/1。

身份含 run/instance/epoch/generation/stream/vehicle/sensor/step/frame/sim_time。墙钟字段仅 capture submission / write completion，不能解释为 GPU 曝光时间。当前通知消费者继承 RGB 的显式权威 epoch 与 minimum_step，重连不扫历史目录。消费者停止读取不产生 ACK 或物理控制调用。

## 已实施文件

- `Simulator/ue55/Source/WksimVisual/WksimDepthSensor.{h,cpp}`：真正 SCS_SceneDepth / PF_R32_FLOAT；有界一个 GPU/写盘工作项、过期取消、单调步号/时间门、NaN 编码。
- `WksimVisualGameMode.{h,cpp}`：可选 `-WksimDepthConfig=`，独立深度配置、端口、目录，权威场景失鲜/新 epoch 即失效；忙丢帧输出计数。为 #21 同时加入已授权只读 `joint_actor_query`，不刷新源状态/年龄。
- `tools/build-ue55.ps1`：加入两个深度源的源/暂存 SHA256 清单。
- `Simulator/ue55/depth.py`：继承已有 RGB socket/epoch 行为；验证深度标定和字节数，生成 ENU 点云及有效掩码。
- `tools/consume_depth.py`：有界实时消费者 CLI；固定一次当前权威绑定，代次变化必须重新绑定启动；不自动发现权威，也不从文件猜测 epoch。
- `tools/audit_depth_geometry.py`：射线与 native box 边界独立相交 oracle，比较 Z 和无效区。
- `tools/validate_depth_slice.py`：准备好的真实 UE 光学验证入口，发送明确标为 synthetic 的权威位姿，不启动任何飞控/物理；核对实际 fixture 模块 PID/path/hash、Actor ACK、采样位姿、5 帧深度几何。
- `validation/test_depth_slice.py`：离线 synthetic 数据 + 真实 loopback UDP 的准入/反投影与几何负例。

## 实际执行与边界

本子代理尚未执行 UE 构建、UE 进程或真实飞控。2 项离线测试通过：

```powershell
python -m unittest discover -s wksim/validation -p test_depth_slice.py -v
```

日志在 `validation/depth-slice-20260908/offline-tests.log`。检查覆盖旧 epoch、重放、重连最小步号、NaN/inf、ENU 轴与单位、近盒遮挡远平面、错厘米单位、无效区错误编码、移动遮挡和偏航安装。合成 oracle 不作为 GPU 或真实物理结果。

本机引擎源码实读 `E:/ue5.5/files/UE_5.5/Engine/Shaders/Private/SceneCapturePixelShader.usf:33`：SceneDepth R 通道取 CalcSceneDepth；`SceneTexturesCommon.ush` 的 CalcSceneDepth 使用 ConvertFromDeviceZ。GPU 实际格式、方向、比例仍以真实验证为准。

结构发现已查 Codebase Memory `index_status`（ready，50515 nodes / 163780 edges），RGB 名字/路径图查询返回 0，未将其解释为没有实现；已知 RGB/GameMode/构建/fixture 路径均直接读实际源码。只读当前实现，不声称图完整或已刷新新源。

模型核验：`C:/Users/PC/.codex/sessions/2026/09/08/rollout-2026-09-08T13-51-48-01a07f5b-a964-77c3-90ad-5553251887d9.jsonl`，turn_context ordinal 7，model=gpt-6-astra、effort=low；没有嵌套委派。

## 下一条真实命令（由主代理集中执行）

在 wksim 根目录先构建，使用命令实际返回的新 candidate manifest；不得用旧 manifest 冒充新深度模块。

```powershell
powershell -NoProfile -File tools/build-ue55.ps1
python tools/validate_depth_slice.py --manifest <本次candidate-manifest.json> --output validation/depth-real-case0-<唯一后缀> --case 0
```

然后以不同新输出目录运行 case 1、2、3。真实光学验证通过后仍需双飞控 ground/airborne 真权威状态关联、丢帧/冷重启/重连和消费者断开期间物理前进证据；本轮不宣称整票验收、扫描 LiDAR 或全部视觉传感器完成。真实运行结果由主代理单独补证，本记录保留子代理交付时边界。
