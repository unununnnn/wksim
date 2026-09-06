# wksim

Prometheus 仿真工具链迁移开发：Windows UE5.5、WSL Ubuntu22.04、ROS2/DDS、PX4 与 ArduCopter SITL。

这是 **2026-09-06 的开发中源码快照**，包含尚在集成的联合场景暂停/恢复改动，不是完整项目交付或经全量验证的发布版。

## 入口

- [规格、阶段目标与实施票据](docs/plan/README.md)
- [运行入口与本机依赖](docs/wksim-runtime.md)
- [独立项目、唯一远端与本机依赖位置](docs/project-isolation.md)
- [ROS2 工作区](ros2/README.md)
- [自主物理模型宿主](Simulator/wksim_core/README.md)
- [UE5.5 显示](Simulator/ue55/README.md)
- [工作台](docs/wksim-console.md)
- [联合空中暂停诊断与连续飞行回归报告](docs/2026-09-06_joint-airborne-pause-report.md)

## 来源与快照范围

移植基线为 [amov-lab/Prometheus](https://github.com/amov-lab/Prometheus/tree/5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce)，固定提交 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`。原有 ROS1 源码和本地已检出的基线文件保留；[上游 README](README.Prometheus.md)、LICENSE 和各子项目许可继续适用。此初始提交从本地稀疏检出的文件建立，**不包含完整上游 Git 历史或未检出的上游资源**。

[SOURCE_SNAPSHOT.json](SOURCE_SNAPSHOT.json) 记录采集时间、来源分支及逐文件输入 SHA256。需要工具读取上游固定 Git 对象时，可以另行获取基线：

```bash
git fetch --depth=1 --filter=blob:none https://github.com/amov-lab/Prometheus.git 5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce
```

本快照包含迁移源码、脚本、规格、测试源码，以及有上游许可记录的 P450 转换资产。未包含本机实验运行目录、原始遥测/截图、构建产物、Codebase Memory 数据库、厂商安装、闭源 DLL 或授权未明确的生成模型源码。报告中的这些本机证据链接在 GitHub 上可能不可打开；它们不是被删除或重新判定的测试结果。

当前构建和联测依赖本机预先准备的 ROS2/飞控/UE 环境及经许可的模型资源，配置中仍有本机路径。不能据本仓库上传成功宣称异机开箱即用、动力学等价或 Full 功能验收完成。
