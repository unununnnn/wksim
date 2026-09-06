# Prometheus ROS2 移植工作区

已迁移上游全部47项接口，以及独立的[命令受理、参考量计算与输出修整库](src/prometheus_control/README.md)。完整控制器、任务、双飞控产品适配和联合场景时钟尚未迁移完成。本工作区与原ROS1包分离，不能把仓库根目录直接当成纯ROS2工作区。

## 构建与验证

需要本机WSL Ubuntu22.04中的ROS2 Humble、ament/ament_cmake_python/rosidl、colcon及标准消息依赖。下列脚本使用现有安装，不下载或安装软件；构建 `prometheus_msgs` 和 `prometheus_control` 两包，创建独立Linux构建目录和新的仓库证据目录。验证网络命名空间需要本机WSL root权限。

在Windows PowerShell运行：

```powershell
wsl.exe -d Ubuntu-22.04 --exec bash /mnt/c/Users/PC/Documents/odid编译/wksim/tools/build-prometheus-ros2.sh
```

脚本打印此次构建目录和证据目录；`exit-code.txt`为0才是整条命令成功。构建失败看`build.log`，接口/命令测试看`unit-tests.log`和`control-tests.log`，接口通信看`runtime.log`和`result.json`。旧证据不覆盖，构建目录保留便于后续使用。

本次已验证的构建可在WSL Bash中使用：

```bash
source /root/wksim-ros2-ByQNy1/install/setup.bash
ros2 interface show prometheus_msgs/msg/UAVCommand
```

只读校验移植文件与固定上游：在wksim仓库根目录运行 `python3 tools/migrate_prometheus_interfaces.py`。它检查上游内容、完整清单、生成结果和额外接口；`--patch`只在目标包尚不存在时输出首次创建补丁，不覆盖现存包。

## 兼容性边界

基线：[Prometheus提交5dcd8cfa764d](https://github.com/amov-lab/Prometheus/tree/5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce/Modules/common/prometheus_msgs)。原ROS1包与其行为仍是迁移来源。新包保留消息/服务/动作名、声明顺序、枚举数值、数组长度、原有数值精度和业务拼写；修改清单和源/目标SHA256位于[UPSTREAM.json](src/prometheus_msgs/UPSTREAM.json)。

| ROS1声明 | ROS2声明 | 理由/限制 |
| --- | --- | --- |
| `Agent_CMD`、`Command_ID` | `agent_cmd`、`command_id` | 字段统一snake_case |
| `Init_Pos_Hover=1`、`Move=4` | `INIT_POS_HOVER=1`、`MOVE=4` | 常量大写，值不变 |
| `BoundingBox.Class` | `class_name` | 避开生成语言关键字 |
| `Header`、`time` | `std_msgs/Header`、`builtin_interfaces/Time` | 显式ROS2类型；Header没有ROS1的seq，Time.sec为int32 |
| `battery_percetage`、`GimbalFollowTrackResSevice` | 原样保留 | 拼写修正将是独立接口变更 |

ROS2名称约束见[官方接口定义](https://design.ros2.org/articles/legacy_interface_definition.html)。此包**不提供ROS1线格式互通**，也不自动提供ROS1桥。`UAVState`经纬度仍是上游float32，不能因本次移植宣称提高定位精度。

`UAVCommand`与`PositionReference`的控制枚举不是同一套值；`UAVSetup.px4_mode`仍指原PX4语义，不自动成为ArduCopter通用模式接口。旧`GAZEBO`常量仅为枚举兼容，不引入Gazebo依赖。接口包本身不执行`StartScript`字符串，也不增加控制行为。

## 验证覆盖

43个消息、3个服务的请求/响应、1个动作的目标/结果/反馈，共52个可序列化类型，分别检查默认值和递归填充的非默认值，合计104次CDR往返。另在私有Linux网络命名空间内实际测试`UAVCommand`话题、`SwitchLocationSource`服务和`CheckForObjects`动作（含反馈和成功状态）；它们是同进程ROS2 RMW测试，不是飞控飞行任务。

接口基线与限制见[接口报告](../docs/2026-09-05_prometheus-ros2-report.md)。命令库通过8项测试与102组原C++方法对照，见[命令迁移报告](../docs/2026-09-05_prometheus-command-report.md)；输出修整另通过8项测试与332组对照（286等价、46有意差异），完整回归40项通过，见[输出修整报告](../docs/2026-09-05_prometheus-shaping-report.md)。下一步继续迁移控制器与实验，通过两套原生DDS产品适配做真实任务验证；库构建通过不能替代该验证。
