# 深度生命周期收口与速度审计修复（2026-09-08 后续）

承接 d1006ca，沿用全部已批准规格、初始票及 Full 账本。本轮关闭 #31 深度相机/点云最小切片；#32 速度整场验收、#33 混合轴/轨迹、#20/G2 的性能与其他 Full/G6 门槛保持开放，未修改或关闭 Wayfinder 父图。

## #31 已批准范围与证据

重新核对票正文、深度约定第5条、#9环境/视觉合同及五项批准，剩余要求是丢帧可见、旧代次拒绝、当前帧重连、图像断流不决定物理。生产者停启和真实冷重置是这些要求的最小验证。此前助手写的“完整要求传感器故障策略”不是已批准的本票退出条件；传感器偏置/冻结/丢失等完整故障仍明确保留在 Full 扩展账本，不删除、不冒称完成，也不把纯视觉流提升为决定物理推进的必需反馈。

原四个光学固定件20帧与真实公共飞行123帧（19帧双机真实离地）已重新复核；其原始运行没有任何物理fault，收紧后的原始审计仍通过。此轮只补生命周期，不重复用光学校准或地面数据冒充实飞。

新增显式 depth_stream_control，复用RGB的停启约束与View公共控制接缝：严格run/instance/epoch/generation、递增请求号、当前/下一stream及布尔状态转换；停用取消待处理采集，重新启用使用新stream，ACK仅表示采集状态受理，完成仍须观察真实新帧。只影响深度采集，未改变权威时间、原生飞控命令或健康检查。

真实结果 `validation/depth-lifecycle-20260908-run2`：

- 同一UE进程停用深度3.037墙钟秒，无新交付帧/元数据，物理继续1456个权威1ms步。
- 新stream `b1df9b9b5bee48b199305b7d6a6a2d9b` 收到至少5个新样本；保留的旧stream通知真实投递后拒绝计数+1。
- 正式 cold-reset 把 epoch `8e7dd7d6721f4ff9838668f58b775641` 变为 `6d309bb48af44cc1a798762d6ff7e25f`，generation 1→2；收到至少5个新epoch样本，旧epoch通知拒绝计数+1。
- 共20帧逐原始clock、两模型truth、原始float32、采集位姿、ENU点云和掩码核验；每个epoch均无物理fault、无未清理进程组。审计重复字节一致，SHA256 `428f349d258dd9bc2170befa437a695df2a0b6e662cf85ebe8d20fa05e2a6345`。

首个整UE重开的尝试在8536步触发原100ms倍率监督，保留为失败且正常清理；本次成功只证明原生采集停启，不冒称整个UE进程重连已重测成功。新UE构建37.19秒通过，清单 `validation/ue55-build-3a008bd4087747399a3e9e293b792979/candidate-manifest.json`，实际模块SHA256 `444fca417e153ac1b1b153b2e3389daa911e44e9f9b33cbc33f7531d8aaf7636`；另用该构建通过正面光学固定件5帧。已备份旧默认清单并将新验证构建设为默认，默认View预检通过；覆盖只读默认文件时使用了显式Force，未修改目录权限或其他工程。

实际命令（Windows，wksim根目录）：

```powershell
powershell -NoProfile -File tools/build-ue55.ps1
python -X utf8 -B tools/validate_joint_depth.py --manifest validation/ue55-build-3a008bd4087747399a3e9e293b792979/candidate-manifest.json --lifecycle --output validation/depth-lifecycle-20260908-run2
python -X utf8 -B tools/validate_joint_depth.py --audit-only --output validation/depth-lifecycle-20260908-run2
python -X utf8 -B tools/validate_depth_slice.py --manifest validation/ue55-build-3a008bd4087747399a3e9e293b792979/candidate-manifest.json --output validation/depth-lifecycle-20260908-optical --case 0
```

## #32 真实失败与审计纠正

两次正式复跑分别为 `joint-velocity-yaw-nnh00wfp`、`joint-velocity-yaw-x8mozm0m`，都因既有 rate_unmet/resource_insufficient 失败，不能关闭 #32。后者在61172步停止，自有进程组为空。所有原阈值不变。

第一场还暴露结束审计错误：速度任务被送入位置窗口并索引 waypoint_reached。新增任务类型分派和独立 velocity_evidence，从1ms原始物理状态重算速度/零保持/偏航积分/无效组合静止窗口，核对请求、控制代次、原生ACK、精确拒绝与退出。nnh原数据的所有窗口可以通过，但整场仍有未恢复fault，离线工具继续返回failed。第二场失败停止不再产生错误的 waypoint_reached 例外。

另修正最终状态归约：已完成物理任务但最终仍有活动fault时不得报pass；已明确恢复并清空活动fault的历史故障允许成功；没有完成飞行的控制故障停止仍是stopped。保留原故障原因，不改变恢复契约。四项真实封存回归含10个篡改负例，以及健康/已恢复/活动故障终态。

验证驱动也修复了两处误报：不再等待已faulted场景满300秒；wrapper不能因停止进程退出0就把failed flow报pass；PX4有意使用命令ID [1,2,3,6]，不再错误要求它像AP一样包含仅AP使用的4/5。

## 后续原生候选与回归

C2接缝已确认：PX4原生具备混合轴/P+V；AP当前批准DDS只支持完整位置或完整速度。新AP P+V候选仅接线现有GlobalPosition完整P/V掩码至原生Guided，保持fence、ready、timeout和正确EKF-origin转换。已编译于 `/root/wksim-ap-pv-vn04950x`，固件SHA256 `7dfeb027e06712380f499611e2ba1bc809ed71f74ae477807ac5b2d51d62bb44`；构建后源快照与准备快照相同，固定OXQqdR原源/清单不变。仍是built-not-admitted，未切换运行profile、控制适配器或默认飞控，不宣称#33完成。真正混合轴仍需明确内部轴模式，禁止外部PID或NaN伪装支持。细节见 C2预检及AP候选工作记录。

本轮矩阵 `validation/session-product-checks-G4vvBMIb`：426项（397通过、29跳过）、旧预检11项通过；19项View/速度审计聚焦检查通过，17项View/深度检查通过（互有重叠，不相加算功能覆盖）。原读取trace代码的ResourceWarning保留说明，未改变验证结果。四个子代理均显式gpt-6-astra/low并从实际JSONL核验，无嵌套；所有真实测试由主代理串行安排。

Full的高频/多传感器/长时资源、完整故障、硬件、可选DLL、正式G6数值预算等义务继续阻止完整Goal完成；本轮未改控制或动力学阈值。
