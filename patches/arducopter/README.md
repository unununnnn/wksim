# 可选 ArduCopter DDS 位置与偏航补丁

仅针对 ArduPilot `1511f27194f1dcc3728270883047bdf022b3fd53` 的隔离 SITL 候选固件，**尚未切换默认固件，也不是完整 Prometheus 飞控适配器**。原生消息中存在 `yaw` 字段，不代表该原版固件会执行它；本机未打补丁对照在首个偏航目标超时。

补丁改动4个文件，43行增加、17行删除。保留原位置接口，新增显式位置＋绝对偏航接口；Copter复用Guided目的地与围栏检查，其他载具默认拒绝新增接口。`map` ENU偏航转换为NED弧度；只接受完整位置、可选偏航，拒绝未实现的速度/加速度/偏航速率、部分位置、FORCE与未知mask位，以及无效数值。不再默默丢弃这些激活字段。

补丁基于 ArduPilot 开源代码；保持其上游归属与 `COPYING.txt` 许可声明。这里只保存补丁，不打包固件或本地RflySim闭源资源；不适用于真机/HIL验收。

## 构建并复测

在本仓库的WSL Ubuntu22.04目录中运行，复用已验证的DDS工具链。脚本要求固定且干净的原源码，新建候选目录，不修改原构建：

```bash
bash tools/build-ap-dds-yaw.sh /root/wksim-dds-VxM6Ni
```

脚本打印新建的 `Candidate` 路径；验证时使用该路径。下面是本次已经构建并实测的目录：

```bash
python3 tools/validate_ap_dds_yaw_boundary.py /root/wksim-ap-dds-yaw-mVgItN
bash tools/run-dds-validation.sh arducopter /root/wksim-dds-VxM6Ni \
  --ap-dds-candidate /root/wksim-ap-dds-yaw-mVgItN --yaw-gate
```

飞行诊断进入独立网络命名空间，保留普通解锁检查；MAVLink只作心跳/遥测观察，不发送飞行控制命令。启动的测试进程由本次诊断收尾，不清理其他进程。输出位于每次新建的 `validation/arducopter-dds-*`。

不带 `--ap-dds-candidate` 的相同 `--yaw-gate` 是原固件负对照，**预期失败**，不能误报整个固件正常功能失败。常规位置飞行回归不带 `--yaw-gate`。

111条编译后接入层断言、候选固件真实三方向偏航任务、未修改固件负对照及PX4回归见[验证报告](../../docs/2026-09-05_arducopter-dds-yaw-report.md)。产品适配必须显式区分固件能力，不能仅凭DDS topic存在或版本名称宣称支持位置＋偏航。

## 可选状态快照扩展

补丁0002追加独立WksimState原生DDS话题，提供home基准、滤波器/位姿有效标志与重置时间。仅对SITL启用，不改变原话题schema；消息源和ROS覆盖层必须匹配。可用构建入口：

```bash
bash tools/build-ap-dds-yaw.sh /root/wksim-dds-VxM6Ni --with-state
```

该入口在新候选目录依次应用0001、0002，构建飞控和`ardupilot_msgs`，打印可source的ROS覆盖层。Prometheus产品节点的固定SITL配置需要两项补丁；原版/仅yaw固件不会被冒充为具有可靠home和里程计状态。新候选 `/root/wksim-ap-dds-yaw-state-4Wr27s` 已完成真实Prometheus任务和地面重连，51项自动检查及111条旧yaw边界断言回归通过，详见[原生节点报告](../../docs/2026-09-05_prometheus-native-report.md)。未切换默认固件，不用于真机/HIL。
