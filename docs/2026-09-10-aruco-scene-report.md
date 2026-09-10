# 真实 UE ArUco 场景与独立标定

#103 的地面场景已完成真实 RGB 采集与独立标定。最终 run `aruco-scene-267899ace7` 的完整身份保存在 `validation/40-aruco-live-scene/run-514743f-03/report.json`；本报告不证明 #104 的相机到双栈飞行闭环，也不提升默认 UE manifest。

## 交付及结果

显式选择 RGB fixture case 4，复用现有原生 RGB capture、Reader 与 ArUco Consumer。标记采用 OpenCV 4.12.0 的 `DICT_6X6_250` / ID 23：黑框外边长 50cm、白边后总长 62.5cm；64 个 Engine Cube 单元、两个临时 unlit 材质和一个遮挡板在运行时创建，不保存新 uasset。引擎/厂商资源保持原件。

场景运动按每个捕获请求的权威整数 step 计算：首秒静止，1–2s 世界 +Y 方向 0.25m/s，2–3s 完全遮挡，随后恢复。每次 CaptureScene 前保存实际组件网格边界、世界位置/缩放/旋转、材质 emissive/unlit/opaque、无碰撞/无物理状态以及实际相机变换。审计从这些网格边界独立投影，不用检测到的姿态反推真值。

| 最终校验 | 结果 |
| --- | --- |
| 真实已完成图像 | 39 帧；外观 8、运动 7、遮挡 8、恢复 16，各阶段至少 5 帧 |
| 最大独立角点误差 | 0.48664 px；原门槛 2 px |
| 最大光学/世界平移误差 | 0.004297 m；原门槛每轴 0.035 m |
| 连续新鲜运动帧速度 | 5 对通过每轴 0.12 m/s 门槛 |
| 完全遮挡 | 8 帧原图无 ID 23，目标立即清空；恢复第一帧速度 null |
| 图像与场景身份 | run/instance/epoch/generation/stream/step/相机逐项一致；全部帧在 300-step 有效期内消费 |
| 退出 | manager 退出 0；所有 epoch 组为空；View stopped |
| 验证 | 6 项真实证据正/负例 + 29 项 Consumer/RGB/View 回归，共 35 项通过 |

最终候选 `E:/ue5.5/build/wksim-native-aruco-20260910-03`，构建退出 0；源码、DLL、引擎和资源输入散列均在 `validation/ue55-build-a5083191163f4b11a4286093c61d28c2/candidate-manifest.json`。采集前核对实际进程加载 DLL 的路径/PID/SHA，未用“编译成功”替代真实运行。

## 失败与审计修正

`run-514743f-01` 已真实采集但距离误差 4.12cm 超出 3.5cm，保留失败原图。旧 Capture 仅关闭运动模糊和 TAA，仍受其他后处理影响。case 4 新增显式校准模式，关闭 PostProcessing、AntiAliasing、Bloom、DepthOfField、EyeAdaptation，并把实际 show flags 写入 RGB 元数据；其他 case 保持原行为。`run-514743f-02` 的 37 帧几何标定通过。

第三候选补齐实际材质/碰撞读回。该场初次审计因运动帧速度 null 被拒绝：前一目标 step1236 的有效期到1536，新帧 step1488 消费时权威 now_step1548，旧目标已过期。Consumer 正确清空速度；原合同只要求连续新鲜运动帧比较速度。最终审计按权威接收时间区分过期断点，要求此时速度必须 null，其余 5 对继续使用原门槛。没有改 Consumer、目标年龄或速度预算。早期拒绝与最终通过均保留。

## 重现

在 Windows 项目根，先按 `tools/build-ue55.ps1` 构建新的独立候选，使用实际返回的 manifest：

```powershell
& work/dependencies/aruco-python/Scripts/python.exe tools/validate_aruco_scene.py --manifest <candidate-manifest.json> --output <新的证据目录>
& work/dependencies/aruco-python/Scripts/python.exe tools/audit_aruco_scene.py <证据目录> --output <新的审计JSON>
$env:WKSIM_ARUCO_SCENE_FIXTURE='<证据目录>'
& work/dependencies/aruco-python/Scripts/python.exe -m unittest validation.test_aruco_scene_audit -v
```

运行器不发送解锁或起飞任务，使用真实 joint 双飞控地面权威状态，120 秒有界采集、独占既有 View/运行资源、只收尾自身进程。运行返回 `acquired` 后仍必须独立审计。

三轮原图、元数据、实际场景、源码快照、原始权威/输入/调度日志与退出证据归档为 `validation/40-aruco-live-scene/aruco-514743f-01.tar.gz`、`-02.tar.gz`、`-03.tar.gz`。`archives-514743f.json` 记录归档及逐成员 SHA，已解流读回一致；未归档 UE/飞控/模型二进制或厂商资产。最终审计源码与运行前快照版本不同，各自散列单独保留，未修改运行快照。
