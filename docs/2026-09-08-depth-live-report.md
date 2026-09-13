# 真实联合深度采样与消费者生命周期（2026-09-08）

最终 `validation/depth-live-20260908-run5` 正式双飞控公共任务、正常降落/停止及原始深度审计通过：123帧，其中19帧经两份原始模型真值确认双机均高于2.5m。关闭消费者至少3墙钟秒，单一权威物理继续1508个1ms步；重新绑定当前代次后至少5帧来自重连时刻以后的新步，未扫历史目录或重放。#31仍开放：此轮是单传感器端到端切片，生产者重启、冷重置及完整要求传感器故障策略仍须验证。

配置在运行前明确：160×120、HFOV90°、载具2、安装[30,0,50]cm、单位四元数、500权威步采样间隔（0.5×时约1帧/墙钟秒）、最大深度100m。Task仍由正式 public_position 输入驱动，hold=8s、waypoint=4s；未改控制误差或1ms/4ms/100ms倍率监督。首期降低采样负载/缩短驻留不代表删除Full的更高频率、多传感器或长时间义务。

实际SceneDepth/R32_FLOAT文件、元数据、ENU点云与有效掩码全部保留。审计从复制出的原始 clock.jsonl / 两份 truth.jsonl 重新定位每个深度采集步，用原始物理位置/姿态和安装外参计算相机位姿；最大位置误差4.982e-5cm、四元数L2误差3.856e-7，沿用先前显示位姿门槛。再次用生产消费者解析原始.f32并反投影，逐值验证保存的点云/掩码。两次审计输出字节一致；不把这些显示/光学误差当成G6动力学等价预算。

已验证C++构建及实际加载模块SHA256为 `3bef1f85023416649faf5237af8da53072cb5002ec6a6f48b0dc2ead491cb9d0`，完整清单位于 `validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json`；源/暂存/模块逐哈希核对。该构建已设为默认 `Simulator/ue55/state-build-manifest.json`，旧默认清单保存在同一验证目录。默认View预检及18项关联检查通过。双飞控core与UE分别运行，消费者不发ACK或决定物理步；正常退场与最终精确身份检查通过，Windows无本轮UE/GCS残留。

## 实際命令与失败记录

```powershell
python -X utf8 -B tools/validate_joint_depth.py --manifest validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json --output validation/depth-live-20260908-run5
python -X utf8 -B tools/validate_joint_depth.py --audit-only --output validation/depth-live-20260908-run5
```

最终目录自带 implementation.json、执行前源码副本、模块探针、真实配置/原始运行、深度图/点云与 depth-audit.json；实际公共任务命令与每个原生进程身份在run证据中。四个光学固定件另见[光学报告](2026-09-08-depth-optical-report.md)。

五次真实尝试不合并成一次成功：

1. run1：物理启动前，子PowerShell无法找到Get-FileHash；实际模块枚举仍保留，改由Python读取该模块路径并核对同一SHA256。
2. run2：100步采样、hold12/waypoint8；消费386帧后51904步触发既定 rate_unmet/resource_insufficient，失败正常停止。
3. run3：500步采样、同一驻留；130帧，80144步触发同一监督限制，失败正常停止。
4. run4：500步采样、hold8/waypoint4；公共飞行正常完成、116帧、断开窗口物理前进1664步，但独立审计拒绝断开瞬间PX4物理高度2.458m（估计高度已满足触发条件）。原2.5m门槛不改；驱动改为断开前要求同一个权威步的两份原始物理高度都达标，并明确要求两个参与者，不能由空集合的all()得到成功。
5. run5：同一500步/8s/4s配置，真实触发前核对物理真值；全部审计通过。

前两次长任务的宿主时序失败仍真实保留；成功的短切片不等于长期资源问题解决。未替用户决定新预算、硬件、DLL或MATLAB范围，未改原Wayfinder父图或Full终态。
