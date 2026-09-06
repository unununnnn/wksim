# UE5.5 权威状态显示模块

产品 v2 已增加独立核心状态源、pathname Unix datagram relay 和 Windows 只读桥，
入口为 `python -m Simulator.ue55.product_bridge`，UE 使用 `-WksimVehicle=1`。
完整契约、独立构建路径和运行命令见 [产品状态流](../../docs/wksim-state-stream.md)。
最终v2已经通过两栈真实产品运行、Actor回读、截图人工检查和显示进程断开/恢复，见[首批产品报告](../../docs/2026-09-05_product-first-wave-report.md)。
下文真实飞行结果及 JSONL 尾读属于原 v1 诊断回归，不作为 v2 产品验收证据。

本模块已在本机用 PX4、ArduCopter 的新一轮真实 DDS 飞行验证实时画面、坐标回读和显示断流恢复。它是显示边界实现：**四旋翼几何体是接入验证模型，不是完成的 Prometheus 机体资产；城市建筑尚不参与自主核心的碰撞计算。**

## 原v1诊断回归命令

使用现有 UE5.5.4、VS C++、Windows Python，以及已经构建的 WSL Humble/DDS 环境。不安装新工具，也不修改参考工程或厂商安装。

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'
./tools/build-ue55.ps1 -Stage 'E:/ue5.5/build/wksim-native-a0e91366'
./tools/validate-ue55.ps1 -Stack arducopter
./tools/validate-ue55.ps1 -Stack px4
wsl.exe -d Ubuntu-22.04 --exec python3 -m unittest validation.test_wksim_core validation.test_sitl_dds validation.test_ue55_bridge -v
```

两个显示诊断顺序执行，共用 Windows 回环 UDP19060。每次创建新的 `validation/ue55-<stack>-*` 目录，包含命令/PID、UE日志、截图、Actor回读、飞行结果引用和清理记录。启动器以隐藏窗口启动**真实 D3D12 渲染**，不使用 NullRHI。截图来自引擎帧缓冲；通过门槛仍需结合截图人工检查机体和场景，不能只看 PNG 文件存在。

启动器只回收它创建的 UE 进程；隐藏窗口的关闭请求若10秒内未生效，会终止该 PID。飞行诊断自行回收自己的 WSL 子进程。视景校验失败时允许有界飞行验证器完成并清理，不使用全局进程名终止其他仿真。

## 边界契约

物理真值由 `Simulator/wksim_core` 的模型进程产生。这里的 Windows 只读桥尾读共享 `truth.jsonl`、合并积压为最新记录，经回环 UDP 发送给 UE。**共享文件是跨私有 WSL 网络命名空间的本机诊断通道，不是最终 ROS2 状态分发接口，也不是跨系统吞吐/延迟验收。** 飞控与任务命令继续使用 WSL 内的原生 DDS，物理不等待 UE ACK。

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `version`、`run_id`、`vehicle_id` | 1、当前32位运行标识、px4或arducopter | 防止误接其他运行；不是认证协议 |
| `sequence` | 0至2^53−1整数，严格递增 | AP保留伺服帧号；PX4使用真值文件完整记录序号，不冒充飞控计数器 |
| `sim_time_s` | 非负有限数，严格递增 | 权威模型时间，不是Windows墙钟 |
| `position_ned_m` | 三个有限值，最大绝对值≤10^6 | NED米 |
| `quaternion_wxyz` | 四个有限值，范数平方偏差≤10^-5 | FRD机体到NED姿态 |
| `rotor_rpm` | 四个有限值，0至100000 | 本机quad-X对应电机转速 |

UE位置为 `[N*100,E*100,-D*100]` 厘米，四元数XYZW为 `[-x,-y,z,w]`。UE返回实际Actor位置/四元数和接收序号；ACK不是图像或帧率证明。0.75个墙钟秒没有有效状态时显示 STALE、停止旋翼动画，恢复后只显示新的当前状态，不回放历史队列或控制命令。

参考 UrbanBlock 停机坪顶面原为+34cm，显示场景整体下移34cm，使顶面对应物理零平面；物理真值和Actor权威坐标不加偏置。机体、相机和旋翼均无独立飞行动力学。

## 本地资源复用

构建脚本从 `E:/ue5.5/build/aesim-ue55-5ce6ee8/visual/unreal/AeroTwinVisual` 复制城市 Content 和两项材质依赖到独立 wksim staging。保留原挂载名的 `AeroTwinVisualRuntime.uplugin` 是**无代码的内容插件**，只挂载 `MI_RefHexX_Body.uasset` 与 `T_RefHexX_Surface.uasset`；不加载旧六旋翼、AirSim、RPC或Gazebo运行模块。

参考资源的来源记录是该工程 `SourceAssets/owned-asset-sources.json`。资产仅在本机复用，当前仓库不打包这些二进制；独立发布所需的资源许可与高保真资产仍需处理。

详细阈值、首次失败原因、截图和准确结果见 [UE5.5验证报告](../../docs/2026-09-05_ue55-report.md)。
