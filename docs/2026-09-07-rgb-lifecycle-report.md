# 原生 RGB 生产者与冷重置

本轮沿用已批准的环境/视觉合同。新增相机专用的显式停启命令，检查run、物理instance/epoch/generation、当前stream_id和请求序号；不连接飞控命令或物理步进接口。停机取消待交付图像，重新启用生成新stream_id，首帧必须来自启用后的权威步。

真实 `validation/rgb-lifecycle-20260907-run2` 通过：相机停机3.0305秒，物理3412→4920继续推进1508步；重启后实际新PNG到达，同一物理epoch中的旧生产者通知被拒绝。随后完整冷重置生成新的物理epoch，两套真实飞控/模型重建，新epoch PNG正常，旧epoch通知被拒绝。25张消费图像完成物理真值/相机位姿及固定几何投影审计；两epoch正常退出。391张实际PNG包含等待冷重置时的历史记录，不把它们全部算作已消费验收帧。

第一例 `rgb-lifecycle-20260907-run1` 在相机重启已经产生新图像后，冷重置期间出现UE D3D12渲染线程访问异常，整例失败。修正后Configure保留渲染目标的UObject/资源；仅改变尺寸时使用引擎ResizeTarget。后一次完整运行未再崩溃，失败与新构建均保留，不删除失败样本。

当前本地候选构建：`validation/ue55-build-7ceff8a5310e400884be47f82115dfa1/candidate-manifest.json`，stage `E:/ue5.5/build/wksim-native-rgb-lifecycle-20260907-c`。前一次编译发现FJsonSerializer参数类型不匹配，改为明确ToSharedRef后编译通过；没有修改引擎源码。

原始审计：`validation/rgb-lifecycle-20260907-run2/physical-audit.json`、`geometry-audit.json`。相机停启ACK仅是配置接受，以上结论另由实际PNG、原始两模型状态、权威时钟和退场记录证明。

空中RGB正在单独验证；完整项目G0–G6/Full与持续1×倍率仍未完成。当前2ms ROS分发候选仍需完整生命周期/DDS恢复回归。没有新关闭#30或Goal，没有放宽数值门槛。
