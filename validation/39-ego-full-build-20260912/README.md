# 完整 EGO 构建证据

`summary.json` 核验四个库、六个 planner 可执行目标、19 份 C++17 编译 flags，以及三组生成消息头。159 个私有构建源文件的身份在 `source-manifest.json`；不提交源文件副本或二进制。

工作区为 RflySim-20.04 中 `/root/wksim-ego-local-pGqjgO`。使用独立 Linux 源码副本，保留 `Modules` 相对目录结构；项目的 `common/include` 与 `uav_control/include` 同时复制。消息包来自已封存的 ROS1 overlay，其 CMake、package.xml、ParamSettings/Bspline 定义已与当前仓库核对一致。

构建仅在子 shell 清理环境：PATH 限于 Linux 工具，移除继承的 CMAKE_PREFIX_PATH、LD_LIBRARY_PATH、PYTHONPATH、ROS_PACKAGE_PATH，然后 source `/opt/ros/noetic/setup.bash`。不修改系统或用户全局配置。

实际构建命令：

```sh
catkin_make --force-cmake -j2 -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_STANDARD=17 -DCMAKE_CXX_STANDARD_REQUIRED=ON \
  -DCMAKE_CXX_EXTENSIONS=OFF -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

旧执行句柄不可回读后，用 `cmake --build build -- -j2` 做终态确认，返回 0；并核验全部目标存在及源码副本哈希。原始日志中的警告和尾随空白保留。

保留的失败包括：消息生成与库编译顺序缺少依赖导致 ParamSettings.h 不存在；相机工具目标遗漏相同依赖导致 DepthCompressed.h 不存在。已修复相应 target dependencies。两次尝试停止检查都发现构建已自行退出，实际未向任何进程发信号。

此证据证明完整构建，不证明 ROS 节点运行、11,000 点云摄入、轨迹生成、clearance、SITL 或飞行完成。
