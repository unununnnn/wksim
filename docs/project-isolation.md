# wksim 独立项目与本机依赖

本项目根目录是 `wksim/`，不是包含其他工程的父文件夹。唯一项目远端为 `https://github.com/unununnnn/wksim.git`，本地 `main` 跟踪 `origin/main`。

## Git 管理边界

- 父文件夹仓库原来指向 wksim 的 `origin` 已解除；父仓库本地排除 `wksim/`，避免混合提交。
- 本仓库的 Prometheus `upstream` 远端已移除。固定来源保留在文档、许可证和本地 `source/prometheus-5dcd8cfa` 标签中。
- 原四个未初始化的 Prometheus 外部子模块已解除 Gitlink 管理，旧定义存于 [Prometheus.gitmodules.reference](Prometheus.gitmodules.reference)，仅作来源记录。
- 本地源文件与其他项目文件均保留。已有未提交的联合场景改动继续作为本仓库工作区改动，不在本次管理提交中混入。

## 当前构建与运行资源

| 资源 | wksim 独立位置 |
|---|---|
| PX4 固定源与 SITL 产物 | `/root/wksim-dependencies/px4-d6f12ad1`（Ubuntu-22.04） |
| 旧 AP 源与诊断产物 | `/root/wksim-dependencies/ardupilot-1511f271`（Ubuntu-22.04） |
| 当前 AP/DDS/ROS2 候选 | 继续使用本项目已有 `/root/wksim-*` 目录 |
| UE 环境与材质输入 | `work/dependencies/ue55/`（本仓库内、仅本机） |
| UE 独立构建示例 | `E:/ue5.5/build/wksim-native-isolated-20260906` |

两份飞控副本具有独立文件，不借助指向其他项目的链接。来源提交、二进制 SHA256 和 Git 修改状态逐项匹配；未复制其他项目的顶层构建缓存。后续重新构建应使用本项目依赖目录及新构建目录。

PX4 提交为 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，固件 SHA256 为 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`。旧 AP 提交为 `1511f27194f1dcc3728270883047bdf022b3fd53`，诊断固件 SHA256 为 `9daf4ca71d32c2d48d292dac5d7432fc2137b1c75770868a1b8c1ee175534f24`；它不是替换当前 DDS/AP 候选。

UE 的 12 个环境/材质/插件文件从已有 wksim 构建中归档，并逐字节校验。`AeroTwinVisualRuntime` 仅是既有 UE 二进制包依赖的内容挂载名称，资源实际位于上述项目私有目录；不是对其他工程的文件引用或运行模块。历史资产来源和运行记录保留，未对二进制包名作破坏性替换。这些资源继续只在本机保存，不随源码提交发布。

`capability-index.json` 的历史 baselines 保持原摘要；新 `resource_locations` 指定当前独立资源位置。准入仍校验原固件和组件内容哈希，未通过更改历史证据来放行新产物。

UE5.5、Visual Studio、ROS2、Python及其系统库仍是正常工具链依赖；本次移除的是对其他本地工程工作副本的依赖，不是把工具链全部静态打包。

## 验证

- 产品矩阵：296 项，跳过21项，其余通过；旧版准入10项通过。记录：`validation/session-product-checks-HUOpig4i/`。
- 初次路径调整触发“历史 baseline 不得变动”检查；保留失败 `validation/session-product-checks-BQ7IUpT4/`，随后改为独立资源位置映射，历史摘要测试恢复通过。
- UE5.5 独立构建退出0，使用的环境输入为本项目 `work/dependencies/ue55/Content`。候选记录：`validation/ue55-build-9858633c1f0842e19cc8778e2dace84c/candidate-manifest.json`。
- 本次没有重跑真实联合飞行，也没有更改其验收结论。

管理工具应打开这个仓库目录。如果 Codex 的项目仍指向上一级文件夹，请将项目目录重新选为 `C:/Users/PC/Documents/odid编译/wksim`；已运行任务的工作目录不会因 Git 远端修改自动迁移。
