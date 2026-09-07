# 独立 PX4 SITL 候选

固定来源为 PX4 提交 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，本机参考目录 `/root/wksim-dependencies/px4-d6f12ad1` 保持不变。下列补丁只由显式实验构建器应用到新建私有副本；不修改原安装、原参考构建或默认生产准入，不用于硬件。

1. `0001-estimator-status-cadence.patch`：`EKF2::PublishStatusFlags` 周期由1仿真秒改为200ms，与已有DDS `rate_limit: 5.` 对齐；状态/故障变化仍立即发布。健康标志内容、原生时钟、状态有效性判断和2秒墙钟新鲜度均不改。
2. `0002-independent-sitl-without-gazebo.patch`：在副本的SITL板配置中去掉gz_msgs/gz_bridge/gz_plugins。参考二进制实际链接libgz；自主物理使用的MAVLink仿真接入仍保留，新候选不得链接或加载Gazebo/ignition/MATLAB库。

首个仅带补丁1的构建 `/root/wksim-px4-state-cNIif6` 仍链接libgz，作为依赖发现记录保留，未用于飞行；新准入要求两个补丁及独立运行库，拒绝该旧候选。空 `etc/init.d/rc.serial` 是此SITL目标的合法生成物，按实际哈希记录；固件与alias文件仍要求非空。

在Ubuntu-22.04/root、项目目录执行：

```bash
bash tools/build-px4-state-cadence.sh
```

构建器完整复制固定源及Git/子模块元数据到新 `/root/wksim-px4-state-*`，排除旧根构建缓存和历史运行文件清单，随后应用补丁、重新构建、核查动态依赖并封存。`wksim-build.json`保留基线/候选全部源文件、Git与子模块身份、删除项、运行文件及链接库；准入重新枚举核对，只有两处源修改和省略历史运行清单被接受。外部SHA256必须由调用方明确给出。

2026-09-06独立候选：`/root/wksim-px4-state-ONa1Kw/wksim-build.json`，SHA256 `d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6`。联合实验入口通过 `--px4-manifest` / `--px4-sha256` 显式选择；默认仍使用参考版本。每次实际运行单独记录固件哈希、源快照和运行开始/结束的 `/proc` 加载映射，不能用构建成功代替飞行验收。

根因实测、回归和剩余门槛见[原生状态新鲜度报告](../../docs/2026-09-06_native-state-cadence-report.md)。正式产品配置接入、完整倍率/掉队/复位及全部Full/G6仍须继续；此候选不宣称任意低速或硬件模式均已满足新鲜度约束。
