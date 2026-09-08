# 深度相机光学固定件实测（2026-09-08）

已实现真实 UE5.5 SceneDepth/R32_FLOAT 深度采集与当前代次点云消费者；本轮四个真实引擎固定件全部通过，每例5帧，共20帧。此处输入位姿明确是光学校准用合成位姿，不是物理仿真或飞控证据。#31 仍待真实联合飞行采样关联、消费者断开/代次生命周期验收，不关闭。

运行前预算完整冻结在 docs/2026-09-08-depth-slice-wip.md：160×120、HFOV90°、每轴fx=fy=80；Z为米制光学平面深度，NaN表示无效。物体边界排除2像素，误差≤max(0.01m,0.002×深度)，有效/无效内部符合率≥0.995，均至少100像素，每例至少5帧。本次不是G6动力学预算。

| case | 几何/安装 | 5帧最大Z误差(m) | 有效/无效区符合率 |
| --- | --- | --- | --- |
| 0 | 正面平面与盒 | 0.0000203324 | 1.0 / 1.0 |
| 1 | 平移安装 | 0.0000203324 | 1.0 / 1.0 |
| 2 | 近盒遮挡 | 0.0000203324 | 1.0 / 1.0 |
| 3 | 偏航安装 | 0.0000441713 | 1.0 / 1.0 |

通过真实GPU读回浮点数，按原生fixture模块导出的几何边界做独立射线/盒相交审计；每帧保存 .f32、标定/位姿/身份元数据、ENU点云及有效掩码。native fixture process_id/module_path/module SHA256均与当前构建一致，采集位姿与已确认Actor应用步一致。异步采集通知只接收当前显式run/instance/epoch/generation/stream，重连最小步号/旧代次拒绝由离线UDP反例检查覆盖，不把这些反例当作实飞。

构建：validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json，源码与暂存输入逐哈希一致。实际命令（Windows，仓库根）：

```powershell
python -X utf8 -B tools/validate_depth_slice.py --manifest validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json --output validation/depth-slice-20260908/real-case0-run1 --case 0
# case 1/2/3 分别使用 real-case1-run1 / real-case2-run1 / real-case3-run1
python -X utf8 -B -m unittest validation.test_wksim_console_visual validation.test_depth_slice tools.test_validate_joint_stale -q
```

18项关联检查通过（15既有View、2深度、1断流审计）；四个校准UE进程均仅用各自Popen退场，report.owned_process_reaped=true。无飞控/物理进程参与这些光学测试；没有新增硬件、LiDAR或G6等价证明。原Full义务不缩减。
