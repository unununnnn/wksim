# ArUco 空中场景：真实捕获与几何验证

显式 case5 的空中场景已通过真实验证。它初始禁用 RGB，在两个飞控执行既有公共任务并稳定悬停后才启用；标记锚定首个真实相机请求对应的载具位姿。**本次没有用图像发送跟踪命令，#104/父 #40 的闭环验收仍未完成。**

## 通过场次

`aruco-scene-530b3e2539`，epoch `3604073ff2b94dc5938972d7cd95e092`，证据 `validation/40-aruco-flight-scene-03/`。UE 候选位于 `E:/ue5.5/build/wksim-native-aruco-flight-20260911-01`；清单为 `validation/ue55-build-f0409a874ed243cdbad4ac9cb38d886d/candidate-manifest.json`。构建退出0，运行前核验实际加载的 DLL/PID/SHA。

| 验证项 | 实测结果 |
| --- | --- |
| 原始图像 | 90 帧，1920×1440、水平 FOV90°、固定挂载[30,20,10]cm |
| 相机启用 | 两机真实 armed、3m附近稳定悬停后启用；启用前没有 RGB 图像且 anchor_valid=false |
| 权威时序 | 初始静止2s、世界+Y 0.25m/s移动4s、完全遮挡2s、恢复4s；锚点不跟随之后的载具运动 |
| 各阶段帧数 | 17 / 27 / 15 / 31，均满足至少5帧 |
| 最大角点误差 | 0.86021px，门槛2px |
| 最大光学平移误差 | 0.007777m，门槛每轴0.035m；机体/世界位置也通过同门槛 |
| 最大连续新鲜帧速度诊断误差 | 0.06244m/s，门槛每轴0.12m/s |
| 真实结束 | 两栈公共任务完成，落地上锁；manager退出0、所有epoch组为空、View stopped |

审计从实际组件网格边界/变换重算角点和投影，核对首个相机位姿与逆挂载推导的锚点；从原始PNG重跑角点与PnP并复算速度，拒绝伪造更准确的target字段。6项真实证据正/负例通过，涵盖初始启用边界、实际网格尺寸、篡改测量、未退出进程和缺失遮挡。另21项观察器/View/输入超时回归通过。1e-9/1e-8只用于同一算法重算字段一致性，不是上述物理/视觉误差预算。

## 失败原件与配置选择

- `40-aruco-flight-scene-01`：RGB一直禁用，起飞接管前PX4拒绝 `missing_home_or_landed_state`，0帧；自有进程已退出。该复合错误没有当场区分两个分支，不能追溯宣称已证明根因。
- `40-aruco-flight-scene-02`：双栈任务成功、87帧640×480空中图像，所有几何门槛通过，但27对运动样本中5对速度误差超0.12m/s，最大0.24527m/s，保留失败判定。
- `40-aruco-flight-scene-03`：使用1920×1440实际采集，原门槛不变，最终90帧全部通过。场景移动在该初始朝向下主要改变深度；提高真实像素分辨率是针对标记深度量化的工程选择，没有平滑旧结果或修改容差。不同场次不作逐位轨迹一致宣称。

原case0–4保持原默认语义，case4仍为原640×480地面标定。case5使用同一64格/白边/遮挡板、临时unlit材质和只读Engine Cube；无新持久uasset、无碰撞/物理权威。主会话已读取本机orion资产规则；外部代理曾找不到该技能，不将其误记为本机不存在。

## 原生接管诊断

新 `tools/observe_px4_setup.py` 经 `WKSIM_OBSERVE_PX4_SETUP=1` 显式启用，只记录原方法实际调用：setup/event/receive/fresh各调用一次，不增加时钟读取或替换判断。检查中的观察先缓存在内存，setup返回后再写入。三个离线语义/恢复检查通过。

第二、三场接管时home已经初始化，land检查为新鲜，均正常接管。记录显示活动land接收间隔可超过2墙钟秒（约2.005s）；固定LandDetector每1仿真秒发布与0.5倍率下2s墙钟预算之间存在边界敏感性，但这不能单独证明第一场错误原因。后续200ms原生owner发布候选另行构建验证，不改变2s检查，不替换Python缓存时间戳。

## 重现与归档

```powershell
& work/dependencies/aruco-python/Scripts/python.exe tools/validate_aruco_scene.py --manifest validation/ue55-build-f0409a874ed243cdbad4ac9cb38d886d/candidate-manifest.json --output <新的目录> --flight-scene --observe-px4-setup --flight-resolution 1920 1440
& work/dependencies/aruco-python/Scripts/python.exe tools/audit_aruco_flight_scene.py <目录> --output <新的audit.json>
```

场次上界400墙钟秒，物理/状态门槛不变。输出中的 `acquired_airborne_scene` 仅表示采集和原公共任务完成，必须再运行独立审计。

三场完整原始图像、场景读回、权威/输入/物理/公共状态、任务生命周期和源码快照已归档并逐成员读回校验。为满足单文件大小限制，仓库保存 `raw-evidence.tar.gz.part-NNN`（每块不超过32MiB）；按各 `archive.json.parts` 顺序拼接并核对整档SHA后再解压。本机完整tar.gz与原目录仍保留，未归档厂商模型/飞控/UE二进制或资产。
